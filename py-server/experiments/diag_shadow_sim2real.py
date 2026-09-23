# ============================================================
# diag_shadow_sim2real — 影子探针 sim-to-real 崩塌的根因判定（只读诊断，不改任何引擎）
#
# 背景（真实数据，非推测）：
#   影子探针 240 样本上的真实有效分（修复后代码，run 20260914_161556 / 161821）：
#     uniform 66.809 / rule 68.948 / heuristic_f2 69.807 / shadow(RL) 68.445~68.487
#   ⇒ 模拟环境（3-seed 合成阶梯）里 RL 胜规则；真实特征空间里 RL 反而**输给规则**。
#
# 本脚本要判定的问题：这是【欠训练】还是【奖励/状态设计缺陷】？
# 判据（与角色B 处理鲶鱼侧同一方法学：解析最优 vs 约束，而非盲目加训练量）：
#   逐个样本、逐个动作 a ∈ {0,1,2,3} 同时算两个量：
#     - eff(a)  ：真实质量分（探针口径 weighted_consistency_score，0-100）
#     - rew(a)  ：训练奖励（review_reward，PPO 实际优化的目标）
#   然后看：
#     Q1 奖励 argmax 与质量 argmax 的一致率 —— 若显著 <100%，奖励与验收口径错位（真缺陷）
#     Q2 规则动作 a_rule 有多大比例本身就是质量最优 —— 规则的空间还有多少
#     Q3 单特征阈值策略能吃到多少头寸 —— 最优策略是否被 1 维阈值可达（可学性）
#     Q4 oracle(按质量) vs oracle(按奖励) 的真实分差 —— 错位造成的真实质量损失
#
# 输出 JSON 落盘，所有数字均真实复算。
# ============================================================

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.quality_gate import review_signals, weighted_consistency_score  # noqa: E402
from engines.review_policy import (  # noqa: E402
    ACTION_TOKENS,
    REVIEW_ACTIONS,
    _rule_action_idx,
    _weights_of,
    review_reward,
    review_state_features,
    review_weight_schema,
)
from engines.review_env_calibrated import discipline_gate  # noqa: E402
from run_shadow_probe import generate_samples  # noqa: E402

import random  # noqa: E402


def _eff(evidence, consensus, action):
    w = review_weight_schema(_weights_of(action))
    return weighted_consistency_score(evidence, consensus, w)[0]


def _rew(evidence, consensus, action, baseline):
    """训练奖励（CalibratedReviewEnv 同口径：gate_after = eff − uniform）。"""
    delta = _eff(evidence, consensus, action) - baseline
    return review_reward(gate_before=0.0, gate_after=delta, precision=True,
                         tokens=ACTION_TOKENS.get(action, 0.0), skip_streak=0)


def main():
    n = 240
    data_seed = 20260914
    rng = random.Random(data_seed)
    samples = generate_samples(n, rng)

    # 候选动作：{0,1,2,3}。skip(4) 不入候选 —— 其 effective 恒 ≡100 属口径陷阱
    # （生产纪律门 reviews_done=0 时恒禁止 skip），与 CalibratedReviewEnv 口径一致。
    ACTIONS = [0, 1, 2, 3]

    rows = []
    for s in samples:
        ev, cs, st = s["evidence"], s["consensus"], s["state"]
        feats = review_state_features(
            evidence=ev, critic=s["critic"], consensus=cs, state=st,
            mode_encoding=s["mode_encoding"], round_ratio=s["round_ratio"])
        s_h, s_c, s_k = review_signals(ev, cs)
        baseline = _eff(ev, cs, 3)   # balanced ≡ uniform（等价，0 增益）

        eff = {a: _eff(ev, cs, a) for a in ACTIONS}
        rew = {a: _rew(ev, cs, a, baseline) for a in ACTIONS}

        a_eff = max(ACTIONS, key=lambda a: eff[a])
        a_rew = max(ACTIONS, key=lambda a: rew[a])
        # 与影子探针口径完全一致：规则动作先过纪律门（探针 rule 臂即如此）
        raw_rule = _rule_action_idx(feats)
        a_rule = discipline_gate(raw_rule, feats, 0, 0)
        if a_rule not in eff:            # 兜底：理论上纪律门已把 4 重定向走
            a_rule = 3

        rows.append({
            "id": s["id"], "features": feats, "signals": [s_h, s_c, s_k],
            "baseline": baseline, "eff": eff, "rew": rew,
            "a_eff": a_eff, "a_rew": a_rew, "a_rule": a_rule,
            "raw_rule": raw_rule,
            "rule_eff": eff[a_rule],
            "uniform_eff": baseline,
            "oracle_eff": eff[a_eff],
            "oracle_rew_eff": eff[a_rew],
        })

    # ── Q1：奖励 argmax 与质量 argmax 的一致率 ──
    agree = sum(1 for r in rows if r["a_eff"] == r["a_rew"])
    # 奖励 argmax 若与质量 argmax 不同，则它是最优值的多少（并列视为一致）
    def _ties_ok(r):
        return abs(r["eff"][r["a_rew"]] - r["oracle_eff"]) < 1e-9
    agree_tie = sum(1 for r in rows if _ties_ok(r))

    # ── Q2：规则动作本身是质量最优的比例 ──
    rule_is_opt = sum(1 for r in rows if _ties_ok({"eff": r["eff"], "a_rew": r["a_rule"],
                                                    "oracle_eff": r["oracle_eff"]}))

    # ── Q3：单特征阈值策略的可达头寸（对 features[1] 与 features[0] 各扫一遍）──
    def best_threshold(idx, act_hi, act_lo):
        """f[idx] > t → act_hi else act_lo；网格搜 t 最大化平均有效分。"""
        vals = sorted({r["features"][idx] for r in rows})
        cands = [v - 1e-9 for v in vals] + [vals[-1] + 1e-9]
        best = (-1e9, None)
        for t in cands:
            tot = sum(r["eff"][act_hi if r["features"][idx] > t else act_lo] for r in rows)
            m = tot / len(rows)
            if m > best[0]:
                best = (m, t)
        return best

    thr_f1_02 = best_threshold(1, 0, 2)     # 高 → trust_honest，低 → trust_consensus
    thr_f1_03 = best_threshold(1, 0, 3)     # 高 → trust_honest，低 → balanced

    # 4 个二值阈值策略（f1 高/低 × f0 高/低）——2 特征决策树可达性
    def best_two_feat_tree():
        idx0 = sorted({r["features"][0] for r in rows})
        idx1 = sorted({r["features"][1] for r in rows})
        cand0 = [v - 1e-9 for v in idx0] + [idx0[-1] + 1e-9]
        cand1 = [v - 1e-9 for v in idx1] + [idx1[-1] + 1e-9]
        best = (-1e9, None)
        # 组合：f1 高 → a1，否则看 f0 → a2 / a3
        for t1 in cand1[:: max(1, len(cand1) // 40)]:
            for t0 in cand0[:: max(1, len(cand0) // 40)]:
                tot = 0.0
                for r in rows:
                    if r["features"][1] > t1:
                        a = 0
                    elif r["features"][0] > t0:
                        a = 1
                    else:
                        a = 2
                    tot += r["eff"][a]
                m = tot / len(rows)
                if m > best[0]:
                    best = (m, (round(t1, 4), round(t0, 4)))
        return best

    tree = best_two_feat_tree()

    unif = sum(r["uniform_eff"] for r in rows) / n
    rule = sum(r["rule_eff"] for r in rows) / n
    oracle = sum(r["oracle_eff"] for r in rows) / n
    oracle_rew = sum(r["oracle_rew_eff"] for r in rows) / n
    best_fixed = {a: sum(r["eff"][a] for r in rows) / n for a in ACTIONS}

    out = {
        "meta": {
            "source": "diag_shadow_sim2real.py (read-only diagnostic)",
            "n_samples": n, "data_seed": data_seed,
            "note": "eff=探针口径真实质量分(0-100)；rew=训练奖励(review_reward)；"
                    "两者 argmax 若不一致即奖励与验收口径错位",
        },
        "arm_means_eff": {
            "uniform": round(unif, 3),
            "rule": round(rule, 3),
            "oracle_by_quality": round(oracle, 3),
            "oracle_by_reward": round(oracle_rew, 3),
            **{f"fixed_{REVIEW_ACTIONS[a]}": round(best_fixed[a], 3) for a in ACTIONS},
        },
        "headroom": {
            "total_vs_uniform": round(oracle - unif, 3),
            "rule_capture_pct": round(100.0 * (rule - unif) / (oracle - unif), 1),
            "reward_oracle_capture_pct": round(100.0 * (oracle_rew - unif) / (oracle - unif), 1),
        },
        "Q1_reward_vs_quality_argmax": {
            "exact_agree_pct": round(100.0 * agree / n, 1),
            "tie_inclusive_agree_pct": round(100.0 * agree_tie / n, 1),
            "reward_oracle_quality_loss": round(oracle - oracle_rew, 4),
        },
        "Q2_rule_is_quality_optimal_pct": round(100.0 * rule_is_opt / n, 1),
        "Q3_reachable_by_threshold": {
            "f2_high_to_trust_honest_else_consensus": {
                "mean_eff": round(thr_f1_02[0], 3), "threshold": round(thr_f1_02[1], 4)},
            "f2_high_to_trust_honest_else_balanced": {
                "mean_eff": round(thr_f1_03[0], 3), "threshold": round(thr_f1_03[1], 4)},
            "two_feature_tree": {"mean_eff": round(tree[0], 3), "thresholds": tree[1]},
        },
        "Q4_quality_argmax_dist": {
            f"{REVIEW_ACTIONS[a]}": sum(1 for r in rows if r["a_eff"] == a) for a in ACTIONS},
        "Q4_reward_argmax_dist": {
            f"{REVIEW_ACTIONS[a]}": sum(1 for r in rows if r["a_rew"] == a) for a in ACTIONS},
    }

    outp = Path(__file__).resolve().parent / "results" / "diag_shadow_sim2real.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n[diag] -> {outp}")


if __name__ == "__main__":
    main()
