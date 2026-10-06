# -*- coding: utf-8 -*-
"""diag_budget_curve — 训练预算-效果曲线（判断"再加预算是否还涨"）

背景
----
`tune_shadow_budget.py` 已测出：校准环境 3000 → 10000 episodes 时，
主评估集捕获率 49.7% → 58.4%，且低 f2 区"躺平率"40.5% → 0.8%。
本节要回答的是**是否仍在上升**（决定"继续加预算"是否是有效建议），
还是已触到信息天花板（此时唯一出路是扩状态，把 s_c/s_k 纳入观测）。

方法
----
固定 1 个种子（seed=7，确定性播种、无早停），在 episodes ∈ {10000, 20000, 40000}
上训练，用**两组独立真实上下文**（主评估集 20260914 / 泛化集 313131）评估：

  捕获率 capture = (策略 − uniform) / (oracle − uniform)
  参照线：rule / heuristic_f2 在同一集合上的捕获率

判读
----
  - 若 capture 随预算单调上升且未收敛 → "继续加预算"有效，应给训练预算下限建议。
  - 若进入平台期 → 已触信息天花板，收益必须靠扩状态（s_c/s_k）而非算力。
  - 只跑 1 个种子，故**结论只能是趋势性的**；若要写入验收数字须补 3 种子。
只读：不修改产品代码。
用法：cd py-server && PYTHONPATH=. .venv/Scripts/python.exe experiments/diag_budget_curve.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engines.review_env_calibrated import CalibratedReviewEnv  # noqa: E402
from engines.review_shadow_probe import build_shadow_policy  # noqa: E402
from tune_shadow_budget import (  # noqa: E402
    GEN_SEED,
    MAIN_SEED,
    OUT,
    _baselines,
    _contexts,
    _evaluate,
)

SEED = 7
BUDGETS = [10000, 20000, 40000]
HORIZONS = [8, 32]
OUT_FILE = OUT.parent / "diag_budget_curve.json"


def main() -> None:
    ms, mf = _contexts(MAIN_SEED)
    gs, gf = _contexts(GEN_SEED)
    bm = _baselines(ms, mf)
    bg = _baselines(gs, gf)

    print("=" * 88)
    print("diag_budget_curve —— 训练预算-效果曲线（seed=7，确定性，无早停）")
    print("=" * 88)
    print(f"参照线 主评估集: rule={bm['rule_capture_pct']}%  heuristic_f2={bm['heuristic_capture_pct']}%  "
          f"头寸={bm['headroom']:+.3f}")
    print(f"参照线 泛化集  : rule={bg['rule_capture_pct']}%  heuristic_f2={bg['heuristic_capture_pct']}%  "
          f"头寸={bg['headroom']:+.3f}")

    rows = []
    for hz in HORIZONS:
        for ep in BUDGETS:
            t0 = time.time()
            p = build_shadow_policy(SEED, warmup_steps=600, ppo_episodes=ep, horizon=hz,
                                    env_factory=lambda sd, h: CalibratedReviewEnv(seed=sd, horizon=h))
            st = getattr(p, "_last_train_stats", {}) or {}
            ev_m = _evaluate(p, ms, mf, bm["uniform"], bm["headroom"])
            ev_g = _evaluate(p, gs, gf, bg["uniform"], bg["headroom"])
            row = {"horizon": hz, "episodes": ep, "seed": SEED,
                   "n_updates": st.get("n_updates"), "main": ev_m, "gen": ev_g,
                   "seconds": round(time.time() - t0, 1)}
            rows.append(row)
            print(f"  hz={hz:<3d} ep={ep:<6d} updates={str(st.get('n_updates')):<5s} | "
                  f"main cap={ev_m['capture_pct']:5.1f}% eff={ev_m['mean_eff']:.3f} "
                  f"躺平率={ev_m['balanced_retreat_low_f2_pct']:5.1f}% | "
                  f"gen cap={ev_g['capture_pct']:5.1f}% | {row['seconds']:.0f}s")

    print("\n主评估集捕获率 vs 预算（判断是否进入平台期）：")
    for hz in HORIZONS:
        seq = [r["main"]["capture_pct"] for r in rows if r["horizon"] == hz]
        gains = [round(seq[i + 1] - seq[i], 1) for i in range(len(seq) - 1)]
        print(f"  hz={hz:<3d}: {seq}  相邻增益={gains}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        json.dump({
            "meta": {"source": "diag_budget_curve.py (read-only, 单种子趋势性诊断)",
                     "seed": SEED, "budgets": BUDGETS, "horizons": HORIZONS,
                     "note": "单种子 ⇒ 结论仅趋势性；写入验收数字须补 3 种子。"},
            "baselines": {"main": bm, "gen": bg},
            "rows": rows,
        }, fh, ensure_ascii=False, indent=2)
    print(f"\n落盘：{OUT_FILE}")


if __name__ == "__main__":
    main()
