#!/usr/bin/env python3
"""重建向量库 netlearn_kb — 只 seed + save，不启动整个后端

背景：vectordb_data/netlearn_kb.json 被git循环会话反复导入中断搞丢了，
只剩 .tmp.NNNN.npy 残留。benchmark 实验1 因 _load 失败跑不了。
本脚本独立执行 main.py 的 _seed_vector_db 逻辑并 _save。

用法: cd py-server && HUGGINGFACE_OFFLINE=1 python rebuild_vectordb.py
"""
import os, sys, time, logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("rebuild_vectordb")

def main():
    from seed_data import SEED_KNOWLEDGE_CHUNKS, SEED_QUESTIONS
    from agents.kg_dag import chapter_to_group
    from db.milvus_client import vector_db

    # vector_db 是抽象层单例（Milvus 优先，InMemoryVectorStore 回退）
    vector_db.connect()
    count = vector_db.count("netlearn_kb")
    logger.info(f"当前 netlearn_kb 文档数: {count}")

    if count > 0:
        logger.info(f"向量库已有 {count} 条，无需重建。如需强制重建请先删除 vectordb_data/netlearn_kb.json")
        vector_db.disconnect()
        return

    # 清理 tmp 残留
    import glob
    tmp_files = glob.glob(str(Path(__file__).parent / "vectordb_data" / "netlearn_kb.json.emb.npy.tmp.*.npy"))
    for tf in tmp_files:
        try:
            os.remove(tf)
        except Exception:
            pass
    logger.info(f"清理 {len(tmp_files)} 个 tmp 残留文件")

    # seed（复刻 main.py _seed_vector_db）
    chunks = []
    for i, chunk in enumerate(SEED_KNOWLEDGE_CHUNKS):
        meta = dict(chunk.get("metadata", {}))
        if "group" not in meta:
            meta["group"] = chapter_to_group(meta.get("subject", ""), meta.get("chapter"))
        chunks.append({
            "id": f"chunk_{i}",
            "text": chunk["content"],
            "metadata": meta,
        })
    for i, q in enumerate(SEED_QUESTIONS):
        chunks.append({
            "id": f"question_{i}",
            "text": f"[{q['type']}] {q['text']} 答案: {q['answer']} 来源: {q['source']}",
            "metadata": {
                "subject": q["subject"], "chapter": q["chapter"],
                "group": chapter_to_group(q["subject"], q.get("chapter")),
                "type": "question", "difficulty": q["difficulty"],
                "question_id": q["id"],
            },
        })

    logger.info(f"准备写入 {len(chunks)} 个文档（{len(SEED_KNOWLEDGE_CHUNKS)} chunks + {len(SEED_QUESTIONS)} questions）")
    t0 = time.perf_counter()
    inserted = vector_db.insert("netlearn_kb", chunks)
    elapsed = time.perf_counter() - t0
    logger.info(f"写入完成: 插入 {inserted} 个文档，耗时 {elapsed:.1f}s")

    count = vector_db.count("netlearn_kb")
    logger.info(f"向量库已保存，最终文档数: {count}")
    vector_db.disconnect()

    # 验证文件
    json_path = Path(__file__).parent / "vectordb_data" / "netlearn_kb.json"
    if json_path.exists():
        size_mb = json_path.stat().st_size / 1024 / 1024
        logger.info(f"✅ netlearn_kb.json 已生成: {size_mb:.1f}MB")
    else:
        logger.error(f"❌ netlearn_kb.json 未生成")

if __name__ == "__main__":
    main()
