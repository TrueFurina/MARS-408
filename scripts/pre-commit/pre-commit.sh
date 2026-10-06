#!/bin/sh
# ============================================================================
# NETLEARN-PRECOMMIT-HOOK v1 —— 门禁唯一真源（入库，受版本控制）#
# 本文件不是 git 会自动执行的位置。必须安装到 `git rev-parse --git-path hooks`：
#     python scripts/install_hooks.py            # 安装 / 更新
#     python scripts/install_hooks.py --check    # 校验与实际安装的一致（drift → exit 1）
#
# 为什么要这样：钩子本体落在 .git/ 下**不受版本控制**，本地提交才跑得到它，
# 而它也能被 `git commit --no-verify` 一键绕过 —— "新克隆 = 零门禁"，
# 且本地全绿不代表进仓库的那一份是全绿的。把真源入库 + 幂等安装器，
# 门禁才能随仓库走，而不是只活在某一台机器上。
#
# □ CI 侧现已闭环（2026-10-03）：.github/workflows/gates.yml + 编排器 run_gates.py。
#   注意 **CI 不能直接执行本脚本**：下面每一步都从 **git 暂存区** 取文件
#   （--cached / staged_files），而 actions/checkout 之后工作区 == HEAD、暂存区恒为空，
#   照搬会让六道门禁"一个文件没查"却全部返回 0 —— 挂六个永远绿的假闸门。
#   CI 走 run_gates.py，由它把「文件集来源」换成 PR diff / 全量后再喂给同一批脚本。
#   本机复现 CI 结论：python scripts/pre-commit/run_gates.py --diff origin/career-literacy
#
# 七道（任一失败即拦截，fail-closed）：
#   [1] 密钥扫描     secrets_scan.py     仅扫本次暂存的 A/C/M 文件
#   [2] 诚实口径     honesty_scan.py     含"已证伪对外红线"的 fail-closed 拦截
#   [3] 口径数字     caliber_check.py    目前**只告警不拦截**（见文末注）
#   [4] 结构守卫     structure_guard.py  根级平铺散落文件必须归位
#   [5] 潜在缺陷     f401_gate.py        F401/F811/F821/F822/F841（仅 py-server）
#   [6] 测试文件禁改 test_file_guard.py  测试与实现同 commit = 逃逸信号
#   [7] 契约漂移     verify_openapi_snapshot.py  随包快照必须 == 运行时真实能力
#
# 注：[3] 的 caliber_check 把疑似口径数字列为告警后**恒返回 0**，不会真正阻断提交。
#     保留在链路里是为了把告警打在每次提交上（人工复核环节），不代表它是一道闸。
#
# 注：[7] 需要 `from main import app`（实测 ~4.3s，见下），故**按改动范围触发**：
#     只有当暂存文件命中「可能改变对外契约」的路径时才跑，其余提交零开销。
#     这是刻意的性能取舍，不是降级 —— 漂移只有可能由那些文件引起，
#     而 CI 与打包器是**无条件**执行的（CI 每次 push/PR 都跑，build_portable.py
#     每次打包都跑且不一致即exit 1），所以不存在"绕过钩子就能悄悄漂移"的路径。
# ============================================================================
set -u

# git 会在工作树顶层执行钩子；显式再 cd 一次，确保从子目录提交时相对路径也成立。
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || ROOT="."
cd "$ROOT" || exit 1

# 解释器解析：$PYTHON > python3 > python。
# 旧写法裸调 `python`：在只装了 python3 的机器上会以"门禁失败"的假象拦住每一次提交，
# 排查成本极高。这里解析失败就明确报错，而不是伪装成门禁不通过。
PY=""
for cand in "${PYTHON:-}" python3 python; do
    if [ -n "$cand" ] && command -v "$cand" >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "❌ [门禁] 未找到可用的 python 解释器（可用 PYTHON=/path/to/python 指定），已中止提交" >&2
    exit 1
fi

# 只扫本次暂存的 A/C/M 文件。
# -z（NUL 分隔）经 xargs -0 传递：本仓库确有带空格的路径（如
# deliverables/芒得很职 考研…/）。旧的 `$(git diff --cached --name-only …)` 未加引号，
# 会在这种路径上把参数拆错、静默漏扫；更糟的是**没有暂存文件时它会退化成全树扫描**。
scan_staged_secrets() {
    if command -v xargs >/dev/null 2>&1; then
        git -c core.quotePath=false diff --cached --name-only --diff-filter=ACM -z \
            | xargs -0 -r "$PY" scripts/pre-commit/secrets_scan.py
    else
        # 兜底（无 xargs）：逐行读取、逐文件调用，同样不拆词、不放空跑全树。
        git -c core.quotePath=false diff --cached --name-only --diff-filter=ACM \
            | while IFS= read -r f; do
                  [ -n "$f" ] || continue
                  "$PY" scripts/pre-commit/secrets_scan.py "$f" || exit 1
              done
    fi
}

echo "=== [1/7] 密钥扫描 ==="
scan_staged_secrets || exit 1

echo "=== [2/7] 诚实口径（含对外红线） ==="
"$PY" scripts/pre-commit/honesty_scan.py --cached || exit 1

echo "=== [3/7] 口径数字（仅告警） ==="
"$PY" scripts/pre-commit/caliber_check.py --cached || exit 1

echo "=== [4/7] 结构守卫 ==="
"$PY" scripts/pre-commit/structure_guard.py || exit 1

echo "=== [5/7] ruff 潜在缺陷 ==="
"$PY" scripts/pre-commit/f401_gate.py || exit 1

echo "=== [6/7] 测试文件禁改 ==="
"$PY" scripts/pre-commit/test_file_guard.py --staged || exit 1

# --- 第 7 道：契约漂移（按改动范围触发，见文件头注 7）---
#
# 为什么要条件触发：这道闸要 `from main import app`，实测 ~4.3s（导入 4.07s +
# app.openapi() 0.28s，见文件头）。无条件挂上的话，每个与契约无关的提交
# （改文档、改前端样式）都要多等 4 秒以上，手感代价明显。
#
# 为什么条件触发**不构成降级**：能改变对外契约的文件就那么几类
# （快照本体、应用身份、路由定义）。改动不命中它们时，契约**在数学上不可能变**，
# 跳过是等价变换而非放行。而真正需要兜底的两条路径都是无条件强制的：
#   - CI（.github/workflows/ci.yml）：每次 PR / push 都跑；
#   - 打包器（scripts/build_portable.py）：每次打包都跑，不一致即 exit 1。
# 三者叠加 → 不存在"绕过本地钩子就能让包内快照悄悄落后"的路径。
echo "=== [7/7] OpenAPI 契约漂移 ==="
OPENAPI_GATE_TMP=$(mktemp 2>/dev/null || echo "${TMPDIR:-/tmp}/openapi_gate_$$")
git -c core.quotePath=false diff --cached --name-only --diff-filter=ACM > "$OPENAPI_GATE_TMP" 2>/dev/null || true
# 命中判定：快照本体 / 应用身份与装配 / 路由与模型定义 / 依赖清单（可能改挂载的 router）。
OPENAPI_GATE_TRIGGERED=$(grep -E \
    '^(py-server/openapi\.json|py-server/main\.py|py-server/api/|py-server/models\.py|py-server/requirements[^/]*\.txt|py-server/pyproject\.toml|py-server/app\.py)' \
    "$OPENAPI_GATE_TMP" 2>/dev/null | head -1)
rm -f "$OPENAPI_GATE_TMP" 2>/dev/null || true
if [ -n "$OPENAPI_GATE_TRIGGERED" ]; then
    # 用项目 venv 解释器跑：它才有 fastapi/pydantic。找不到就退到 $PY，
    # 此时脚本会因缺依赖 exit 2（环境错误，非漂移），不会被误读成契约问题。
    OPENAPI_PY=""
    for cand in "py-server/.venv/Scripts/python.exe" "py-server/.venv/bin/python"; do
        if [ -x "$cand" ]; then
            OPENAPI_PY="$cand"
            break
        fi
    done
    [ -n "$OPENAPI_PY" ] || OPENAPI_PY="$PY"
    "$OPENAPI_PY" scripts/verify_openapi_snapshot.py || exit 1
else
    echo "  (本次改动不涉及对外契约文件，跳过；CI 与打包器仍无条件校验)"
fi

echo "✅ 七道门禁全部通过"
