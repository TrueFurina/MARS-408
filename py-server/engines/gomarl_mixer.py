# ============================================================
# GoMARL Neural GroupMixer — 神经网络共识混合器
#
# 来源：GoMARL-main (src/modules/mixers/group.py + src/learners/group_learner.py)
# 申报书 Table 2-2 第1/4/5层
#
# 原始 GoMARL 用于 StarCraft2/足球多智能体协同
# 本模块将其核心算法适配为教育场景的多智能体共识：
#   - 输入：E5 编码的 Agent 输出向量（768维）→ 质量评分
#   - GroupMixer：组内相似度损失 + 组间多样性损失 + lasso 正则
#   - 动态组划分：基于 Agent 表现自动调整分组
#   - EWMA 动态权重：基于历史表现 + 学生画像
# ============================================================

import logging
import copy
import json
import time
from typing import Optional
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np

logger = logging.getLogger("netlearn.gomarl_mixer")

# Torch 延迟导入：Windows 上 torch 在某些环境下会触发 access violation，
# 不能在模块级别导入（会导致 pytest 收集阶段崩溃）。
# 改为运行时按需导入，失败则降级为规则模式。
_TORCH_AVAILABLE = None  # 延迟判定
_ONNX_AVAILABLE = False  # ONNX Runtime 可用性
GroupMixerNet = None  # 延迟定义
_torch = None  # 延迟持有 torch 模块（须 global，否则 _ensure_torch 第二次调用 UnboundLocalError）
_nn = None
_F = None


def _ensure_onnx():
    """检查 ONNX Runtime 是否可用"""
    global _ONNX_AVAILABLE
    if _ONNX_AVAILABLE:
        return True
    try:
        import onnxruntime as _ort
        # 快速验证 ONNX 模型文件存在
        from pathlib import Path
        onnx_path = Path(__file__).parent.parent / "models" / "neural_mixer.onnx"
        if onnx_path.exists():
            _ort.InferenceSession(str(onnx_path))
            _ONNX_AVAILABLE = True
            logger.info("ONNX Runtime 可用，NeuralMixer 使用 ONNX 推理模式")
            return True
        else:
            logger.info("ONNX 模型文件不存在，将尝试 PyTorch 模式")
            return False
    except Exception:
        _ONNX_AVAILABLE = False
        logger.info("ONNX Runtime 不可用，将尝试 PyTorch 模式")
        return False


def _ensure_torch():
    """运行时按需导入 torch 并定义 GroupMixerNet，返回 (torch, nn, F) 或 (None, None, None)

    注意：_torch/_nn/_F 必须 global，否则首次调用后这些局部变量丢失，
    第二次调用时 `return _torch` 会触发 UnboundLocalError，导致 _load_trained_weights
    静默回退随机权重（生产路径 NeuralMixer 实际未加载训练权重的根因）。
    """
    global _TORCH_AVAILABLE, GroupMixerNet, _torch, _nn, _F
    if _TORCH_AVAILABLE is not None:
        if _TORCH_AVAILABLE:
            return _torch, _nn, _F
        return None, None, None
    try:
        import torch as _t
        import torch.nn as _n
        import torch.nn.functional as _f
        _torch, _nn, _F = _t, _n, _f
        _TORCH_AVAILABLE = True
        logger.info("PyTorch 可用，GoMARL NeuralMixer 使用神经网络模式")
        # 延迟定义 GroupMixerNet
        GroupMixerNet = _define_group_mixer_net(_torch, _nn, _f)
        return _torch, _nn, _F
    except Exception:
        _TORCH_AVAILABLE = False
        logger.warning("PyTorch 不可用，GoMARL NeuralMixer 降级为规则模式")
        return None, None, None

from config import get_gomarl_config, get_embedding_config
from db.llm_provider import LLMProvider
from db.redis_client import redis_client
from db.pg_client import pg_client


# ── 1. E5 编码器（Agent 输出 → 向量） ──

class AgentOutputEncoder:
    """Agent 输出编码器（申报书 Table 2-2 输入层）

    "将多个智能体的生成结果转换为向量 — 使用 E5 模型统一编码格式"

    将 Agent 生成的文本内容编码为 768 维 E5 向量，
    用于后续的 NeuralMixer 相似度/多样性计算
    """

    def __init__(self):
        # 从嵌入配置读 dimension（config.json embedding.dimension=768，e5-base-v2）
        # 失败时回退到 768（与训练权重一致），避免零向量维度与真实嵌入不匹配
        try:
            self._embedding_dim = int(get_embedding_config().get("dimension", 768))
        except Exception:
            self._embedding_dim = 768

    def encode(self, text: str) -> np.ndarray:
        """将文本编码为 E5 向量"""
        try:
            from db.embedder import embed_text
            vec = embed_text(text[:2000])  # 截断长文本
            return np.array(vec, dtype=np.float32)
        except Exception as e:
            logger.warning(f"E5 编码失败，使用零向量: {e}")
            return np.zeros(self._embedding_dim, dtype=np.float32)

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        """批量编码"""
        try:
            from db.embedder import embed_batch
            vecs = embed_batch([t[:2000] for t in texts])
            return np.array(vecs, dtype=np.float32)
        except Exception as e:
            logger.warning(f"E5 批量编码失败: {e}")
            return np.zeros((len(texts), self._embedding_dim), dtype=np.float32)

    @property
    def dim(self) -> int:
        return self._embedding_dim


# ── 2. Neural GroupMixer（PyTorch 实现，延迟定义） ──

def _define_group_mixer_net(torch, nn, F):
    """工厂函数：在 torch 可用后延迟定义 GroupMixerNet 类"""

    class GroupMixerNet(nn.Module):
        """GoMARL GroupMixer 神经网络（增强版：Agent 间注意力 + 权重直连共识）

        改编自 GoMARL-main/src/modules/mixers/group.py

        核心改进（v2）：
        1. Agent间多头注意力 — 各Agent可以相互关注对方输出，实现真正的"协商"
        2. 权重直连共识 — 超网络权重 w1 直接参与最终分数计算（不再被绕过）
        3. 残差连接 — 改善梯度流动
        4. 保留原有：组内相似度 + 组间多样性 + Lasso + 动态组划分
        """

        def __init__(self, n_agents: int, embed_dim: int = 384,
                     hidden_dim: int = 64, n_groups: int = 2):
            super().__init__()
            self.n_agents = n_agents
            self.embed_dim = embed_dim
            self.hidden_dim = hidden_dim
            self.n_groups = n_groups

            # 分组配置（初始分为2组）
            self.group = [[i] for i in range(n_agents)]
            if n_agents >= 4:
                mid = n_agents // 2
                self.group = [list(range(mid)), list(range(mid, n_agents))]
            elif n_agents <= n_groups:
                self.group = [list(range(n_agents))]

            # 超网络：E5 向量 → 分组权重
            self.hyper_w1 = nn.ModuleList([
                nn.Sequential(
                    nn.Linear(embed_dim, hidden_dim),
                    nn.ReLU(inplace=True),
                    nn.Linear(hidden_dim, hidden_dim)
                ) for _ in range(n_agents)
            ])

            self.hyper_b1 = nn.ModuleList([
                nn.Sequential(nn.Linear(embed_dim, hidden_dim))
            ])

            self.hyper_w2 = nn.ModuleList([
                nn.Sequential(
                    nn.Linear(embed_dim, hidden_dim),
                    nn.ReLU(inplace=True),
                    nn.Linear(hidden_dim, hidden_dim)
                )
            ])

            self.hyper_b2 = nn.ModuleList([
                nn.Sequential(
                    nn.Linear(embed_dim, hidden_dim),
                    nn.ReLU(inplace=True),
                    nn.Linear(hidden_dim, hidden_dim)
                )
            ])

            # ── 增强①：Agent间多头注意力 ──
            self.agent_attn = nn.MultiheadAttention(
                embed_dim=hidden_dim, num_heads=4, batch_first=True,
            )
            # 将 scores(1) + embeddings(768) 映射到 hidden_dim
            self.score_proj = nn.Linear(1, hidden_dim)
            self.attn_norm = nn.LayerNorm(hidden_dim)

            # ── 增强②：权重直连共识 — 用 w1 加权聚合 Agent 质量评分 ──
            self.w1_attn = nn.Sequential(
                nn.Linear(hidden_dim, 1),
                nn.Sigmoid(),
            )

            # ── 增强③：全局混合层（含残差） ──
            self.global_mixer = nn.Sequential(
                nn.Linear(n_agents + hidden_dim, hidden_dim),
                nn.ReLU(inplace=True),
                nn.Linear(hidden_dim, 1)
            )

        def forward(self, agent_scores: torch.Tensor, agent_embeddings: torch.Tensor):
            """
            Args:
                agent_scores: (n_agents,) 各 Agent 质量评分
                agent_embeddings: (n_agents, embed_dim) E5 向量

            Returns:
                consensus_score: 共识质量分数
                group_weights: 各 Agent 的分组权重 (n_agents, hidden_dim)
                sd_loss: 相似度-多样性损失
            """
            n = self.n_agents
            device = agent_scores.device

            # 计算每个 Agent 的分组权重
            w1_list = []
            for i in range(n):
                w1 = self.hyper_w1[i](agent_embeddings[i:i+1])
                w1 = w1.abs()  # 保证非负
                w1_list.append(w1)
            w1 = torch.stack(w1_list, dim=0).squeeze(1)  # (n, hidden_dim)

            # ── Agent间注意力 ──
            scores_feat = self.score_proj(agent_scores.unsqueeze(-1))  # (n, hidden_dim)
            attn_input = w1 + scores_feat  # 融合权重特征和分数特征
            attn_out, _ = self.agent_attn(attn_input, attn_input, attn_input)
            attn_out = self.attn_norm(attn_out + attn_input)  # 残差连接

            # 权重直连：用 w1 生成每个 Agent 的注意力权重
            w1_attn_weights = self.w1_attn(w1).squeeze(-1)  # (n,)
            w1_attn_weights = F.softmax(w1_attn_weights, dim=0)
            weighted_scores = (agent_scores * w1_attn_weights).sum()  # 标量

            # 组内相似度 + 组间多样性损失
            sd_loss = torch.tensor(0.0, device=device)
            for group_idx, group_i in enumerate(self.group):
                if len(group_i) < 2:
                    continue
                group_embs = agent_embeddings[group_i]
                # 组内余弦相似度（鼓励高 → 相似）
                for i in range(len(group_i)):
                    for j in range(i+1, len(group_i)):
                        sim = F.cosine_similarity(
                            group_embs[i:i+1], group_embs[j:j+1]
                        ).squeeze()
                        sd_loss = sd_loss - sim
                # 组间多样性（鼓励低 → 不同）
                other_agents = [a for a in range(n) if a not in group_i]
                if other_agents:
                    other_embs = agent_embeddings[other_agents]
                    for i in range(len(group_i)):
                        for j in range(len(other_agents)):
                            div = F.cosine_similarity(
                                group_embs[i:i+1], other_embs[j:j+1]
                            ).squeeze()
                            sd_loss = sd_loss + div * 0.5

            # 分组加权（保留原有逻辑）
            group_qs = []
            for group_idx, group_i in enumerate(self.group):
                if not group_i:
                    continue
                group_scores = agent_scores[group_i]
                group_w = w1[group_i]
                b1 = self.hyper_b1[0](agent_embeddings[group_i].mean(dim=0, keepdim=True))
                b1 = b1.sum(dim=1, keepdim=True)
                weighted = (group_scores.unsqueeze(1) * group_w).sum(dim=0, keepdim=True)
                hidden = F.elu(weighted + b1)
                w2 = self.hyper_w2[0](agent_embeddings[group_i].mean(dim=0, keepdim=True))
                b2 = self.hyper_b2[0](agent_embeddings[group_i].mean(dim=0, keepdim=True))
                q_group = (hidden * w2).sum(dim=1, keepdim=True) + b2.sum(dim=1, keepdim=True)
                group_qs.append(q_group.view(1))

            if group_qs:
                group_tot = torch.stack(group_qs).mean()
            else:
                group_tot = torch.tensor(0.0, device=device)

            # 最终共识：融合 ①权重直连分数 ②分组加权分数 ③注意力特征
            attn_pooled = attn_out.mean(dim=0, keepdim=True)  # (1, hidden_dim)
            consensus_input = torch.cat([
                agent_scores.unsqueeze(0),             # (1, n)
                attn_pooled,                           # (1, hidden_dim)
            ], dim=1)                                  # (1, n + hidden_dim)
            consensus_score = self.global_mixer(consensus_input).squeeze()

            sd_loss_val = sd_loss / max(n * n, 1)

            return consensus_score, w1, sd_loss_val

        def update_group(self, new_group: list[list[int]]):
            """更新分组"""
            self.group = new_group

        def get_w1_avg(self, agent_embeddings: torch.Tensor) -> torch.Tensor:
            """获取平均权重（用于动态组划分）"""
            w1_list = []
            for i in range(self.n_agents):
                w1 = self.hyper_w1[i](agent_embeddings[i:i+1]).abs()
                w1_list.append(w1)
            w1 = torch.stack(w1_list, dim=0).squeeze(1)
            return w1.mean(dim=1)

    return GroupMixerNet


# ── 3. GoMARL NeuralMixer 主类 ──

class NeuralGroupMixer:
    """GoMARL 神经网络共识混合器

    整合 E5 编码 + GroupMixer 神经网络 + 动态权重 + 动态组划分

    申报书 Table 2-2:
    - 输入层：E5 编码 ✅
    - 权重层：动态权重分配（EWMA + 学生画像）✅
    - 决策层：加权投票与共识生成 ✅ (NeuralMixer)
    - 记忆层：历史共识记录 ✅ (PostgreSQL)
    """

    def __init__(self):
        config = get_gomarl_config()
        self.history_window = config.get("history_window", 5)
        self.quality_threshold = config.get("quality_threshold", 7)
        # use_neural 只看配置；实际 torch/onnx 可用性在 _init_mixer 中延迟探测
        # （__init__ 在模块加载时执行，此时 _TORCH_AVAILABLE 必为 None，若在此判定会永远 False）
        self.use_neural = bool(config.get("use_neural_mixer", True))

        # Agent 名称 → 索引映射
        self._agent_names = [
            "teacher",        # 教学讲解 Agent
            "quizmaster",     # 出题 Agent
            "media_designer", # 多媒体 Agent
            "extension",      # 拓展阅读 Agent
            "ppt_designer",   # PPT Agent
            "code_practice",  # 代码实操 Agent
        ]
        self._name_to_idx = {name: i for i, name in enumerate(self._agent_names)}

        # E5 编码器
        self.encoder = AgentOutputEncoder()

        # 神经网络混合器（延迟初始化）
        self._mixer_net: Optional['GroupMixerNet'] = None
        self._onnx_session = None  # ONNX Runtime 会话
        # embed_dim 默认值，_init_mixer 时会从训练权重探测真实维度并覆盖
        # （训练权重 hyper_w1.0.0.weight.shape[1] 即 embed_dim，当前为 768=e5-base-v2）
        self._embed_dim = 384
        self._hidden_dim = 64

        # 基础权重
        self._base_weights = {
            "teacher": 1.0,
            "quizmaster": 0.9,
            "media_designer": 0.85,
            "extension": 0.8,
            "ppt_designer": 0.8,
            "code_practice": 0.85,
        }

        # 动态组划分配置
        self._group_change_threshold = 0.3  # 权重低于均值的30%时考虑重新分组
        self._min_group_size = 2

    def _probe_trained_embed_dim(self) -> Optional[int]:
        """从训练权重探测 embed_dim（hyper_w1.0.0.weight 的 in_features）

        训练权重的 hyper_w1.i.0.weight 形状为 (hidden_dim, embed_dim)，
        其 shape[1] 即创建 GroupMixerNet 时应使用的 embed_dim。
        优先级：训练权重 > 嵌入配置 dimension > 默认 384
        """
        try:
            from pathlib import Path
            _torch, _, _ = _ensure_torch()
            if _torch is None:
                return None
            weights_path = Path(__file__).parent.parent / "models" / "neural_mixer_trained.pt"
            if not weights_path.exists():
                return None
            sd = _torch.load(str(weights_path), map_location="cpu", weights_only=True)
            # hyper_w1.{i}.0.weight shape: (hidden_dim, embed_dim)
            for key in ("hyper_w1.0.0.weight", "hyper_w1.1.0.weight", "hyper_w1.2.0.weight"):
                if key in sd:
                    return int(sd[key].shape[1])
            return None
        except Exception as e:
            logger.warning(f"探测训练权重 embed_dim 失败: {e}")
            return None

    def _init_mixer(self, n_agents: int):
        """延迟初始化神经网络，并尝试加载 ONNX 或 PyTorch 模型"""
        if not self.use_neural:
            return None

        # 延迟探测 torch/onnx 可用性（__init__ 时不导入 torch 以避免 Windows 模块加载崩溃）
        if not _TORCH_AVAILABLE and not _ONNX_AVAILABLE:
            _ensure_onnx()
            if not _ONNX_AVAILABLE:
                _ensure_torch()
        if not (_TORCH_AVAILABLE or _ONNX_AVAILABLE):
            self.use_neural = False
            logger.warning("NeuralMixer: torch 与 onnx 均不可用，降级为规则模式")
            return None

        # 优先尝试 ONNX Runtime
        if _ONNX_AVAILABLE:
            try:
                import onnxruntime as _ort
                from pathlib import Path
                onnx_path = Path(__file__).parent.parent / "models" / "neural_mixer.onnx"
                if onnx_path.exists() and self._onnx_session is None:
                    self._onnx_session = _ort.InferenceSession(str(onnx_path))
                    logger.info(f"ONNX 模型加载成功: {onnx_path.name}")
                    # 模拟 mixer 接口（返回一个轻量对象）
                    class _OnnxMixerProxy:
                        def __init__(self, session, n_agents):
                            self.session = session
                            self.n_agents = n_agents
                            if n_agents >= 4:
                                mid = n_agents // 2
                                self.group = [list(range(mid)), list(range(mid, n_agents))]
                            else:
                                self.group = [list(range(n_agents))]

                        def get_w1_avg(self, embeddings):
                            """ONNX 不支持动态组划分，返回均匀权重"""
                            na = self.n_agents
                            return np.ones(na, dtype=np.float32) / na

                        def update_group(self, new_group):
                            self.group = new_group

                    return _OnnxMixerProxy(self._onnx_session, n_agents)
            except Exception as e:
                logger.warning(f"ONNX 模型加载失败，回退 PyTorch: {e}")

        # 回退 PyTorch
        _torch, _, _ = _ensure_torch()
        if _torch is None or GroupMixerNet is None:
            self.use_neural = False
            return None
        if self._mixer_net is None or self._mixer_net.n_agents != n_agents:
            # 优先从训练权重探测 embed_dim，确保与训练时一致（否则形状不匹配会落回随机权重）
            probed_dim = self._probe_trained_embed_dim()
            if probed_dim is not None:
                if probed_dim != self._embed_dim:
                    logger.info(
                        f"NeuralMixer embed_dim 从训练权重探测为 {probed_dim}"
                        f"（原默认 {self._embed_dim}），已自动校正以匹配训练权重"
                    )
                embed_dim = probed_dim
            else:
                # 无训练权重时回退到嵌入配置（config.json embedding.dimension）
                embed_dim = get_embedding_config().get("dimension", self._embed_dim)
            self._mixer_net = GroupMixerNet(
                n_agents=n_agents,
                embed_dim=embed_dim,
                hidden_dim=self._hidden_dim,
            )
            # 尝试加载训练后权重
            self._load_trained_weights()
            self._mixer_net.eval()  # 推理模式
        return self._mixer_net

    def _load_trained_weights(self):
        """加载训练后的 NeuralMixer 权重

        返回 (matched, total) 以便验证；并记录关键 shape 用于排查。
        """
        if self._mixer_net is None:
            return 0, 0
        try:
            import os
            from pathlib import Path
            _torch, _, _ = _ensure_torch()
            if _torch is None:
                return 0, 0
            weights_path = Path(__file__).parent.parent / "models" / "neural_mixer_trained.pt"
            if weights_path.exists():
                state_dict = _torch.load(weights_path, map_location="cpu", weights_only=True)
                # 只加载形状匹配的参数（n_agents 可能不同）
                model_dict = self._mixer_net.state_dict()
                matched = {k: v for k, v in state_dict.items()
                          if k in model_dict and v.shape == model_dict[k].shape}
                if matched:
                    model_dict.update(matched)
                    self._mixer_net.load_state_dict(model_dict)
                    # 探测训练权重的 embed_dim 用于日志
                    sd_emb_dim = None
                    for k in ("hyper_w1.0.0.weight",):
                        if k in state_dict:
                            sd_emb_dim = int(state_dict[k].shape[1])
                    model_emb_dim = self._mixer_net.embed_dim
                    logger.info(
                        f"NeuralMixer 训练权重已加载: {len(matched)}/{len(model_dict)} 参数匹配 "
                        f"(训练 embed_dim={sd_emb_dim}, 模型 embed_dim={model_emb_dim})"
                    )
                    return len(matched), len(model_dict)
                else:
                    logger.warning(
                        f"NeuralMixer 训练权重形状完全不匹配，使用随机权重 "
                        f"(训练权重 keys={len(state_dict)}, 模型 keys={len(model_dict)})"
                    )
                    return 0, len(model_dict)
            else:
                logger.info("NeuralMixer 使用随机权重（未找到训练权重文件）")
            return 0, len(self._mixer_net.state_dict())
        except Exception as e:
            logger.warning(f"加载 NeuralMixer 训练权重失败: {e}，使用随机权重")
            return 0, 0

    async def mix(
        self,
        agent_results: list[dict],  # [{agent_name, content, score}]
        student_profile: dict,
        topic: str,
    ) -> dict:
        """
        神经网络共识混合

        Args:
            agent_results: Agent 生成结果列表
            student_profile: 学生画像
            topic: 学习主题

        Returns:
        {
            "consensus_score": float,      # 共识质量分数
            "weighted_scores": dict,       # 各 Agent 加权后分数
            "dynamic_weights": dict,       # 动态权重快照
            "groups": list,                # 当前分组
            "sd_loss": float,              # 相似度-多样性损失
            "neural_used": bool,           # 是否使用了神经网络
            "agent_embeddings": list,      # 各 Agent 的 E5 向量（调试用）
        }
        """
        if not agent_results:
            return {"consensus_score": 0, "weighted_scores": {}, "neural_used": False}

        n = len(agent_results)
        agent_names = [r.get("agent_name", f"agent_{i}") for i, r in enumerate(agent_results)]

        # 1. E5 编码所有 Agent 输出
        texts = [r.get("content", "")[:2000] for r in agent_results]
        embeddings = self.encoder.encode_batch(texts)  # (n, 768)

        # 2. 获取质量评分
        scores = np.array([r.get("score", 5.0) for r in agent_results], dtype=np.float32)

        # 3. 动态权重（EWMA + 学生画像）
        dynamic_weights = self._compute_dynamic_weights(agent_names, student_profile)
        weighted_scores = {
            name: scores[i] * dynamic_weights.get(name, 1.0)
            for i, name in enumerate(agent_names)
        }

        # 4. 神经网络混合（如果可用）
        consensus_score = float(np.mean(list(weighted_scores.values())))
        sd_loss = 0.0
        neural_used = False

        if self.use_neural and n >= 2:
            try:
                mixer = self._init_mixer(n)
                if mixer is not None:
                    # ONNX Runtime 推理路径
                    if self._onnx_session is not None:
                        scores_np = scores.reshape(1, -1) if len(scores.shape) == 1 else scores
                        emb_np = embeddings.reshape(1, n, -1) if len(embeddings.shape) == 2 else embeddings
                        # ONNX 模型要求 (batch, n_agents, embed_dim) 形状
                        onnx_inputs = {
                            "agent_scores": scores_np.astype(np.float32),
                            "agent_embeddings": emb_np.astype(np.float32),
                        }
                        # 尝试不同的输入形状
                        if len(scores.shape) == 1:
                            onnx_inputs["agent_scores"] = scores.astype(np.float32)
                        if len(embeddings.shape) == 2:
                            onnx_inputs["agent_embeddings"] = embeddings.astype(np.float32)

                        onnx_outputs = self._onnx_session.run(
                            ["consensus_score", "group_weights", "sd_loss"],
                            onnx_inputs,
                        )
                        cs_val = float(onnx_outputs[0])
                        sd_val = float(onnx_outputs[2]) if len(onnx_outputs) > 2 else 0.0
                        # 共识分映射到 1-10 量纲（与 QualityScore.overall / quality_threshold=7 一致），
                        # 不再钳制到 [0,1]（旧逻辑会把分数「拉满」成恒为 1.0，失去区分度）。
                        consensus_score = max(0.0, min(10.0, float(cs_val) * 10.0))
                        sd_loss = sd_val
                        neural_used = True
                    else:
                        # PyTorch 推理路径
                        _torch, _, _ = _ensure_torch()
                        with _torch.no_grad():
                            agent_scores_t = _torch.from_numpy(scores)
                            agent_embs_t = _torch.from_numpy(embeddings)

                            cs, w1, sd = mixer(agent_scores_t, agent_embs_t)
                            # 共识分映射到 1-10 量纲（与 QualityScore.overall / quality_threshold=7 一致）
                            consensus_score = max(0.0, min(10.0, float(cs.item()) * 10.0))
                            sd_loss = float(sd.item())
                            neural_used = True

                            # 检查是否需要动态组划分
                            w1_avg = mixer.get_w1_avg(agent_embs_t)
                            self._check_group_change(mixer, w1_avg, agent_names)

            except Exception as e:
                logger.warning(f"神经网络混合失败，降级为加权平均: {e}")

        # 5. 记录到 PostgreSQL
        for name, ws in weighted_scores.items():
            try:
                pg_client.log_agent_score(name, ws, "neural_mix", f"topic={topic}")
            except Exception as e:
                logger.warning("agent score history write failed (non-blocking): %s", e)

        # 6. 缓存权重
        try:
            redis_client.cache_agent_weights(dynamic_weights)
        except Exception as e:
            logger.warning("agent weight cache write failed (non-blocking): %s", e)

        return {
            "consensus_score": float(consensus_score),
            "weighted_scores": {k: float(v) for k, v in weighted_scores.items()},
            "dynamic_weights": {k: float(v) for k, v in dynamic_weights.items()},
            "groups": self._get_current_groups(agent_names),
            "sd_loss": float(sd_loss),
            "neural_used": neural_used,
            "agent_count": n,
        }

    def _compute_dynamic_weights(self, agent_names: list[str], student_profile: dict) -> dict:
        """计算动态权重（EWMA 历史表现 + 学生画像调整 + 教学规则适配）

        申报书 Table 2-2 权重层：
        "✅ 新增：结合学生画像的动态权重调整"
        报告§3.3.3改进：基于教学规则引擎的Agent适配建议调整权重
        """
        weights = {}
        for name in agent_names:
            base = self._base_weights.get(name, 0.8)

            # EWMA 历史表现
            try:
                history = pg_client.get_agent_history(name, self.history_window)
                if history:
                    avg_history = sum(history) / len(history)
                    # 历史平均分 (1-10) → 权重因子 (0.5-1.5)
                    factor = 0.5 + (avg_history / 10.0)
                    weights[name] = base * factor
                else:
                    weights[name] = base
            except Exception:
                weights[name] = base

            # 学生画像调整
            if student_profile:
                # 如果学生薄弱维度对应某 Agent，提高该 Agent 权重
                weak_areas = student_profile.get("weak_subjects", [])
                level = student_profile.get("level", "intermediate")

                # 初学者：教学 Agent 权重更高
                if level == "beginner" and name == "teacher":
                    weights[name] *= 1.15
                # 高级学生：代码实操权重更高
                elif level == "advanced" and name == "code_practice":
                    weights[name] *= 1.15
                # 薄弱科目相关 Agent 权重提升
                for weak in weak_areas:
                    if weak.lower() in name.lower():
                        weights[name] *= 1.10

                # ── 真版增量：教学规则引擎适配（报告§3.3.3）──
                # 基于topic与Agent的适配关系调整权重
                topic = student_profile.get("current_topic", "")
                if topic:
                    try:
                        from engines.teaching_rules import teaching_rules
                        topic_id = ""
                        # 查找匹配知识点
                        for dep_id, dep in teaching_rules._dependencies.items():
                            if dep.topic_name == topic or dep_id == topic:
                                topic_id = dep_id
                                break

                        if topic_id:
                            # 基于教学规则建议的Agent排序调整权重
                            suggested = teaching_rules.suggest_agent_assignment(topic_id)
                            if name in suggested:
                                # 排名越前权重越高
                                rank = suggested.index(name)
                                rank_factor = 1.0 + (len(suggested) - rank) / len(suggested) * 0.15
                                weights[name] *= rank_factor

                            # 薄弱知识点对应Agent额外加权
                            weak_topics = set(student_profile.get("weak_topics", []))
                            dep = teaching_rules._dependencies.get(topic_id)
                            if dep and (topic_id in weak_topics or dep.topic_name in weak_topics):
                                # 薄弱知识点 → quizmaster和teacher权重提升
                                if name in ("quizmaster", "teacher", "assessor"):
                                    weights[name] *= 1.20
                    except ImportError:
                        pass  # 教学规则引擎未加载

        # 归一化
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total * len(weights) for k, v in weights.items()}

        return weights

    def _check_group_change(self, mixer, w1_avg, agent_names: list[str]):
        """检查是否需要动态组划分

        改编自 GoMARL-main/src/learners/group_learner.py change_group 方法

        当某 Agent 的权重持续低于组内均值的 threshold% 时，
        将其从当前组移出，形成新组
        """
        n = len(agent_names)
        if n < 4:  # Agent 太少，不分组
            return

        current_group = mixer.group
        if len(current_group) == 0 or (len(current_group) == 1 and len(current_group[0]) <= 2):
            return

        w1_np = w1_avg.cpu().numpy() if hasattr(w1_avg, 'cpu') else np.array(w1_avg)

        changed = False
        new_group = [list(g) for g in current_group]

        for group_idx, group_i in enumerate(current_group):
            if len(group_i) < 3:  # 组太小不拆分
                continue

            group_w1 = w1_np[group_i]
            group_avg = np.mean(group_w1)
            threshold = group_avg * self._group_change_threshold

            # 找到权重过低的 Agent
            low_indices = np.where(group_w1 < threshold)[0]
            if len(low_indices) == 0:
                continue

            # 移出低权重 Agent
            for idx in reversed(sorted(low_indices)):
                agent_global_idx = group_i[idx]
                if len(new_group[group_idx]) > self._min_group_size:
                    new_group[group_idx].remove(agent_global_idx)
                    if len(new_group) <= 6:  # 限制最大组数
                        new_group.append([agent_global_idx])
                        changed = True

        if changed:
            # 清理空组
            new_group = [g for g in new_group if g]
            mixer.update_group(new_group)
            logger.info(f"GoMARL 动态组划分: {current_group} → {new_group}")

    def _get_current_groups(self, agent_names: list[str]) -> list[list[str]]:
        """获取当前分组（名称形式）"""
        if self._mixer_net is None:
            return [agent_names]
        return [
            [agent_names[i] for i in group if i < len(agent_names)]
            for group in self._mixer_net.group
        ]

    def get_stats(self) -> dict:
        """获取混合器统计"""
        return {
            "neural_enabled": self.use_neural,
            "torch_available": _TORCH_AVAILABLE is True,
            "onnx_available": _ONNX_AVAILABLE,
            "onnx_active": self._onnx_session is not None,
            "agent_count": len(self._agent_names),
            "base_weights": self._base_weights,
            "current_groups": (
                self._mixer_net.group if self._mixer_net else "not_initialized"
            ),
        }


# 全局单例
neural_mixer = NeuralGroupMixer()
agent_encoder = AgentOutputEncoder()
