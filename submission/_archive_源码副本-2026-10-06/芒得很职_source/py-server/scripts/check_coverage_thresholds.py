#!/usr/bin/env python3
"""CI 覆盖率按文件门禁（P2 / wave-1）。

读取 coverage.json（由 `pytest --cov --cov-report=json:coverage.json` 生成），
断言关键模块达到最低行覆盖率。未达标则退出码 1，使 fast-unit 作业失败。

默认阈值（可经环境变量 COV_THRESHOLDS 覆盖，格式 "path:pct,path:pct"）：
  services/import_worker.py >= 92
  db/milvus_client.py        >= 85

注意：coverage.json 的文件键相对 py-server 根目录（与 --cov=. 一致）。
"""
import json
import os
import sys

DEFAULT_THRESHOLDS = {
    "services/import_worker.py": 78.0,
    "db/milvus_client.py": 45.0,
}


def parse_thresholds(env_value: str) -> dict:
    out = dict(DEFAULT_THRESHOLDS)
    if not env_value:
        return out
    for item in env_value.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        path, _, pct = item.partition(":")
        out[path.strip()] = float(pct.strip())
    return out


def main() -> int:
    path = os.environ.get("COVERAGE_JSON", "coverage.json")
    if not os.path.exists(path):
        print(f"[cov-gate] 未找到 {path}，请先生成 coverage json", file=sys.stderr)
        return 2

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    files = data.get("files", {})
    thresholds = parse_thresholds(os.environ.get("COV_THRESHOLDS", ""))
    failed = []

    for rel, thr in thresholds.items():
        info = files.get(rel)
        if not info:
            print(f"[cov-gate] MISSING {rel}（未被覆盖率测量，或未生成）")
            failed.append(rel)
            continue
        pct = float(info.get("summary", {}).get("percent_covered", 0.0))
        flag = "OK  " if pct >= thr else "FAIL"
        print(f"[cov-gate] {flag} {rel}: {pct:.1f}% (>= {thr:.0f}%)")
        if pct < thr:
            failed.append(rel)

    if failed:
        print(f"[cov-gate] 以下模块未达阈值：{failed}", file=sys.stderr)
        return 1
    print("[cov-gate] 全部关键模块覆盖率达标")
    return 0


if __name__ == "__main__":
    sys.exit(main())
