# ============================================================
# Dockerfile — 芒得很职 多智能体职业素养实训平台
# 多阶段构建：前端构建 → Python后端（含 Milvus 支持）
# 注意：必须以 BuildKit 构建（RUN --mount=type=cache 需要），本机 compose 默认回退 legacy，需 DOCKER_BUILDKIT=1
# ============================================================

# ── Stage 1: 前端产物 ──
# 容器内 npm ci 经代理拉 npmjs.org 会被 SSL 掐断（多次"Exit handler never called"），
# 改为宿主机构建（npm ci --registry=npmmirror + npm run build-only），此处直接 COPY 产物 dist/

# ── Stage 2: Python后端 ──
FROM python:3.12-slim

# 安装系统依赖（PyMilvus 二进制包无需 gcc，但保留 libffi 以防降级回退）
# gosu：用于以非 root 用户运行应用（F-014），回退 setpriv（util-linux，slim 自带）
# 换清华镜像源（国内直连提速，避开代理链路）
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
    curl libffi-dev ffmpeg gosu \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN groupadd -r mangdehenzhi && useradd -r -g mangdehenzhi -d /app -s /sbin/nologin mangdehenzhi

WORKDIR /app

# ── D7：镜像元数据标签（固定 VERSION，避免 latest）──
ARG VERSION=1.0.0
ARG BUILD_DATE
LABEL org.opencontainers.image.title="芒得很职 多智能体职业素养实训平台"
LABEL org.opencontainers.image.version="$VERSION"
LABEL org.opencontainers.image.created="$BUILD_DATE"
LABEL org.opencontainers.image.description="芒得很职 多智能体职业素养实训平台（GOMARL + FrugalRAG）"
LABEL maintainer="芒得很职 Team"

# 复制并安装 Python 依赖（先复制作业文件，利用 Docker 层缓存）
COPY py-server/pyproject.toml py-server/uv.lock ./
# uv.lock 记录的是 files.pythonhosted.org（经代理慢/易断），改写为清华镜像直连
RUN sed -i 's|https://files.pythonhosted.org|https://pypi.tuna.tsinghua.edu.cn|g' uv.lock
# uv 下载缓存挂载为持久 cache volume（存于 VM 磁盘，引擎重启不丢，断点续传）
# 限流 uv 并发：默认 50 并发下载是历史死亡窗口的触发负载（4GB 限额 VM 内内存尖峰），
# 实测并发 4 连续 18 分钟稳定；EOF 家族第 4 例（1018s 处）后加入此限流
ENV UV_CONCURRENT_DOWNLOADS=4
ENV UV_CONCURRENT_INSTALLS=4
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uv \
    && uv sync --frozen --no-dev --no-install-project

# 复制后端代码
COPY py-server/ ./

# 复制前端构建产物（宿主机预构建）
COPY dist ./static

# 确保代码/依赖/静态资源属主为运行时非 root 用户
RUN chown -R mangdehenzhi:mangdehenzhi /app

# F-014：显式创建运行时可写目录（含 bind mount 挂载点 vectordb_data / milvus_lite_data / data），
# 并授权给运行时用户 mangdehenzhi，避免挂载卷沿用宿主机 UID 导致无写权限。
RUN mkdir -p /app/vectordb_data /app/milvus_lite_data /app/data /app/sessions /app/plots /app/assets /app/media \
    && chown -R mangdehenzhi:mangdehenzhi /app/vectordb_data /app/milvus_lite_data /app/data /app/sessions /app/plots /app/assets /app/media

# F-014：启动入口（已随 COPY py-server/ ./ 带入）——以 root 修复挂载卷属主，再用 gosu 切换非 root 运行
# sed 剥离 CR：Windows 工作区 checkout 可能是 CRLF（core.autocrlf=true），
# 一旦烘进镜像，`set -e` 会被解析成 `set -e\r` → 报 "set: Illegal option -"、entrypoint 启动即崩。
# .gitattributes 已从源头锁 LF；这里作为构建上下文的纵深兜底，与 Dockerfile.final 保持一致。
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

# 环境变量
ENV PYTHONPATH=/app
# uv 走清华 PyPI 镜像（国内直连提速，压进引擎存活窗口）
ENV UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
ENV STATIC_DIR=/app/static
ENV HOST=0.0.0.0
ENV PORT=8002
# ADR-007/008 单写者：环境变量层固化单进程，防编排器注入 >1
# （uvicorn 不读该变量，但 main.py 启动守卫会核验 WEB_CONCURRENCY/UVICORN_WORKERS，>1 即 fail-fast）
ENV WEB_CONCURRENCY=1
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
# ADR-007 硬约束：CLI 显式 --workers 1（单进程），与上方 ENV WEB_CONCURRENCY=1 双保险
CMD ["uv", "run", "python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]
