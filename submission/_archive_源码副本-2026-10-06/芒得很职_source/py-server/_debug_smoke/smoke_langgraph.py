"""LangGraph 完整流水线冒烟测试（直调 agent_graph，绕开 HTTP/鉴权）。
验证 10 节点全链路 + ppt_file 真产出 + 无空壳异常。"""
import sys, os, asyncio, time, json
# 复刻 main.py 启动期环境（HF 离线 + .env），否则 bge-reranker 会连 HF 超时卡死
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
sys.path.insert(0, os.getcwd())
from config import _load_dotenv
_load_dotenv()

async def main():
    from agents.graph import agent_graph
    from db.milvus_client import vector_db
    vector_db.connect()
    kb_count = vector_db.count("netlearn_kb")
    print(f"=== KB 已连接，netlearn_kb count={kb_count} ===", flush=True)
    state = {
        "messages": [], "user_request": "讲解TCP三次握手的过程和意义",
        "student_profile": {"knowledge_base":"beginner","learning_style":"reading","weak_points":"三次握手序列号变化"},
        "topic": "TCP三次握手", "difficulty": "medium", "course": "computer_network",
        "diagnosis": None, "plan": None, "retrieved_chunks": None,
        "teacher_doc": None, "quiz": None, "media_plan": None, "extension": None,
        "mindmap": None, "code_practice": None, "ppt_outline": None, "video_script": None,
        "consensus": None, "critic_report": None, "evidence_report": None,
        "current_agent": "coordinator", "error": None, "status": "coordinating",
        "regenerate_round": 0,
    }
    merged = {}
    nodes_seen = []
    t0 = time.time()
    print("=== LangGraph 冒烟启动: topic=TCP三次握手 ===", flush=True)
    try:
        async for event in agent_graph.astream(state, stream_mode="updates"):
            for node, upd in event.items():
                nodes_seen.append(node)
                merged.update(upd)
                nonnull = [k for k in upd if upd.get(k) is not None]
                print(f"[{time.time()-t0:5.1f}s] {node}: {nonnull[:10]}", flush=True)
    except Exception as e:
        print(f"!!! PIPELINE EXCEPTION: {type(e).__name__}: {e}", flush=True)
        import traceback; traceback.print_exc()
        return
    print("=== PIPELINE DONE ===", flush=True)
    print(f"nodes_seen({len(nodes_seen)}): {nodes_seen}", flush=True)
    print(f"total_time: {time.time()-t0:.1f}s", flush=True)
    # 关键产物核验
    pf = merged.get("ppt_file")
    print("PPT_FILE_OK=", bool(pf and pf.get("ok")), "FILE=", (pf or {}).get("filename"), "SLIDES=", (pf or {}).get("slide_count"), flush=True)
    cs = merged.get("consensus") or {}
    print("CONSENSUS_STATUS=", cs.get("status"), "SCORE=", cs.get("overall_score"), flush=True)
    print("EVIDENCE_PRESENT=", merged.get("evidence_report") is not None, flush=True)
    print("CRITIC_PRESENT=", merged.get("critic_report") is not None, flush=True)
    # 路径规划产物（实际写入 state["path_plan"]，含 KG-DAG 拓扑序列 kg_ordered_chapters）
    path_plan = merged.get("path_plan") or {}
    kg_chapters = path_plan.get("kg_ordered_chapters") or []
    kg_weak = path_plan.get("kg_weak_groups") or []
    source = path_plan.get("planning_source", "n/a")
    print("PATH_PLAN_PRESENT=", bool(path_plan), "PLANNING_SOURCE=", source, flush=True)
    print("PATH_KG_CHAPTERS=", len(kg_chapters), "PATH_KG_WEAK_GROUPS=", len(kg_weak), flush=True)
    # PATH_LEN 反映 KG-DAG 拓扑章节序列长度（演示数据下应为 26 个 group 的全序，非空）
    print("PATH_LEN=", len(kg_chapters), flush=True)
    print("ERROR=", merged.get("error"), flush=True)

asyncio.run(main())
