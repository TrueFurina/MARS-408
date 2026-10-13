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

  # 模式 C（混态：**每场会话**前 N 次 LLM 调用成功，其后强制降级）
  LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=... python experiments/career_llm_baseline.py \
      --mode mixed --fail-after 4 \
      --out experiments/results/career_baseline_mixed_<date>.json

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

import importlib
import db.pg_client as _pgc_shadowed  # noqa: E402,F401
# ⚠️ 上面这行**拿不到模块**：db/__init__.py 里 `from .pg_client import pg_client` 会把
# **实例**绑成 `db.pg_client` 这个包属性，遮蔽同名子模块。所以 `import db.pg_client as X`
# 得到的是 PgClient 实例，往它身上设属性不会改到模块全局 —— 曾因此**静默污染真实库**
# （2026-10-14 实测：20 场基线会话写进了服务器 data/pg_fallback.db）。
# 必须先 import 包、再用 importlib 取真正的模块对象：
import db as _db_pkg  # noqa: E402,F401

_pgc = importlib.import_module("db.pg_client")
assert type(_pgc).__name__ == "module", "取到的不是模块（遮蔽未处理），拒绝继续"
_pgc._FALLBACK_DIR = _TMP
_pgc._FALLBACK_DB = os.path.join(_TMP, "pg_fallback.db")


def _verify_isolation() -> None:
    """fail-closed：确认落库连接真的指向临时目录，否则拒绝运行。

    加这道闸的原因：上面那个遮蔽陷阱**不会报错**（属性设在一个没人用的对象上），
    只会安静地把测试数据写进真实库。宁可直接失败，也不接受"看起来没问题"。
    """
    _pgc.pg_client.connect()
    conn = _pgc.pg_client._conn
    if conn is None:
        raise SystemExit("❌ DB 隔离校验失败：pg_client 未建立连接")
    files = [r[2] for r in conn.execute("PRAGMA database_list").fetchall()]
    ok = [f for f in files if f and os.path.abspath(f).startswith(os.path.abspath(_TMP))]
    if not ok:
        raise SystemExit(
            f"❌ DB 隔离校验失败：连接实际指向 {files}，预期位于 {_TMP}。"
            "拒绝运行，以免污染真实 data/*.db。")
    print(f"[baseline] DB 隔离校验通过 → {ok[0]}")

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


async def run_scenario(cs, store, sc: dict, llm_state: dict | None = None) -> dict:
    rec: dict = {"id": sc["id"], "title": sc["title"], "type": sc["type"]}
    if llm_state is not None:  # 每场会话独立计数
        llm_state["calls"] = 0
        llm_state["failed"] = 0
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
    if llm_state is not None:
        rec["llm_calls"] = {"calls": llm_state["calls"], "failed": llm_state["failed"]}
    rec["elapsed_s"] = round(time.time() - t0, 2)
    return rec


def inject_fail_after(n: int) -> dict:
    """让前 n 次 LLM 调用走真实通道，之后一律抛 LLMUnavailable —— 制造「部分降级」混态。

    只 patch 类方法：career_nodes 每个节点都 `LLMProvider()` new 新实例，patch 实例无效。
    用途：验证「脚本/证据来自真实模型、但评估已降级」时，系统是否仍能产出可对齐的报告。
    """
    import db.llm_provider as _lp
    orig = _lp.LLMProvider.text_completion
    # calls/failed 按「每场会话」计（由 run_scenario 在场景开始时清零），
    # total_* 为全程累计。语义：每场实训跑到第 n+1 次 LLM 调用时模型服务挂了。
    state = {"limit": n, "calls": 0, "failed": 0, "total_calls": 0, "total_failed": 0}

    async def _wrapped(self, *a, **kw):
        state["calls"] += 1
        state["total_calls"] += 1
        if state["calls"] > n:
            state["failed"] += 1
            state["total_failed"] += 1
            raise _lp.LLMUnavailable(
                f"[injected] 本场第 {state['calls']} 次 LLM 调用起强制失败（fail_after={n}）")
        return await orig(self, *a, **kw)

    _lp.LLMProvider.text_completion = _wrapped
    return state


async def run(mode: str, out_path: str, fail_after: int = -1) -> int:
    llm = probe_llm()
    llm_state = inject_fail_after(fail_after) if fail_after >= 0 else None
    if llm_state:
        print(f"[baseline] ⚠️ 故障注入：前 {fail_after} 次 LLM 调用放行，其后强制失败（混态用例）")

    from services import career_service as cs
    from db import career_store as store

    _verify_isolation()  # 先证明写的是临时库，再动手

    print(f"[baseline] mode={mode} llm={json.dumps(llm, ensure_ascii=False)}")
    print(f"[baseline] 隔离 DB = {os.environ['NETLEARN_USER_DB']}")

    out: dict = {
        "mode": mode,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "llm": llm,
        "injected_fail_after": fail_after if fail_after >= 0 else None,
        "answers_sha": __import__("hashlib").sha256(
            "\n".join(ANSWERS).encode("utf-8")).hexdigest()[:16],
        "scenarios": [],
    }
    for sc in cs.list_scenarios():
        rec = await run_scenario(cs, store, sc, llm_state)
        out["scenarios"].append(rec)
        tag = rec.get("error") if rec["status"] == "error" else \
            f"script_llm={rec['script_gen']['opening_from_llm']} " \
            f"overall={rec['assessment']['overall']} " \
            f"chain={rec['assessment']['evidence_chain_len']}"
        if rec.get("llm_calls"):
            tag += f" llm={rec['llm_calls']['calls']}/失败{rec['llm_calls']['failed']}"
        print(f"  - {sc['id']:32s} {rec['status']:5s} {rec['elapsed_s']:6.2f}s  {tag}")

    if llm_state:
        out["llm_calls"] = {"limit_per_scenario": llm_state["limit"],
                            "total_calls": llm_state["total_calls"],
                            "total_failed_injected": llm_state["total_failed"]}
        print(f"[baseline] LLM 调用统计: 全程总调用={llm_state['total_calls']} "
              f"其中注入失败={llm_state['total_failed']}")

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
    ap.add_argument("--mode", choices=["mock", "real", "mixed"], help="运行模式标签（写入结果）")
    ap.add_argument("--out", help="运行结果 / 对比报告输出路径")
    ap.add_argument("--fail-after", type=int, default=-1, metavar="N",
                    help="故障注入：前 N 次 LLM 调用放行、其后强制失败（制造部分降级混态）")
    ap.add_argument("--compare", nargs=2, metavar=("A_JSON", "B_JSON"),
                    help="对比两份运行结果，产出 markdown 报告")
    args = ap.parse_args()

    if args.compare:
        return compare(args.compare[0], args.compare[1], args.out)
    if not args.mode or not args.out:
        ap.error("运行模式需要同时提供 --mode 与 --out")
    return asyncio.run(run(args.mode, args.out, args.fail_after))


if __name__ == "__main__":
    sys.exit(main())
