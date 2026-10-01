#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pilot_stats.py — 芒得很职 · 国创赛试点成效统计（T1-5）

读取 pilot_pre.csv + pilot_post.csv（按 user_id 内连接），输出：
  1) 各维配对 t 检验（p 值 + Cohen's d）—— 自评(self_*) vs 系统评(ecd_*)
  2) ICC（自评 vs 系统评，两向随机单测度绝对一致 ICC(2,1)）
  3) 教师盲评(teacher_blind) vs 系统评均值 Pearson r
  4) 鲶鱼触发组(catfish_triggered=1) vs 未触发组(=0) 抗压维度前后差对比（独立 t 检验）

红线（与《试点数据采集模板》一致）：
  · 无显著差异时如实输出「未见显著差异」，绝不美化、绝不编造 p 值。
  · 真实样本量 N 必须写入输出与证据页；合成/演示数据不得冒充真实样本。
  · 输入 CSV 须已脱敏（仅 user_id，无姓名全称）。

依赖：pandas, numpy, scipy。缺失时脚本给出明确报错而非静默出错。
用法：
  python pilot_stats.py --pre pilot_pre.csv --post pilot_post.csv [--md pilot_stats_report.md]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy import stats

DIMS = ["express", "stress", "decomp", "collab", "tech", "solve"]
DIM_CN = {
    "express": "表达逻辑",
    "stress": "抗压应变",
    "decomp": "方案拆解",
    "collab": "协作沟通",
    "tech": "技术汇报",
    "solve": "问题解决",
}


def load_and_join(pre_path: str, post_path: str) -> pd.DataFrame:
    pre = pd.read_csv(pre_path)
    post = pd.read_csv(post_path)
    need_pre = ["user_id"] + [f"self_{d}" for d in DIMS] + ["teacher_impression"]
    need_post = ["user_id"] + [f"ecd_{d}" for d in DIMS] + ["teacher_blind", "catfish_triggered"]
    miss_pre = [c for c in need_pre if c not in pre.columns]
    miss_post = [c for c in need_post if c not in post.columns]
    if miss_pre or miss_post:
        raise SystemExit(f"[字段缺失] pre 缺 {miss_pre}；post 缺 {miss_post}。请核对《试点数据采集模板》。")
    df = pre.merge(post, on="user_id", how="inner", suffixes=("", "_post"))
    return df


def cohen_d_paired(diff: np.ndarray) -> float:
    diff = np.asarray(diff, dtype=float)
    n = len(diff)
    if n < 2:
        return float("nan")
    sd = diff.std(ddof=1)
    if sd == 0:
        return float("nan")
    return float(diff.mean() / sd)


def paired_test(name: str, a: np.ndarray, b: np.ndarray) -> dict:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    diff = a - b
    n = len(diff)
    if n < 2:
        return {"name": name, "n": n, "ok": False, "sig": False}
    if np.std(diff, ddof=1) == 0:
        return {"name": name, "n": n, "ok": True, "sig": False,
                "mean_diff": float(diff.mean()), "t": float("nan"),
                "p": float("nan"), "d": float("nan"), "note": "前后差异标准差为0，无法做 t 检验"}
    res = stats.ttest_rel(a, b)
    t = float(res.statistic)
    p = float(res.pvalue)
    d = cohen_d_paired(diff)
    return {"name": name, "n": n, "ok": True, "sig": bool(p < 0.05),
            "mean_diff": float(diff.mean()), "t": t, "p": p, "d": d}


def icc_2_1(ratings: np.ndarray) -> float:
    """两向随机效应、单测度、绝对一致 ICC(2,1)。ratings: shape (n_items, n_raters)。"""
    ratings = np.asarray(ratings, dtype=float)
    n, k = ratings.shape
    if n < 2 or k < 2:
        return float("nan")
    grand = ratings.mean()
    row_means = ratings.mean(axis=1)  # 受试者（user×dim）均值，跨 k 个评分源
    col_means = ratings.mean(axis=0)  # 评分源（self/system）均值，跨 n 个受试者
    ss_total = ((ratings - grand) ** 2).sum()
    # 两向 ANOVA：受试者平方和乘 k，评分源平方和乘 n（标准定义，不可写反）
    ss_rows = k * ((row_means - grand) ** 2).sum()  # 受试者（user×dim）效应
    ss_cols = n * ((col_means - grand) ** 2).sum()  # 评分源（self/system）效应
    ss_err = ss_total - ss_rows - ss_cols
    df_rows = n - 1
    df_err = df_rows * (k - 1)
    if df_err <= 0:
        return float("nan")
    ms_rows = ss_rows / df_rows
    ms_err = ss_err / df_err
    denom = ms_rows + (k - 1) * ms_err
    if denom == 0:
        return float("nan")
    return float((ms_rows - ms_err) / denom)


def fmt_p(p: float) -> str:
    if np.isnan(p):
        return "N/A"
    if p < 1e-4:
        return "<0.0001"
    return f"{p:.4f}"


def run(pre_path: str, post_path: str) -> dict:
    df = load_and_join(pre_path, post_path)
    n = len(df)
    lines = []
    md = []

    lines.append(f"=== 芒得很职 · 国创赛试点成效统计 ===")
    lines.append(f"匹配样本量 N = {n}（前后测按 user_id 内连接）")
    md.append(f"# 试点成效统计报告（N={n}）")
    md.append("")
    md.append(f"> 匹配样本量 N = **{n}**。合成/演示数据不得冒充真实样本。")
    md.append("")

    if n < 2:
        msg = "样本量不足（N<2），无法进行任何统计检验。"
        lines.append(msg)
        md.append(f"**{msg}**")
        return {"text": "\n".join(lines), "md": "\n".join(md), "n": n}

    # 1) 各维配对 t 检验
    lines.append("")
    lines.append("【1】各维配对 t 检验（系统评 ecd_* − 自评 self_*，差值=系统评−自评）")
    md.append("## 1. 各维配对 t 检验（系统评 − 自评）")
    md.append("")
    md.append("> 差值 = 系统评 − 自评；该检验反映前后测**评分变化**，不等同于因果性学习增益。")
    md.append("")
    md.append("| 维度 | N | 平均差(系统评−自评) | t | p | Cohen's d | 结论 |")
    md.append("|---|---|---|---|---|---|---|")
    sig_any = False
    for d in DIMS:
        r = paired_test(DIM_CN[d], df[f"ecd_{d}"].values, df[f"self_{d}"].values)
        if not r["ok"]:
            s = f"  · {DIM_CN[d]}：样本不足，跳过"
            lines.append(s)
            md.append(f"| {DIM_CN[d]} | {r['n']} | - | - | - | - | 样本不足 |")
            continue
        if "note" in r:
            s = f"  · {DIM_CN[d]}：{r['note']}"
            lines.append(s)
            md.append(f"| {DIM_CN[d]} | {r['n']} | {r['mean_diff']:+.3f} | - | - | - | {r['note']} |")
            continue
        verdict = "差异显著" if r["sig"] else "未见显著差异"
        sig_any = sig_any or r["sig"]
        s = (f"  · {DIM_CN[d]}：平均差(系统评−自评) {r['mean_diff']:+.3f} "
             f"(t={r['t']:.3f}, p={fmt_p(r['p'])}, d={r['d']:+.3f}) → {verdict}")
        lines.append(s)
        md.append(f"| {DIM_CN[d]} | {r['n']} | {r['mean_diff']:+.3f} | {r['t']:.3f} | {fmt_p(r['p'])} | {r['d']:+.3f} | {verdict} |")

    # 2) ICC（自评 vs 系统评）
    lines.append("")
    lines.append("【2】ICC（自评 vs 系统评，ICC(2,1) 绝对一致）")
    md.append("")
    md.append("## 2. ICC（自评 vs 系统评）")
    md.append("")
    stack = []
    for _, row in df.iterrows():
        for d in DIMS:
            stack.append([row[f"self_{d}"], row[f"ecd_{d}"]])
    icc = icc_2_1(np.array(stack))
    if np.isnan(icc):
        s = "  · 无法计算（数据不足）"
        lines.append(s)
        md.append("**无法计算（数据不足）**")
    else:
        qual = "优秀" if icc >= 0.75 else ("可接受" if icc >= 0.5 else "偏低")
        s = f"  · ICC(2,1) = {icc:.3f}（{qual}一致性）"
        lines.append(s)
        md.append(f"**ICC(2,1) = {icc:.3f}**（{qual}一致性）")
        md.append("")
        md.append("> 仅说明两种评分源的一致性，不代表系统“教会了”学生。")

    # 3) 教师盲评 vs 系统评 Pearson r
    lines.append("")
    lines.append("【3】教师盲评(teacher_blind) vs 系统评均值 Pearson r")
    md.append("")
    md.append("## 3. 教师盲评 vs 系统评")
    md.append("")
    sys_mean = df[[f"ecd_{d}" for d in DIMS]].mean(axis=1)
    r, p = stats.pearsonr(df["teacher_blind"].values, sys_mean.values)
    s = f"  · Pearson r = {r:.3f}（p={fmt_p(p)}，N={n}）"
    lines.append(s)
    md.append(f"**Pearson r = {r:.3f}**（p={fmt_p(p)}，N={n}）。教师盲评与系统评均值的相关性。")
    md.append("")

    # 4) 鲶鱼触发组 vs 未触发组 抗压前后差
    lines.append("")
    lines.append("【4】鲶鱼加压：触发组 vs 未触发组 · 抗压维度(抗压应变)前后差对比")
    md.append("")
    md.append("## 4. 鲶鱼加压效应（抗压应变前后差：ecd_stress − self_stress）")
    md.append("")
    diff_stress = (df["ecd_stress"] - df["self_stress"]).values
    trig = df["catfish_triggered"].values.astype(int)
    if set(trig) <= {0} or set(trig) <= {1}:
        s = "  · 仅存在单一分组（鲶鱼触发或未触发样本为空），无法做组间对比。"
        lines.append(s)
        md.append("**仅存在单一分组，无法做组间对比。**")
    else:
        g1 = diff_stress[trig == 1]
        g0 = diff_stress[trig == 0]
        t_res = stats.ttest_ind(g1, g0, equal_var=False)
        s = (f"  · 触发组(N={len(g1)}) 抗压前后差均值 {g1.mean():+.3f}；"
             f"未触发组(N={len(g0)}) {g0.mean():+.3f}；"
             f"组间差 t={t_res.statistic:.3f}, p={fmt_p(float(t_res.pvalue))}")
        lines.append(s)
        verdict = "鲶鱼组抗压提升显著更高" if float(t_res.pvalue) < 0.05 else "两组抗压提升未见显著差异"
        lines.append(f"    → {verdict}")
        md.append(f"| 分组 | N | 抗压前后差均值 |")
        md.append("|---|---|---|")
        md.append(f"| 鲶鱼触发 | {len(g1)} | {g1.mean():+.3f} |")
        md.append(f"| 未触发 | {len(g0)} | {g0.mean():+.3f} |")
        md.append("")
        md.append(f"组间独立 t 检验：t={t_res.statistic:.3f}, p={fmt_p(float(t_res.pvalue))} → **{verdict}**")

    # 总览结论（诚实）
    lines.append("")
    lines.append("【总览】")
    if not sig_any:
        lines.append("  · 各维系统评与自评均未见显著差异：如实记录，不美化。")
        md.append("## 总览")
        md.append("")
        md.append("**各维系统评与自评均未见显著差异：如实记录，不美化。**")
        md.append("")
        md.append("> 提示：本统计仅反映前后测评分变化，不构成“系统教会学生”的因果证据；如需因果结论需随机对照设计。")
    else:
        lines.append("  · 存在系统评与自评差异显著的维度（详见上表）；未显著维度同样如实列出。")
        md.append("## 总览")
        md.append("")
        md.append("存在系统评与自评差异显著的维度（见上表）；未显著维度已如实列出，未做美化。")
        md.append("")
        md.append("> 提示：差异显著仅表示前后测评分变化，不构成“系统教会学生”的因果证据；如需因果结论需随机对照设计。")

    return {"text": "\n".join(lines), "md": "\n".join(md), "n": n}


def main(argv=None):
    ap = argparse.ArgumentParser(description="芒得很职国创赛试点成效统计 (T1-5)")
    ap.add_argument("--pre", required=True, help="前测 CSV 路径 (pilot_pre.csv)")
    ap.add_argument("--post", required=True, help="后测 CSV 路径 (pilot_post.csv)")
    ap.add_argument("--md", default=None, help="可选：将 Markdown 报告写入该路径")
    args = ap.parse_args(argv)

    try:
        result = run(args.pre, args.post)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"[运行失败] {type(e).__name__}: {e}")

    print(result["text"])
    if args.md:
        with open(args.md, "w", encoding="utf-8") as f:
            f.write(result["md"])
        print(f"\n[已写入 Markdown 报告] {args.md}")


if __name__ == "__main__":
    main()
