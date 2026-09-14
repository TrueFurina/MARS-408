"""Silent-exception audit for py-server core modules.

Flags `except` handlers whose body performs neither logging nor re-raising,
i.e. failures that vanish without a trace. Aligned with the project's
evidence-chain principle: a degraded path must be observable.

Usage: python scripts/_scan_silent_except.py
Read-only. Excludes nested crypto_platform copies, tests, scripts and archives.
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "py-server"
CORE_DIRS = ["agents", "engines", "db", "api", "services", "shared", "schemas", "middleware"]
SKIP_PARTS = {"crypto_platform", "tests", "scripts", "archive", "node_modules", "__pycache__", "experiments"}

EXCEPT_RE = re.compile(r"^(\s*)except\b")
# tokens that count as "the failure is observable"
OBSERVABLE = ("logger.", "logging.", "log.", "warn", "print(", "raise", "traceback", "sentry", "capture_exception", "sys.stderr")


def block_body(lines: list[str], start: int) -> tuple[list[str], int]:
    """Return the body lines of the except block starting at `start` (index of the except line)."""
    indent = len(lines[start]) - len(lines[start].lstrip())
    body: list[str] = []
    i = start + 1
    while i < len(lines):
        raw = lines[i]
        if raw.strip() == "":
            body.append(raw)
            i += 1
            continue
        cur = len(raw) - len(raw.lstrip())
        if cur <= indent:
            break
        body.append(raw)
        i += 1
    return body, i


def is_observable(body: list[str]) -> bool:
    joined = "\n".join(body)
    if any(tok in joined for tok in OBSERVABLE):
        return True
    return False


def main() -> int:
    findings: list[tuple[str, int, str]] = []
    scanned = 0
    for d in CORE_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for py in sorted(base.rglob("*.py")):
            if any(part in SKIP_PARTS for part in py.parts):
                continue
            scanned += 1
            try:
                text = io.open(py, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            lines = text.splitlines()
            for idx, line in enumerate(lines):
                if not EXCEPT_RE.match(line):
                    continue
                body, _ = block_body(lines, idx)
                # single-line form: `except X: pass` or `except X: return y`
                stripped = line.split(":", 1)[1].strip() if ":" in line else ""
                if stripped:
                    body = [stripped] + body
                if not is_observable(body):
                    rel = py.relative_to(ROOT.parent).as_posix()
                    findings.append((rel, idx + 1, line.strip()))

    print(f"scanned_py_files={scanned}")
    print(f"silent_except_count={len(findings)}")
    for rel, ln, snippet in findings:
        print(f"  {rel}:{ln}: {snippet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
