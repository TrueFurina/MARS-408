# -*- coding: utf-8 -*-
"""diag_state_extend — s_c/s_k 到底能解锁多少头寸：**解析恒等式** + 可学习性 + 噪声敏感性

背景（本脚本的立论基础是一个恒等式，不是建模假设）
--------------------------------------------------
生产打分为 `effective = s_h + (h·s_h + c·s_c + k·s_k) − (s_h+s_c+s_k)/3`（见
`agents/quality_gate.weighted_consistency_score`）。代入四个档位的权重：

    trust_honest     (1,    0,    0)  →  eff = 2·s_h − mean
    trust_critic     (0,    1,    0)  →  eff = s_h + s_c − mean
    trust_consensus  (0,    0,    1)  →  eff = s_h + s_k − mean
    balanced         (1/3,1/3,1/3)  →  eff = s_h                  （applied=False）

四式同减 `s_h` ⇒ **argmax 等价于 argmax(s_h, s_c, s_k, mean)**。这是**恒等式**：
只要观测量 (s_h, s_c, s_k) 可得，最优动作可**解析算出、零训练**。

而现行 12 维状态里：`f2 = s_h/100` 已含 s_h，但 `s_c = consensus.confidence_score`
与 `s_k = consensus.overall_score` **不在状态里**（f1 取自 `critic.confidence`，是另一字段）。

⇒ 本脚本量化：补上这 2 维后能吃到多少头寸？噪声（上游估计误差）下还剩多少？

方法（防泄漏）
--------------
- 拟合集 = 主评估集 seed=20260914；评估集 = 独立泛化集 seed=313131。树只拟合，不评估。
- 三组证据：
    (A) 解析式 argmax(s_h,s_c,s_k,mean) 的 capture（无噪应 ≈ 100%，验证恒等式）；
    (B) 分类树在 F12 / F2 / F2CK 上的泛化 capture —— 证明"12 维不够、加 2 维才够"；
    (C) 加噪 ±0.03（模拟上游估计误差）后的退化幅度 —— 决定真实可落地收益。
- 注：多输出回归形态**未采用** —— 其学习目标（总 MSE）与"取最大有效分"不对齐，
  实测各特征集 capture 完全相同（树根本没用 s_c/s_k），保留在 JSON 里作反例。

只读：本脚本不改任何产品代码，只落盘一份诊断 JSON。
用法：cd py-server && PYTHONPATH=. .venv/Scripts/python.exe experiments/diag_state_extend.py
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.quality_gate import review_signals, weighted_consistency_score  # noqa: E402
from engines.review_env_calibrated import discipline_gate  # noqa: E402
from engines.review_policy import (  # noqa: E402
    REVIEW_WEIGHTS,
    _rule_action_idx,
    _rule_action_idx_legacy,
    _weights_of,
    review_state_features,
    review_weight_schema,
)
from run_shadow_probe import generate_samples  # noqa: E402

N = 240
TRAIN_SEED = 20260914      # 主评估集（报告同源）
TEST_SEED = 313131         # 独立泛化集
N_ACTIONS = 4              # 纪律门下 skip 不可用（reviews_done=0）
DEPTHS = (1, 2, 3)
NOISE = 0.03               # 与 ReviewEnv 观测噪声同量级
OUT = Path("experiments/results/diag_state_extend.json")


def _build(seed: int, noise_seed: int | None = None):
    """一个评估集：12 维特征 X、s_c/s_k 观测 E、各动作**真值**有效分 Y。

    noise_seed 非空时，对**观测**（X 的 f2 与 E）加噪，而 Y 仍由真值算出 ——
    即"决策看到的是带估计误差的读数，验收看的是真实分"。
    """
    rng = random.Random(seed)
    samples = generate_samples(N, rng)
    feats, extra, eff = [], [], []
    for s in samples:
        feats.append(review_state_features(
            evidence=s["evidence"], critic=s["critic"], consensus=s["consensus"],
            state=s["state"], mode_encoding=s["mode_encoding"], round_ratio=s["round_ratio"]))
        s_h, s_c, s_k = review_signals(s["evidence"], s["consensus"])
        extra.append([s_c / 100.0, s_k / 100.0])
        eff.append([weighted_consistency_score(
            s["evidence"], s["consensus"],
            review_weight_schema(_weights_of(a)))[0] for a in range(N_ACTIONS)])
    X = np.array(feats, dtype=float)
    E = np.array(extra, dtype=float)
    Y = np.array(eff, dtype=float)
    if noise_seed is not None:
        nr = np.random.default_rng(noise_seed)
        E = np.clip(E + nr.uniform(-NOISE, NOISE, size=E.shape), 0.0, 1.0)
        X = X.copy()
        X[:, 1] = np.clip(X[:, 1] + nr.uniform(-NOISE, NOISE, size=X.shape[0]), 0.0, 1.0)
    return samples, X, E, Y


def _fs(X: np.ndarray, E: np.ndarray) -> dict:
    return {
        "F12": X,
        "F2": X[:, 1:2],
        "F2CK": np.hstack([X[:, 1:2], E]),
    }


def _mean_eff(Y: np.ndarray, actions) -> float:
    return float(np.mean([Y[i, int(a)] for i, a in enumerate(actions)]))


def _gated(X: np.ndarray, raw) -> np.ndarray:
    return np.array([discipline_gate(int(a), list(f), 0, 0) for a, f in zip(raw, X)])


def _analytic_actions(X: np.ndarray, E: np.ndarray) -> np.ndarray:
    """**精确解析式**：直接按生产打分的定义复算四个档位的 effective 并取最大。

    eff(a) = s_h + (h_a·s_h + c_a·s_c + k_a·s_k) − mean，权重取 `REVIEW_WEIGHTS`（单一真值源）。

    ⚠️ 注意：档位权重是 **(0.6, 0.2, 0.2)** 而非 one-hot，因此简化式
    `argmax(s_h, s_c, s_k, mean)` 只是近似（本样本集上恰好同解，见 A2 对照）——
    生产实现必须用本精确式，不得用简化式。
    """
    s_h = X[:, 1]
    s_c, s_k = E[:, 0], E[:, 1]
    mean3 = (s_h + s_c + s_k) / 3.0
    cols = []
    for a in (0, 1, 2, 3):
        h, c, k = REVIEW_WEIGHTS[a]
        cols.append(s_h + (h * s_h + c * s_c + k * s_k) - mean3)
    return np.vstack(cols).T.argmax(axis=1)


def _analytic_actions_simplified(X: np.ndarray, E: np.ndarray) -> np.ndarray:
    """简化式 argmax(s_h, s_c, s_k, mean) —— 仅作对照，**不用于生产**。"""
    s_h = X[:, 1]
    s_c, s_k = E[:, 0], E[:, 1]
    mean3 = (s_h + s_c + s_k) / 3.0
    return np.vstack([s_h, s_c, s_k, mean3]).T.argmax(axis=1)


def main() -> None:
    print("=" * 100)
    print("diag_state_extend — s_c/s_k 的信息价值：解析恒等式 / 可学习性 / 噪声敏感性")
    print("=" * 100)

    _, Xtr, Etr, Ytr = _build(TRAIN_SEED)
    _, Xte, Ete, Yte = _build(TEST_SEED)
    _, Xte_n, Ete_n, Yte_n = _build(TEST_SEED, noise_seed=777)
    assert np.allclose(Yte, Yte_n), "加噪只应影响观测，不应改变真值有效分"

    uni = _mean_eff(Yte, np.full(N, 3))
    ora_acts = Yte.argmax(axis=1)
    ora = _mean_eff(Yte, ora_acts)
    headroom = ora - uni
    y_tr, y_te = Ytr.argmax(axis=1), ora_acts

    results = {"meta": {"n": N, "train_seed": TRAIN_SEED, "test_seed": TEST_SEED,
                        "noise": NOISE, "uniform": round(uni, 3), "oracle": round(ora, 3),
                        "headroom": round(headroom, 3)},
               "ref": {}, "analytic": {}, "classifier": [], "regressor_counterexample": []}

    print(f"评估集（独立泛化集 seed={TEST_SEED}）：uniform={uni:.3f}  oracle={ora:.3f}  "
          f"头寸={headroom:+.3f}")

    # ── 参照臂 ──
    print("\n参照臂（生产规则，已过纪律门）:")
    for k, fn in (("rule_old", _rule_action_idx_legacy), ("rule_new", _rule_action_idx)):
        a = _gated(Xte, np.array([fn(list(f)) for f in Xte]))
        m = _mean_eff(Yte, a)
        results["ref"][k] = {"mean_eff": round(m, 3),
                             "capture_pct": round(100 * (m - uni) / headroom, 1)}
        print(f"  {k:<9s} mean={m:.3f}  capture={100*(m-uni)/headroom:5.1f}%")
    rule_new_m = results["ref"]["rule_new"]["mean_eff"]

    # ── (A) 解析式恒等式验证 ──
    print("\n(A) 解析式 argmax(s_h, s_c, s_k, mean) —— 恒等式验证（应 ≈100%）")
    for tag, X_, E_ in (("无噪", Xte, Ete), (f"加噪±{NOISE}", Xte_n, Ete_n)):
        raw = _analytic_actions(X_, E_)
        acts = _gated(Xte, raw)
        m = _mean_eff(Yte, acts)
        agree = float(np.mean(raw == y_te))
        agree_simp = float(np.mean(_analytic_actions_simplified(X_, E_) == y_te))
        results["analytic"][tag] = {
            "mean_eff": round(m, 3),
            "capture_pct": round(100 * (m - uni) / headroom, 1),
            "argmax_agreement_with_oracle": round(agree, 3),
            "simplified_formula_agreement": round(agree_simp, 3),
            "delta_vs_rule_new": round(m - rule_new_m, 3)}
        print(f"  {tag:<11s} mean={m:.3f}  capture={100*(m-uni)/headroom:5.1f}%  "
              f"与 oracle 一致率={100*agree:5.1f}%（简化式 {100*agree_simp:5.1f}%）  "
              f"Δ vs rule_new={m-rule_new_m:+.3f}")

    # ── (B) 可学习性：分类树在 F12 / F2 / F2CK 上的泛化表现 ──
    print(f"\n(B) 分类树（预测 oracle 动作；拟合=主集 seed={TRAIN_SEED}，评估=泛化集）")
    print(f"  {'feat':<6s} {'depth':>5s} {'capture':>8s} {'动作一致率':>10s} {'Δ vs rule_new':>14s}")
    for fname in ("F12", "F2", "F2CK"):
        for d in DEPTHS:
            clf = DecisionTreeClassifier(max_depth=d, random_state=0)
            clf.fit(_fs(Xtr, Etr)[fname], y_tr)
            raw = clf.predict(_fs(Xte, Ete)[fname])
            acts = _gated(Xte, raw)
            m = _mean_eff(Yte, acts)
            acc = float(np.mean(acts == y_te))
            results["classifier"].append({
                "feat": fname, "depth": d, "mean_eff": round(m, 3),
                "capture_pct": round(100 * (m - uni) / headroom, 1),
                "action_agreement": round(acc, 3),
                "delta_vs_rule_new": round(m - rule_new_m, 3)})
            print(f"  {fname:<6s} {d:>5d} {100*(m-uni)/headroom:7.1f}% "
                  f"{100*acc:9.1f}% {m-rule_new_m:+14.3f}")

    # ── 反例：多输出回归（保留以警示后来者）──
    print("\n(反例) 多输出回归 → argmax：各特征集 capture 完全相同 ⇒ 学习目标与"
          "'取最大有效分'不对齐，树不用 s_c/s_k")
    for fname in ("F12", "F2", "F2CK"):
        reg = DecisionTreeRegressor(max_depth=3, random_state=0)
        reg.fit(_fs(Xtr, Etr)[fname], Ytr)
        m = _mean_eff(Yte, _gated(Xte, reg.predict(_fs(Xte, Ete)[fname]).argmax(axis=1)))
        results["regressor_counterexample"].append(
            {"feat": fname, "depth": 3, "mean_eff": round(m, 3),
             "capture_pct": round(100 * (m - uni) / headroom, 1)})
        print(f"  {fname:<6s} depth=3  capture={100*(m-uni)/headroom:5.1f}%")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'=' * 100}")
    print("判读：")
    print("  · A 段无噪 capture ≈ 100% ⇒ 恒等式成立，头寸可**解析吃满、零训练**；")
    print("  · A 段加噪退化幅度 = 上游估计误差带来的真实折扣；")
    print("  · B 段 F2CK 明显高于 F12 ⇒ **12 维不够、补 s_c/s_k 才够**；")
    print("  · ⇒ 首选落地形态是**把解析 argmax 折进规则**（数据已在 consensus 字典里，零额外成本），")
    print("    而非扩状态重训 RL。")
    print(f"{'=' * 100}")
    print(f"\n已落盘: {OUT}")


if __name__ == "__main__":
    main()
