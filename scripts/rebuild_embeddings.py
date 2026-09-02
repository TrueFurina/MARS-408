#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""用本地 E5 重建 netlearn_kb 向量库（当前 2113 条全为 fallback_zero 零向量）。

背景（2026-09-02 实测）：
  vectordb_data/netlearn_kb.json 内 2113 条向量 L2 范数全为 0，meta 中自标记
  `embedding_status == "fallback_zero"`；检索路径（db/milvus_client.py）
  会主动排除该类条目 —— 即向量分支实际空转，线上效果全靠 BM25 降级。

本脚本在 E5 本地化（models/e5-base-v2）之后把零向量替换为真 768 维嵌入：
  - 原文件先**复制备份**到 vectordb_data/_backup/（红线：只追加、不删除）
  - 同时更新 JSON 真源（embeddings + metas.embedding_status）与 .emb.npy 缓存
  - 写入采用 tmp + os.replace 原子替换，避免半写文件

用法（在 py-server 目录下）：
    .venv/Scripts/python.exe ../scripts/rebuild_embeddings.py [--prefix] [--limit N]
      --prefix  为 passage 文本加 "passage: " 前缀（e5 官方推荐，检索时 query 需对应加 "query: "）
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY_SERVER = HERE.parent / "py-server"
KB_DIR = PY_SERVER / "vectordb_data"
KB_JSON = KB_DIR / "netlearn_kb.json"
KB_NPY = KB_DIR / "netlearn_kb.json.emb.npy"
MODEL_DIR = PY_SERVER / "models" / "e5-base-v2"
BACKUP_DIR = KB_DIR / "_backup"

sys.path.insert(0, str(PY_SERVER))

STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")


def backup() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for src in (KB_JSON, KB_NPY):
        if src.exists():
            dst = BACKUP_DIR / f"{src.name}.zerovec-{STAMP}.bak"
            shutil.copy2(src, dst)
            print(f"[backup] {src.name} -> {dst.name} ({src.stat().st_size / 1e6:.1f} MB)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefix", action="store_true", help='passage 文本加 "passage: " 前缀')
    ap.add_argument("--limit", type=int, default=0, help="只编码前 N 条（调试用）")
    args = ap.parse_args()

    if not MODEL_DIR.is_dir():
        print(f"[rebuild] FAIL: 本地 E5 不存在 {MODEL_DIR}")
        return 2
    if not KB_JSON.exists():
        print(f"[rebuild] FAIL: 语料不存在 {KB_JSON}")
        return 2

    import numpy as np

    kb = json.load(open(KB_JSON, encoding="utf-8"))
    texts: list[str] = kb["texts"]
    ids = kb["ids"]
    metas = kb["metas"]
    if args.limit:
        texts, ids, metas = texts[: args.limit], ids[: args.limit], metas[: args.limit]
    print(f"[rebuild] 语料 {len(texts)} 条（prefix={args.prefix}）")

    # --limit 为干跑验证，不写盘、也不产生备份副本
    if not args.limit:
        backup()

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from sentence_transformers import SentenceTransformer

    t0 = time.time()
    model = SentenceTransformer(str(MODEL_DIR))
    print(f"[rebuild] 模型加载 {time.time() - t0:.1f}s，维度 {model.get_sentence_embedding_dimension()}")

    inputs = [f"passage: {t}" for t in texts] if args.prefix else texts
    t1 = time.time()
    vecs = model.encode(
        inputs,
        batch_size=32,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    vecs = np.asarray(vecs, dtype=np.float32)
    dt = time.time() - t1
    print(f"[rebuild] 编码完成 {vecs.shape}，耗时 {dt:.1f}s（{len(texts) / max(dt, 1e-9):.1f} 条/秒）")

    norms = np.linalg.norm(vecs, axis=1)
    zero_cnt = int((norms < 1e-6).sum())
    print(f"[rebuild] 零向量数 = {zero_cnt} / {len(vecs)}（应为 0）")
    if zero_cnt:
        print("[rebuild] ABORT: 仍存在零向量，不写入")
        return 3
    print(f"[rebuild] 范数 min={norms.min():.4f} max={norms.max():.4f} mean={norms.mean():.4f}")

    # ── 更新 meta 状态（检索路径据此排除 fallback_zero）──
    # 只对本次参与编码的条目更新；limit 场景下保持其余不变
    full_metas = kb["metas"]
    for i in range(len(ids)):
        full_metas[i]["embedding_status"] = "e5_real"
        full_metas[i]["embedding_model"] = "intfloat/e5-base-v2"
        full_metas[i]["embedding_prefix"] = "passage" if args.prefix else "none"
        full_metas[i]["embedded_at"] = STAMP

    # JSON 真源：写入真向量（保留 4 位小数压缩体积）
    if args.limit:
        print("[rebuild] --limit 模式：跳过写盘（仅验证）")
        return 0
    kb["embeddings"] = [[round(float(x), 4) for x in row] for row in vecs.tolist()]

    tmp_json = KB_JSON.with_suffix(f".json.tmp.{os.getpid()}")
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False)
    os.replace(tmp_json, KB_JSON)
    print(f"[rebuild] JSON 已更新 {KB_JSON.stat().st_size / 1e6:.1f} MB")

    tmp_npy = KB_NPY.with_suffix(f".npy.tmp.{os.getpid()}")
    np.save(tmp_npy, vecs)
    os.replace(tmp_npy, KB_NPY)
    print(f"[rebuild] NPY 缓存已更新 {KB_NPY.stat().st_size / 1e6:.1f} MB")

    print("[rebuild] DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
