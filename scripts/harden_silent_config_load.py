"""Harden silent config/startup degradation paths.

Three broad `except Exception: pass` handlers on the core path currently hide
failures that matter:

1. config.py `_load_dotenv()`  -> a malformed .env is dropped silently, so
   credentials silently go missing.
2. config.py `load_config()`   -> a malformed config.json is dropped silently,
   so the app runs on built-in DEFAULTS (empty keys / wrong model) with no
   signal at all. Same failure class as the P0 empty-vector-DB incident.
3. main.py `/api/status/competition` -> a failing user-count query is swallowed
   and the endpoint reports `user_count: 0`, i.e. a status endpoint that lies.

Each handler gains an observable warning while keeping the original fallback
behaviour (fail-open unchanged; only observability is added).

CRLF-safe: reads/writes with newline="" so every line ending is preserved.
Idempotent: re-running is a no-op. Unique-anchor asserted before each patch.

Usage: python scripts/harden_silent_config_load.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "py-server" / "config.py"
MAIN = ROOT / "py-server" / "main.py"

# ── (path, marker, old, new) ────────────────────────────────────────────────
PATCHES: list[tuple[Path, str, str, str]] = []

# 1) module-level logger so the warnings below have somewhere to go
PATCHES.append((
    CONFIG,
    "config.py::module-logger",
    "from typing import Optional\r\n\r\n# 配置文件路径\r\n",
    'from typing import Optional\r\n\r\nlogger = logging.getLogger("netlearn.config")\r\n\r\n# 配置文件路径\r\n',
))

# 2) .env parse failure -> observable
PATCHES.append((
    CONFIG,
    "config.py::dotenv-warn",
    "                    os.environ[key] = val\r\n    except Exception:\r\n        pass\r\n",
    '                    os.environ[key] = val\r\n'
    "    except Exception as e:\r\n"
    '        logger.warning(".env 解析失败，已忽略（凭据可能缺失）: %s", e)\r\n',
))

# 3) config.json parse failure -> observable
PATCHES.append((
    CONFIG,
    "config.py::json-warn",
    "                _deep_merge(config, file_config)\r\n"
    "            except Exception:\r\n"
    "                pass\r\n",
    "                _deep_merge(config, file_config)\r\n"
    "            except Exception as e:\r\n"
    "                logger.warning(\r\n"
    '                    "config.json 解析失败，已回退内置 DEFAULTS（凭据/模型配置可能为空）: %s", e\r\n'
    "                )\r\n",
))

# 4) status endpoint must not silently report 0 users
PATCHES.append((
    MAIN,
    "main.py::user-count-warn",
    "        user_count = row[0] if row else 0\r\n    except Exception:\r\n        pass\r\n",
    "        user_count = row[0] if row else 0\r\n"
    "    except Exception as e:\r\n"
    '        logger.warning("competition_status 读取用户总数失败，返回 0: %s", e)\r\n',
))


def main() -> int:
    cache: dict[Path, str] = {}
    applied = skipped = failed = 0

    for path, marker, old, new in PATCHES:
        if path not in cache:
            cache[path] = io.open(path, encoding="utf-8", newline="").read()
        text = cache[path]

        if new in text:
            print(f"[skip] {marker}: already applied")
            skipped += 1
            continue

        if new.split("\r\n")[0] in text and "except Exception as e" in text and old not in text:
            print(f"[skip] {marker}: already applied (shape match)")
            skipped += 1
            continue

        n = text.count(old)
        if n != 1:
            print(f"[FAIL] {marker}: anchor found {n} times (expected 1)")
            failed += 1
            continue

        cache[path] = text.replace(old, new, 1)
        applied += 1
        print(f"[ok]   {marker}: patched")

    for path, text in cache.items():
        if text != io.open(path, encoding="utf-8", newline="").read():
            io.open(path, "w", encoding="utf-8", newline="").write(text)
            print(f"[write] {path.relative_to(ROOT)}")

    print(f"applied={applied} skipped={skipped} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
