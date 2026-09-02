#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""幂等创建管理员账号（不清空任何既有数据）。

背景：seed_users.py 会 DELETE 全部 users 表，属于破坏性操作；
本脚本只调用幂等的 ensure_admin()，已存在则跳过，绝不删除任何账号。

口令来源优先级：
  1. 环境变量 ADMIN_PASSWORD
  2. py-server/.env 中的 ADMIN_PASSWORD=
  3. 缺失则报错退出（不写弱口令回仓库）

用法：
    py-server/.venv/Scripts/python.exe ../scripts/create_admin.py [username]
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY_SERVER = HERE.parent / "py-server"
sys.path.insert(0, str(PY_SERVER))

ENV_FILE = PY_SERVER / ".env"


def read_env_password() -> str | None:
    if not ENV_FILE.exists():
        return None
    text = ENV_FILE.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"^\s*ADMIN_PASSWORD\s*=\s*(.+?)\s*$", text, re.M)
    if not m:
        return None
    val = m.group(1).strip().strip('"').strip("'")
    return val or None


def main() -> int:
    username = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD") or read_env_password()
    if not password:
        print("[create-admin] FAIL: 未找到 ADMIN_PASSWORD（环境变量或 py-server/.env）")
        return 2

    from db import user_store as us

    before = us.get_user_by_username(username) if hasattr(us, "get_user_by_username") else None
    if before:
        print(f"[create-admin] 账号 {username} 已存在（role={before.get('role')}），未做修改")
        return 0

    us.ensure_admin(username, password, display_name="系统管理员")
    print(f"[create-admin] 已创建管理员: {username}（口令长度 {len(password)}，不在日志中明文打印）")

    # 回读验证
    getter = getattr(us, "get_user_by_username", None)
    if getter:
        row = getter(username)
        print(f"[create-admin] 回读: role={row.get('role') if row else 'N/A'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
