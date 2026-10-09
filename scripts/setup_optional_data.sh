#!/usr/bin/env bash
# ============================================================
# setup_optional_data.sh — 为 fresh clone 创建可选数据目录并落占位说明
#
# 背景（见 README「可选数据：教材与本地模型」）：
#   全新克隆时 ./documents 与 ./py-server/models 均不存在（被 .gitignore 排除），
#   Docker 会按 bind mount 语义自动创建空目录挂载 → 容器内挂载点为空 →
#   教材导入 / 本地模型推理表现为"功能凭空消失"。本脚本在克隆后一键建好目录
#   + 占位 README，让目录真实存在、并给出明确的放入指引。
#
# 用法： bash scripts/setup_optional_data.sh
# 前置： 无（纯本地目录操作，不需要 Docker）
# ============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

make_placeholder() {
  local dir="$1" note="$2"
  mkdir -p "$dir"
  if [ ! -f "$dir/README.md" ]; then
    cat > "$dir/README.md" <<EOF
# 可选数据目录（占位）

$note

- 本目录为**可选大体积数据**，不入库（被 .gitignore 排除），仅此 README.md 与 .gitkeep 占位文件随仓库跟踪。
- 放入真实数据后，容器启动 preflight 会显示 ✅ 已就绪；留空则相关能力优雅降级，核心流程仍可运行。
- 放入数据后重启容器生效：docker-compose restart app。
EOF
  fi
  touch "$dir/.gitkeep"
}

# 教材目录（真实目录，安全写入占位）
make_placeholder "$REPO_ROOT/documents" \
  "把教材文件（PDF / 笔记 / 课件等）放入本目录，后端 import_worker 会扫描并建立教材检索索引。"

# 本地模型目录：仅当它不是指向冷存盘的 symlink 时才建目录（避免污染冷存）
MODELS_DIR="$REPO_ROOT/py-server/models"
if [ -L "$MODELS_DIR" ]; then
  echo "[setup] 跳过 py-server/models：检测到指向冷存盘的 symlink，保持原样（无需创建）。"
else
  make_placeholder "$MODELS_DIR" \
    "把 E5 / reranker 本地模型目录（如 e5-base-v2/）放入本目录，或按 .env 的 MODEL_DIR 指定路径。"
fi

echo "✅ 可选数据目录已就绪："
echo "   ./documents/         （教材，可放文件）"
echo "   ./py-server/models/  （本地模型；若为 symlink 则跳过）"
echo "   放入真实数据后执行：docker-compose restart app"
