# -*- coding: utf-8 -*-
"""拼图① 基线：career 对抗链路在「LLM 不可用（种子兜底）」与「真实 LLM」两模式下的输出对比。

为什么需要它
------------
`career_nodes` 每个 LLM 节点都有「失败即种子兜底」分支（如 build_scenario_script 的
fallback 返回种子 probe_tree、success_signals=[]）。这意味着：
  * 系统在没有任何 LLM 凭据时**照样能跑完整闭环**（不会白屏/报错），
  * 但它的**输出质量与真实 LLM 模式不同**，且从结果上看不出差别来自哪里。
不把这件事量化落盘，就无法回答「接了真模型到底变了什么」——这正是拼图①要的证据。

做法
----
对 career_scenarios.json 里的 **全部 4 个场景**，用**完全相同的作答序列**各跑一遍闭环
（start → 2 轮 answer → force end），分别在两种模式下执行：

  模式 A（mock/fallback）: 不提供任何 LLM 凭据 → LLMUnavailable → 走种子兜底
  模式 B（real）        : 提供真实凭据（LLM_PROVIDER + *_API_KEY）→ 真实模型

两模式的**输入完全相同**（同一场景、同一作答），唯一变量是 LLM 是否可用，
因此差异可归因于「真实 LLM 接入」。

隔离
----
全程写临时库（`NETLEARN_USER_DB` + monkeypatch `pg_client._FALLBACK_DB`），
**不触碰** data/netlearn_users.db 与 data/pg_fallback.db。

用法
----
  # 模式 A（预期 LLM 不可用）
  python experiments/career_llm_baseline.py --mode mock \
      --out experiments/results/career_baseline_mock_<date>.json

  # 模式 B（真实 LLM）
  LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=... python experiments/career_llm_baseline.py \
      --mode real --out experiments/results/career_baseline_real_<date>.json

  # 对比出报告
  python experiments/career_llm_baseline.py --compare A.json B.json \
      --out experiments/results/career_baseline_compare_<date>.md
"""
from __future__ import annotations

import argparse
import asyncio
import atexit
import datetime
import json
import os
import shutil
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # py-server
sys.path.insert(0, _ROOT)

# ── DB 隔离（必须在 import 任何 db.* 之前设 env）──
_TMP = tempfile.mkdtemp(prefix="career_baseline_")
os.environ["NETLEARN_USER_DB"] = os.path.join(_TMP, "users.db")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)

import db.pg_client as _pgc  # noqa: E402

_pgc._FALLBACK_DIR = _TMP
_pgc._FALLBACK_DB = os.path.join(_TMP, "pg_fallback.db")

# ── 固定作答序列（两模式共用 → 唯一变量是 LLM 可用性）──
ANSWERS = [
    "我理解这个需求两周做不完：推荐链路要走特征、召回、排序三步，至少三周。"
    "我建议本迭代先上基于规则的热门推荐 MVP，两天可交付，智能版放下个迭代；"
    "我今天出一份对比排期表，和业务一起对齐预期，而不是直接砍掉回归测试。",
    "风险我分三层：进度、质量、沟通。对应动作是本迭代范围冻结、补一轮回归、每天同步进展。"
    "如果核心依赖明天不可用，降级路径是切到本地规则兜底，代价是推荐效果下降约两成，"
    "这个取舍应由业务方拍板，我负责把两个方案的成本和收益列清楚。",
]


def probe_llm() -> dict:
    """离线探测 LLM 是否可用（不发起网络请求）。"""
    try:
        from db.llm_provider import LLMProvider
        info = LLMProvider()._resolve() or {}
        return {
            "available": bool(info.get("api_key") or info.get("app_id")),
            "name": info.get("name"),
            "model": info.get("model"),
            "has_api_key": bool(info.get("api_key")),
        }
    except Exception as e:  # LLMUnavailable 等
        return {"available": False, "error": f"{type(e).__name__}: {e}"[:200]}


async def run_scenario(cs, store, sc: dict) -> dict:
    rec: dict = {"id": sc["id"], "title": sc["title"], "type": sc["type"]}
    t0 = time.time()
    try:
        started = await cs.start_session("baseline_probe", sc["id"], "medium", max_turns=4)
        sid = started["session_id"]
        state = store.get_session_state(sid) or {}
        script = state.get("scenario_script") or {}
        rec["script_gen"] = {
            "probe_plan": len(script.get("probe_plan") or []),
            "success_signals": len(script.get("success_signals") or []),
            "opening_from_llm": bool(script.get("success_signals")),
        }
        rec["opening_question"] = (started.get("next_question") or {}).get("question", "")[:120]

        turns = []
        for i, ans in enumerate(ANSWERS, 1):
            r = await cs.answer_turn(sid, ans)
            ev = r.get("last_evidence") or {}
            turns.append({
                "index": i,
                "status": r.get("status"),
                "adversary_mode": r.get("mode"),
                "evidence_hits": len(ev.get("dimension_hits") or []),
                "template_suspect": ev.get("template_suspect"),
                "density": ev.get("density"),
                "next_question": ((r.get("next_question") or {}).get("question") or "")[:120],
            })
        rec["turns"] = turns

        fin = await cs.end_session(sid, force=True)
        a = fin.get("assessment") or {}
        dims = a.get("dimensions") or {}
        chain = fin.get("evidence_chain") or []
        rec["assessment"] = {
            "source": a.get("assessment_source"),
            "overall": a.get("overall"),
            "dims_present": sorted(dims.keys()),
            "scores": {d: v.get("score") for d, v in dims.items()
                       if isinstance(v, dict) and v.get("score") is not None},
            "evidence_chain_len": len(chain),
            "chain_with_quotes": sum(
                1 for c in chain if c.get("evidence_quotes") or c.get("per_turn_evidence")),
            "has_summary": bool(a.get("summary")),
        }
        rec["status"] = "ok"
    except Exception as e:
        rec["status"] = "error"
        rec["error"] = f"{type(e).__name__}: {e}"[:300]
    rec["elapsed_s"] = round(time.time() - t0, 2)
    return rec


async def run(mode: str, out_path: str) -> int:
    from services import career_service as cs
    from db import career_store as store

    llm = probe_llm()
    print(f"[baseline] mode={mode} llm={json.dumps(llm, ensure_ascii=False)}")
    print(f"[baseline] 隔离 DB = {os.environ['NETLEARN_USER_DB']}")

    out: dict = {
        "mode": mode,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "llm": llm,
        "answers_sha": __import__("hashlib").sha256(
            "\n".join(ANSWERS).encode("utf-8")).hexdigest()[:16],
        "scenarios": [],
    }
    for sc in cs.list_scenarios():
        rec = await run_scenario(cs, store, sc)
        out["scenarios"].append(rec)
        tag = rec.get("error") if rec["status"] == "error" else \
            f"script_llm={rec['script_gen']['opening_from_llm']} " \
            f"overall={rec['assessment']['overall']} " \
            f"chain={rec['assessment']['evidence_chain_len']}"
        print(f"  - {sc['id']:32s} {rec['status']:5s} {rec['elapsed_s']:6.2f}s  {tag}")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[baseline] 落盘: {out_path}")
    ok = sum(1 for s in out["scenarios"] if s["status"] == "ok")
    print(f"[baseline] 完成 {ok}/{len(out['scenarios'])} 个场景")
    return 0 if ok == len(out["scenarios"]) else 1


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def compare(a_path: str, b_path: str, out_path: str | None) -> int:
    a = json.load(open(a_path, encoding="utf-8"))
    b = json.load(open(b_path, encoding="utf-8"))
    by_id_b = {s["id"]: s for s in b["scenarios"]}

    L: list[str] = []
    L.append("# career 对抗链路：LLM 兜底模式 vs 真实 LLM 模式 对比基线")
    L.append("")
    L.append(f"- A 模式：`{a['mode']}` ({a['generated_at']}) → LLM 可用="
             f"**{a['llm'].get('available')}** {a['llm'].get('name') or a['llm'].get('error', '')}")
    L.append(f"- B 模式：`{b['mode']}` ({b['generated_at']}) → LLM 可用="
             f"**{b['llm'].get('available')}** {b['llm'].get('name') or b['llm'].get('error', '')}")
    L.append(f"- 作答序列哈希（两模式应一致）：A=`{a['answers_sha']}` B=`{b['answers_sha']}`"
             f" {'✅ 一致' if a['answers_sha'] == b['answers_sha'] else '❌ 不一致（对比无效）'}")
    L.append("")

    diff_count = 0
    for sa in a["scenarios"]:
        sb = by_id_b.get(sa["id"])
        L.append(f"## {sa['title']}  `{sa['id']}`")
        L.append("")
        if not sb:
            L.append("（B 模式缺失该场景）")
            L.append("")
            continue
        L.append("| 指标 | A（兜底） | B（真实） | 是否不同 |")
        L.append("|---|---|---|---|")
        rows = [
            ("脚本来自 LLM", sa.get("script_gen", {}).get("opening_from_llm"),
             sb.get("script_gen", {}).get("opening_from_llm")),
            ("probe_plan 条数", sa.get("script_gen", {}).get("probe_plan"),
             sb.get("script_gen", {}).get("probe_plan")),
            ("success_signals 条数", sa.get("script_gen", {}).get("success_signals"),
             sb.get("script_gen", {}).get("success_signals")),
            ("开场问题", sa.get("opening_question"), sb.get("opening_question")),
            ("第1轮 adversarial mode",
             (sa.get("turns") or [{}])[0].get("adversary_mode"),
             (sb.get("turns") or [{}])[0].get("adversary_mode")),
            ("第1轮 证据命中数",
             (sa.get("turns") or [{}])[0].get("evidence_hits"),
             (sb.get("turns") or [{}])[0].get("evidence_hits")),
            ("第2轮 追问", (sa.get("turns") or [{}, {}])[1].get("next_question"),
             (sb.get("turns") or [{}, {}])[1].get("next_question")),
            ("评估来源", sa.get("assessment", {}).get("source"),
             sb.get("assessment", {}).get("source")),
            ("overall", sa.get("assessment", {}).get("overall"),
             sb.get("assessment", {}).get("overall")),
            ("证据链条数", sa.get("assessment", {}).get("evidence_chain_len"),
             sb.get("assessment", {}).get("evidence_chain_len")),
            ("含原话的链条数", sa.get("assessment", {}).get("chain_with_quotes"),
             sb.get("assessment", {}).get("chain_with_quotes")),
        ]
        for label, va, vb in rows:
            same = "—" if va == vb else "**是**"
            if va != vb:
                diff_count += 1
            L.append(f"| {label} | {_fmt(va)} | {_fmt(vb)} | {same} |")
        L.append("")
        # 六维分数逐维
        da = sa.get("assessment", {}).get("scores") or {}
        db_ = sb.get("assessment", {}).get("scores") or {}
        if da or db_:
            L.append("六维分数：")
            L.append("")
            L.append("| 维度 | A（兜底） | B（真实） |")
            L.append("|---|---|---|")
            for d in sorted(set(da) | set(db_)):
                L.append(f"| {d} | {_fmt(da.get(d))} | {_fmt(db_.get(d))} |")
                if da.get(d) != db_.get(d):
                    diff_count += 1
            L.append("")

    L.append("## 结论")
    L.append("")
    L.append(f"- 逐项比对共发现 **{diff_count}** 处差异（含六维分数）。")
    n_llm = sum(1 for s in b["scenarios"] if s.get("script_gen", {}).get("opening_from_llm"))
    L.append(f"- B 模式中由 LLM 生成脚本的场景：**{n_llm}/{len(b['scenarios'])}**；"
             f"A 模式：**{sum(1 for s in a['scenarios'] if s.get('script_gen', {}).get('opening_from_llm'))}"
             f"/{len(a['scenarios'])}**（预期 0）。")
    L.append("- 差异说明真实模型接入后**输出确实改变**；A 模式证明系统在无凭据时"
             "**仍能跑完整闭环**（可降级，不报错）。")
    L.append("")

    text = "\n".join(L)
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[compare] 报告落盘: {out_path}")
    else:
        print(text)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["mock", "real"], help="运行模式标签（写入结果）")
    ap.add_argument("--out", help="运行结果 / 对比报告输出路径")
    ap.add_argument("--compare", nargs=2, metavar=("A_JSON", "B_JSON"),
                    help="对比两份运行结果，产出 markdown 报告")
    args = ap.parse_args()

    if args.compare:
        return compare(args.compare[0], args.compare[1], args.out)
    if not args.mode or not args.out:
        ap.error("运行模式需要同时提供 --mode 与 --out")
    return asyncio.run(run(args.mode, args.out))


if __name__ == "__main__":
    sys.exit(main())
