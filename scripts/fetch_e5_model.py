#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""离线/镜像下载 intfloat/e5-base-v2 到本地 models/e5-base-v2。

背景：本沙箱直连 huggingface.co 不可达（HTTP 000 / exit 7），但 hf-mirror.com
镜像可达（实测 200）。本脚本默认走镜像端点，允许用 HF_ENDPOINT 覆盖。

用法（在 py-server 目录下执行 venv python）：
    py-server/.venv/Scripts/python.exe ../scripts/fetch_e5_model.py

只做下载与完整性校验，不改动任何既有文件（红线：只追加、不删除）。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ID = "intfloat/e5-base-v2"
# e5 推理所需最小文件集；排除 .msgpack/.h5/flax/tf 等无用大件
ALLOW_PATTERNS = [
    "config.json",
    "pytorch_model.bin",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "special_tokens_map.json",
    "modules.json",
    "sentence_bert_config.json",
    "1_Pooling/config.json",
]
REQUIRED = ["config.json", "vocab.txt", "tokenizer.json"]


def main() -> int:
    # 目标目录：py-server/models/e5-base-v2（与 config.json 的 embedding 配置对齐）
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    target = repo_root / "py-server" / "models" / "e5-base-v2"

    endpoint = os.environ.get("HF_ENDPOINT") or "https://hf-mirror.com"
    os.environ["HF_ENDPOINT"] = endpoint
    # 镜像站不需要 HF_TOKEN，但保留用户既有值
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    # 关键：huggingface_hub>=0.30 默认走 Xet 存储后端（cas-server.xethub.hf.co），
    # 该域名在本沙箱不可达（401/超时）。禁用后回退到常规 HTTP 直连下载。
    os.environ["HF_HUB_DISABLE_XET"] = "1"

    print(f"[fetch-e5] endpoint = {endpoint}")
    print(f"[fetch-e5] target   = {target}")

    target.mkdir(parents=True, exist_ok=True)

    from huggingface_hub import snapshot_download  # 延迟导入，失败信息更清晰

    t0 = time.time()
    try:
        path = snapshot_download(
            repo_id=REPO_ID,
            local_dir=str(target),
            allow_patterns=ALLOW_PATTERNS,
            max_workers=4,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[fetch-e5] FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    dt = time.time() - t0
    print(f"[fetch-e5] downloaded to {path} in {dt:.1f}s")

    files = sorted(p.name for p in target.iterdir() if p.is_file())
    print("[fetch-e5] files:")
    for name in files:
        size = (target / name).stat().st_size
        print(f"  - {name} ({size / 1e6:.2f} MB)")

    missing = [r for r in REQUIRED if not (target / r).exists()]
    has_weight = (target / "pytorch_model.bin").exists() or (
        target / "model.safetensors"
    ).exists()
    if missing or not has_weight:
        print(f"[fetch-e5] INCOMPLETE missing={missing} weight={has_weight}")
        return 3

    print("[fetch-e5] OK — 最小可用文件集齐全")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
