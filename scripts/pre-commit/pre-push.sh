#!/bin/sh
# ============================================================================
# NETLEARN-PREPUSH-HOOK v1 —— 本地钩子第二层（入库真源）
#
# 为什么分两层（REA #43）：
#   pre-commit 的红线是**手感**——每次提交都跑，必须秒级。所以它把重闸
#   （契约漂移 ~4.3s）改成「按改动范围触发」，并把全量扫描留给别处。
#   pre-push 一台机器一天只跑几次，代价可以放大两个数量级：这里把
#   「提交时可能被条件触发跳过」的静态闸**无条件**跑一遍，且**收集全部失败**
#   再一次性报告（推送前你要的是一张清单，不是第一个错）。
#
# 本层**不跑单元测试**：pytest 全量 1300+ 用例、分钟级，那是 CI 的职责。
# 本地只补「静态可判、并且 CI 一定会拦」的那些项，保证推上去不是白推。
#
# 五道（任一失败 → 拦截推送）：
#   [1] 钩子自身漂移   install_hooks.py --check   真源与已安装内容必须一致
#   [2] 契约快照       verify_openapi_snapshot.py 无条件（不再按改动范围跳过）
#   [3] 广告 schema    check_schema_advertisement.py --gate  可达递归
#   [4] 克隆闸         dup_scan.py --gate         只拦新增
#   [5] 错误文案闸     check_error_wording.py     用户可见错误不得直出内部原文
#
# 安装 / 校验：
#   python scripts/install_hooks.py            # 同时装 pre-commit 与 pre-push
#   python scripts/install_hooks.py --check    # drift → exit 1
#
# 绕过：`git push --no-verify` 仍然有效（git 的既定能力，不试图封堵）。
# 但 CI 侧 verify-structural.yml 与 ci.yml 跑同一批脚本 —— 绕过本地只省时间，
# 不改变"进主干必须绿"的事实。
# ============================================================================
set -u

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT="."
cd "$ROOT" || exit 1

# 解释器解析：$PYTHON > python3 > python（解析失败明确报错，不伪装成门禁不通过）
PY=""
for cand in "${PYTHON:-}" python3 python; do
    if [ -n "$cand" ] && command -v "$cand" >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "❌ [pre-push] 未找到可用的 python 解释器（可用 PYTHON=/path/to/python 指定），已中止推送" >&2
    exit 1
fi

# 契约闸要 import 应用，只有项目 venv 里有 fastapi/pydantic
VENV_PY=""
for cand in "py-server/.venv/Scripts/python.exe" "py-server/.venv/bin/python"; do
    if [ -x "$cand" ]; then
        VENV_PY="$cand"
        break
    fi
done
[ -n "$VENV_PY" ] || VENV_PY="$PY"

FAILED=""
FAIL_COUNT=0
TOTAL=5

run_gate() {
    idx=$1
    name=$2
    shift 2
    echo "=== [$idx/$TOTAL] $name ==="
    if "$@"; then
        return 0
    fi
    FAIL_COUNT=$((FAIL_COUNT + 1))
    FAILED="$FAILED
  - [$idx] $name"
    return 1
}

# [1] 钩子漂移：别人的机器上钩子可能还是旧版；本地先自检，避免"我这台绿、他那台红"
run_gate 1 "钩子自身漂移" "$PY" scripts/install_hooks.py --check --quiet

# [2] 契约快照：无条件跑（pre-commit 只因 4.3s 代价按范围触发，这里补全）
run_gate 2 "OpenAPI 契约快照" "$VENV_PY" scripts/verify_openapi_snapshot.py

# [3] 广告 schema 可达递归（REA #31）
run_gate 3 "广告 schema 可达递归" "$PY" scripts/check_schema_advertisement.py --gate

# [4] 克隆新增闸（REA #20）
run_gate 4 "克隆新增" "$PY" scripts/dup_scan.py --gate

# [5] 用户可见错误文案（REA #12/#170）
run_gate 5 "错误文案直出" "$PY" scripts/check_error_wording.py --root py-server

echo
if [ "$FAIL_COUNT" -ne 0 ]; then
    echo "🔴 [pre-push] $FAIL_COUNT/$TOTAL 道门禁未通过：$FAILED" >&2
    echo "   修好后重推；CI 会跑同一批脚本，绕过本地只会把红灯推到远端。" >&2
    exit 1
fi
echo "✅ [pre-push] 五道门禁全部通过"
