#!/usr/bin/env bash
# scripts/test.sh — 运行 py-server 后端测试（环境清洗封装）
#
# 背景：WorkBuddy 的 Bash shell 会向环境注入 sitecustomize shim
# （经由 PYTHONPATH / PYTHONSTARTUP / NODE_OPTIONS / ELECTRON_RUN_AS_NODE），
# 该 shim 会污染 pytest 子进程，导致大面积 setup ERROR / SystemExit:1，
# 表现为「退出码非 0、passed/failed 全空」。
# 解法（2026-09-19 实锤，权威回归以 Linux/CI 为准）：用 env -u 清除这些变量后再启动 pytest。
# 本脚本固化该解法，团队统一通过它跑测试，避免每次手敲一长串 env -u。
#
# 用法：
#   ./scripts/test.sh                  # 跑全部（等价于 pytest，从 py-server 目录加载 pyproject 配置）
#   ./scripts/test.sh tests/test_x.py  # 跑指定文件
#   ./scripts/test.sh -q --cov         # 透传任意 pytest 参数
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 定位 venv 解释器：Windows 用 Scripts/python.exe，其它平台用 bin/python
if [ -x "$REPO_ROOT/py-server/.venv/Scripts/python.exe" ]; then
  PY="$REPO_ROOT/py-server/.venv/Scripts/python.exe"
elif [ -x "$REPO_ROOT/py-server/.venv/bin/python" ]; then
  PY="$REPO_ROOT/py-server/.venv/bin/python"
else
  echo "✗ 未找到 py-server venv，请先执行：cd py-server && uv sync --frozen" >&2
  exit 1
fi

cd "$REPO_ROOT/py-server"
# 关键：清除 WorkBuddy shell 注入的污染变量后再跑 pytest
exec env -u PYTHONPATH -u PYTHONSTARTUP -u NODE_OPTIONS -u ELECTRON_RUN_AS_NODE \
  "$PY" -m pytest "$@"
