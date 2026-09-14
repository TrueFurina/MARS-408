"""main.py 演示账号凭据改为「单一真值源」——字节级 CRLF 安全补丁。

背景：
  py-server/main.py 的演示种子写入块里重复硬编码了演示账号与口令字面量，
  而真值定义在 seed_demo_data.py 的 DEMO_USERNAME / DEMO_PASSWORD。
  重复带来两个实际风险：
    1) 漂移：改 seed_demo_data 的口令但漏改 main.py 的幂等探测 → authenticate 恒失败
       → 每次启动都重复播种（幂等性失效）。
    2) 凭据回显：生产分支日志把口令明文写进日志。

行为保持不变：仍用同一账号/口令做幂等探测，仍只在非生产环境播种。
"""
from __future__ import annotations

import io
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "py-server" / "main.py"

OLD = (
    "    # ── 首次启动时写入演示种子数据（仅非生产环境，避免生产自动创建弱口令演示账户）──\r\n"
    "    try:\r\n"
    '        env = os.environ.get("NETLEARN_ENV", "development").lower()\r\n'
    '        if env not in ("production", "prod"):\r\n'
    "            from db.user_store import authenticate\r\n"
    '            if authenticate("demo", "demo123456") is None:\r\n'
    "                from seed_demo_data import seed_demo_data\r\n"
    "                seed_demo_data()\r\n"
    "        else:\r\n"
    '            logger.info("生产环境跳过演示种子账户写入（demo/demo123456）。")\r\n'
    "    except Exception as e:\r\n"
    '        logger.warning(f"演示种子数据写入失败（非阻塞）: {e}")\r\n'
)

NEW = (
    "    # ── 首次启动时写入演示种子数据（仅非生产环境，避免生产自动创建弱口令演示账户）──\r\n"
    "    # 演示账号/口令以 seed_demo_data 的 DEMO_USERNAME / DEMO_PASSWORD 为唯一真值源。\r\n"
    "    # 此处不得再写字面量：一是防止漂移（改了口令却漏改幂等探测 → 每次启动重复播种），\r\n"
    "    # 二是避免把凭据明文回显进日志（原生产分支日志含明文口令）。\r\n"
    "    try:\r\n"
    '        env = os.environ.get("NETLEARN_ENV", "development").lower()\r\n'
    '        if env not in ("production", "prod"):\r\n'
    "            from db.user_store import authenticate\r\n"
    "            from seed_demo_data import DEMO_PASSWORD, DEMO_USERNAME, seed_demo_data\r\n"
    "            if authenticate(DEMO_USERNAME, DEMO_PASSWORD) is None:\r\n"
    "                seed_demo_data()\r\n"
    "        else:\r\n"
    '            logger.info("生产环境跳过演示种子账户写入。")\r\n'
    "    except Exception as e:\r\n"
    '        logger.warning(f"演示种子数据写入失败（非阻塞）: {e}")\r\n'
)

MARKER = "DEMO_PASSWORD, DEMO_USERNAME"


def main() -> int:
    raw = io.open(TARGET, "rb").read()
    crlf = raw.count(b"\r\n")
    lone_lf = raw.count(b"\n") - crlf
    print(f"补丁前: CRLF={crlf} lone_LF={lone_lf}")
    if lone_lf:
        print("!! 存在裸 LF，放弃修改以保持行尾纪律")
        return 3

    text = raw.decode("utf-8")

    if MARKER in text:
        print("已应用（幂等）：未做任何修改")
        return 0

    if text.count(OLD) != 1:
        print(f"!! 锚点命中数 = {text.count(OLD)}（应为 1），放弃修改")
        return 2

    backup = TARGET.with_suffix(".py.bak_single_source")
    shutil.copy2(TARGET, backup)
    print(f"备份 -> {backup.name}")

    new_text = text.replace(OLD, NEW)
    io.open(TARGET, "wb").write(new_text.encode("utf-8"))

    raw2 = io.open(TARGET, "rb").read()
    crlf2 = raw2.count(b"\r\n")
    lone_lf2 = raw2.count(b"\n") - crlf2
    print(f"补丁后: CRLF={crlf2} lone_LF={lone_lf2}")

    checks = {
        "含 DEMO_PASSWORD 引用": "DEMO_PASSWORD, DEMO_USERNAME" in new_text,
        "含 authenticate(DEMO_USERNAME": "authenticate(DEMO_USERNAME, DEMO_PASSWORD)" in new_text,
        "已移除旧字面量调用": 'authenticate("demo",' not in new_text,
        "生产分支不再回显凭据": "（demo/demo123456）" not in new_text,
        "CRLF 未破坏": lone_lf2 == 0,
    }
    ok = all(checks.values())
    for k, v in checks.items():
        print(f"  [{'OK' if v else 'FAIL'}] {k}")
    if not ok:
        print("!! 校验未通过，回滚")
        shutil.copy2(backup, TARGET)
        return 4
    print("补丁应用成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())
