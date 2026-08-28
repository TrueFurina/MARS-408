#!/usr/bin/env bash
# ============================================================
# 作品副本更新脚本（第十六循环P0）
# 用途：把项目根最新后端源码同步到提交包 08013417作品/ 副本（快照已归档至 archive/08013417_参赛快照/）
# 背景：第十二循环核对发现 08013417作品/ 源码副本落后于项目根
#       （关键文件 07 月 vs 项目根 08 月，缺记忆/插件新文件，195 vs 213 .py）
# 用法：bash scripts/update_workspace_copy.sh
# 注意：仅同步后端 py-server（作品目录无独立 src，前端用 dist 构建产物）
# ============================================================
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/py-server"
DEST="$ROOT/archive/08013417_参赛快照/08013417作品/py-server/py-server"

echo "== MARS-408 作品副本更新 =="
echo "源目录:   $SRC"
echo "目标目录: $DEST"

[ -d "$SRC" ] || { echo "❌ 源目录不存在: $SRC"; exit 1; }
[ -d "$DEST" ] || { echo "❌ 目标目录不存在: $DEST（作品目录结构异常）"; exit 1; }

# 排除清单（缓存/环境/构建/数据）
EXCLUDES=(
  --exclude '.venv'
  --exclude '__pycache__'
  --exclude '.pytest-tmp'
  --exclude '.pytest_cache'
  --exclude '*.pyc'
  --exclude '*.log'
  --exclude '*.db'
  --exclude '*.sqlite3'
)

# 优先 rsync（Git Bash/MSYS 可用），失败回退 find+cp
if command -v rsync >/dev/null 2>&1; then
  echo "使用 rsync 同步..."
  rsync -a --delete "${EXCLUDES[@]}" "$SRC/" "$DEST/"
else
  echo "rsync 不可用，使用 find+cp 同步..."
  rm -rf "$DEST"
  mkdir -p "$DEST"
  find "$SRC" -type f \
    ! -path '*/.venv/*' ! -path '*/__pycache__/*' \
    ! -path '*/.pytest-tmp/*' ! -path '*/.pytest_cache/*' \
    ! -name '*.pyc' ! -name '*.log' ! -name '*.db' ! -name '*.sqlite3' \
    -exec sh -c 'mkdir -p "$2/$(dirname "${1#$3/}")" && cp "$1" "$2/${1#$3/}"' _ {} "$DEST" "$SRC" \;
fi

COUNT=$(find "$DEST" -name '*.py' | wc -l)
echo "✅ 作品副本 py-server 已同步（排除缓存/构建/数据）"
echo "   目标 .py 文件数: $COUNT（项目根应为 213，副本同步后应接近）"
echo "   建议验证: cd py-server && pytest -q 跑通后再封包"
