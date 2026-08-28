#!/bin/sh
# ============================================================
# docker-entrypoint.sh — MARS-408 非 root 运行入口（F-014）
# 以 root 启动：修复 bind mount 挂载点（vectordb_data / milvus_lite_data 等）
# 沿用宿主机 UID/GID 导致的无写权限问题，再切换非 root 用户运行应用。
# ============================================================
set -e

RUNTIME_USER="mars408"
RUID=$(id -u "${RUNTIME_USER}")
RGID=$(id -g "${RUNTIME_USER}")

# 运行时可写目录：确保存在并归属运行时用户。
# bind mount 默认沿用宿主机 UID/GID，容器内 mars408 可能无写权限，
# 故每次启动前修复属主（2>/dev/null 容忍个别路径不可写）。
for d in /app/vectordb_data /app/milvus_lite_data /app/data /app/sessions /app/plots /app/assets /app/media; do
  mkdir -p "$d"
  chown -R "${RUID}:${RGID}" "$d" 2>/dev/null || true
done

# 切换非 root 用户执行实际命令（来自 Dockerfile CMD：uvicorn ...）
# 优先 gosu（Debian 提供），回退 setpriv（util-linux，slim 自带）
if command -v gosu >/dev/null 2>&1; then
  exec gosu "${RUNTIME_USER}" "$@"
elif command -v setpriv >/dev/null 2>&1; then
  exec setpriv --reuid="${RUID}" --regid="${RGID}" --clear-groups -- "$@"
else
  exec su -s /bin/sh "${RUNTIME_USER}" -c "exec $*"
fi
