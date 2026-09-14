# ============================================================
# review_env_calibrated — 校准版评审权重环境（让 RL 学到真实的上下文增益）
#
# 为什么需要这个模块（证据：experiments/diag_review_headroom.py）
# ---------------------------------------------------------------
# 原 ReviewEnv（engines/review_policy.py）的奖励是"合成阶梯"：
#     matched=5.0 > balanced=3.0 > mismatched=1.0 > skip=0.0
#   balanced 被赋予 3.0（最优的 60%），于是 PPO 的最优策略就是"躺平在 balanced"
#   —— 收益只损失 40%，探索风险却是正的。实测 3 个种子 240 样本里 99.2%~100% 选 balanced。
#
# 但生产真实质量函数（agents/quality_gate.weighted_consistency_score）里：
#     Δ_eff(action) = (c − 1/3)·(s_c − s_h) + (k − 1/3)·(s_k − s_h)
#     balanced（1/3,1/3,1/3）⇒ Δ_eff ≡ 0
#   在 240 条真实形态样本上 balanced 是 0/240 次最优；oracle 相对 uniform 有 +5.47 头寸，
#   且仅凭 f2（evidence_consistency）单特征阈值即可吃到 60.2% 头寸（+3.215，超过规则基线）。
#   ⇒ 原环境把"零增益"教成了"近优增益"，这才是 sim-to-real 崩塌的根因，而非状态不可学。
#
# 本模块做法（faithful simulator，而非"调参调到 RL 赢"）
# ---------------------------------------------------------------
#   1. 奖励分支**直接调用生产同款函数** weighted_consistency_score 复算：
#        gate_after = effective − uniform_baseline  （即相对现状的真实增益；balanced ⇒ 0）
#   2. 上下文 (s_h, s_c, s_k) 按与线上同分布采样（分布镜像 run_shadow_probe.generate_samples，
#      但独立抽样、互不复用样本 → 训练集与评测集不重叠）。
#   3. 12 维特征由真实 review_state_features 从合成 evidence/consensus/critic/state 生成，
#      保证特征语义、维度、取值范围与线上完全一致。
#   4. 纪律：skip 因 effective ≡ 100 属口径陷阱，按生产纪律门 _block_skip（reviews_done=0
#      口径）禁用本环境中的 skip 捷径，避免学到"跳过评审拿满分"的退化解。
#
# 不变式：不修改 engines/review_policy.py（A 的交付物原样保留）；本模块仅新增。
# ============================================================

import random
from typing import Optional

from agents.quality_gate import review_signals, weighted_consistency_score
from engines.review_policy import (
    ACTION_TOKENS,
    REVIEW_MIN_REVIEW,
    SKIP_STREAK_LIMIT,
    STATE_DIM,
    UNIFORM_WEIGHTS,
    _weights_of,
    review_reward,
    review_state_features,
    review_weight_schema,
)


def discipline_gate(action: int, features: list, skip_streak: int = 0,
                    reviews_done: int = 0) -> int:
    """与 review_policy.select_action 内 _block_skip 逐字一致的纪律门（本模块内复刻）。

    - reviews_done < REVIEW_MIN_REVIEW 或 skip_streak ≥ SKIP_STREAK_LIMIT 时禁止 skip：
      证据强（f2 ≥ 0.6）压回 trust_honest，否则压回 balanced。
    """
    if action == 4 and (reviews_done < REVIEW_MIN_REVIEW or skip_streak >= SKIP_STREAK_LIMIT):
        return 0 if (features and len(features) > 1 and features[1] >= 0.6) else 3
    return action


class CalibratedReviewEnv:
    """与现实同构的评审权重环境：奖励 = 生产质量函数的真实增益（balanced 恒为 0）。

    接口与 ReviewEnv 完全一致（reset / step / horizon / rng），可直接传给
    ReviewWeightPolicy.warmup_with_rules / train_ppo / evaluate_policy。
    """

    def __init__(self, seed: int = 42, horizon: int = 6, noisy: bool = True,
                 reviews_done: int = 0):
        self.rng = random.Random(seed)
        self.horizon = max(1, int(horizon))
        self.noisy = noisy
        # reviews_done 固定为 0：本环境建模"单次独立评审决策"（与影子探针口径一致），
        # 使纪律门恒禁止 skip → 不会学到"跳过评审"的退化解。
        self._reviews_done_fixed = int(reviews_done)
        self.step_count = 0
        self.skip_streak = 0
        self.reviews_done = 0
        self._sample_context()

    # ── 上下文采样：分布镜像线上真实形态样本 ──
    def _sample_context(self) -> None:
        r = self.rng
        status = r.choice(["pass", "conflict", "none"])
        has_overall = (status != "none") and (r.random() < 0.8)
        budget = r.choice([2000, 4000])

        self._evidence = {
            "consistency_score": round(r.uniform(30.0, 100.0), 1),
            "coverage": r.randint(0, 8),
            "expected_coverage": max(1, r.randint(2, 8)),
        }
        self._critic = {
            "confidence": round(r.uniform(0.2, 0.95), 3),
            "valid_count": r.randint(0, 5),
            "invalid_count": r.randint(0, 5),
        }
        self._consensus = {
            "status": status,
            "confidence_score": round(r.uniform(0.3, 0.95), 3),
            "overall_score": round(r.uniform(40.0, 95.0), 1) if has_overall else None,
            "disagreement": round(r.uniform(0.0, 1.0), 3),
        }
        self._state = {
            "gate_retry_count": r.randint(0, 3),
            "token_budget": budget,
            "tokens_used": round(r.uniform(0.0, budget), 1),
            "last_consistency": round(r.uniform(30.0, 100.0), 1),
            "disagreement": round(r.uniform(0.0, 1.0), 3),
        }
        self._mode_encoding = round(r.uniform(0.0, 1.0), 3)
        # 三信号真值（供本环境记账；与生产 review_signals 完全同源）
        self.s_h, self.s_c, self.s_k = review_signals(self._evidence, self._consensus)

    def _features(self) -> list:
        return review_state_features(
            evidence=self._evidence, critic=self._critic, consensus=self._consensus,
            state=self._state, mode_encoding=self._mode_encoding,
            round_ratio=(self.step_count + 1) / self.horizon,
        )

    def reset(self) -> list:
        self.step_count = 0
        self.skip_streak = 0
        self.reviews_done = 0
        self._sample_context()
        return self._features()

    def step(self, action: int) -> tuple[list, float, bool]:
        """action ∈ [0,4] → (features, reward, done)。

        奖励 = review_reward(gate_after = effective − uniform_baseline, ...)：
        gate 分支由生产同款 weighted_consistency_score 复算，故 balanced 恒得 0 增益，
        只有"按上下文选对信任对象"才会拿到正增益 —— 这正是 PPO 需要的可学梯度。
        """
        self.step_count += 1
        try:
            action = int(action)
        except (TypeError, ValueError):
            action = 3
        if not (0 <= action < 5):
            action = 3

        feats = self._features()
        eff_action = discipline_gate(action, feats, self.skip_streak,
                                     self._reviews_done_fixed)

        # ── 无效 skip 拦截（防"白嫖安全网"退化解）──
        # 本口径下纪律门恒禁止 skip（reviews_done=0）。若只做"重定向"，由于生产 _block_skip
        # 的兜底规则（f2 ≥ 0.6 → trust_honest，否则 balanced）本身恰是一个不错的启发式，
        # 策略会学会"恒输出 4"去免费获得该兜底 —— 那不是学到的策略，是白嫖安全网。
        # 故把"被纪律门拒绝的 skip"记为无效动作并给负奖励，迫使策略在 {0,1,2,3} 上真学映射。
        if action == 4 and eff_action != 4:
            self._sample_context()
            return self._features(), -1.0, self.step_count >= self.horizon

        # ── 生产同款真实质量复算 ──
        w = review_weight_schema(_weights_of(eff_action))
        effective, _applied = weighted_consistency_score(
            self._evidence, self._consensus, w)
        baseline, _ = weighted_consistency_score(
            self._evidence, self._consensus, dict(UNIFORM_WEIGHTS))
        delta = effective - baseline          # balanced ⇒ 0；skip 不可达

        if eff_action == 4:
            self.skip_streak += 1
        else:
            self.skip_streak = 0
        if eff_action != 4:
            self.reviews_done += 1

        reward = review_reward(
            gate_before=0.0, gate_after=delta, precision=True,
            tokens=ACTION_TOKENS.get(eff_action, 0.0), skip_streak=self.skip_streak,
        )

        # 单次决策语境：本步结束后换下一条独立上下文
        self._sample_context()
        return self._features(), reward, self.step_count >= self.horizon


def oracle_action(env: CalibratedReviewEnv) -> int:
    """当前上下文下的真实最优档位（诊断/对比用，非策略）。"""
    best_a, best_v = 3, float("-inf")
    for a in range(4):
        w = review_weight_schema(_weights_of(a))
        v = weighted_consistency_score(env._evidence, env._consensus, w)[0]
        if v > best_v:
            best_v, best_a = v, a
    return best_a
