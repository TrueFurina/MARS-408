# ============================================================
# Dockerfile — MARS-408 408 个性化学习系统
# 多阶段构建：前端构建 → Python后端（含 Milvus 支持）
# ============================================================

# ── Stage 1: 构建前端 ──
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

# 只复制前端所需的文件（利用 .dockerignore + 显式 COPY 减少层体积）
COPY package*.json ./
COPY index.html ./
COPY env.d.ts ./
COPY tsconfig*.json ./
COPY vite.config.ts ./
COPY public/ ./public/
COPY src/ ./src/

RUN npm ci && npm run build-only

# ── Stage 2: Python后端 ──
FROM python:3.12-slim

# 安装系统依赖（PyMilvus 二进制包无需 gcc，但保留 libffi 以防降级回退）
# gosu：用于以非 root 用户运行应用（F-014），回退 setpriv（util-linux，slim 自带）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libffi-dev ffmpeg gosu \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN groupadd -r mars408 && useradd -r -g mars408 -d /app -s /sbin/nologin mars408

WORKDIR /app

# ── D7：镜像元数据标签（固定 VERSION，避免 latest）──
ARG VERSION=1.0.0
ARG BUILD_DATE
LABEL org.opencontainers.image.title="MARS-408 个性化学习系统"
LABEL org.opencontainers.image.version="$VERSION"
LABEL org.opencontainers.image.created="$BUILD_DATE"
LABEL org.opencontainers.image.description="408 考研 GOMARL + FrugalRAG 多智能体学习系统"
LABEL maintainer="MARS-408 Team"

# 复制并安装 Python 依赖（先复制作业文件，利用 Docker 层缓存）
COPY py-server/pyproject.toml py-server/uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev --no-install-project

# 复制后端代码
COPY py-server/ ./

# 复制前端构建产物
COPY --from=frontend-builder /app/frontend/dist ./static

# 确保代码/依赖/静态资源属主为运行时非 root 用户
RUN chown -R mars408:mars408 /app

# F-014：显式创建运行时可写目录（含 bind mount 挂载点 vectordb_data / milvus_lite_data / data），
# 并授权给运行时用户 mars408，避免挂载卷沿用宿主机 UID 导致无写权限。
RUN mkdir -p /app/vectordb_data /app/milvus_lite_data /app/data /app/sessions /app/plots /app/assets /app/media \
    && chown -R mars408:mars408 /app/vectordb_data /app/milvus_lite_data /app/data /app/sessions /app/plots /app/assets /app/media

# F-014：启动入口（已随 COPY py-server/ ./ 带入）——以 root 修复挂载卷属主，再用 gosu 切换非 root 运行
RUN chmod +x /app/docker-entrypoint.sh

# 环境变量
ENV PYTHONPATH=/app
ENV STATIC_DIR=/app/static
ENV HOST=0.0.0.0
ENV PORT=8002
ENV LLM_PROVIDER=auto
ENV MILVUS_HOST=milvus
ENV MILVUS_PORT=19530

# F-014：不再在此直接 USER，改由 docker-entrypoint.sh 以 root 启动并 gosu 切换非 root 用户运行。
# （bind mount 挂载点需 root 修复属主后再降权，故入口负责降权。）

# 暴露端口
EXPOSE 8002

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -sf http://localhost:8002/api/status || exit 1

# 启动命令（作为 entrypoint 的参数；entrypoint 负责修复挂载卷属主并以非 root 用户运行）
# ADR-007 硬约束：必须 --workers 1（单进程），多进程会重新引入多写者(last-writer-wins)。切勿加 --workers N (N>1)。
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uv", "run", "python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
