#!/usr/bin/env python
# ============================================================
# audit_eval_artifacts — 只读审计评测产物，输出"哪些读数还能引用"
#
# 为什么需要它：2026-09-14 出现三起口径事故（训练预算被静默饿死 / 精准率量纲漂移 /
#   评测未施纪律护栏），产物文件本身不会自述"我过时了"。靠记忆判定会出错，
#   故把判定依据（meta 里的 episodes、batch、n_updates、train_env）扫出来对账。
#
# 只读：本脚本不写入、不移动、不删除任何产物文件。
# 用法（在 py-server/ 下）：.venv/Scripts/python.exe ../scripts/audit_eval_artifacts.py
# ============================================================

import glob
import json
import os
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "py-server",
                    "experiments", "results")
BASE = os.path.normpath(BASE)

META_KEYS = ("train_env", "env", "warmup_steps", "ppo_episodes", "ppo_batch_episodes",
             "batch_episodes", "horizon", "shadow_seeds", "seeds", "n_samples",
             "data_seed", "eval_episodes_per_cell")
DIFF_KEYS = ("arm_means", "delta_vs_rule", "delta_vs_uniform", "delta_vs_mappo",
             "delta_vs_heuristic", "shadow_action_dist", "mappo_action_dist")


def _fmt(v):
    if isinstance(v, float):
        return round(v, 4)
    return v


def summarize(path: str) -> dict:
    d = json.load(open(path, encoding="utf-8"))
    meta = {}
    for cand in ("meta", "config"):
        if isinstance(d.get(cand), dict):
            meta.update(d[cand])
    out = {
        "file": os.path.basename(path),
        "meta": {k: meta[k] for k in META_KEYS if k in meta},
        "n_updates": meta.get("n_updates_per_seed") or meta.get("n_updates"),
    }
    for k in DIFF_KEYS:
        v = d.get(k)
        if isinstance(v, dict):
            out[k] = {k2: _fmt(x) for k2, x in v.items()}
    ag = d.get("aggregate_by_scheme")
    if isinstance(ag, dict):
        out["agg"] = {k: _fmt(v.get("mean_return"))
                      for k, v in ag.items() if isinstance(v, dict)}
    abl = d.get("constant_action_ablation")
    if isinstance(abl, dict) and abl:
        best = max(abl.items(), key=lambda kv: kv[1].get("mean_return", -1e9))
        out["best_constant"] = [best[0], _fmt(best[1].get("mean_return"))]
    if isinstance(d.get("results"), list):
        out["budget_sweep"] = [
            {"label": r.get("meta", {}).get("label"),
             "n_updates": r.get("meta", {}).get("n_updates_per_seed"),
             "shadow": _fmt(r.get("arm_means", {}).get("shadow")),
             "d_rule": _fmt(r.get("delta_vs_rule", {}).get("mean"))}
            for r in d["results"]]
    return out


def main() -> int:
    patterns = [
        "review_shadow_summary_*.json", "sweep_shadow_budget_*.json",
        "review_mappo_eval_*.json", "review_mappo_ablation_*.json",
        "review_action_dist_*.json", "tune_shadow_budget.json",
        "diag_budget_curve.json", "diag_rule_upgrade.json",
    ]
    total = 0
    for pat in patterns:
        files = sorted(glob.glob(os.path.join(BASE, pat)))
        if not files:
            continue
        print("=" * 96)
        print("PATTERN:", pat, f"({len(files)})")
        print("=" * 96)
        for p in files:
            try:
                s = summarize(p)
            except Exception as e:  # 产物坏了也要显式说，不能静默跳过
                print(f"- {os.path.basename(p)}  [读取失败: {e}]")
                continue
            total += 1
            print(f"- {s['file']}")
            if s["meta"]:
                print("    meta      :", s["meta"])
            if s["n_updates"]:
                print("    n_updates :", s["n_updates"])
            for k in DIFF_KEYS:
                if k in s:
                    print(f"    {k:<10}:", s[k])
            if "agg" in s:
                print("    agg       :", s["agg"])
            if "best_constant" in s:
                print("    best_const:", s["best_constant"])
            if "budget_sweep" in s:
                for r in s["budget_sweep"]:
                    print("      *", r)
            print()
    print(f"[audit] 共扫描 {total} 个产物文件（只读，未修改任何文件）")
    print("[audit] 状态判定与处置见同目录 INVALID-ARTIFACTS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
