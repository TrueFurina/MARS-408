# ============================================================
# 芒得很职 — 基于 GOMARL 与 FrugalRAG 的计算机类学生职业素养对抗实训平台
# FastAPI 主入口 —— 只做「组装」，不含任何业务逻辑
#
# M-4 拆分（2026-09-27，原 882 行 → 组装层）：
#   环境引导   → app/env.py
#   生命周期   → app/lifespan.py
#   中间件     → app/middleware.py
#   异常处理   → app/errors.py
#   路由注册   → app/routers.py
#   运维端点   → app/status.py
#   静态/SPA   → app/static_sites.py
#
# ⚠️ 顺序约束（改动前必须读懂）：
#   1) bootstrap() 必须在任何业务 import 之前（见 app/env.py 说明）
#   2) 中间件 / 静态挂载 / 路由 / SPA 的注册顺序 = Starlette 包装顺序，不可随意调换
#   3) 以下重导出符号是现有测试与脚本的公开契约，删除会让它们 ImportError：
#      app / lifespan / _seed_vector_db / competition_status
# ============================================================

import logging
import os

# ① 环境引导：必须最先执行（HF 离线标记 / .env / 结构化日志）
from app.env import bootstrap
bootstrap()

from fastapi import FastAPI

from app import errors, middleware, routers, static_sites
from app.status import competition_status, install as install_status_routes, status
# “支撑式重导出”：lifespan 与 _seed_vector_db 属历史公开契约（tests/scripts 直接引用）
from app.lifespan import _seed_vector_db, lifespan  # noqa: F401

logger = logging.getLogger("netlearn")

app = FastAPI(
    title="芒得很职 — 基于 GOMARL 与 FrugalRAG 的计算机类学生职业素养对抗实训平台",
    description="芒得很职 计算机类学生职业素养对抗实训多智能体系统。\n\n"
                "## 核心架构\n"
                "- 11 节点 LangGraph 多智能体流水线（含 evidence_check 证据校验 + quality_gate 产物验收闸门）\n"
                "- GOMARL 共识引擎（NeuralMixer 神经网络加权融合）\n"
                "- FrugalRAG 检索增强生成（E5 + BM25 + 个性化重排）\n"
                "- 7 种学习资源并行生成\n\n"
                "## 技术栈\n"
                "后端: FastAPI + LangGraph + PyTorch + Milvus\n"
                "前端: Vue 3 + TypeScript + Vite\n"
                "LLM: DeepSeek / 讯飞星火 X2 两通道（P0 不接 Qwen2.5）\n\n"
                "## 安全\n"
                "- 94.88% API 认证覆盖率（241/254 个 /api 端点；"
                "scripts/verify_auth_coverage.py 可复现重算）\n"
                "- JWT HMAC-SHA256 Token\n"
                "- PBKDF2 密码哈希\n"
                "- DOMPurify XSS 防护\n"
                "- 安全响应头 (CSP/HSTS/X-Frame-Options)",
    version="2.0.0",
    lifespan=lifespan,
)

# ── OpenAPI 去重：GET+HEAD 同挂一条 route 时的 operationId 重号 ─────────────────
# /api/status 用 `api_route(methods=["GET","HEAD"])` 一条 route 挂两个方法（必须是一条，
# 否则 `verify_auth_coverage.collect()` 按 route 计数会把 /api 端点从 245 顶到 246）。
# 但 FastAPI 会为这两个方法各生成一个 operation，且**复用同一个 operationId**
# （实测：get 与 head 都写成 `status_api_status_head`，并告警
#  "Duplicate Operation ID ..."）。OpenAPI 规范要求 operationId 唯一 ⇒ 不对齐的话
# 随源码包发出的 openapi.json 会是**非法文档**。
#
# 处置：HEAD 是 HTTP 传输层的便利语义（GET 可用处即应可用），按惯例**不列入对外契约**；
# 故此处把与同路径 GET 重号的 head 操作摘掉 —— 对外契约仍是 246 操作、与快照逐字一致，
# 而路由表本身未改（HEAD 仍然真实可用，`tests/test_app_status_invariants.py`
# ::test_head_status_endpoint_supported 守着这一点）。
# 该告警由 FastAPI 在生成阶段抛出、且我们紧随其后确定性地消除，故就地点屏蔽，
# 避免每次导出契约都刷一条已被处理的噪音。
_app_openapi = app.openapi


def _openapi_dedup_head() -> dict:
    """导出契约前摘掉与同路径 GET 重号的 head 操作（见上方说明）。"""
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message=r".*Duplicate Operation ID.*", category=UserWarning
        )
        spec = _app_openapi()
    for ops in (spec.get("paths") or {}).values():
        head, get = ops.get("head"), ops.get("get")
        if head and get and head.get("operationId") == get.get("operationId"):
            ops.pop("head")
    return spec


app.openapi = _openapi_dedup_head

# ② 静态资源（plots / media）
static_sites.install_plots_media(app)

# ③ 中间件（CORS / GZip / 指标 / 安全头 / 体积限制 / 限流）
middleware.install(app)

# ④ 统一异常处理（D-08 / F-017 脱敏）
errors.install(app)

# ⑤ 业务路由（统一 /api 前缀）
routers.install(app)

# ⑥ 运维端点（/api/status、/api/status/competition、/metrics）
install_status_routes(app)

# ⑦ 前端 SPA 挂载（最后：SPA fallback 需包在最外层，且依赖 /assets 已挂载）
static_sites.install_spa(app)

# 兼容旧 import 路径：这些符号历史上位于 main 模块
__all__ = ["app", "lifespan", "_seed_vector_db", "competition_status", "status"]


def resolve_bind() -> tuple[str, int]:
    """解析 uvicorn 的绑定地址 (host, port)（环境变量驱动）。

    发布通道硬契约：容器化/沙箱化发布时运行环境会注入 ``PORT``，服务必须监听它
    并绑定 ``0.0.0.0`` 才能被外部访问。本函数把绑定地址从硬编码改为环境变量驱动，
    同时**保持本机开发的默认行为完全不变**（仍是 ``127.0.0.1:8002``）。

    规则（纯函数，便于单元测试，不读取除环境变量外的任何状态）：
      - ``port = int(os.environ["PORT"])`` 若 ``PORT`` 已设置，否则 ``8002``；
      - ``host = os.environ["HOST"]`` 若显式设置（最高优先级）；
        否则当 ``PORT`` 已设置时用 ``"0.0.0.0"``（沙箱需对外可达），
        否则用 ``"127.0.0.1"``（本机开发默认，避免无意暴露到局域网）。

    返回:
        (host, port) 二元组。
    """
    raw_port = os.environ.get("PORT")
    port = int(raw_port) if raw_port else 8002
    host = os.environ.get("HOST") or ("0.0.0.0" if raw_port else "127.0.0.1")
    return host, port


if __name__ == "__main__":
    import uvicorn

    reload_mode = os.environ.get("UVICORN_RELOAD", "").lower() in ("1", "true", "yes")
    _host, _port = resolve_bind()
    # workers=1 不可改：vectordb_data/.import_writer.lock 为单写者锁（见 lifespan._assert_single_worker）。
    uvicorn.run("main:app", host=_host, port=_port, reload=reload_mode, workers=1)
