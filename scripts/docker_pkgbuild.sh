#!/usr/bin/env bash
# ============================================================
# docker_pkgbuild.sh — 芒得很职 docker 分离式构建前置（pkgbuild 阶段）
#
# 背景：容器内 npm ci / uv sync 经代理拉取会被 SSL 掐断。故把"装依赖"从镜像 build
# 挪到宿主机预构建 + 持久卷：
#   • 前端：宿主机 `npm ci --registry=npmmirror && npm run build-only` 生成 dist/
#   • 后端：本脚本构建 studyhelp-base:deps 基础镜像，并把 uv 依赖装进 studyhelp_venv 持久卷
#
# 前置：
#   1. Docker 守护进程已启动（Docker Desktop / dockerd）
#   2. 已在仓库根生成 dist/（前端预构建）
#
# 用法： bash scripts/docker_pkgbuild.sh
# 跑完后再 `docker compose up -d`
# ============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> [1/2] 构建 studyhelp-base:deps 基础镜像（python:3.12-slim + 清华源 apt + uv + mangdehenzhi 用户）"
docker build -f Dockerfile.base -t studyhelp-base:deps .

echo "==> [2/2] 初始化 studyhelp_venv 持久卷（uv sync，约 5.1GB，可能耗时数分钟）"
docker volume create studyhelp_venv >/dev/null

# py-server 只读挂载（不污染仓库），复制进 /tmp/build 后改 uv.lock 源为清华镜像，
# uv sync 生成 .venv，再拷入持久卷 /venv（= studyhelp_venv）。
docker run --rm \
  -v "${REPO_ROOT}/py-server:/workspace:ro" \
  -v studyhelp_venv:/venv \
  -w /workspace \
  studyhelp-base:deps \
  sh -c "cp -r /workspace /tmp/build && cd /tmp/build \
    && sed -i 's|https://files.pythonhosted.org|https://pypi.tuna.tsinghua.edu.cn|g' uv.lock \
    && uv sync --frozen --no-dev --no-install-project \
    && cp -r .venv/. /venv/"

echo "✅ pkgbuild 完成：studyhelp-base:deps 镜像 + studyhelp_venv 卷就绪"
echo "   下一步：docker compose up -d   # 访问 http://localhost:8002"
