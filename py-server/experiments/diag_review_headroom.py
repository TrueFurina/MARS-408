# ============================================================
# diag_review_headroom — 三元评审权重「真实可挖头寸 / 状态可观测性 / 可达成上限」诊断
#
# 背景：影子探针发现 3 个 PPO 种子在真实特征空间塌缩为恒定 balanced（no-op）。
# 本脚本回答：这是「没头寸」还是「环境奖励教错了」还是「状态不够」？
#
# 真实质量函数（agents/quality_gate.weighted_consistency_score）展开：
#     Δ_eff(action) = (c − 1/3)·(s_c − s_h) + (k − 1/3)·(s_k − s_h)
#   其中 (h,c,k) 为动作对应三元权重，s_h/s_c/s_k 为 honest/critic/consensus 三信号。
#   balanced（1/3,1/3,1/3）⇒ Δ_eff ≡ 0；skip ⇒ effective ≡ 100（口径陷阱）。
#
# 三段结论：
#   A. 头寸：oracle 相对 uniform / rule 的真实增益
#   B. 可观测性：12 维特征是否携带「最优动作」信息
#   C. 可达成上限：任何基于这 12 维特征的策略最多能拿多少（train/test 切分）
#
# 只读诊断：不修改任何生产代码。
# ============================================================

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_shadow_probe import generate_samples  # noqa: E402

from agents.quality_gate import review_signals, weighted_consistency_score  # noqa: E402
from engines.review_policy import (  # noqa: E402
    REVIEW_ACTIONS,
    REVIEW_MIN_REVIEW,
    SKIP_STREAK_LIMIT,
    _rule_action_idx,
    _weights_of,
    review_state_features,
    review_weight_schema,
)

FEAT_NAMES = ["f1 critic_confidence", "f2 evidence_consistency(=s_h/100)", "f3 evidence_coverage",
              "f4 consensus_status", "f5 gate_retry_count", "f6 disagreement_level",
              "f7 valid_critic_count", "f8 invalid_critic_count", "f9 quality_delta",
              "f10 cost_ratio", "f11 mode_encoding", "f12 round_ratio"]


def _eff(evidence, consensus, action_idx):
    w = review_weight_schema(_weights_of(action_idx))
    e, _applied = weighted_consistency_score(evidence, consensus, w)
    return e


def _block_skip(idx, feats, skip_streak, reviews_done):
    """与 review_policy.select_action 内 _block_skip 逐字一致的纪律门。

    生产版已修掉差一：判据是 `skip_streak >= SKIP_STREAK_LIMIT - 1`
    （原 `>= SKIP_STREAK_LIMIT` 会放过第 1 次连发）。此处必须同步。
    """
    if idx == 4 and (reviews_done < REVIEW_MIN_REVIEW
                     or skip_streak >= SKIP_STREAK_LIMIT - 1):
        return 0 if (feats and len(feats) > 1 and feats[1] >= 0.6) else 3
    return idx


def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 1e-12 or vy <= 1e-12:
        return float("nan")
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / math.sqrt(vx * vy)


def _mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def main():
    rng = random.Random(20260914)
    samples = generate_samples(240, rng)
    n = len(samples)

    feats_all, s_h_all, s_c_all, s_k_all = [], [], [], []
    eff = []            # eff[i][a] = 第 i 样本选动作 a 的真实有效分
    uni, rule_gated = [], []
    oracle_eff, oracle_act = [], []
    for s in samples:
        feats = review_state_features(
            evidence=s["evidence"], critic=s["critic"], consensus=s["consensus"],
            state=s["state"], mode_encoding=s["mode_encoding"], round_ratio=s["round_ratio"])
        feats_all.append(feats)
        s_h, s_c, s_k = review_signals(s["evidence"], s["consensus"])
        s_h_all.append(s_h); s_c_all.append(s_c); s_k_all.append(s_k)

        row = [_eff(s["evidence"], s["consensus"], a) for a in range(5)]
        eff.append(row)
        uni.append(row[3])

        r_idx = _rule_action_idx(feats)
        rule_gated.append(row[_block_skip(r_idx, feats, 0, 0)])

        best_a = max(range(4), key=lambda a: row[a])   # 纪律门下 skip 不可用
        oracle_act.append(best_a)
        oracle_eff.append(row[best_a])

    print("=" * 78)
    print("A. 真实空间可挖头寸（240 条真实形态样本 / 真实 weighted_consistency_score）")
    print("=" * 78)
    print(f"  uniform（现状，balanced）    mean effective = {_mean(uni):8.3f}")
    print(f"  rule（加纪律门，公平口径）    mean effective = {_mean(rule_gated):8.3f}  "
          f"(Δ vs uniform {_mean(rule_gated) - _mean(uni):+7.3f})")
    print(f"  ORACLE（纪律门下 0/1/2/3）   mean effective = {_mean(oracle_eff):8.3f}  "
          f"(Δ vs uniform {_mean(oracle_eff) - _mean(uni):+7.3f})")

    print("\n  各「恒定动作」的真实平均有效分（判断 balanced 是否已是最优常量）：")
    for a in range(5):
        print(f"    action={a} {REVIEW_ACTIONS[a]:<16s} mean = {_mean([eff[i][a] for i in range(n)]):8.3f}")

    print(f"\n  oracle 动作分布 = "
          f"{ {REVIEW_ACTIONS[a]: oracle_act.count(a) for a in range(4)} }")
    print(f"  → balanced 被选为最优的次数 = {oracle_act.count(3)} / {n}"
          f"（{100.0 * oracle_act.count(3) / n:.1f}%）")

    print("\n  纪律门公平性核查（探针口径 reviews_done=0, skip_streak=0）：")
    r_free = [_eff(samples[i]["evidence"], samples[i]["consensus"],
                   _rule_action_idx(feats_all[i])) for i in range(n)]
    skip_free = sum(1 for i in range(n) if _rule_action_idx(feats_all[i]) == 4)
    print(f"    不加纪律门：rule mean = {_mean(r_free):.3f}（skip 率 {100.0 * skip_free / n:.1f}%"
          f"，skip ⇒ effective≡100 ⇒ 口径虚高）")
    print(f"    加纪律门  ：rule mean = {_mean(rule_gated):.3f}（skip 率 0.0%）")
    print(f"    ⚠️ skip 动作 effective ≡ 100 ⇒ 任何「放开 skip」的对比都是口径陷阱，必须锁纪律门。")

    print("\n" + "=" * 78)
    print("B. 状态可观测性：12 维特征与最优动作驱动量的相关")
    print("=" * 78)
    d_c = [s_c_all[i] - s_h_all[i] for i in range(n)]
    d_k = [s_k_all[i] - s_h_all[i] for i in range(n)]
    print(f"    {'特征':<34s} {'corr(·,s_c−s_h)':>16s} {'corr(·,s_k−s_h)':>16s}")
    for j, nm in enumerate(FEAT_NAMES):
        col = [feats_all[i][j] for i in range(n)]
        print(f"    {nm:<34s} {_pearson(col, d_c):16.3f} {_pearson(col, d_k):16.3f}")
    print("    注：f1 名义为 critic_confidence，但真实 s_c 取自 consensus.confidence_score，"
          "二者不同字段 → f1 相关≈0。")

    print("\n" + "=" * 78)
    print("C. 可达成上限：任何「仅基于 12 维特征」的策略最多能拿多少")
    print("=" * 78)
    half = n // 2
    tr, te = list(range(half)), list(range(half, n))
    uni_te = _mean([uni[i] for i in te])
    oracle_te = _mean([oracle_eff[i] for i in te])

    # 策略类：单特征阈值分裂 → 左右各选一个动作（深度 1，等价一个小网络能表达的最简上下文策略）
    best = (uni_te, None, None, 3, 3)
    for j in range(12):
        col = sorted({feats_all[i][j] for i in tr})
        for t in col:
            left = [i for i in tr if feats_all[i][j] <= t]
            right = [i for i in tr if feats_all[i][j] > t]
            if len(left) < 8 or len(right) < 8:
                continue
            a_l = max(range(4), key=lambda a: _mean([eff[i][a] for i in left]))
            a_r = max(range(4), key=lambda a: _mean([eff[i][a] for i in right]))
            score = _mean([eff[i][a_l] if feats_all[i][j] <= t else eff[i][a_r] for i in te])
            if score > best[0]:
                best = (score, j, t, a_l, a_r)

    print(f"  uniform（现状）              test mean = {uni_te:8.3f}")
    print(f"  最佳单特征阈值策略（train→test） test mean = {best[0]:8.3f}  "
          f"(Δ vs uniform {best[0] - uni_te:+7.3f})")
    if best[1] is not None:
        print(f"    最优切分: {FEAT_NAMES[best[1]]} thr={best[2]:.4f} → "
              f"≤取{REVIEW_ACTIONS[best[3]]} / >取{REVIEW_ACTIONS[best[4]]}")
    print(f"  rule（加纪律门，test 集）     test mean = {_mean([rule_gated[i] for i in te]):8.3f}")
    print(f"  ORACLE（完全信息上界）        test mean = {oracle_te:8.3f}")

    capture = (best[0] - uni_te) / (oracle_te - uni_te) if oracle_te > uni_te else float("nan")
    print(f"\n  ⇒ 单特征策略可捕获头寸的 {100.0 * capture:.1f}%"
          f"（{best[0] - uni_te:+.3f} / {oracle_te - uni_te:+.3f}）")


if __name__ == "__main__":
    main()
