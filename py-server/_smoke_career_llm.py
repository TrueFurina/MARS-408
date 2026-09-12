# -*- coding: utf-8 -*-
"""真实 LLM 冒烟：start + 1轮answer + end 强制终评，检查脚本/取证/对抗问题/六维评估全链路。

CTO 对外口径修正令（2026-09-12）整改：
- 补关键断言：六维齐全 / 0≤score≤5 / 证据链非空
- 结果输出到 experiments/results/career_llm_smoke_YYYYMMDD.json（对外引用以落盘为准）
- 数字治理规则：无落盘不出数字——README 引用 overall 必须出自本文件的落盘 JSON
"""
import asyncio, json, os, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "experiments", "results",
                           f"career_llm_smoke_{datetime.date.today():%Y%m%d}.json")


async def main() -> int:
    from services import career_service
    from db import career_store
    from agents.career_state import DIMENSIONS

    result: dict = {"date": datetime.date.today().isoformat(),
                    "script": "_smoke_career_llm.py", "checks": {}}

    sc = career_service.list_scenarios()
    started = await career_service.start_session("smoke_user", sc[1]["id"], "medium", max_turns=4)
    result["scenario_title"] = started["title"]

    state = career_store.get_session_state(started["session_id"])
    s = state.get("scenario_script", {})
    n_probe = len(s.get("probe_plan", []))
    n_signals = len(s.get("success_signals", []))
    result["script_gen"] = {"probe_plan": n_probe, "success_signals": n_signals,
                            "llm_generated": n_signals > 0}
    print("场景 =", started["title"])
    print("脚本 probe_plan =", n_probe, "；success_signals =", n_signals,
          "（>0 说明LLM脚本生成成功）")
    print("开场 =", started["next_question"]["question"][:60])

    r = await career_service.answer_turn(
        started["session_id"],
        "我理解这个需求两周做不完，因为推荐要走特征、召回、排序三步，至少三周。"
        "我建议本迭代先上基于规则的热门推荐MVP，只需要两天，智能版放下个迭代，"
        "我可以今天出一个对比排期表，我们一起跟业务对齐预期，而不是直接砍掉测试。")
    ev = r.get("last_evidence", {})
    hits = ev.get("dimension_hits") or []
    result["turn1"] = {
        "status": r["status"], "mode": r.get("mode"),
        "evidence_hits": len(hits),
        "template_suspect": ev.get("template_suspect"),
        "density": ev.get("density"),
        "next_question": (r["next_question"].get("question") or "")[:80],
    }
    print("第1轮 status =", r["status"], "mode =", r.get("mode"))
    print("取证 dimension_hits =", hits)
    print("取证套话嫌疑/密度 =", ev.get("template_suspect"), ev.get("density"))
    print("LLM下一问 =", r["next_question"]["question"][:80])

    # ── 终评：强制结束触发六维 ECD 评估 + 证据链 ──
    fin = await career_service.end_session(started["session_id"], force=True)
    assessment = fin.get("assessment") or {}
    chain = fin.get("evidence_chain") or []
    dims = assessment.get("dimensions") or {}
    scored = {d: v.get("score") for d, v in dims.items() if v.get("score") is not None}
    result["assessment"] = {
        "source": assessment.get("assessment_source"),
        "overall": assessment.get("overall"),
        "dims_present": sorted(dims.keys()),
        "scores": scored,
        "evidence_chain_len": len(chain),
        "chain_with_quotes": sum(1 for c in chain if c.get("evidence_quotes") or c.get("per_turn_evidence")),
    }
    print("终评 source =", assessment.get("assessment_source"),
          "overall =", assessment.get("overall"))
    print("六维分 =", scored)
    print("证据链条数 =", len(chain))

    # ── 关键断言（修正令：六维齐全 / 0≤score≤5 / 证据链非空）──
    checks = result["checks"]
    checks["scenario_started"] = bool(started.get("session_id"))
    checks["script_has_probe_plan"] = n_probe >= 1
    checks["evidence_collected"] = isinstance(ev, dict) and "density" in ev
    checks["next_question_returned"] = bool(r["next_question"].get("question"))
    checks["six_dims_complete"] = set(dims.keys()) == set(DIMENSIONS)
    checks["scores_in_range"] = all(0 <= float(x) <= 5 for x in scored.values()) if scored else False
    checks["evidence_chain_nonempty"] = len(chain) >= 1
    result["passed"] = all(checks.values())

    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("结果已落盘:", os.path.normpath(RESULT_PATH))
    print("SMOKE DONE, passed =", result["passed"])
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
