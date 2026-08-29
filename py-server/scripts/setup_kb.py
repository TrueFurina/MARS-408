#!/usr/bin/env python3
# ============================================================
# 一键恢复知识库（E5 模型 + 向量库）
#
# 背景：会话间非 git 提交产物会被清空——venv、models/e5-base-v2、
#       vectordb_data/netlearn_kb.json(.emb.npy) 全丢，只剩 .tmp 残留。
#       本脚本把"恢复 KB"做成可重复执行的一步操作，联网时即可重建：
#         1. 确保 E5 (intfloat/e5-base-v2, 768维) 落在 models/e5-base-v2
#            （缺失则从 HuggingFace 下载；离线则给出清晰指引并退出）
#         2. 重建向量库 netlearn_kb（复用 rebuild_vectordb.main 的 seed 逻辑）
#         3. 校验：向量矩阵形状 (N,768) 且零向量数为 0（诚实红线：不得有零向量）
#
# 用法（在 py-server 目录下，且已重建 venv 并 pip install -r requirements.txt）:
#     python scripts/setup_kb.py            # 模型缺失则下载；已存在则跳过
#     python scripts/setup_kb.py --force    # 忽略已有模型，强制重新下载
#     python scripts/setup_kb.py --skip-model  # 假定模型已在位，只重建向量库
#
# 注意：本脚本只负责"恢复持久产物"，不替代正常后端启动。
#       真实 E5 推理需 sentence-transformers + torch（见 requirements.txt）。
# ============================================================
import argparse
import os
import sys
import time
import logging
from pathlib import Path

# 将 py-server 根目录加入 sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("setup_kb")

EMBED_MODEL_NAME = "intfloat/e5-base-v2"
EMBED_DIM = 768
MODEL_DIR = ROOT / "models" / "e5-base-v2"
VECTOR_DIR = ROOT / "vectordb_data"


def _model_files_present(model_dir: Path) -> bool:
    """判断模型目录是否已含有效 E5 文件（config.json + 权重 + tokenizer）。"""
    if not model_dir.is_dir():
        return False
    required = ["config.json", "tokenizer.json", "model.safetensors"]
    safetensors = (model_dir / "model.safetensors").exists()
    bin_weights = (model_dir / "pytorch_model.bin").exists()
    has_weights = safetensors or bin_weights
    return (
        (model_dir / "config.json").exists()
        and (model_dir / "tokenizer.json").exists()
        and has_weights
    )


def _provision_model(force: bool) -> bool:
    """确保 E5 模型在位；缺失则下载。返回 True 表示模型可用。"""
    if MODEL_DIR.exists() and _model_files_present(MODEL_DIR) and not force:
        logger.info(f"✅ E5 模型已就位: {MODEL_DIR}")
        return True

    if MODEL_DIR.exists() and not _model_files_present(MODEL_DIR):
        logger.warning(f"模型目录存在但不完整: {MODEL_DIR}，将重新下载")

    logger.info(f"准备下载 {EMBED_MODEL_NAME} → {MODEL_DIR}")
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        logger.error(
            "❌ 缺少 huggingface_hub（pip install huggingface_hub），无法下载模型。"
        )
        return False

    # 允许联网下载（覆盖可能的离线环境变量）
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_download(
            repo_id=EMBED_MODEL_NAME,
            local_dir=str(MODEL_DIR),
            local_dir_use_symlinks=False,
        )
    except Exception as e:  # 网络受限 / 无 token / 代理失败
        logger.error("❌ E5 模型下载失败: %s", e)
        logger.error(
            "离线恢复方案：手动把 e5-base-v2 整目录放到 %s\n"
            "（来源：https://huggingface.co/%s ，或团队共享的内部镜像）。",
            MODEL_DIR, EMBED_MODEL_NAME,
        )
        return False

    if not _model_files_present(MODEL_DIR):
        logger.error("❌ 下载完成但关键文件缺失，请检查 %s", MODEL_DIR)
        return False
    logger.info(f"✅ E5 模型下载完成: {MODEL_DIR}")
    return True


def _rebuild_vectordb() -> bool:
    """重建向量库（复用 rebuild_vectordb.main，只 seed+save 不启动后端）。"""
    try:
        import rebuild_vectordb
    except Exception as e:
        logger.error("❌ 无法导入 rebuild_vectordb: %s", e)
        return False
    try:
        rebuild_vectordb.main()
    except Exception as e:
        logger.error("❌ 重建向量库失败: %s", e)
        return False
    return True


def _verify() -> dict:
    """校验向量库产物：形状与零向量数。返回统计 dict。"""
    npy_path = VECTOR_DIR / "netlearn_kb.json.emb.npy"
    stats = {"npy_exists": npy_path.exists()}
    if not npy_path.exists():
        logger.error("❌ 向量矩阵缺失: %s", npy_path)
        return stats
    try:
        import numpy as np
        arr = np.load(str(npy_path))
        n_zero = int(np.sum(np.all(arr == 0, axis=1)))
        stats["shape"] = list(arr.shape)
        stats["n_vectors"] = int(arr.shape[0])
        stats["dim"] = int(arr.shape[1]) if arr.ndim == 2 else None
        stats["n_zero_vectors"] = n_zero
        logger.info(
            f"向量库校验: shape={arr.shape}, 零向量={n_zero}"
        )
        if arr.ndim != 2 or arr.shape[1] != EMBED_DIM:
            logger.error(f"❌ 维度异常（应为 768），实际 {arr.shape}")
            stats["ok"] = False
        elif n_zero > 0:
            logger.error(f"❌ 存在 {n_zero} 条零向量（诚信红线：不得有零向量）")
            stats["ok"] = False
        else:
            logger.info("✅ 向量库校验通过：维度正确且无零向量")
            stats["ok"] = True
    except Exception as e:
        logger.error("❌ 校验出错: %s", e)
        stats["ok"] = False
    return stats


def main():
    ap = argparse.ArgumentParser(description="一键恢复 MARS-408 知识库 (E5 + 向量库)")
    ap.add_argument("--force", action="store_true", help="强制重新下载 E5 模型")
    ap.add_argument("--skip-model", action="store_true", help="假定模型已在位，跳过模型检查/下载")
    args = ap.parse_args()

    t0 = time.perf_counter()
    model_ok = True
    if not args.skip_model:
        model_ok = _provision_model(force=args.force)
        if not model_ok:
            logger.error("模型不可用，中止（向量库需 E5 才能构建）。")
            sys.exit(2)

    rebuilt = _rebuild_vectordb()
    if not rebuilt:
        sys.exit(3)

    stats = _verify()
    elapsed = time.perf_counter() - t0
    logger.info(f"总耗时 {elapsed:.1f}s")
    if not stats.get("ok"):
        sys.exit(4)
    logger.info("🎉 KB 恢复完成")


if __name__ == "__main__":
    main()
