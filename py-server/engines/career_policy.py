# ============================================================
# career_policy — P3③ 鲶鱼机制 MAPPO 化（决策层）
#
# 按 docs/CTO-芒得很职P3鲶鱼MAPPO化设计-2026-09-12.md 实现：
#   - 只换决策层：decide_career_mode 输出契约与规则版一致（三模式），
#     下游追问生成/评估零改动
#   - 复用 mappo_policy 的 ActorNet/CriticNet 构建框架（_build_networks）
#     与 warmup_with_rules 思路（规则版做监督预热），不复用其模型权重
#   - 默认灰度关闭（config: career.use_career_mappo=False），规则版兜底
# ============================================================

import json
import logging
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger("netlearn.career.policy")

# 动作空间：与现有三模式一一对应（设计文档 0/1/2）
CAREER_ACTIONS = ["normal", "escalating", "catfish"]

# 奖励权重（设计文档初值，可调）
REWARD_W = {"gain": 0.5, "evidence": 0.3, "cost": 0.15, "discipline": 0.05}

CATFISH_MAX_CONTINUE = 2  # 与 career_state 保持一致（纪律项）

try:  # torch 可用才构建网络（与 mappo_policy 同策略：延迟导入）
    from engines.mappo_policy import _build_networks as _mp_build_networks
    _TORCH_HINT = True
except Exception:  # pragma: no cover - torch 缺失环境
    _mp_build_networks = None
    _TORCH_HINT = False


# ────────────────────────────────────────────────────────────
# 状态特征（8 维，设计文档 MDP 定义）
# ────────────────────────────────────────────────────────────

def career_state_features(turns: list[dict], six_scores: Optional[dict] = None,
                          profile_level: str = "intermediate",
                          current_mode: str = "normal",
                          catfish_streak: int = 0,
                          max_turns: int = 8) -> list[float]:
    """对抗上下文 → 8 维状态向量（全部归一化到 0-1）。"""
    turns = turns or []
    n = len(turns)
    turn_ratio = min(1.0, n / max(1, max_turns))

    # 最近 3 轮证据密度均值
    dens = [float((t.get("evidence") or {}).get("density", 0.5)) for t in turns[-3:]]
    evidence_density = sum(dens) / len(dens) if dens else 0.5

    # 最近 3 轮规则作答质量（按密度映射 0-5 分，无证据轮计中性 2.5）
    qualities = [min(5.0, 1.0 + d * 4.0) for d in dens] if dens else [2.5]
    answer_quality = sum(qualities) / len(qualities) / 5.0

    mode_ordinal = {"normal": 0.0, "escalating": 0.5, "catfish": 1.0}.get(current_mode, 0.0)
    catfish_ratio = min(1.0, catfish_streak / max(1, CATFISH_MAX_CONTINUE))

    level_code = {"beginner": 0.25, "intermediate": 0.5, "advanced": 0.75}.get(profile_level, 0.5)

    # 六维分数方差（越高越需要加压探测）
    scores = [float(v) for v in (six_scores or {}).values() if v is not None]
    if len(scores) >= 2:
        mean = sum(scores) / len(scores)
        variance = sum((x - mean) ** 2 for x in scores) / len(scores)
        dimension_variance = min(1.0, variance / 4.0)  # 5 分制方差上限 ~4
    else:
        dimension_variance = 0.5  # 无评估数据时中性

    cost_ratio = turn_ratio  # 已消耗轮次预算比例（成本感知）

    return [turn_ratio, evidence_density, answer_quality, mode_ordinal,
            catfish_ratio, level_code, dimension_variance, cost_ratio]


# ────────────────────────────────────────────────────────────
# 奖励（4 分量，可复算）
# ────────────────────────────────────────────────────────────

def career_reward(prev_six: dict, curr_six: dict,
                  prev_density: float, curr_density: float,
                  tokens: float = 0.0, catfish_streak: int = 0) -> float:
    """r = w1*Δ六维均分 + w2*Δ证据密度 - w3*token成本 - w4*鲶鱼滥用"""
    def _avg(d: dict) -> float:
        vals = [float(v) for v in d.values() if v is not None]
        return sum(vals) / len(vals) if vals else 0.0

    gain = _avg(curr_six) - _avg(prev_six)
    evid = curr_density - prev_density
    token_cost = min(1.0, max(0.0, tokens / 2000.0))  # 2000 token 归一化
    abuse = max(0, catfish_streak - CATFISH_MAX_CONTINUE)  # 超限轮数
    return (REWARD_W["gain"] * gain
            + REWARD_W["evidence"] * evid
            - REWARD_W["cost"] * token_cost
            - REWARD_W["discipline"] * abuse * 5.0)


# ────────────────────────────────────────────────────────────
# 合成对抗环境（训练 / 对比实验用）
# ────────────────────────────────────────────────────────────

class CareerAdversaryEnv:
    """模拟学生对抗环境：模式选择 → 学生证据密度/六维响应 → 奖励。

    设计意图（答辩可讲）：
      - 常规模式稳定小幅提升；加压在低密度时有效、高质量作答时收益递减；
      - 鲶鱼打破模板化作答（高收益），但连压超限触发纪律惩罚（防捷径）；
      - 每次模式切换有固定 token 成本（加压/鲶鱼提示词更长）。
    """

    MODE_TOKENS = {"normal": 600.0, "escalating": 900.0, "catfish": 1100.0}

    def __init__(self, seed: int = 42, horizon: int = 8, template_student: bool = False):
        self.rng = random.Random(seed)
        self.horizon = horizon
        self.template_student = template_student  # 模板型学生：常规模式学不到东西
        self.step_count = 0
        self.density = 0.5
        self.six = {d: 2.5 for d in ("expression", "stress", "decompose",
                                     "collab", "presentation", "problem_solving")}
        self.catfish_streak = 0

    def reset(self) -> list[float]:
        self.step_count = 0
        self.density = 0.35 if self.template_student else 0.5
        self.six = {d: 2.5 for d in self.six}
        self.catfish_streak = 0
        return self._features()

    def _features(self) -> list[float]:
        turn_ratio = self.step_count / self.horizon
        mode_ordinal = {"normal": 0.0, "escalating": 0.5, "catfish": 1.0}.get(
            self._last_mode, 0.0) if hasattr(self, "_last_mode") else 0.0
        return [turn_ratio, self.density, self.density, mode_ordinal,
                min(1.0, self.catfish_streak / CATFISH_MAX_CONTINUE),
                0.5, 0.3, turn_ratio]

    def step(self, action: int) -> tuple[list[float], float, bool]:
        """action: 0=normal 1=escalating 2=catfish → (features, reward, done)"""
        self.step_count += 1
        mode = CAREER_ACTIONS[action] if 0 <= action < len(CAREER_ACTIONS) else "normal"
        self._last_mode = mode

        if mode == "normal":
            delta_d = -0.04 if self.template_student else 0.03
        elif mode == "escalating":
            delta_d = 0.10 if self.density < 0.45 else 0.02
        else:  # catfish
            delta_d = 0.16 if self.density < 0.5 else 0.05
        self.density = max(0.1, min(0.95, self.density + self.rng.uniform(-0.02, 0.02) + delta_d))

        # 六维均分随证据密度温和提升
        prev_avg = sum(self.six.values()) / len(self.six)
        lift = (self.density - 0.5) * 0.5 + self.rng.uniform(-0.1, 0.1)
        self.six = {d: max(1.0, min(5.0, v + lift / len(self.six))) for d, v in self.six.items()}
        curr_avg = sum(self.six.values()) / len(self.six)

        # 鲶鱼纪律
        self.catfish_streak = self.catfish_streak + 1 if mode == "catfish" else 0

        reward = career_reward(
            {"avg": prev_avg}, {"avg": curr_avg},
            self.density - 0.05, self.density,
            tokens=self.MODE_TOKENS.get(mode, 600.0),
            catfish_streak=self.catfish_streak)
        return self._features(), reward, self.step_count >= self.horizon


# ────────────────────────────────────────────────────────────
# 策略：规则预热 + PPO 微调（复用 mappo_policy 网络构建）
# ────────────────────────────────────────────────────────────

def _rule_action_idx(env_feats: list[float]) -> int:
    """规则版策略（监督预热的安全起点）：低密度加压，连续模板/低分放鲶鱼"""
    density, quality, catfish_ratio = env_feats[1], env_feats[2], env_feats[4]
    if catfish_ratio >= 1.0:
        return 0
    if density < 0.35:
        return 2 if quality < 0.45 else 1
    if density < 0.45:
        return 1
    return 0


class CareerModePolicy:
    """三模式决策策略：规则预热 → PPO 微调；推理失败自动降级规则版。"""

    def __init__(self, hidden: int = 64, lr: float = 3e-4, gamma: float = 0.99,
                 clip_epsilon: float = 0.2):
        self.state_dim = 8
        self.n_actions = len(CAREER_ACTIONS)
        self.gamma = gamma
        self.clip_epsilon = clip_epsilon
        self._torch = None
        self._actor = None
        self._trained = False
        try:
            import torch  # noqa: 延迟导入
            self._torch = torch
            if _mp_build_networks is not None:
                # 复用 mappo_policy 的网络构建（encoder + 动作头框架）
                ActorNet, _Critic = _mp_build_networks(torch)
                self._actor = ActorNet(self.state_dim, hidden)
        except Exception as e:  # pragma: no cover
            logger.warning(f"career 策略网络构建失败（规则版兜底）: {e}")

    # ── 规则预热：用规则版决策做监督训练 ──
    def warmup_with_rules(self, env: CareerAdversaryEnv, steps: int = 800,
                          seed: int = 7) -> dict:
        if self._torch is None or self._actor is None:
            return {"warmed": False, "reason": "torch 不可用"}
        torch = self._torch
        rng = random.Random(seed)
        opt = torch.optim.Adam(self._actor.parameters(), lr=3e-4)
        losses = []
        for _ in range(steps):
            feats = env.reset()
            for _t in range(env.horizon):
                target = torch.tensor([_rule_action_idx(feats)], dtype=torch.long)
                x = torch.tensor([feats], dtype=torch.float32)
                probs = self._actor(x)["difficulty"] if isinstance(self._actor(x), dict) else self._actor(x)
                if isinstance(probs, dict):
                    probs = probs["difficulty"]
                loss = torch.nn.functional.cross_entropy(probs, target)
                opt.zero_grad(); loss.backward(); opt.step()
                losses.append(float(loss.item()))
                feats, _r, done = env.step(_rule_action_idx(feats))
                if done:
                    break
        self._trained = True
        return {"warmed": True, "steps": steps, "mean_loss": sum(losses) / max(1, len(losses))}

    # ── 动作选择：mappo → 失败降级规则 ──
    def select_action(self, features: list[float], deterministic: bool = True) -> tuple[int, str]:
        if self._torch is None or self._actor is None or not self._trained:
            return _rule_action_idx(features), "rule"
        try:
            torch = self._torch
            x = torch.tensor([features], dtype=torch.float32)
            self._actor.eval()
            with torch.no_grad():
                out = self._actor(x)
            probs = out["difficulty"][0] if isinstance(out, dict) else out[0]
            idx = int(probs.argmax().item()) if deterministic else int(torch.multinomial(probs, 1).item())
            # 纪律硬约束：鲶鱼连压超限直接压回 normal（防捷径，不依赖网络自觉）
            if idx == 2 and features[4] >= 1.0:
                idx = 0
            return idx, "mappo"
        except Exception as e:
            logger.warning(f"career MAPPO 推理失败，规则降级: {e}")
            return _rule_action_idx(features), "rule_fallback"

    def save(self, path: str):
        if self._torch is not None and self._actor is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._torch.save(self._actor.state_dict(), path)


# ────────────────────────────────────────────────────────────
# 决策层入口（career_nodes.decide_adversary_mode 委托到本函数）
# ────────────────────────────────────────────────────────────

def _mappo_enabled() -> bool:
    """灰度开关：config career.use_career_mappo，默认 False（规则版）"""
    try:
        import config
        return bool((config.get_career_config() or {}).get("use_career_mappo", False))
    except Exception:
        return False


def maybe_mappo_decide(turns: list[dict], current_mode: str, catfish_continuous: int,
                       rule_fn) -> Optional[tuple[str, bool, int]]:
    """灰度入口：规则注入式决策（避免 career_nodes ↔ career_policy 循环导入）。

    返回 None → 调用方走规则版（灰度关闭 / MAPPO 异常降级）；
    返回 (mode, triggered, cont) → 与规则版同契约。
    """
    if not _mappo_enabled():
        return None
    try:
        from agents.career_state import CATFISH_MAX_CONTINUE as _CMC
        feats = career_state_features(turns, current_mode=current_mode,
                                      catfish_streak=catfish_continuous)
        policy = _get_shared_policy()
        idx, source = policy.select_action(feats, deterministic=True)
        mode = CAREER_ACTIONS[idx] if 0 <= idx < len(CAREER_ACTIONS) else "normal"
        # 契约对齐：触发标记与连压计数语义与规则版一致；纪律超限强制回 normal
        if mode == "catfish":
            cont = catfish_continuous + 1
            if cont > _CMC:
                return "normal", False, 0
        elif mode == "escalating":
            cont = catfish_continuous + 1 if current_mode == "escalating" else 1
        else:
            cont = 0
        triggered = mode in ("escalating", "catfish") and mode != current_mode
        logger.info("career MAPPO 决策 mode=%s source=%s", mode, source)
        return mode, triggered, cont
    except Exception as e:
        logger.warning(f"career MAPPO 决策失败，规则版兜底: {e}")
        return None


_SHARED_POLICY: Optional[CareerModePolicy] = None


def _get_shared_policy() -> CareerModePolicy:
    """进程内共享策略实例（加载 checkpoint；无则规则预热一次）"""
    global _SHARED_POLICY
    if _SHARED_POLICY is None:
        _SHARED_POLICY = CareerModePolicy()
        ckpt = Path(__file__).parent.parent / "models" / "career_mode_policy.pt"
        if ckpt.exists() and _SHARED_POLICY._torch is not None:
            try:
                _SHARED_POLICY._actor.load_state_dict(
                    _SHARED_POLICY._torch.load(str(ckpt), weights_only=True))
                _SHARED_POLICY._trained = True
            except Exception as e:
                logger.warning(f"career 策略 checkpoint 加载失败（预热替代）: {e}")
        if not _SHARED_POLICY._trained:
            _SHARED_POLICY.warmup_with_rules(CareerAdversaryEnv(seed=7), steps=200, seed=7)
    return _SHARED_POLICY


def reset_shared_policy():
    """测试/重训后清空共享实例"""
    global _SHARED_POLICY
    _SHARED_POLICY = None
