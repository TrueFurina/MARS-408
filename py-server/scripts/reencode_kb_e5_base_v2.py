#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向量库重编码脚本 —— 把 netlearn_kb 的 embedding 用指定 E5 模型全量重算。

背景
----
实机 175.178.234.11 上的 2245 条向量是用 multilingual-e5-base 重算的，而：
  - 训练脚本 train_mixer_real_v2.py / train_mixer_real.py 用的是 e5-base-v2；
  - 本地仓库 netlearn_kb.json 是 e5-base-v2 编码（重编码余弦 +1.0000）；
  - gomarl_mixer / benchmark_2026-10-08.json 均指向 e5-base-v2。
config.py 的 DEFAULTS 误用 multilingual 是偏离，故推荐把全链路对齐到 e5-base-v2。

本脚本只做「重编码」这一件事，不改任何业务代码：
  1. 备份 netlearn_kb.json 与 .emb.npy；
  2. 用目标模型对已落盘的 texts 重新算 embedding；
  3. 回写 JSON 的 embeddings 字段，并**同步覆盖 .emb.npy 缓存**
     （否则 _load 优先读 .npy，会用回旧向量）；
  4. 不动 collection 名、不动 metadata、不动业务逻辑。

配置切换（embedding.model）是独立步骤，见 docs/E5模型选型与向量库重编码方案.md，
不要在跑本脚本之前切配置——本脚本通过 monkeypatch config.get_embedding_config
强制目标模型，与部署配置解耦，避免误伤。

用法
----
  #  dry-run：只校验可读、统计条数、抽 3 条重编码看是否真发生变化（不写盘）
  python scripts/reencode_kb_e5_base_v2.py --dry-run

  #  正式执行（默认目标 intfloat/e5-base-v2）
  python scripts/reencode_kb_e5_base_v2.py

  #  指定其它模型 / 指定 KB 文件
  python scripts/reencode_kb_e5_base_v2.py --model intfloat/multilingual-e5-base --kb vectordb_data/netlearn_kb.json
"""

import argparse
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEFAULT_MODEL = "intfloat/e5-base-v2"
DEFAULT_KB = os.path.join(ROOT, "vectordb_data", "netlearn_kb.json")


def force_target_model(model: str):
    """monkeypatch config.get_embedding_config，让 embedder 加载目标模型。

    与部署配置解耦：本脚本不读也不改部署用的 config.json，避免误伤其它环境。

    关键修复：同时把 local_model_repo 指到部署约定目录
    ``py-server/models/<model_basename>``（与 deploy/start_linux.sh 的 MODEL_DIR 一致）。
    否则原 config 的 local_model_repo 仍指向 multilingual 目录，且未设本地目录时
    SentenceTransformer 会去联网下载 e5-base-v2——服务器若无外网/未预打包会中途失败。
    该目录不存在时 embedder 仍会回退到 SentenceTransformer(model_name) 联网拉取。
    """
    import config

    _orig = config.get_embedding_config
    model_basename = model.split("/")[-1]
    local_repo = os.path.join(ROOT, "models", model_basename)

    def _patched():
        base = _orig() if callable(_orig) else {}
        base = dict(base)
        base["model"] = model
        base["dimension"] = 768
        base["local_model_repo"] = local_repo
        return base

    config.get_embedding_config = _patched
    print(f"[info] 目标模型={model}  local_model_repo={local_repo}"
          f"({'存在' if os.path.isdir(local_repo) else '不存在→回退联网'})")
    return config


def main():
    ap = argparse.ArgumentParser(description="netlearn_kb 向量重编码（e5-base-v2 默认）")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"目标 E5 模型（默认 {DEFAULT_MODEL}）")
    ap.add_argument("--kb", default=DEFAULT_KB, help="netlearn_kb.json 路径")
    ap.add_argument("--dry-run", action="store_true", help="只校验与抽样，不写盘")
    args = ap.parse_args()

    kb_path = os.path.abspath(args.kb)
    npy_path = kb_path + ".emb.npy"
    if not os.path.exists(kb_path):
        sys.exit(f"[FATAL] 找不到 KB 文件: {kb_path}")

    # 1) 强制目标模型后再导入 embedder（embed_batch 在调用时才读 config，故 patch 生效）
    force_target_model(args.model)
    from db import embedder  # noqa: E402  (import after patch 才吃得到目标模型)
    from db.embedder import embed_batch  # noqa: E402

    # 2) 读盘
    t0 = time.time()
    with open(kb_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    texts = data.get("texts", [])
    old_embs = data.get("embeddings") or []
    n = len(texts)
    print(f"[info] KB={kb_path}")
    print(f"[info] 条目数={n}  已有 embeddings 数={len(old_embs)}")
    if n == 0:
        sys.exit("[FATAL] texts 为空，中止（防止误清空向量库）")
    if len(old_embs) not in (0, n):
        sys.exit(f"[FATAL] embeddings 长度 {len(old_embs)} 与 texts {n} 不一致，结构异常，中止")

    # 3) 抽样重编码，确认目标模型确实会产出不同向量（dry-run 也跑这步）
    sample_idx = list(range(0, min(3, n)))
    sample_vecs = embed_batch([texts[i] for i in sample_idx])
    print(f"[info] 目标模型={embedder._effective_model_name()}  抽样重编码 {len(sample_vecs)} 条 OK")

    if args.dry_run:
        # 与旧向量比对，确认“真的发生了变化”
        if old_embs:
            import numpy as np
            for i, idx in enumerate(sample_idx):
                ov = np.asarray(old_embs[idx], dtype=np.float32)
                nv = np.asarray(sample_vecs[i], dtype=np.float32)
                cos = float(np.dot(ov, nv) / (np.linalg.norm(ov) * np.linalg.norm(nv) + 1e-9))
                print(f"  sample[{idx}] cos(old,new) = {cos:.4f}  (≠1 表示模型已切换)")
        print("[dry-run] 未写盘，退出。去掉 --dry-run 执行正式重编码。")
        return

    # 4) 全量重编码
    print(f"[info] 全量重编码 {n} 条（可能较慢，取决于模型加载与硬件）...")
    new_vecs = embed_batch(texts)
    if len(new_vecs) != n:
        sys.exit(f"[FATAL] 重编码返回 {len(new_vecs)} 条，期望 {n}，中止")

    # 5) 备份（写盘前）
    ts = time.strftime("%Y%m%d_%H%M%S")
    shutil.copy2(kb_path, kb_path + f".bak_{ts}")
    if os.path.exists(npy_path):
        shutil.copy2(npy_path, npy_path + f".bak_{ts}")
    print(f"[info] 已备份: {kb_path}.bak_{ts}  /  {npy_path}.bak_{ts}")

    # 6) 回写 JSON embeddings
    import numpy as np
    arr = np.asarray(new_vecs, dtype=np.float32)
    data["embeddings"] = arr.tolist()
    with open(kb_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    # 7) 同步覆盖 .emb.npy 缓存（关键：否则 _load 优先读 .npy 用回旧向量）
    np.save(npy_path, arr)

    dt = time.time() - t0
    print(f"[done] 重编码完成 {n} 条，耗时 {dt:.1f}s")
    print(f"[done] 已写回 {kb_path} 与其 .emb.npy 缓存")
    print("[next] 现在请按方案切 config embedding.model 并重启后端，再核验 /api/status 与 top1_score")


if __name__ == "__main__":
    main()
