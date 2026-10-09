#!/bin/sh
# ============================================================
# docker-entrypoint.sh — 芒得很职 非 root 运行入口（F-014）
# 以 root 启动：修复 bind mount 挂载点（vectordb_data / milvus_lite_data 等）
# 沿用宿主机 UID/GID 导致的无写权限问题，再切换非 root 用户运行应用。
# ============================================================
set -e

RUNTIME_USER="mangdehenzhi"
RUID=$(id -u "${RUNTIME_USER}")
RGID=$(id -g "${RUNTIME_USER}")

# 运行时可写目录：确保存在并归属运行时用户。
# bind mount 默认沿用宿主机 UID/GID，容器内 mangdehenzhi 可能无写权限，
# 故每次启动前修复属主（2>/dev/null 容忍个别路径不可写）。
for d in /app/vectordb_data /app/milvus_lite_data /app/data /app/sessions /app/plots /app/assets /app/media; do
  mkdir -p "$d"
  chown -R "${RUID}:${RGID}" "$d" 2>/dev/null || true
done

# ── 可选只读数据预检（把"静默空挂载"显式化）──
# ./documents（教材）与 ./py-server/models（E5/reranker 本地模型）是**可选大体积数据**：
# 教材 gitignored（数百 MB）、models 在宿主机是指向冷存盘的 symlink，均不入库。
# fresh clone 时宿主源目录不存在 → Docker 按 bind mount 语义创建**空目录** →
# 容器内挂载点为空 → 教材/本地模型缺失，表现为"功能凭空消失"。
# 这里在启动时显式检查并给出可操作提示，避免把数据缺失误判为功能缺陷。
check_optional_data() {
  _path="$1"
  _label="$2"
  _hint="$3"
  if [ ! -d "$_path" ]; then
    echo "[preflight] ⚠️  ${_label}：目录不存在 ${_path}"
    echo "[preflight]     ${_hint}"
  else
    # 仅统计真实数据文件：忽略占位文件（.gitkeep / README.md / .placeholder），
    # 避免"仅有占位"被误判为已就绪。
    _real="$(ls -A "$_path" 2>/dev/null | grep -vE '^(\.gitkeep|README\.md|\.placeholder)$')"
    if [ -z "$_real" ]; then
      echo "[preflight] ⚠️  ${_label}：挂载点为空 ${_path}（仅占位或宿主源目录缺失，Docker 自动创建了空目录）"
      echo "[preflight]     ${_hint}"
    else
      echo "[preflight] ✅ ${_label}：已就绪 ${_path}"
    fi
  fi
}

check_optional_data "/app/documents" "教材目录 documents" \
  "如需教材：把教材文件放入宿主 ./documents/ 后重启容器；留空则教材检索/后台导入能力降级，核心流程仍可运行。"
check_optional_data "/app/models" "本地模型 models（E5 / reranker）" \
  "如需本地模型：放入宿主 ./py-server/models/（或按 .env 指定路径）后重启容器；留空则相关能力降级，核心流程仍可运行。"

# 切换非 root 用户执行实际命令（来自 Dockerfile CMD：uvicorn ...）
# 优先 gosu（Debian 提供），回退 setpriv（util-linux，slim 自带）
if command -v gosu >/dev/null 2>&1; then
  exec gosu "${RUNTIME_USER}" "$@"
elif command -v setpriv >/dev/null 2>&1; then
  exec setpriv --reuid="${RUID}" --regid="${RGID}" --clear-groups -- "$@"
else
  exec su -s /bin/sh "${RUNTIME_USER}" -c "exec $*"
fi
