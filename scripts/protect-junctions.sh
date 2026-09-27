#!/usr/bin/env bash
# scripts/protect-junctions.sh
#
# 问题：本仓库 py-server/models 与 node_modules 是跨盘 junction（→ D:/MARL_cold_storage/...）。
# git 无法穿越 junction，会把 py-server/models 误判为「未跟踪目录」，
# 并把其内已跟踪的 .pt 显示为「已删除（ D）」——历史上多次造成假删除、误提交。
#
# 现状守卫由两份本地（不进版本库）配置组成：
#   1) .git/info/exclude 里的 `py-server/models`
#   2) git update-index --skip-worktree py-server/models/career_mode_policy.pt
# 但 .git/info/exclude 不随仓库分发，新克隆后会丢失，git status 再次报错。
#
# 本脚本在「克隆 / 切换分支 / 重检出处」后一键重建上述守卫，使脆弱点不再静默复发。
# 它不移动、不修改任何模型或依赖文件，仅调整 git 的本地忽略与跳过标记。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

EXCLUDE=".git/info/exclude"

# 1) 本地 exclude：静音 junction 目录（仅本机，不进版本库）
if [ -f "$EXCLUDE" ]; then
  grep -qx "py-server/models" "$EXCLUDE" || echo "py-server/models" >> "$EXCLUDE"
else
  echo "py-server/models" >> "$EXCLUDE"
fi

# 2) skip-worktree：已跟踪的模型文件不再被 git 触碰（避免假删除）
PT="py-server/models/career_mode_policy.pt"
if git ls-files --error-unmatch "$PT" >/dev/null 2>&1; then
  git update-index --skip-worktree "$PT"
  echo "✓ skip-worktree 已应用到 $PT"
else
  echo "⚠ $PT 未被 git 跟踪，跳过 skip-worktree（模型文件可能尚未就位；守卫在文件就位后仍需重建）"
fi

echo "✓ junction 守卫已重建。执行 'git status' 应不再把 py-server/models 显示为未跟踪或已删除。"
