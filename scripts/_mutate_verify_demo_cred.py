"""变异验证：破坏「演示凭据单一真值源 / 生产守门」不变量，测试必须失败。

对 main.py 做 4 个变异体，每个都直接写盘（字节级，保持 CRLF），
运行目标测试文件，期望出现失败；结束后从内存恢复原字节并校验 sha256。
"""
from __future__ import annotations

import hashlib
import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "py-server" / ".venv" / "Scripts" / "python.exe"
MAIN = ROOT / "py-server" / "main.py"
TESTFILE = "tests/test_demo_credential_single_source.py"

# 变异体：名称 -> (原字节片段, 变异后字节片段)
MUTANTS: list[tuple[str, bytes, bytes]] = [
    (
        "M1 退回硬编码字面量",
        b'            if authenticate(DEMO_USERNAME, DEMO_PASSWORD) is None:\r\n',
        b'            if authenticate("demo", "demo123456") is None:\r\n',
    ),
    (
        "M2 去掉生产守门",
        b'        if env not in ("production", "prod"):\r\n',
        b"        if True:\r\n",
    ),
    (
        "M3 生产分支也播种",
        b'            logger.info("\xe7\x94\x9f\xe4\xba\xa7\xe7\x8e\xaf\xe5\xa2\x83\xe8\xb7\xb3\xe8\xbf\x87\xe6\xbc\x94\xe7\xa4\xba\xe7\xa7\x8d\xe5\xad\x90\xe8\xb4\xa6\xe6\x88\xb7\xe5\x86\x99\xe5\x85\xa5\xe3\x80\x82")\r\n',
        b'            seed_demo_data()\r\n'
        b'            logger.info("\xe7\x94\x9f\xe4\xba\xa7\xe7\x8e\xaf\xe5\xa2\x83\xe8\xb7\xb3\xe8\xbf\x87\xe6\xbc\x94\xe7\xa4\xba\xe7\xa7\x8d\xe5\xad\x90\xe8\xb4\xa6\xe6\x88\xb7\xe5\x86\x99\xe5\x85\xa5\xe3\x80\x82")\r\n',
    ),
    (
        "M4 日志回显凭据",
        b'            logger.info("\xe7\x94\x9f\xe4\xba\xa7\xe7\x8e\xaf\xe5\xa2\x83\xe8\xb7\xb3\xe8\xbf\x87\xe6\xbc\x94\xe7\xa4\xba\xe7\xa7\x8d\xe5\xad\x90\xe8\xb4\xa6\xe6\x88\xb7\xe5\x86\x99\xe5\x85\xa5\xe3\x80\x82")\r\n',
        b'            logger.info("skip %s/%s", DEMO_USERNAME, DEMO_PASSWORD)\r\n',
    ),
]


def run_tests() -> tuple[int, str]:
    p = subprocess.run(
        [str(PY), "-m", "pytest", TESTFILE, "-q", "-p", "no:cacheprovider",
         "--basetemp=E:/Program/MARL/study-help-pro/py-server/.pytest_tmp/mut"],
        cwd=str(ROOT / "py-server"), capture_output=True, text=True, errors="replace",
    )
    return p.returncode, p.stdout


def failed_names(out: str) -> list[str]:
    names = []
    for line in out.splitlines():
        if line.startswith("FAILED "):
            names.append(line.split("::")[-1].split(" ")[0])
    return names


def main() -> int:
    original = MAIN.read_bytes()
    orig_sha = hashlib.sha256(original).hexdigest()
    print(f"原始 main.py sha256={orig_sha[:16]} bytes={len(original)}")
    print("=" * 88)

    code0, out0 = run_tests()
    print(f"[基线] 退出码={code0}（期望 0）")
    if code0 != 0:
        print(out0[-1500:])
        print("!! 基线未通过，变异验证无意义")
        return 2
    print("=" * 88)

    killed = 0
    for name, old, new in MUTANTS:
        body = MAIN.read_bytes()
        n = body.count(old)
        if n != 1:
            print(f"[{name}] 锚点命中 {n} 次（应为 1）——跳过")
            continue
        try:
            MAIN.write_bytes(body.replace(old, new))
            rc, out = run_tests()
            fails = failed_names(out)
            status = "KILLED" if rc != 0 and fails else "SURVIVED(测试无效!)"
            if status.startswith("KILLED"):
                killed += 1
            print(f"[{name}] 退出码={rc} -> {status}")
            if fails:
                for f in fails[:6]:
                    print(f"        杀死者: {f}")
            else:
                print("        !! 无测试失败，该变异体存活")
        finally:
            MAIN.write_bytes(original)
            assert hashlib.sha256(MAIN.read_bytes()).hexdigest() == orig_sha, "恢复失败!"
    print("=" * 88)
    print(f"结果: {killed}/{len(MUTANTS)} 变异体被杀死")
    restored = hashlib.sha256(MAIN.read_bytes()).hexdigest()
    print(f"恢复校验: {'OK' if restored == orig_sha else '!! 不一致'}")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
