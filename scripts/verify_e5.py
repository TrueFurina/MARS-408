#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""校验本地 E5（intfloat/e5-base-v2）是否真正可用。

用于回答"向量检索到底走真 E5 还是 BM25 降级"这一诚信问题：
本脚本只做一件事——用本地目录加载模型并对中文文本编码，输出维度/范数/示例相似度。

用法（在 py-server 目录下）：
    py-server/.venv/Scripts/python.exe ../scripts/verify_e5.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY_SERVER = HERE.parent / "py-server"
MODEL_DIR = PY_SERVER / "models" / "e5-base-v2"

sys.path.insert(0, str(PY_SERVER))


def main() -> int:
    if not MODEL_DIR.is_dir():
        print(f"[verify-e5] FAIL: 模型目录不存在 {MODEL_DIR}")
        return 2

    weights = [p for p in MODEL_DIR.iterdir() if p.is_file() and p.suffix in {".bin", ".safetensors"}]
    if not weights:
        print(f"[verify-e5] FAIL: 未找到权重文件（pytorch_model.bin / model.safetensors）")
        return 2

    for w in weights:
        print(f"[verify-e5] 权重: {w.name} ({w.stat().st_size / 1e6:.1f} MB)")

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    import numpy as np
    from sentence_transformers import SentenceTransformer

    print("[verify-e5] 加载中（CPU，首次约 10-30s）...")
    model = SentenceTransformer(str(MODEL_DIR))
    dim = model.get_sentence_embedding_dimension()
    print(f"[verify-e5] 加载完成，维度 = {dim}")

    probes = [
        "三次握手的过程是什么",
        "TCP 连接建立需要几个报文",
        "红黑树的插入调整",
    ]
    vecs = model.encode(probes, normalize_embeddings=True)
    vecs = np.asarray(vecs, dtype=np.float32)
    print(f"[verify-e5] encode shape = {vecs.shape}")

    norms = np.linalg.norm(vecs, axis=1)
    print(f"[verify-e5] L2 范数 = {[round(float(n), 4) for n in norms]}")

    sim_related = float(vecs[0] @ vecs[1])
    sim_unrelated = float(vecs[0] @ vecs[2])
    print(f"[verify-e5] sim(三次握手, TCP建连) = {sim_related:.4f}")
    print(f"[verify-e5] sim(三次握手, 红黑树)   = {sim_unrelated:.4f}")

    ok = dim == 768 and abs(float(norms[0]) - 1.0) < 1e-3 and sim_related > sim_unrelated
    if ok:
        print("[verify-e5] OK — 语义可分辨，向量检索具备恢复条件")
        return 0
    print("[verify-e5] FAIL — 维度/归一化/语义分辨有异常")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
