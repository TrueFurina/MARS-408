# -*- coding: utf-8 -*-
"""验证脚本：InMemoryVectorStore 持久化三处修复是否真的生效（变异验证）。

覆盖（每条都先构造"修复前会失败"的场景，再断言修复后行为正确）：
  V1 空库守门       —— 内存空集合 + 磁盘实质数据 → 拒绝覆盖，文件大小不变
  V2 np.save 后缀   —— 保存后二进制缓存真实更新，且不遗留 .tmp.*.npy 垃圾
  V3 非结构性异常   —— MemoryError 不移动原文件、不产生 corrupted 备份
  V4 结构性异常     —— JSONDecodeError 才备份，且用 copy2：原文件仍在 + 备份存在

用法：cd py-server && python ../scripts/verify_vectordb_guard.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "py-server")))

from db.milvus_client import InMemoryVectorStore  # noqa: E402

DIM = 768
COLL = "netlearn_kb"
results: list[tuple[str, bool, str]] = []


def _report(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _big_json(path: str, n: int = 400) -> None:
    """写一个 > 1MB 的合法库文件（模拟真实 KB 规模）。"""
    payload = {
        "ids": [f"id-{i}" for i in range(n)],
        "texts": [("知识点内容 " * 40) + str(i) for i in range(n)],
        "metas": [{"subject": "ds", "idx": i} for i in range(n)],
        "embeddings": [[0.01 * ((i + j) % 7) for j in range(DIM)] for i in range(n)],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


# ── V1 空库守门 ─────────────────────────────────────────────────────────────
def v1_empty_overwrite_guard() -> None:
    tmp = tempfile.mkdtemp(prefix="vdb_v1_")
    try:
        store = InMemoryVectorStore(persist_path=tmp)
        target = os.path.join(tmp, f"{COLL}.json")
        _big_json(target)
        before = os.path.getsize(target)
        assert before > 1024 * 1024, f"前置条件失败：测试文件仅 {before} bytes"

        store._ensure_collection(COLL)  # 空集合
        store._save_unlocked(COLL)

        after = os.path.getsize(target)
        _report(
            "V1 空库守门：拒绝以空集合覆盖非空持久化文件",
            after == before and not os.path.exists(target + f".tmp.{os.getpid()}"),
            f"size {before} -> {after}",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── V2 np.save 后缀修复 ─────────────────────────────────────────────────────
def v2_npsave_suffix() -> None:
    tmp = tempfile.mkdtemp(prefix="vdb_v2_")
    try:
        store = InMemoryVectorStore(persist_path=tmp)
        store.add(
            COLL,
            ids=["a", "b", "c"],
            texts=["t1", "t2", "t3"],
            metas=[{"k": 1}, {"k": 2}, {"k": 3}],
            embeddings=[[0.1 * (i + 1)] * DIM for i in range(3)],
            save=True,
        )
        emb_cache = os.path.join(tmp, f"{COLL}.json.emb.npy")
        leftovers = [f for f in os.listdir(tmp) if ".tmp." in f]
        ok_cache = os.path.exists(emb_cache)
        shape_ok = False
        if ok_cache:
            import numpy as np

            arr = np.load(emb_cache)
            shape_ok = arr.shape == (3, DIM)
        _report(
            "V2 np.save 后缀：二进制缓存真实落盘且无 .tmp 残留",
            ok_cache and shape_ok and not leftovers,
            f"cache={ok_cache} shape_ok={shape_ok} tmp残留={leftovers}",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── V3 非结构性异常不移动原文件 ─────────────────────────────────────────────
def v3_nonstructural_no_rename() -> None:
    tmp = tempfile.mkdtemp(prefix="vdb_v3_")
    try:
        store = InMemoryVectorStore(persist_path=tmp)
        target = os.path.join(tmp, f"{COLL}.json")
        _big_json(target, n=50)
        with mock.patch("json.load", side_effect=MemoryError("模拟内存不足")):
            loaded = store._load(COLL)
        still_there = os.path.exists(target)
        backups = [f for f in os.listdir(tmp) if ".corrupted." in f]
        _report(
            "V3 非结构性异常(MemoryError)：原文件保留、无 corrupted 备份",
            (not loaded) and still_there and not backups,
            f"loaded={loaded} 原文件={still_there} 备份={backups}",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── V4 结构性异常 copy2 备份且保留原文件 ────────────────────────────────────
def v4_structural_backup_keeps_original() -> None:
    tmp = tempfile.mkdtemp(prefix="vdb_v4_")
    try:
        store = InMemoryVectorStore(persist_path=tmp)
        target = os.path.join(tmp, f"{COLL}.json")
        _big_json(target, n=50)
        with mock.patch("json.load", side_effect=json.JSONDecodeError("bad", "d", 0)):
            loaded = store._load(COLL)
        original_kept = os.path.exists(target)
        backups = [f for f in os.listdir(tmp) if ".corrupted." in f]
        _report(
            "V4 结构性异常(JSONDecodeError)：copy2 备份 + 原文件保留",
            (not loaded) and original_kept and len(backups) == 1,
            f"loaded={loaded} 原文件={original_kept} 备份数={len(backups)}",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    for fn in (
        v1_empty_overwrite_guard,
        v2_npsave_suffix,
        v3_nonstructural_no_rename,
        v4_structural_backup_keeps_original,
    ):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            _report(fn.__name__, False, f"{type(e).__name__}: {e}")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n{passed}/{len(results)} 通过")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
