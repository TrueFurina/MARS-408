"""变异验证：证明 test_config_observability.py 的 3 条断言真的有效。

对每处加固「反向撤销」（logger.warning -> pass），跑对应测试并断言**必须 FAIL**，
随后立刻还原。若撤销后测试仍 PASS，说明该测试是摆设（杀不死变异体）。

Usage: python scripts/_mutate_verify_config_obs.py
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / "py-server" / ".venv" / "Scripts" / "python.exe"
PY_SERVER = ROOT / "py-server"

MUTATIONS = [
    (
        "M1 config.json 告警",
        ROOT / "py-server" / "config.py",
        "test_malformed_config_json_warns_and_still_falls_back",
        "                _deep_merge(config, file_config)\r\n"
        "            except Exception as e:\r\n"
        "                logger.warning(\r\n"
        '                    "config.json 解析失败，已回退内置 DEFAULTS（凭据/模型配置可能为空）: %s", e\r\n'
        "                )\r\n",
        "                _deep_merge(config, file_config)\r\n"
        "            except Exception:\r\n"
        "                pass\r\n",
    ),
    (
        "M2 .env 告警",
        ROOT / "py-server" / "config.py",
        "test_malformed_dotenv_warns",
        "                    os.environ[key] = val\r\n"
        "    except Exception as e:\r\n"
        '        logger.warning(".env 解析失败，已忽略（凭据可能缺失）: %s", e)\r\n',
        "                    os.environ[key] = val\r\n"
        "    except Exception:\r\n"
        "        pass\r\n",
    ),
    (
        "M3 状态端点告警",
        ROOT / "py-server" / "main.py",
        "test_competition_status_warns_on_db_error",
        "        user_count = row[0] if row else 0\r\n"
        "    except Exception as e:\r\n"
        '        logger.warning("competition_status 读取用户总数失败，返回 0: %s", e)\r\n',
        "        user_count = row[0] if row else 0\r\n"
        "    except Exception:\r\n"
        "        pass\r\n",
    ),
]


def run_test(name: str) -> int:
    return subprocess.run(
        [
            str(PY), "-m", "pytest", "tests/test_config_observability.py",
            "-k", name, "-q", "-p", "no:cacheprovider",
            "--basetemp=" + str(PY_SERVER / ".pytest_tmp" / "mut"),
        ],
        cwd=str(PY_SERVER), capture_output=True, text=True,
    ).returncode


def main() -> int:
    results = []
    for label, path, test_name, patched, unpatched in MUTATIONS:
        original = io.open(path, encoding="utf-8", newline="").read()
        if patched not in original:
            print(f"[SKIP] {label}: 加固形态未找到（可能已被改动）")
            results.append((label, "SKIP"))
            continue
        try:
            io.open(path, "w", encoding="utf-8", newline="").write(
                original.replace(patched, unpatched, 1)
            )
            rc = run_test(test_name)
            verdict = "KILLED(测试正确失败)" if rc != 0 else "SURVIVED(测试无效!)"
            results.append((label, verdict))
            print(f"[{verdict}] {label} -> {test_name} (pytest rc={rc})")
        finally:
            io.open(path, "w", encoding="utf-8", newline="").write(original)  # 立刻还原
            assert io.open(path, encoding="utf-8", newline="").read() == original, "还原失败!"

    print("\n=== 变异验证汇总 ===")
    for label, verdict in results:
        print(f"  {label}: {verdict}")
    bad = [r for r in results if r[1] != "KILLED(测试正确失败)"]
    print(f"\n结论: {'全部变异体被杀死（测试有效）' if not bad else '存在未杀死/SKIP 的变异体，需检查'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
