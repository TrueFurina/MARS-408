"""独立播种向量知识库 netlearn_kb（复用 main.py 启动期逻辑）。
让 RAG 检索在 demo/冒烟时真正有知识可检索。"""
import sys, os
sys.path.insert(0, os.getcwd())

from seed_data import SEED_KNOWLEDGE_CHUNKS, SEED_QUESTIONS
from agents.kg_dag import chapter_to_group
from db.milvus_client import vector_db

vector_db.connect()
print(f"播种前 count(netlearn_kb) = {vector_db.count('netlearn_kb')}", flush=True)

chunks = []
for i, chunk in enumerate(SEED_KNOWLEDGE_CHUNKS):
    meta = dict(chunk.get("metadata", {}))
    if "group" not in meta:
        meta["group"] = chapter_to_group(meta.get("subject", ""), meta.get("chapter"))
    chunks.append({"id": f"chunk_{i}", "text": chunk["content"], "metadata": meta})

for i, q in enumerate(SEED_QUESTIONS):
    chunks.append({
        "id": f"question_{i}",
        "text": f"[{q['type']}] {q['text']} 答案: {q['answer']} 来源: {q['source']}",
        "metadata": {
            "subject": q["subject"], "chapter": q["chapter"],
            "group": chapter_to_group(q["subject"], q.get("chapter")),
            "type": "question", "difficulty": q["difficulty"], "question_id": q["id"],
        },
    })

print(f"待插入 {len(chunks)} 条 (chunks={len(SEED_KNOWLEDGE_CHUNKS)} + questions={len(SEED_QUESTIONS)})，开始 embedding...", flush=True)
inserted = vector_db.insert("netlearn_kb", chunks)
print(f"插入完成: inserted={inserted}", flush=True)
print(f"播种后 count(netlearn_kb) = {vector_db.count('netlearn_kb')}", flush=True)
vector_db.disconnect()
print("DONE", flush=True)
