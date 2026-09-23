# ============================================================
# review_policy — 三元评审权重 MAPPO 化（评审权重学习器）
#
# 按 docs/CTO-芒得很职三元评审权重MAPPO化攻坚令-2026-09-14.md 实现：
#   - MDP：12 维评审上下文状态 → 5 档权重动作（诚实/批评者/共识 三元权重）
#   - 奖励：4 分量（评审质量增益 + 精准评审 - 成本 - skip 纪律）
#   - 学习：规则预热（监督）→ PPO 微调（CTDE + GAE + clip）
#   - 灰度：config gomarl.use_review_mappo 默认 False；推理异常 → 均匀权重（fail-open）
#   - 纪律：skip 连发 ≥2 重罚 + review_min_review 硬约束（防"一律 skip 省钱"捷径）
#
# 与 P3③ career_policy 的边界（攻坚令第 6 节风险项）：
#   本模块 = 评审权重（输出质量控制）；career_policy = 对抗模式（教学过程控制）。
#   两者 MDP 独立、状态维度不同（12 vs 8）、不共享网络权重，勿混用。
#
# 诚信约束：所有对外数字必须来自落盘 JSON；torch 不可用时如实标注降级，不伪造训练结果。
# ============================================================

# ⚠️⚠️⚠️ 合成环境禁用声明（诚信红线，2026-09-15 审查补强）
# 本文件的 `ReviewEnv` / `ReviewWeightPolicy.train_ppo` / `warmup_with_rules` /
# `evaluate_policy` 是**合成/训练环境**，奖励阶梯仅作历史对照，**不复刻生产打分函数**。
# 任何 RL / 训练效果的对外宣称必须以 `engines/review_env_calibrated.py`
# （奖励复用生产 `weighted_consistency_score`）为准，且**先证同分布**。
# 历史上曾因"在合成环境里宣称 RL ≥ 规则"得出被否证的虚高结论 —— 禁止重蹈。
# 生产真值源仅：`discipline_gate` / `review_precision` / `analytic_review_action` /
# `decide_review_weight`（均轻量、无 torch 依赖）。

import logging
import math
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger("netlearn.review.policy")

# ── 动作空间：5 档离散权重（攻坚令 3.1 动作表）──
REVIEW_ACTIONS = ["trust_honest", "trust_critic", "trust_consensus", "balanced", "skip_review"]

# 每档对应的三元权重向量 (w_honest, w_critic, w_consensus)
REVIEW_WEIGHTS = {
    0: (0.6, 0.2, 0.2),      # 证据强 → 信诚实 Agent
    1: (0.2, 0.6, 0.2),      # 批评质量高 → 信批评者（多挑错）
    2: (0.2, 0.2, 0.6),      # 共识分歧小 → 信共识（保稳定）
    3: (1 / 3, 1 / 3, 1 / 3),  # 默认均衡（= 现状无加权语义）
    4: (0.0, 0.0, 0.0),      # skip：不评审直接放行（受纪律硬约束）
}

# 均匀权重：灰度关闭 / 降级时的行为（等价于现状，零侵入）
UNIFORM_WEIGHTS = {"honest": 1 / 3, "critic": 1 / 3, "consensus": 1 / 3}

# 奖励权重（攻坚令 3.1 初值）
REWARD_W = {"gate": 0.4, "precision": 0.35, "cost": 0.15, "discipline": 0.10}

# 纪律常量（攻坚令 3.3 灰度配置）
REVIEW_MIN_REVIEW = 2      # 每会话至少 2 次真实评审（防 skip 捷径）
SKIP_STREAK_LIMIT = 2      # skip 连发 ≥2 触发重罚 + 硬约束压回

# 各档位 token 成本（用于成本项与 ReviewEnv 模拟，相对量纲）
ACTION_TOKENS = {0: 900.0, 1: 1000.0, 2: 800.0, 3: 950.0, 4: 0.0}

# ── 评审环境动力学调参（决定"按上下文选档"是否真有可学增益）──
# 设计意图（攻坚令 3.1 / 阶段 3 验收"RL ≥ 规则 ≥ 监督"）：
#   1) 档位增益阶梯 matched > balanced > mismatched > skip：选对上下文档位收益最高；
#      恒定 balanced（= 均匀基线）只是中等 → 存在可学增益空间。
#      而不当训练标签，攻坚令第 6 节）
#   2) 真最优档位由 (consistency, critic_quality, disagreement) 的**联合判据**决定。
#      ⚠️ 历史说明已失效（2026-09-14）：本段原写"生产规则是级联、与环境**刻意不同源**，
#      故规则在联合区必然误判，这是 RL 的可学增益来源"。该设定**依赖规则保持级联** ——
#      而生产规则已按实测（`experiments/diag_rule_upgrade.py`）**折进解析阈值**
#      （f2 > 0.675 → trust_honest，否则 trust_consensus），capture 由 39.1% → 54.8%。
#      ⇒ "不同源"论证不再成立，**不得再据本段宣称 RL ≥ 规则**。
#      真实效果一律以 `engines/review_env_calibrated.py`（奖励复用生产
#      `weighted_consistency_score`，balanced 恒 0 增益）+ 报告口径为准。
REV_GAIN_MATCHED = 5.0      # 选对上下文档位
REV_GAIN_BALANCED = 3.0     # 均衡（安全默认，恒定中等）
REV_GAIN_MISMATCH = 1.0     # 选错上下文档位（次优信号）
REV_GAIN_SKIP = 0.0         # 跳过（零质量增益）

# 联合判据边界（环境真最优档位）—— 与规则级联判据刻意不同源
ENV_DISAGREE_HIGH = 0.55    # 分歧 ≥ 此值：任何单一信任都危险 → 均衡
ENV_CONS_HIGH = 0.60        # 证据强度达标
ENV_CQ_LOW = 0.20           # 批评信号弱（低于此值才允许"证据强 → 信诚实"）
ENV_CQ_HIGH = 0.35          # 批评信噪比高
ENV_DISAGREE_LOW = 0.30     # 共识分歧低

# 状态维度（攻坚令 3.1 状态表，共 12 维）
STATE_DIM = 12


# ────────────────────────────────────────────────────────────
# 状态特征（12 维，确定性可复算）
# ────────────────────────────────────────────────────────────

def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def review_state_features(
    evidence: Optional[dict] = None,
    critic: Optional[dict] = None,
    consensus: Optional[dict] = None,
    state: Optional[dict] = None,
    mode_encoding: float = 0.5,
    round_ratio: float = 0.5,
) -> list[float]:
    """评审上下文 → 12 维状态向量（全部归一到 0-1，缺失字段取中性值）。

    维度顺序严格对齐攻坚令 3.1 状态表，便于跨模块复算与测试断言。
    """
    evidence = evidence or {}
    critic = critic or {}
    consensus = consensus or {}
    state = state or {}

    # 1 critic_confidence：规则值，仅作输入特征（不当训练标签，攻坚令第 6 节）
    f1 = _clamp01(float(critic.get("confidence", 0.5)))
    # 2 evidence_consistency：0-100 分制 → /100
    f2 = _clamp01(float(evidence.get("consistency_score", 50.0)) / 100.0)
    # 3 evidence_coverage：覆盖条目 / 期望条目
    expected = float(evidence.get("expected_coverage") or 0)
    covered = float(evidence.get("coverage") or 0)
    f3 = _clamp01(covered / expected) if expected > 0 else _clamp01(covered / 5.0)
    # 4 consensus_status：pass/conflict/none → 0/1/2 → /2
    status = str(consensus.get("status", "none")).lower()
    f4 = {"pass": 0.0, "conflict": 0.5, "none": 1.0}.get(status, 1.0)
    # 5 gate_retry_count：clamp /3
    f5 = _clamp01(float(state.get("gate_retry_count", 0)) / 3.0)
    # 6 disagreement_level：辩论分歧代理（0-1 原值）
    f6 = _clamp01(float(consensus.get("disagreement", state.get("disagreement", 0.5))))
    # 7 valid_critic_count：有效质疑 /5
    f7 = _clamp01(float(critic.get("valid_count", 0)) / 5.0)
    # 8 invalid_critic_count：无效质疑 /5
    f8 = _clamp01(float(critic.get("invalid_count", 0)) / 5.0)
    # 9 quality_delta：本轮 vs 上轮 consistency 差（clamp -1..1 → 映射到 0-1 便于网络输入）
    last_c = state.get("last_consistency")
    if last_c is None:
        f9 = 0.5
    else:
        delta = (float(evidence.get("consistency_score", 50.0)) - float(last_c)) / 100.0
        f9 = _clamp01((max(-1.0, min(1.0, delta)) + 1.0) / 2.0)
    # 10 cost_ratio：已消耗 token / 预算
    budget = float(state.get("token_budget") or 0)
    used = float(state.get("tokens_used") or 0)
    f10 = _clamp01(used / budget) if budget > 0 else _clamp01(used / 4000.0)
    # 11 mode_encoding：教学模式编码（0-1）
    f11 = _clamp01(float(mode_encoding))
    # 12 round_ratio：当前轮 / max_rounds
    f12 = _clamp01(float(round_ratio))

    return [f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12]


# ────────────────────────────────────────────────────────────
# 权重协议（校验 + 归一化）
# ────────────────────────────────────────────────────────────

def review_weight_schema(w: Optional[dict] = None) -> dict:
    """校验并归一化三元权重：w_h + w_c + w_k ≈ 1.0（skip 时全 0）。

    非法/缺失输入 → 均匀权重（fail-open，等价于现状）。
    """
    if not isinstance(w, dict):
        return dict(UNIFORM_WEIGHTS)
    try:
        h = max(0.0, float(w.get("honest", 0.0)))
        c = max(0.0, float(w.get("critic", 0.0)))
        k = max(0.0, float(w.get("consensus", 0.0)))
    except (TypeError, ValueError):
        return dict(UNIFORM_WEIGHTS)

    total = h + c + k
    if total <= 1e-9:
        # 全 0 = skip 语义：合法，但不归一化（保持 skip 可识别）
        return {"honest": 0.0, "critic": 0.0, "consensus": 0.0}
    return {"honest": h / total, "critic": c / total, "consensus": k / total}


def _weights_of(action_idx: int) -> dict:
    """动作索引 → 三元权重 dict（越界 → 均匀权重）。"""
    if action_idx not in REVIEW_WEIGHTS:
        return dict(UNIFORM_WEIGHTS)
    h, c, k = REVIEW_WEIGHTS[action_idx]
    return {"honest": h, "critic": c, "consensus": k}


def _features_valid(features) -> bool:
    """状态特征合法性：必须 12 维且全部有限（非 NaN/Inf）。

    NaN 进入线性层不会抛异常，会静默产出任意权重 —— 因此必须显式拦截，
    否则"fail-open 到均匀权重"的兜底形同虚设。
    """
    if not features or len(features) != STATE_DIM:
        return False
    try:
        return all(math.isfinite(float(v)) for v in features)
    except (TypeError, ValueError):
        return False


# ────────────────────────────────────────────────────────────
# 奖励（4 分量，可复算，防捷径）
# ────────────────────────────────────────────────────────────

def review_reward(
    gate_before: float,
    gate_after: float,
    precision: bool,
    tokens: float = 0.0,
    skip_streak: int = 0,
    return_components: bool = False,
) -> float:
    """r = w1·Δgate_quality + w2·precision_bonus - w3·cost_penalty - w4·skip_abuse

    - Δgate_quality：返工后 consistency / 通过判定改善（+）
    - precision_bonus：正确放行优质产物 +；错误放行 −（精准评审）
    - cost_penalty：本轮 token 归一化（−）
    - skip_abuse：skip 连发 ≥ SKIP_STREAK_LIMIT 重罚（防"全 skip 省钱"捷径）

    return_components=True → 返回 {"gate","precision","cost","discipline","total"} 明细。
    供**判别力审计**使用：可测出某个分项在动作维度上是否恒为常数（即"名义有权重、
    实际不参与决策"）。该判断只能通过本函数的分项透视得到，禁止外部复刻公式 ——
    复刻会导致审计结论与被审计对象不同源（本项目已多次因此得出过错误结论）。
    """
    delta_gate = float(gate_after) - float(gate_before)
    precision_bonus = 1.0 if precision else -1.0
    cost = min(1.0, max(0.0, float(tokens) / 2000.0))
    abuse = max(0, int(skip_streak) - SKIP_STREAK_LIMIT + 1) if skip_streak >= SKIP_STREAK_LIMIT else 0
    total = (REWARD_W["gate"] * delta_gate
             + REWARD_W["precision"] * precision_bonus
             - REWARD_W["cost"] * cost
             - REWARD_W["discipline"] * abuse * 5.0)
    if return_components:
        return {
            "gate": REWARD_W["gate"] * delta_gate,
            "precision": REWARD_W["precision"] * precision_bonus,
            "cost": -REWARD_W["cost"] * cost,
            "discipline": -REWARD_W["discipline"] * abuse * 5.0,
            "total": total,
        }
    return total


# ────────────────────────────────────────────────────────────
# 合成评审环境（训练 / 对比实验用，零 LLM）
# ────────────────────────────────────────────────────────────

class ReviewEnv:
    """模拟评审环境：权重档位选择 → 评审质量 / 成本 → 奖励。

    动力学设计（保证阶段 3 验收"RL ≥ 规则 ≥ 监督"可达，见模块顶部调参常量）：
      - 每个 episode 重新采样评审上下文 (consistency / critic_quality /
        disagreement)（宽区间、互相独立），episode 内缓慢漂移 → 4 个评审档位
        都成为真最优，"按上下文选档"才有可学信号。
      - 档位增益阶梯：matched(选对上下文档位) > balanced(安全默认) > mismatched > skip。
        balanced 恒为中等增益，故固定 balanced（= 均匀基线）必被上下文策略超越。
      - 真最优档位用**联合判据**（ENV_*），规则是**级联判据** → 规则在联合区
        （如"强证据 + 高分歧"）系统性次优，RL 可学得更好。
      - skip 零质量增益且质量未达标时 precision 判错 → 重罚；连发触发纪律惩罚（防捷径）。

    奖励经协议函数 review_reward 复算：delta_gate = 档位增益（0-5 增益量纲），
    再叠加 precision / cost / discipline 三分量。
    """

    def __init__(self, seed: int = 42, horizon: int = 6, noisy: bool = True):
        self.rng = random.Random(seed)
        self.horizon = horizon
        self.noisy = noisy
        self.step_count = 0
        self.skip_streak = 0
        self.reviews_done = 0
        self._last_action = 3
        # 最近一次 step 的原生 precision 判定（None = 尚未 step）。
        # 暴露给评测脚本读取，使"精准率"指标**同源**于环境定义，而非在脚本里
        # 复刻阈值 —— 复刻曾致量纲漂移（0-100 改 0-1 后脚本硬编码 60/75 ⇒ 精准率
        # 恒为 0，而全部单测仍绿）。
        self.last_precision: Optional[bool] = None
        self._sample_context()

    def _sample_context(self) -> None:
        """采样一次评审上下文（三个隐变量独立均匀采样，覆盖全部档位区域）。

        回归背景：旧版把起点固定在 (consistency=0.50, critic_quality=0.15,
        disagreement=0.55) 且三者单调上升 → 轨迹只穿过 2 个档位、规则仅在 1/6 步
        次优（可学增益上限 +0.13/步）→ 信号弱到不可学，RL 学不动。改为每个
        episode 重新采样宽区间上下文，使 4 个评审档位都成为真最优。
        """
        self.consistency = self.rng.uniform(0.15, 0.90)
        self.critic_quality = self.rng.uniform(0.02, 0.60)
        self.disagreement = self.rng.uniform(0.10, 0.85)
        # 共识状态与分歧负相关（分歧低才易 pass），与真实语义一致
        self.consensus_pass = self.disagreement < 0.45

    def reset(self) -> list[float]:
        self.step_count = 0
        self.skip_streak = 0
        self.reviews_done = 0
        self._last_action = 3
        self.last_precision = None
        self._sample_context()
        return self._features()

    def _true_best(self) -> int:
        """环境真最优档位（**联合判据**）。

        顺序即优先级：高分歧一票否决 → 强证据且批评弱 → 批评信噪比高 → 共识已 pass。

        ⚠️ 历史说明已失效（2026-09-14）：本段原称"与规则的级联判据刻意不同源，
        规则在强证据+高分歧区必然误判，故 RL 只需学到别盲信即可超过规则"。
        生产规则已折进解析阈值（`RULE_EVIDENCE_HONEST`），**不再是级联** ——
        该论证随之失效，不得再据此宣称 RL ≥ 规则。
        本环境（合成奖励阶梯）保留仅作历史对照；**真实效果以
        `engines/review_env_calibrated.py` 为准**（奖励复用生产函数）。
        """
        if self.disagreement >= ENV_DISAGREE_HIGH:
            return 3  # 高分歧：任何单一信任都危险 → 均衡
        if self.consistency >= ENV_CONS_HIGH and self.critic_quality < ENV_CQ_LOW:
            return 0  # 证据强且批评信号弱 → trust_honest
        if self.critic_quality >= ENV_CQ_HIGH:
            return 1  # 批评信噪比高 → trust_critic
        if self.consensus_pass and self.disagreement <= ENV_DISAGREE_LOW:
            return 2  # 共识已 pass 且分歧低 → trust_consensus
        return 3

    def _features(self) -> list[float]:
        """观测特征 = 隐状态 + 观测噪声（策略与规则看到的是同一份带噪观测）。

        给 consistency / disagreement 也加噪，使规则在阈值附近误判 —— 这与真实
        场景一致：上下文靠间接指标估计，不是精确读数。
        """
        noise = (lambda: self.rng.uniform(-0.03, 0.03)) if self.noisy else (lambda: 0.0)
        return [
            _clamp01(0.5 + noise()),                               # 1 critic_confidence
            _clamp01(self.consistency + noise()),                  # 2 evidence_consistency
            _clamp01(0.5 + noise()),                               # 3 evidence_coverage
            0.0 if self.consensus_pass else 1.0,                  # 4 consensus_status
            min(1.0, self.step_count / 3.0),                       # 5 gate_retry_count
            _clamp01(self.disagreement + noise()),                # 6 disagreement_level
            _clamp01(self.critic_quality + 0.2 + noise()),         # 7 valid_critic_count
            _clamp01(0.2 + abs(noise())),                         # 8 invalid_critic_count
            0.5,                                                  # 9 quality_delta（中性）
            min(1.0, self.step_count / max(1, self.horizon)),     # 10 cost_ratio
            0.5,                                                  # 11 mode_encoding
            min(1.0, (self.step_count + 1) / max(1, self.horizon)),  # 12 round_ratio
        ]

    def _gain(self, action: int) -> float:
        best = self._true_best()
        if action == 4:
            return REV_GAIN_SKIP
        if action == best:
            return REV_GAIN_MATCHED
        if action == 3:
            return REV_GAIN_BALANCED
        return REV_GAIN_MISMATCH

    def gain_of(self, action: int) -> float:
        """当前上下文下给定动作的质量增益（公开入口，**不**推进环境状态）。

        供评测 / 审计脚本复用同一判据，避免外部复刻增益阶梯 —— 复刻即漂移。
        """
        return self._gain(action)

    def step(self, action: int) -> tuple[list[float], float, bool]:
        """action ∈ [0,4] → (features, reward, done)"""
        self.step_count += 1
        action = int(action) if 0 <= int(action) < len(REVIEW_ACTIONS) else 3
        self._last_action = action

        gain = self._gain(action)
        if action == 4:
            self.skip_streak += 1
        else:
            self.skip_streak = 0
            self.reviews_done += 1

        # 精准评审：判定逻辑已抽为模块级 `review_precision`（唯一真值实现），此处只调用，
        # 避免"环境一套、评测脚本另一套"的量纲漂移。语义与历史教训见该函数 docstring。
        precision = review_precision(self.consistency, action)
        self.last_precision = precision  # 供评测脚本同源读取（勿在外部复刻阈值）

        reward = review_reward(
            gate_before=0.0, gate_after=float(gain), precision=precision,
            tokens=ACTION_TOKENS.get(action, 0.0), skip_streak=self.skip_streak,
        )

        # 上下文缓慢漂移（幅度小于采样区间宽度，episode 内可跨 1-2 个档位区域）
        d = self.rng.uniform(-0.03, 0.03) if self.noisy else 0.0
        self.consistency = _clamp01(self.consistency + 0.03 + d)
        self.critic_quality = _clamp01(self.critic_quality + 0.02 + d)
        self.disagreement = _clamp01(self.disagreement - 0.02 + d)
        self.consensus_pass = self.disagreement < 0.45
        return self._features(), reward, self.step_count >= self.horizon


# ────────────────────────────────────────────────────────────
# 规则版策略（warmup 监督标签来源，安全起点）
# ────────────────────────────────────────────────────────────

# ── 规则证据门槛（解析推导，非拟合）──
# 生产有效分展开式 effective = s_h + (c − 1/3)·(s_c − s_h) + (k − 1/3)·(s_k − s_h)，
# 令 trust_honest(=s_h) 与 trust_consensus 的**期望**相等，解出证据强度交点 s_h ≈ 67.5 分
# ⇒ f2 ≈ 0.675。该值来自三信号独立假设下的解析期望，**不在任何评估集上拟合**，故无泄漏。
RULE_EVIDENCE_HONEST = 0.675

# 规则折法（2026-09-14 实测选定；见 experiments/diag_rule_upgrade.py +
# results/diag_rule_upgrade.json）：
#   实测否证了"问题在阈值位置"的假设 —— 仅把级联门槛 0.6 → 0.675（其余不变）：
#     主集 −0.033 (t=−0.27) / 独立泛化集 −0.133 (t=−1.02)，**无改善甚至略负**。
#   真因是低证据区**回落到 balanced**（其真实增益恒 0，且 240 样本中 0 次最优）。
#   故折法 = 阈值二分支（f2 > 0.675 → trust_honest，否则 trust_consensus）：
#     主集 +0.859 (t=+3.27) / 泛化 +1.032 (t=+2.87)，capture 54.8% / 50.1%
#     （对比现行级联 39.1% / 33.1%）。
#   保留 critic 支路的变体反而更差（主集 −0.132）⇒ critic 判据（valid−invalid ≥ 0.25）
#   经实测不可靠，**确定性规则不再主动选 critic**；critic 档位仍在动作集内，RL 路径可选。
RULE_F2_BINARY = True   # 回退开关：置 False → 走 `_rule_action_idx_legacy`（原级联）


def _rule_action_idx(features: list[float]) -> int:
    """规则版评审权重选择（**已折进解析阈值**，2026-09-14 实测选定）。

    - 成本高压且质量已达标 → skip（真实评审次数/连发仍由 `discipline_gate` 硬约束）
    - 证据强（f2 > RULE_EVIDENCE_HONEST）→ trust_honest
    - 否则 → trust_consensus

    为什么不再 balanced 兜底：实测 balanced 在 240 条真实形态样本中 **0 次最优**、
    相对增益恒 0 —— 兜底到它等于主动放弃头寸（capture 39.1% → 54.8%）。

    回退：`RULE_F2_BINARY = False` → `_rule_action_idx_legacy`（原级联，保留供对照）。
    """
    if not RULE_F2_BINARY:
        return _rule_action_idx_legacy(features)
    if not features or len(features) < STATE_DIM:
        return 3
    consistency, cost_ratio = features[1], features[9]
    if consistency >= 0.75 and cost_ratio >= 0.6:
        return 4
    return 0 if consistency > RULE_EVIDENCE_HONEST else 2


def _rule_action_idx_legacy(features: list[float]) -> int:
    """原级联版规则（2026-09-14 之前的默认）。**保留供回退与历史数字对照**，不在默认路径上。

    实测 capture 主集 39.1% / 泛化 33.1%，低于折进阈值版 15.6 / 17.0 个百分点；
    保留原因：① 一键回退；② 历史报告的数字需可复现到当时的实现。
    """
    if not features or len(features) < STATE_DIM:
        return 3
    consistency, status, disagree = features[1], features[3], features[5]
    valid_c, invalid_c = features[6], features[7]
    cost_ratio = features[9]
    if consistency >= 0.75 and cost_ratio >= 0.6:
        return 4
    if consistency >= 0.6:
        return 0
    if (valid_c - invalid_c) >= 0.25:
        return 1
    if status <= 0.1 and disagree <= 0.35:
        return 2
    return 3


# ────────────────────────────────────────────────────────────
# 解析最优档位（恒等式；零训练、零搜索）
# ────────────────────────────────────────────────────────────
# 生产打分为 effective = s_h + (h·s_h + c·s_c + k·s_k) − mean
# （见 agents/quality_gate.weighted_consistency_score）。四档有效分因此**可直接算出**，
# 最优档位是**解析解**：
#
#     eff(trust_honest)    = s_h + (0.6·s_h + 0.2·s_c + 0.2·s_k) − mean
#     eff(trust_critic)    = s_h + (0.2·s_h + 0.6·s_c + 0.2·s_k) − mean
#     eff(trust_consensus) = s_h + (0.2·s_h + 0.2·s_c + 0.6·s_k) − mean
#     eff(balanced)        = s_h
#
# 实测（`experiments/diag_state_extend.py`，独立泛化集 seed=313131）：
#   · 无噪：capture **100.0%**，与 oracle 动作一致率 **100.0%**；
#   · 加噪 ±0.03（模拟上游估计误差）：capture **99.7%**，一致率 96.2% ⇒ 对误差稳健；
#   · 对比：折进阈值的二分支规则 50.1%；RL 最优配置 56.1%。
#
# **关键前提**：决策读到的 (s_h, s_c, s_k) 与打分**同源**。生产链路两者都经
# `review_signals(evidence, consensus)` 取同一份 evidence/consensus ⇒ 前提成立。
# ⚠️ 诚实边界：这证明"**在 effective 这一目标函数下**最优动作可解析求出"，
#    不等于"effective 提升 = 真实教学质量提升"（effective 仍是代理指标）。
RULE_MODE = "analytic"   # "analytic"（默认：解析最优）| "f2_binary" | "legacy"


def analytic_review_action(evidence: Optional[dict] = None,
                           consensus: Optional[dict] = None) -> int:
    """解析最优评审档位（0..3）：按生产打分定义复算四档有效分并取最大。

    与打分函数**同源**（同一 `review_signals`），故结果与 `weighted_consistency_score`
    的实际 argmax 逐位一致（由 `tests/test_review_analytic.py` 以恒等式守护）。

    只在 0..3 中选（skip=4 由 `discipline_gate` 依纪律决定，不在此处放行）。
    """
    from agents.quality_gate import review_signals  # 延迟导入，避免与 agents 循环
    s_h, s_c, s_k = review_signals(evidence or {}, consensus or {})
    mean3 = (s_h + s_c + s_k) / 3.0
    best_a, best_v = 3, float("-inf")
    for a in (0, 1, 2, 3):
        h, c, k = REVIEW_WEIGHTS[a]
        v = s_h + (h * s_h + c * s_c + k * s_k) - mean3
        if v > best_v:
            best_a, best_v = a, v
    return best_a


def review_precision(consistency: float, action: int) -> bool:
    """评审精准判定的**唯一真值实现**（环境 / 评测脚本 / 指纹 / 测试共用）。

    语义（攻坚令 3.1：precision = "正确放行优质产物"）：
      - 产物质量达标（consistency ≥ 0.5）→ 放行即正确 → True；
      - 质量不达标 → 只有**真实评审过**（非 skip）才算拦住了 → True；skip 属漏检重罚 → False。

    ⚠️ 衡量的是"放行判定是否正确"，**不是**"是否选中最优档位"。早期实现把"档位错配"
    也判成 False，使错配奖励被 -0.35 抵消到 ≈0，低于 skip 的 0.35、远低于 balanced 的
    1.48 —— 奖励地形出现人为悬崖，RL 学不到"次优也比不评审好"。

    为什么必须是函数：本判定曾被评测脚本按旧量纲**复刻**成 `thr = 75.0 if idx==4 else 60.0`
    （0-100 时代产物）。量纲改为 0-1 后该复刻体恒判 False ⇒ 精准率四臂全 0，而全部单测
    仍绿。抽成函数后，外部只能调用、无法"改一个数字"式地悄悄漂移。
    """
    return True if consistency >= 0.5 else (action != 4)


def discipline_gate(idx: int, features: list, skip_streak: int = 0,
                    reviews_done: int = 0) -> int:
    """评审纪律硬约束的**唯一真值实现**（生产 / 评测 / 校准环境共用）。

    规则（攻坚令阶段 3）：skip 连发 ≥2 发生率为 0 ⇒ 必须在**第 2 次连发发生前**拦截。
    若等 `skip_streak >= SKIP_STREAK_LIMIT(2)` 才拦，第 2 次连发已经发生，与验收指标
    直接冲突（原实现此处差一，已修）。

    触发拦截时压回：证据强（features[1] ≥ 0.6）→ trust_honest(0)，否则 balanced(3)。

    为什么必须是单一实现（血泪）：本规则此前在代码库里存在 **3 份**互不引用的复制 ——
      (a) `ReviewWeightPolicy.select_action` 内闭包 `_block_skip`
      (b) `evaluate_policy` 内闭包 `_apply_discipline`
      (c) `engines/review_env_calibrated.py` 的模块级 `discipline_gate`（逐字复刻）
    修 (a) 的差一时，(b)(c) 不会跟着改 → 静默漂移。已实际付代价：角色 C 的评测脚本
    因绕开护栏而报出 `discipline_ok=False / max_skip_streak=2` 的**假警报**，把
    "脚本口径错误"误诊为"策略违规"。现统一为本函数，其余位置只做委托。
    """
    if idx == 4 and (reviews_done < REVIEW_MIN_REVIEW
                     or skip_streak >= SKIP_STREAK_LIMIT - 1):
        return 0 if (features and len(features) > 1 and features[1] >= 0.6) else 3
    return idx


# ────────────────────────────────────────────────────────────
# 策略网络（独立 12→5 头，不污染 mappo_policy 现有 3 动作头）
# ────────────────────────────────────────────────────────────

def _seed_all(seed: int) -> None:
    """全链路播种：让同一 seed 的实验结果可逐位复算。

    必须在**网络初始化之前**调用（权重初始化走 torch 全局 RNG）；
    PPO 的动作采样 dist.sample() 同样依赖该 RNG，故一次播种覆盖全流程。
    """
    random.seed(seed)
    try:
        import numpy as _np
        _np.random.seed(seed % (2 ** 32))
    except Exception:
        pass
    try:
        import torch as _torch
        _torch.manual_seed(seed)
    except Exception:
        pass


class ReviewWeightPolicy:
    """三元评审权重策略：规则预热 → PPO 微调；推理失败自动降级规则/均匀权重。"""

    def __init__(self, hidden: int = 64, lr: float = 3e-4, gamma: float = 0.99,
                 clip_epsilon: float = 0.2, gae_lambda: float = 0.95,
                 seed: Optional[int] = 42):
        self.state_dim = STATE_DIM
        self.n_actions = len(REVIEW_ACTIONS)
        self.gamma = gamma
        self.clip_epsilon = clip_epsilon
        self.gae_lambda = gae_lambda
        self.lr = lr
        self._torch = None
        self._actor = None
        self._critic = None
        self._trained = False
        # 网络权重初始化走 torch 全局 RNG：不播种则每次进程结果都不同，
        # 3-seed 实验将不可复算（实测同 seed 两次跑动作分布不同）。
        if seed is not None:
            _seed_all(seed)
        try:
            import torch  # 延迟导入（torch 缺失环境走规则降级）
            self._torch = torch
            self._actor = self._build_actor(torch, hidden)
            self._critic = self._build_critic(torch, hidden)
            self._opt = torch.optim.Adam(
                list(self._actor.parameters()) + list(self._critic.parameters()), lr=lr)
        except Exception as e:  # pragma: no cover - torch 缺失
            logger.warning(f"评审权重策略网络构建失败（规则版兜底）: {e}")

    # ── 网络（独立构建，风格对齐 mappo_policy._build_networks）──
    def _build_actor(self, torch, hidden: int):
        n_actions, state_dim = self.n_actions, self.state_dim

        class _Actor(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.encoder = torch.nn.Sequential(
                    torch.nn.Linear(state_dim, hidden), torch.nn.Tanh(),
                    torch.nn.Linear(hidden, hidden), torch.nn.Tanh(),
                )
                self.head = torch.nn.Linear(hidden, n_actions)

            def forward(self, s):
                return torch.softmax(self.head(self.encoder(s)), dim=-1)

        return _Actor()

    def _build_critic(self, torch, hidden: int):
        state_dim = self.state_dim

        class _Critic(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.net = torch.nn.Sequential(
                    torch.nn.Linear(state_dim, hidden), torch.nn.Tanh(),
                    torch.nn.Linear(hidden, hidden), torch.nn.Tanh(),
                    torch.nn.Linear(hidden, 1),
                )

            def forward(self, s):
                return self.net(s).squeeze(-1)

        return _Critic()

    @property
    def torch_available(self) -> bool:
        return self._torch is not None and self._actor is not None

    # ── 规则预热：用规则版决策做监督训练（安全起点）──
    def warmup_with_rules(self, env: Optional[ReviewEnv] = None, steps: int = 800,
                          seed: int = 7) -> dict:
        if not self.torch_available:
            return {"warmed": False, "reason": "torch 不可用", "steps": 0}
        torch = self._torch
        env = env or ReviewEnv(seed=seed)
        opt = torch.optim.Adam(self._actor.parameters(), lr=self.lr)
        losses = []
        for _ in range(steps):
            feats = env.reset()
            for _t in range(env.horizon):
                target = torch.tensor([_rule_action_idx(feats)], dtype=torch.long)
                x = torch.tensor([feats], dtype=torch.float32)
                probs = self._actor(x)
                loss = torch.nn.functional.cross_entropy(probs, target)
                opt.zero_grad()
                loss.backward()
                opt.step()
                losses.append(float(loss.item()))
                feats, _r, done = env.step(_rule_action_idx(feats))
                if done:
                    break
        self._trained = True
        return {"warmed": True, "steps": steps,
                "mean_loss": sum(losses) / max(1, len(losses)),
                "final_loss": losses[-1] if losses else None}

    # ── PPO 微调（GAE + clip；轨迹来自 ReviewEnv，零 LLM）──
    def train_ppo(self, env: Optional[ReviewEnv] = None, episodes: int = 3000,
                  horizon: int = 6, seed: int = 42, epochs: int = 4,
                  batch_episodes: int = 48) -> dict:
        """轻量 PPO：按批收集轨迹 → GAE → clip 更新 actor/critic。

        返回可落盘统计（含每 episode 回报，用于绘制收敛曲线）。
        torch 不可用 → 如实返回 {"trained": False, "reason": ...}，不伪造曲线。

        ⚠️ 训练预算（episodes/batch_episodes）是**决定验收结论的关键超参**，非无关紧要：
        实测 episodes=400 时 RL 回报 1.14~1.23 < 规则 1.26（欠训练，结论"RL 不如规则"）；
        episodes≥1500 时 RL 升至 1.83~1.98 > 规则（真实收敛）。默认值取扫参最稳档
        （3000/48，3-seed 最低值最高）。对外引用数字必须同时标注该预算，否则不可复算。
        """
        if not self.torch_available:
            return {"trained": False, "reason": "torch 不可用", "episodes": 0}
        torch = self._torch
        env = env or ReviewEnv(seed=seed, horizon=horizon)
        returns_curve: list[float] = []
        # ── batch 化更新（关键修复）──
        # 旧实现"每 1 个 episode（6 步）立刻更新一次"：单批仅 6 个样本，优势标准化
        # 除以 6 样本的 std → 梯度方差极大，实测把 warmup 出的策略直接打崩
        # （argmax 从 trust_honest 漂到 skip_review，均值回报 2.01 → 1.75，
        #  3/3 seed improved=False）。改为攒 batch_episodes 条轨迹再统一 GAE + 更新。
        buffer: list[dict] = []
        n_updates = 0

        def _det_return(n_ep: int = 40) -> float:
            """确定性策略在**独立环境实例**上的平均回报（部署口径，无采样噪声）。

            为什么必须单独算（实测证据，experiments/diag_train_return_vs_eval.py）：
            returns_curve 用**随机采样**动作累计。一旦策略给"被纪律门恒拒绝的 skip(4)"
            分配概率，每一步都吃 −1.0 惩罚 —— 63 次更新后 P(步=skip)≈19%，
            训练回报从 24.5 掉到 10.4 且 `improved=False`，而**同一策略**的确定性回报
            是 44.4（5 次更新时仅 29.9），真实质量分同样上升（69.896 vs 规则 68.948）。
            ⇒ 只看随机回报会把"策略变好"读成"PPO 无效"。部署走的是 argmax，
              故决策质量应以确定性回报为准。
            环境实例用 seed+7777 的独立副本，避免与训练轨迹重叠。
            """
            try:
                ev = type(env)(seed=seed + 7777, horizon=horizon)
            except Exception:
                ev = env
            tot = 0.0
            for _ in range(n_ep):
                s_d = ev.reset()
                ep_r = 0.0
                for _t in range(horizon):
                    x = torch.tensor([s_d], dtype=torch.float32)
                    self._actor.eval()
                    with torch.no_grad():
                        a = int(self._actor(x)[0].argmax().item())
                    s_d, r, done = ev.step(a)
                    ep_r += float(r)
                    if done:
                        break
                tot += ep_r
            self._actor.train()
            return tot / max(1, n_ep)

        det_before = _det_return()

        def _flush(buf: list[dict]) -> None:
            if not buf:
                return
            nonlocal n_updates
            n_updates += 1
            s_t = torch.tensor([s for ep in buf for s in ep["states"]], dtype=torch.float32)
            a_t = torch.tensor([a for ep in buf for a in ep["actions"]], dtype=torch.long)
            old_logp_t = torch.stack([lp for ep in buf for lp in ep["logps"]]).detach()
            adv_flat, ret_flat = [], []
            for ep in buf:
                next_v = 0.0 if ep["dones"][-1] else float(self._critic(
                    torch.tensor([ep["last_state"]], dtype=torch.float32)).item())
                advantages, gae = [], 0.0
                for i in reversed(range(len(ep["rewards"]))):
                    v_i = float(ep["values"][i].item())
                    v_next = (float(ep["values"][i + 1].item())
                              if i + 1 < len(ep["values"]) else next_v)
                    delta = ep["rewards"][i] + self.gamma * v_next - v_i
                    gae = delta + self.gamma * self.gae_lambda * (0.0 if ep["dones"][i] else gae)
                    advantages.insert(0, gae)
                adv_flat.extend(advantages)
                ret_flat.extend(adv + float(ep["values"][i].item())
                                for i, adv in enumerate(advantages))
            adv_t = torch.tensor(adv_flat, dtype=torch.float32)
            ret_t = torch.tensor(ret_flat, dtype=torch.float32)
            if adv_t.numel() > 1:
                adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)
            for _e in range(epochs):
                probs = self._actor(s_t)
                dist = torch.distributions.Categorical(probs)
                new_logp = dist.log_prob(a_t)
                ratio = torch.exp(new_logp - old_logp_t)
                surr1 = ratio * adv_t
                surr2 = torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon) * adv_t
                actor_loss = -torch.min(surr1, surr2).mean()
                critic_loss = torch.nn.functional.mse_loss(self._critic(s_t), ret_t)
                entropy = dist.entropy().mean()
                # 熵系数 0.01 → 0.003：原值在 5 动作空间里过强，持续把分布推向近似均匀
                # （含本不该选的 skip），是策略崩坏的第二推手。
                loss = actor_loss + 0.5 * critic_loss - 0.003 * entropy
                self._opt.zero_grad()
                loss.backward()
                self._opt.step()

        for _ep in range(episodes):
            states, actions, rewards, logps, values, dones = [], [], [], [], [], []
            s = env.reset()
            ep_return = 0.0
            for _t in range(horizon):
                x = torch.tensor([s], dtype=torch.float32)
                probs = self._actor(x)
                dist = torch.distributions.Categorical(probs)
                a = int(dist.sample().item())
                logp = dist.log_prob(torch.tensor([a], dtype=torch.long))
                v = self._critic(x)
                ns, r, done = env.step(a)
                states.append(s); actions.append(a); rewards.append(float(r))
                logps.append(logp); values.append(v); dones.append(bool(done))
                ep_return += float(r)
                s = ns
                if done:
                    break
            returns_curve.append(ep_return)
            buffer.append({"states": states, "actions": actions, "rewards": rewards,
                           "logps": logps, "values": values, "dones": dones,
                           "last_state": s})
            if len(buffer) >= batch_episodes or _ep == episodes - 1:
                _flush(buffer)
                buffer = []

        self._trained = True
        det_after = _det_return()
        head = returns_curve[:max(1, len(returns_curve) // 3)]
        tail = returns_curve[-max(1, len(returns_curve) // 3):]
        return {
            "trained": True, "episodes": episodes, "horizon": horizon, "seed": seed,
            # 有效预算显式落盘：batch_episodes 一旦改变语义（旧版每 episode 更新一次），
            # 未显式传参的调用方会被静默饿死（实测影子探针 200 episode 从 200 次更新
            # 降到 4 次）。把真实更新次数返回，任何调用方都能审计"是否真训了"。
            "batch_episodes": int(batch_episodes), "n_updates": n_updates,
            "returns": returns_curve,
            "mean_return": sum(returns_curve) / max(1, len(returns_curve)),
            "mean_return_first_third": sum(head) / max(1, len(head)),
            "mean_return_last_third": sum(tail) / max(1, len(tail)),
            # ⚠️ `improved` 基于**随机采样**回报，会被"无效 skip 惩罚 + 采样噪声"主导，
            #    与真实策略质量可脱钩（实测出现 improved=False 而质量上升）。审计决策
            #    质量请用 `improved_deterministic`（部署走 argmax），`improved` 仅保留
            #    向后兼容，不得单独作为"PPO 是否有效"的证据。
            "improved": (sum(tail) / max(1, len(tail))) > (sum(head) / max(1, len(head))),
            "det_return_before": round(det_before, 4),
            "det_return_after": round(det_after, 4),
            "improved_deterministic": det_after > det_before,
        }

    # ── 动作选择：mappo → 失败降级规则 ──
    def select_action(self, features: list[float], deterministic: bool = True,
                      skip_streak: int = 0, reviews_done: int = 0) -> tuple[int, str]:
        """返回 (action_idx, source)；source ∈ {"mappo", "rule", "rule_fallback"}。

        纪律硬约束（不依赖网络自觉）：统一走模块级 `discipline_gate`（单一真值源），
        见该函数 docstring 对"三份复制曾静默漂移"的说明。
        """
        if not _features_valid(features):
            logger.warning("评审状态特征非法（NaN/Inf/维度不符），规则层直接均衡兜底")
            return 3, "rule_fallback"

        if not self.torch_available or not self._trained:
            return discipline_gate(_rule_action_idx(features), features,
                                   skip_streak, reviews_done), "rule"
        try:
            torch = self._torch
            x = torch.tensor([features], dtype=torch.float32)
            self._actor.eval()
            with torch.no_grad():
                probs = self._actor(x)[0]
            idx = int(probs.argmax().item()) if deterministic else \
                int(torch.multinomial(probs, 1).item())
            return discipline_gate(idx, features, skip_streak, reviews_done), "mappo"
        except Exception as e:
            logger.warning(f"评审权重 MAPPO 推理失败，规则降级: {e}")
            return discipline_gate(_rule_action_idx(features), features,
                                   skip_streak, reviews_done), "rule_fallback"

    def save(self, path: str):
        if not self.torch_available:
            return False
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._torch.save({"actor": self._actor.state_dict(),
                          "critic": self._critic.state_dict()}, path)
        return True


# ────────────────────────────────────────────────────────────
# 协议入口（攻坚令 3.3 签名）
# ────────────────────────────────────────────────────────────

def _mappo_enabled() -> bool:
    """灰度开关：优先复用 config.use_review_mappo()（单点真值），默认 False（=现状均匀权重）。

    优先调用 config 的专用访问器，避免本模块与 config 各读一次 gomarl 段导致口径漂移；
    访问器不存在（旧版 config）时回退直读 gomarl 段，仍默认关闭。
    """
    try:
        import config
        accessor = getattr(config, "use_review_mappo", None)
        if callable(accessor):
            return bool(accessor())
        return bool((config.get_gomarl_config() or {}).get("use_review_mappo", False))
    except Exception:
        return False


def decide_review_weight(
    features: list[float],
    use_mappo: bool = False,
    skip_streak: int = 0,
    reviews_done: int = 0,
    evidence: Optional[dict] = None,
    consensus: Optional[dict] = None,
) -> dict:
    """三元评审权重决策（攻坚令 3.3 接口签名）。

    use_mappo=False → 均匀权重（= 现状，灰度安全，行为零变化）；
    use_mappo=True  → 按 `RULE_MODE`：
        "analytic"（默认）→ 解析最优档位（需 evidence/consensus；缺任一则退策略路径）
        "f2_binary" / "legacy" → 走策略（未训练时即规则档）
    任何异常 → 均匀权重（fail-open）。
    返回 {"weights": {...}, "source": "analytic"/"mappo"/"rule"/"uniform", "action": int}
    """
    if not use_mappo:
        return {"weights": dict(UNIFORM_WEIGHTS), "source": "uniform", "action": 3}
    if RULE_MODE == "analytic" and evidence is not None and consensus is not None \
            and _features_valid(features):
        try:
            idx = discipline_gate(analytic_review_action(evidence, consensus), features,
                                  skip_streak, reviews_done)
            return {"weights": review_weight_schema(_weights_of(idx)),
                    "source": "analytic", "action": idx}
        except Exception as e:  # noqa: BLE001 - 解析失败即退策略路径
            logger.warning(f"解析档位决策失败，退回策略路径: {e}")
    if not _features_valid(features):
        logger.warning("评审权重决策输入特征非法，均匀权重兜底")
        return {"weights": dict(UNIFORM_WEIGHTS), "source": "uniform", "action": 3}
    try:
        policy = _get_shared_policy()
        idx, source = policy.select_action(
            features, deterministic=True, skip_streak=skip_streak, reviews_done=reviews_done)
        weights = review_weight_schema(_weights_of(idx))
        return {"weights": weights, "source": source, "action": idx}
    except Exception as e:
        logger.warning(f"评审权重决策失败，均匀权重兜底: {e}")
        return {"weights": dict(UNIFORM_WEIGHTS), "source": "uniform", "action": 3}


_SHARED_POLICY: Optional[ReviewWeightPolicy] = None


def _get_shared_policy() -> ReviewWeightPolicy:
    """进程内共享策略实例：优先加载 checkpoint，否则规则预热一次。"""
    global _SHARED_POLICY
    if _SHARED_POLICY is None:
        _SHARED_POLICY = ReviewWeightPolicy()
        ckpt = Path(__file__).parent.parent / "models" / "review_weight_policy.pt"
        if ckpt.exists() and _SHARED_POLICY.torch_available:
            try:
                state = _SHARED_POLICY._torch.load(str(ckpt), weights_only=True)
                _SHARED_POLICY._actor.load_state_dict(state["actor"])
                _SHARED_POLICY._trained = True
            except Exception as e:
                logger.warning(f"评审权重 checkpoint 加载失败（预热替代）: {e}")
        if not _SHARED_POLICY._trained:
            _SHARED_POLICY.warmup_with_rules(ReviewEnv(seed=7), steps=200, seed=7)
    return _SHARED_POLICY


def reset_shared_policy():
    """测试 / 重训后清空共享实例"""
    global _SHARED_POLICY
    _SHARED_POLICY = None


# ────────────────────────────────────────────────────────────
# 评估：三方案对比（A=RL / B=固定规则 / C=均匀基线）
# ────────────────────────────────────────────────────────────

def evaluate_policy(policy_or_mode, env: ReviewEnv, horizon: int = 6) -> dict:
    """在给定环境下评估一个决策方式的平均回报与 skip 行为。

    policy_or_mode: "rule" | "uniform" | ReviewWeightPolicy 实例
    """
    feats = env.reset()
    total, skips, skip_streak, reviews_done, max_skip_streak = 0.0, 0, 0, 0, 0

    def _apply_discipline(idx: int, f: list[float]) -> int:
        """纪律护栏对三方案（RL/规则/监督）一视同仁。

        理由：① 验收指标"skip 连发 ≥2 发生率为 0"是全方案共同要求（攻坚令阶段 3）；
        ② 若只给 RL 加护栏，规则版会因 skip 省成本而虚高，对比不公平。

        委托模块级 `discipline_gate`（单一真值源），此处不再自行复刻规则 ——
        复刻是此前三份实现静默漂移的成因。
        """
        return discipline_gate(idx, f, skip_streak, reviews_done)

    for _ in range(horizon):
        if policy_or_mode == "rule":
            idx = _apply_discipline(_rule_action_idx(feats), feats)
        elif policy_or_mode == "uniform":
            idx = 3
        else:
            idx, _src = policy_or_mode.select_action(
                feats, deterministic=True, skip_streak=skip_streak, reviews_done=reviews_done)
            idx = _apply_discipline(idx, feats)
        if idx == 4:
            skips += 1
            skip_streak += 1
            max_skip_streak = max(max_skip_streak, skip_streak)
        else:
            skip_streak = 0
            reviews_done += 1
        feats, r, done = env.step(idx)
        total += r
        if done:
            break
    return {
        "mean_return": total / max(1, horizon),
        "total_return": total,
        "skip_count": skips,
        "max_skip_streak": max_skip_streak,
        "reviews_done": reviews_done,
        "discipline_violation": max_skip_streak >= SKIP_STREAK_LIMIT,
    }
