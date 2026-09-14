# -*- coding: utf-8 -*-
"""一次性修复脚本：InMemoryVectorStore 持久化三处缺陷（INC-2026-09-14）

背景（落盘反查，非推测）：
  1) 读路径无锁：多个 Python 进程（并发 pytest / 多 worker）同时加载与保存同一
     JSON，会读到半截文件 → 抛异常 → 旧容错用 os.rename 把主文件"搬走" →
     系统以空库启动。磁盘实证：vectordb_data/ 下累积多个
     netlearn_kb.json.corrupted.<ts>，主文件一度消失。
  2) 容错过宽且带破坏性：任何异常（MemoryError / OSError / 并发竞争）都会
     触发 rename，把完好的主库误判为"损坏"并移走。
  3) np.save(str) 会自动追加 ".npy" 后缀，使随后的 os.replace(emb_tmp, ...)
     找不到文件 → 二进制缓存从未成功更新，且每次保存遗留 6.5MB 垃圾。

修复（全部为非破坏性加固，不改变正常路径行为）：
  A. _load 复用写锁文件做读写互斥（读锁），并将主体下沉为 _load_unlocked；
  B. 异常分支：只有真正的结构/解析错误才备份，且用 shutil.copy2（主文件永存），
     其余故障仅告警、绝不移动原文件；
  C. np.save 改为显式二进制文件句柄写入；
  D. _save_unlocked 增加"空库覆盖守门"：内存集合为空而磁盘已存在实质数据时
     拒绝写入，防止"加载失败→空库→_save 覆盖"把真数据清零。

用法：python scripts/fix_vectordb_load_guard.py [--apply]
默认 dry-run，加 --apply 才写盘。
"""
from __future__ import annotations

import io
import os
import sys

TARGET = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "py-server",
    "db",
    "milvus_client.py",
)

# ── 补丁 1：np.save 后缀 bug ────────────────────────────────────────────────
OLD_NPSAVE = (
    '                emb_tmp = emb_path + f".tmp.{os.getpid()}"\n'
    "                np.save(emb_tmp, np.asarray(coll[\"embeddings\"], dtype=np.float32))\n"
    "                os.replace(emb_tmp, emb_path)\n"
)
NEW_NPSAVE = (
    '                emb_tmp = emb_path + f".tmp.{os.getpid()}"\n'
    "                # INC-2026-09-14: np.save(str) 会自动追加 \".npy\" 后缀，导致随后\n"
    "                # os.replace(emb_tmp, ...) 找不到文件，二进制缓存从未真正更新，\n"
    "                # 且每次保存遗留一个 6.5MB 垃圾文件。改用显式句柄写，路径可控。\n"
    "                with open(emb_tmp, \"wb\") as _emb_f:\n"
    "                    np.save(_emb_f, np.asarray(coll[\"embeddings\"], dtype=np.float32))\n"
    "                os.replace(emb_tmp, emb_path)\n"
)

# ── 补丁 2：空库覆盖守门 ────────────────────────────────────────────────────
OLD_SAVE_HEAD = (
    "        coll = self._collections[name]\n"
    "        filepath = os.path.join(self._persist_path, f\"{name}.json\")\n"
    '        tmppath = filepath + f".tmp.{os.getpid()}"\n'
)
NEW_SAVE_HEAD = (
    "        coll = self._collections[name]\n"
    "        filepath = os.path.join(self._persist_path, f\"{name}.json\")\n"
    "        # INC-2026-09-14 空库覆盖守门：内存集合为空而磁盘已存在实质数据时拒绝写入。\n"
    "        # 这挡住「加载失败 → 空库启动 → _save 覆盖」这条把真库清零的链路。\n"
    "        if len(coll[\"ids\"]) == 0 and os.path.exists(filepath):\n"
    "            try:\n"
    "                _disk_size = os.path.getsize(filepath)\n"
    "            except OSError:\n"
    "                _disk_size = 0\n"
    "            if _disk_size > _EMPTY_OVERWRITE_GUARD_BYTES:\n"
    "                logger.error(\n"
    "                    \"InMemoryVectorStore 拒绝以空集合覆盖非空持久化文件: %s (%d bytes)\\n\"\n"
    "                    \"  通常意味着上游加载失败导致空库启动，已阻止数据清零。\",\n"
    "                    filepath,\n"
    "                    _disk_size,\n"
    "                )\n"
    "                return\n"
    '        tmppath = filepath + f".tmp.{os.getpid()}"\n'
)

# ── 补丁 3a：_load 改为加锁包装 ─────────────────────────────────────────────
OLD_LOAD_HEAD = (
    "    def _load(self, name: str) -> bool:\n"
    "        \"\"\"从 JSON 加载（损坏时自动备份原文件并降级为空库，防止静默数据覆盖）\"\"\"\n"
    "        filepath = os.path.join(self._persist_path, f\"{name}.json\")\n"
    "        if not os.path.exists(filepath):\n"
    "            return False\n"
    "        try:\n"
)
NEW_LOAD_HEAD = (
    "    def _load(self, name: str) -> bool:\n"
    "        \"\"\"从 JSON 加载（读锁保护；任何异常都不移动/删除原文件）\n"
    "\n"
    "        INC-2026-09-14: 读路径原先无锁。多个 Python 进程（并发 pytest / 多 worker）\n"
    "        同时加载与保存同一 JSON 会读到半截文件，进而触发旧逻辑的\"损坏\"误判并把\n"
    "        主文件 rename 走。这里复用写锁文件做读写互斥，保证加载期间无并发写入。\n"
    "        \"\"\"\n"
    "        filepath = os.path.join(self._persist_path, f\"{name}.json\")\n"
    "        if not os.path.exists(filepath):\n"
    "            return False\n"
    "        if self._file_lock is None:\n"
    "            return self._load_unlocked(name, filepath)\n"
    "        try:\n"
    "            with self._file_lock:\n"
    "                return self._load_unlocked(name, filepath)\n"
    "        except filelock.Timeout:\n"
    "            logger.error(\n"
    "                \"InMemoryVectorStore 读锁获取超时(30s)，跳过本次加载: %s\\n\"\n"
    "                \"  若频繁出现，请检查是否有进程长时间持有写锁。\",\n"
    "                name,\n"
    "            )\n"
    "            return False\n"
    "\n"
    "    def _load_unlocked(self, name: str, filepath: str) -> bool:\n"
    "        \"\"\"实际加载逻辑（调用方须已持有写锁，或本实例无 filelock）\"\"\"\n"
    "        try:\n"
)

# ── 补丁 3b：异常分支去破坏性 ───────────────────────────────────────────────
OLD_EXCEPT = (
    "        except Exception as e:\n"
    "            # P0 修复：JSON 损坏时备份原文件 + ERROR 日志，防止空库 _save 覆盖数据\n"
    "            import time as _time\n"
    '            backup_path = filepath + f".corrupted.{int(_time.time())}"\n'
    "            try:\n"
    "                os.rename(filepath, backup_path)\n"
    "                logger.error(\n"
    '                    f"InMemoryVectorStore 加载失败（JSON 损坏）: {e}\\n"\n'
    '                    f"  原文件已备份到: {backup_path}\\n"\n'
    '                    f"  系统将以空库启动，请检查备份文件并手动恢复数据！"\n'
    "                )\n"
    "            except OSError:\n"
    "                logger.error(\n"
    '                    f"InMemoryVectorStore 加载失败（JSON 损坏）: {e}\\n"\n'
    '                    f"  原文件备份失败，路径: {filepath}\\n"\n'
    '                    f"  系统将以空库启动，请立即检查数据文件！"\n'
    "                )\n"
    "            return False\n"
)
NEW_EXCEPT = (
    "        except Exception as e:\n"
    "            # INC-2026-09-14: 旧实现用 os.rename 把主文件搬走。一旦遇到非结构性\n"
    "            # 故障（内存不足 / 并发读写竞争 / 文件被占用），完好的主库会被误判\n"
    "            # \"损坏\"并移走，系统随之以空库启动，运行态与对外口径脱节。\n"
    "            # 现在：① 仅真正的结构/解析错误才备份；② 备份用 copy2，主文件永存；\n"
    "            #       ③ 其余故障只告警，绝不移动或删除原文件。\n"
    "            _structural = isinstance(e, (json.JSONDecodeError, ValueError, KeyError))\n"
    "            if _structural:\n"
    "                import shutil as _shutil\n"
    "                import time as _time\n"
    '                backup_path = filepath + f".corrupted.{int(_time.time())}"\n'
    "                try:\n"
    "                    _shutil.copy2(filepath, backup_path)\n"
    "                    logger.error(\n"
    "                        \"InMemoryVectorStore 加载失败（结构损坏）: %s\\n\"\n"
    "                        \"  已备份副本到: %s（原文件保留未动）\\n\"\n"
    "                        \"  系统将以空库启动，请检查备份文件。\",\n"
    "                        e,\n"
    "                        backup_path,\n"
    "                    )\n"
    "                except OSError as _oe:\n"
    "                    logger.error(\n"
    "                        \"InMemoryVectorStore 加载失败且备份失败: %s / %s（原文件保留）\",\n"
    "                        e,\n"
    "                        _oe,\n"
    "                    )\n"
    "            else:\n"
    "                logger.error(\n"
    "                    \"InMemoryVectorStore 加载失败（非结构性故障，未备份、未移动原文件）: \"\n"
    "                    \"%s: %s\\n  常见原因：内存不足或并发读写竞争。原文件保持原样: %s\",\n"
    "                    type(e).__name__,\n"
    "                    e,\n"
    "                    filepath,\n"
    "                )\n"
    "            return False\n"
)

# ── 补丁 4：模块级常量 ──────────────────────────────────────────────────────
OLD_CONST_ANCHOR = "class InMemoryVectorStore:\n"
NEW_CONST_ANCHOR = (
    "# INC-2026-09-14: 空库覆盖守门阈值。持久化 JSON 超过该体积即视为\"实质数据\"，\n"
    "# 拒绝以空集合覆盖，防止加载失败导致的连锁清零。\n"
    "_EMPTY_OVERWRITE_GUARD_BYTES = 1024 * 1024  # 1 MB\n"
    "\n"
    "class InMemoryVectorStore:\n"
)


def _norm(text: str) -> str:
    """统一换行，便于跨 CRLF/LF 匹配（写回时再还原为原换行风格）。"""
    return text.replace("\r\n", "\n")


def main() -> int:
    apply = "--apply" in sys.argv
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        raw = f.read()
    crlf = "\r\n" in raw
    text = _norm(raw)

    patches = [
        ("常量 _EMPTY_OVERWRITE_GUARD_BYTES", OLD_CONST_ANCHOR, NEW_CONST_ANCHOR),
        ("np.save 后缀修复", OLD_NPSAVE, NEW_NPSAVE),
        ("空库覆盖守门", OLD_SAVE_HEAD, NEW_SAVE_HEAD),
        ("_load 读锁包装", OLD_LOAD_HEAD, NEW_LOAD_HEAD),
        ("异常分支去破坏性", OLD_EXCEPT, NEW_EXCEPT),
    ]

    ok = True
    for label, old, new in patches:
        old_n, new_n = _norm(old), _norm(new)
        cnt = text.count(old_n)
        if cnt != 1:
            ok = False
            print(f"[FAIL] {label}: 锚点命中 {cnt} 次（期望 1）")
            continue
        text = text.replace(old_n, new_n, 1)
        print(f"[OK  ] {label}: 已替换")

    if not ok:
        print("\n存在未命中补丁，未写盘。")
        return 1

    if crlf:
        text = text.replace("\n", "\r\n")
    if apply:
        with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print(f"\n已写盘: {TARGET}")
    else:
        print("\n[DRY-RUN] 未写盘。加 --apply 生效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
