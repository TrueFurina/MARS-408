# ============================================================
# app/static_sites.py — 静态资源与前端 SPA 挂载（M-4 拆分，自 main.py 下沉）
#
# 挂载顺序：plots / media（服务端产物）→ /assets、/showcase（前端 dist）→ SPA fallback 中间件。
# SPA fallback 必须最后注册（它是请求到响应的最外层包装），且与 StaticFiles 的
# 307 重定向行为耦合，改动前先看下面注释。
# ============================================================

import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.env import logger

# py-server 根目录（本文件位于 py-server/app/）
_PY_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 仓库根目录（前端 dist 在仓库根，不在 py-server 下 —— 沿用拆分前 main.py 的相对关系）
_REPO_ROOT = os.path.dirname(_PY_SERVER_DIR)

__all__ = ["install_plots_media", "install_spa"]


def install_plots_media(app: FastAPI) -> None:
    """挂载服务端生成的图片与多模态产物目录。"""
    plots_dir = os.path.join(_PY_SERVER_DIR, "plots")
    os.makedirs(plots_dir, exist_ok=True)
    app.mount("/plots", StaticFiles(directory=plots_dir), name="plots")

    # 多模态生成产物（.pptx / 视频等）静态服务，供前端/演示下载
    media_dir = os.path.join(_PY_SERVER_DIR, "media")
    os.makedirs(media_dir, exist_ok=True)
    app.mount("/media", StaticFiles(directory=media_dir), name="media")


def install_spa(app: FastAPI) -> None:
    """挂载前端 SPA（上线前检查 P2-1 / ADR-007 Docker 单镜像生产）。

    Dockerfile 已将前端 dist 拷至 ${STATIC_DIR}（默认 py-server/dist），挂载为根路径
    fallback，使单镜像对外暴露 UI；开发环境若 dist 不存在则跳过（仅 API 模式）。
    """
    static_dir = os.environ.get("STATIC_DIR") or os.path.join(_REPO_ROOT, "dist")
    if not os.path.isdir(static_dir):
        logger.info(f"前端静态目录不存在（{static_dir}），跳过 SPA 挂载（仅 API 模式）。")
        return

    # 挂载静态资源目录
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="spa_assets")
    # 挂载 showcase 展示页面（HTML 原型文件）
    showcase_dir = os.path.join(static_dir, "showcase")
    if os.path.isdir(showcase_dir):
        app.mount("/showcase", StaticFiles(directory=showcase_dir), name="showcase")

    index_path = os.path.join(static_dir, "index.html")

    # 用中间件处理 SPA 路由：所有 404 的 GET 请求返回 index.html
    @app.middleware("http")
    async def spa_fallback(request: Request, call_next):
        response = await call_next(request)
        # StaticFiles 挂载（如 /showcase）会对精确匹配的目录路径返回 307 重定向
        # （/showcase → /showcase/），导致 Vue SPA 路由 /showcase 直接访问时 404。
        # 此处将 307 也回退到 index.html，让 Vue Router 接管该路径。
        if response.status_code in (307, 404) and request.method == "GET" \
                and not request.url.path.startswith("/api/") \
                and not request.url.path.startswith("/assets/") \
                and not request.url.path.startswith("/plots/") \
                and not request.url.path.startswith("/media/") \
                and not request.url.path.startswith("/showcase/"):
            headers = {"Cache-Control": "no-cache, no-store, must-revalidate"}
            return FileResponse(index_path, headers=headers)
        return response

    logger.info(f"前端 SPA 已挂载: {static_dir} -> /")
