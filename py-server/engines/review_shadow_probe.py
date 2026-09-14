# ============================================================
# review_shadow_probe — 三元评审权重 MAPPO 影子探针（角色 C · 观测效果，不干预决策）
#
# 设计目标（用户："我就看效果"）：
#   在真实评审上下文分布上，旁路运行一个【真训过 PPO】的 MAPPO 权重策略，
#   用真实的 quality_gate 质量判定函数复算"若采用该权重"的有效一致性分，
#   与当前各基线（uniform=现状 / rule=规则 / mappo_current=线上共享策略仅预热）
#   做逐样本对比，量化 MAPPO 在真实特征空间里的质量与纪律效果。
#
# 不变式（fail-open 不被破坏）：
#   - observe() 只读不写：绝不修改任何传入的 evidence/consensus/state/critic；
#   - 绝不替换真实决策返回值——真实链路仍以 baseline 决策为准；
#   - shadow 仅作为"对照观测"存在，不参与任何真实判定。
#
# 诚信约束：本模块不生成任何对外数字，所有效果数字来自真实复算函数落盘 JSON。
# ============================================================

from collections import Counter
from typing import Optional, Sequence

from engines.review_policy import (
    REVIEW_ACTIONS,
    UNIFORM_WEIGHTS,
    _rule_action_idx,
    _weights_of,
    decide_review_weight,
    review_state_features,
    review_weight_schema,
)
from agents.quality_gate import weighted_consistency_score, review_signals


def build_shadow_policy(seed: int, warmup_steps: int = 300, ppo_episodes: int = 60,
                        horizon: int = 6):
    """构造一个真训过 PPO 的影子策略（与 3-seed 实验同构，确定性播种）。

    返回 ReviewWeightPolicy 实例；torch 不可用则返回未训练实例（observe 时退化为规则等价）。
    仅在构造期做确定性设置，避免污染主流程 RNG 状态。
    """
    from engines.review_policy import ReviewEnv, ReviewWeightPolicy
    try:
        import torch
        torch.set_num_threads(1)
        try:
            torch.use_deterministic_algorithms(True)
        except Exception:
            pass
    except Exception:
        pass
    p = ReviewWeightPolicy(seed=seed)
    if not p.torch_available:
        return p
    p.warmup_with_rules(ReviewEnv(seed=seed), steps=warmup_steps, seed=seed)
    p.train_ppo(ReviewEnv(seed=seed, horizon=horizon), episodes=ppo_episodes,
                horizon=horizon, seed=seed)
    return p


def _bl_mappo(feats, skip_streak=0, reviews_done=0):
    return decide_review_weight(feats, use_mappo=True,
                                skip_streak=skip_streak, reviews_done=reviews_done)


def observe(evidence, consensus, state, shadow_policies, critic=None,
            skip_streak: int = 0, reviews_done: int = 0,
            mode_encoding: float = 0.5, round_ratio: float = 0.5) -> dict:
    """旁路观测一条真实评审样本的 MAPPO 影子效果。

    返回 dict 记录；绝不修改 evidence/consensus/state/critic，绝不干预真实决策。

    效果量化口径：用真实的 weighted_consistency_score 复算"若采用该权重"的有效一致性分，
    delta = 影子有效分 − 基线有效分，即相对现状（uniform）的真实质量偏移。
    """
    feats = review_state_features(
        evidence=evidence, critic=critic or {}, consensus=consensus, state=state,
        mode_encoding=mode_encoding, round_ratio=round_ratio)

    # ── baseline 复算（真实质量函数）──
    uni_w = dict(UNIFORM_WEIGHTS)
    uni_eff, uni_applied = weighted_consistency_score(evidence, consensus, uni_w)

    rule_idx = _rule_action_idx(feats)
    rule_w = review_weight_schema(_weights_of(rule_idx))
    rule_eff, rule_applied = weighted_consistency_score(evidence, consensus, rule_w)

    mappo_out = _bl_mappo(feats, skip_streak=skip_streak, reviews_done=reviews_done)
    mappo_w = mappo_out.get("weights") or dict(UNIFORM_WEIGHTS)
    mappo_eff, mappo_applied = weighted_consistency_score(evidence, consensus, mappo_w)

    # ── 影子 RL：多 seed 取有效分均值 + 动作众数 ──
    shadow_effs, shadow_actions = [], []
    for p in (shadow_policies or []):
        idx, _src = p.select_action(
            feats, deterministic=True, skip_streak=skip_streak, reviews_done=reviews_done)
        shadow_actions.append(idx)
        sw = review_weight_schema(_weights_of(idx))
        se, _applied = weighted_consistency_score(evidence, consensus, sw)
        shadow_effs.append(se)

    if shadow_effs:
        shadow_eff = sum(shadow_effs) / len(shadow_effs)
        shadow_action = Counter(shadow_actions).most_common(1)[0][0]
    else:
        # 无影子策略 → 退化为均匀等价，便于结构统一（实际驱动脚本必传策略）
        shadow_eff = uni_eff
        shadow_action = 3
    shadow_w = review_weight_schema(_weights_of(shadow_action))

    s_h, s_c, s_k = review_signals(evidence, consensus)

    return {
        "features": [round(x, 4) for x in feats],
        "signals": {"honest": round(s_h, 2), "critic": round(s_c, 2), "consensus": round(s_k, 2)},
        "baseline": {
            "uniform": {"weights": uni_w, "effective": uni_eff, "applied": uni_applied},
            "rule": {"weights": rule_w, "effective": rule_eff, "applied": rule_applied,
                     "action": rule_idx, "action_name": REVIEW_ACTIONS[rule_idx]},
            "mappo_current": {"weights": mappo_w, "effective": mappo_eff,
                              "applied": mappo_applied, "source": mappo_out.get("source")},
        },
        "shadow": {
            "weights": shadow_w, "effective": round(shadow_eff, 3),
            "action": shadow_action, "action_name": REVIEW_ACTIONS[shadow_action],
            "per_seed_effective": [round(e, 3) for e in shadow_effs],
            "per_seed_actions": shadow_actions,
            "n_seeds": len(shadow_effs),
        },
        "delta": {
            "shadow_vs_uniform_effective": round(shadow_eff - uni_eff, 3),
            "shadow_vs_rule_effective": round(shadow_eff - rule_eff, 3),
            "shadow_vs_mappo_effective": round(shadow_eff - mappo_eff, 3),
            "action_differs_from_uniform": shadow_action != 3,
            "action_differs_from_rule": shadow_action != rule_idx,
            "action_differs_from_mappo": shadow_action != mappo_out.get("action", 3),
        },
    }


def summarize(records: Sequence[dict]) -> dict:
    """聚合一批观测记录为效果快照。全部结果来自真实复算，无编造。"""
    n = len(records)
    if n == 0:
        return {"n": 0}

    def _mean(xs):
        return sum(xs) / len(xs) if xs else float("nan")

    def _std(xs):
        if len(xs) < 2:
            return 0.0
        m = _mean(xs)
        return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5

    du = [r["delta"]["shadow_vs_uniform_effective"] for r in records]
    dr = [r["delta"]["shadow_vs_rule_effective"] for r in records]
    dm = [r["delta"]["shadow_vs_mappo_effective"] for r in records]

    shadow_actions = [r["shadow"]["action"] for r in records]
    rule_actions = [r["baseline"]["rule"]["action"] for r in records]
    mappo_actions = [r["baseline"]["mappo_current"].get("action", 3) for r in records]

    # 多 seed 一致性（影子同一动作的判别式：各 seed 有效分方差均值）
    seed_vars = []
    for r in records:
        ps = r["shadow"]["per_seed_effective"]
        if len(ps) >= 2:
            seed_vars.append(_std(ps) ** 2)
    seed_std = _mean([v ** 0.5 for v in seed_vars]) if seed_vars else 0.0

    return {
        "n": n,
        "shadow_action_dist": dict(Counter(shadow_actions)),
        "rule_action_dist": dict(Counter(rule_actions)),
        "mappo_action_dist": dict(Counter(mappo_actions)),
        "delta_vs_uniform": {"mean": round(_mean(du), 3), "std": round(_std(du), 3),
                              "pct_improve": round(100.0 * sum(1 for x in du if x > 0) / n, 1)},
        "delta_vs_rule": {"mean": round(_mean(dr), 3), "std": round(_std(dr), 3),
                           "pct_improve": round(100.0 * sum(1 for x in dr if x > 0) / n, 1)},
        "delta_vs_mappo": {"mean": round(_mean(dm), 3), "std": round(_std(dm), 3),
                            "pct_improve": round(100.0 * sum(1 for x in dm if x > 0) / n, 1)},
        "shadow_skip_rate": round(100.0 * sum(1 for a in shadow_actions if a == 4) / n, 1),
        "shadow_differs_from_uniform_rate": round(
            100.0 * sum(1 for r in records if r["delta"]["action_differs_from_uniform"]) / n, 1),
        "shadow_differs_from_rule_rate": round(
            100.0 * sum(1 for r in records if r["delta"]["action_differs_from_rule"]) / n, 1),
        "shadow_seed_std": round(seed_std, 3),
    }
