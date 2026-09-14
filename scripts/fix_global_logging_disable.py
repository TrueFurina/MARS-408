"""修复测试会话级日志污染：test_teacher_role.py 顶层 logging.disable 会全局生效。

问题：模块顶层调用 logging.disable(logging.CRITICAL) 是**进程级全局开关**，
导入即生效且直到会话结束都不恢复 —— 会静默掉**其它所有模块**的日志断言。
（实证：tests/test_config_observability.py 单跑 3 passed，全量跑 3 failed，
捕获到的日志恒为空。）

修复：改为该模块内的 autouse fixture，作用域限定在本模块用例，退出即还原。

CRLF-safe + 唯一锚点断言 + 幂等。
Usage: python scripts/fix_global_logging_disable.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "py-server" / "tests" / "test_teacher_role.py"

OLD = "logging.disable(logging.CRITICAL)  # 保持测试输出干净\r\n"

NEW = (
    "@pytest.fixture(autouse=True)\r\n"
    "def _quiet_module_logging():\r\n"
    '    """仅在本模块用例期间抑制日志。\r\n'
    "\r\n"
    "    注意：绝不能把 logging.disable() 放在模块顶层——它是**进程级全局开关**，\r\n"
    "    导入即生效且直到会话结束都不还原，会静默掉其它模块的日志断言。\r\n"
    '    """\r\n'
    "    logging.disable(logging.CRITICAL)\r\n"
    "    yield\r\n"
    "    logging.disable(logging.NOTSET)\r\n"
)


def main() -> int:
    text = io.open(TARGET, encoding="utf-8", newline="").read()

    if NEW in text:
        print("[skip] 已是修正后的作用域化形态")
        return 0

    n = text.count(OLD)
    if n != 1:
        print(f"[FAIL] 锚点命中 {n} 次（期望 1），未改动")
        return 1

    io.open(TARGET, "w", encoding="utf-8", newline="").write(text.replace(OLD, NEW, 1))
    print("[ok] test_teacher_role.py 的 logging.disable 已作用域化")

    check = io.open(TARGET, encoding="utf-8", newline="").read()
    assert "logging.disable(logging.NOTSET)" in check
    crlf = check.count("\r\n")
    lone = check.count("\n") - crlf
    print(f"[verify] CRLF={crlf} lone_LF={lone}")
    return 0 if lone == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
