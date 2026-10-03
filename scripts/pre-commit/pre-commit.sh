#!/bin/sh
# ============================================================================
# NETLEARN-PRECOMMIT-HOOK v1 —— 门禁唯一真源（入库，受版本控制）
#
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
# 六道（任一失败即拦截，fail-closed）：
#   [1] 密钥扫描     secrets_scan.py     仅扫本次暂存的 A/C/M 文件
#   [2] 诚实口径     honesty_scan.py     含"已证伪对外红线"的 fail-closed 拦截
#   [3] 口径数字     caliber_check.py    目前**只告警不拦截**（见文末注）
#   [4] 结构守卫     structure_guard.py  根级平铺散落文件必须归位
#   [5] 潜在缺陷     f401_gate.py        F401/F811/F821/F822/F841（仅 py-server）
#   [6] 测试文件禁改 test_file_guard.py  测试与实现同 commit = 逃逸信号
#
# 注：[3] 的 caliber_check 把疑似口径数字列为告警后**恒返回 0**，不会真正阻断提交。
#     保留在链路里是为了把告警打在每次提交上（人工复核环节），不代表它是一道闸。
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

echo "=== [1/6] 密钥扫描 ==="
scan_staged_secrets || exit 1

echo "=== [2/6] 诚实口径（含对外红线） ==="
"$PY" scripts/pre-commit/honesty_scan.py --cached || exit 1

echo "=== [3/6] 口径数字（仅告警） ==="
"$PY" scripts/pre-commit/caliber_check.py --cached || exit 1

echo "=== [4/6] 结构守卫 ==="
"$PY" scripts/pre-commit/structure_guard.py || exit 1

echo "=== [5/6] ruff 潜在缺陷 ==="
"$PY" scripts/pre-commit/f401_gate.py || exit 1

echo "=== [6/6] 测试文件禁改 ==="
"$PY" scripts/pre-commit/test_file_guard.py --staged || exit 1

echo "✅ 六道门禁全部通过"
