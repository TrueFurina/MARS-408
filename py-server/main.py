# ============================================================
# MARS-408 — 基于 GOMARL 与 FrugalRAG 的 408 考研个性化学习系统
# FastAPI 主入口（重构版：路由拆分 + Milvus/InMemoryVectorStore 抽象层）
# ============================================================

import os
import logging
import time

# 本机无外网：强制 HuggingFace / Transformers 离线，避免检索重排模型
# (BAAI/bge-reranker-base) 在每次请求时尝试下载并因连接超时反复重试约 90s，
# 同步阻塞事件循环导致 LangGraph 协作流（retriever→rerank）卡死、后端无响应。
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# 尽早加载 .env（AUTH_SECRET / XF_* 等）到 os.environ，必须在 import 任何
# 模块级读取 os.environ 的模块（如 shared.auth）之前执行，否则 AUTH_SECRET
# 模块级读取为空、每次启动生成临时密钥（重启后已签发 Token 全部失效）。
from config import _load_dotenv
_load_dotenv()

# ── D11：结构化日志（JSON：ts/level/logger/msg）── 尽早启用，覆盖启动与关键错误 ──
from shared.logging_config import setup_structured_logging
_log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
setup_structured_logging(getattr(logging, _log_level, logging.INFO))

from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.exceptions import RequestValidationError

# ── 数据层 ──
from db.milvus_client import vector_db
from db.pg_client import pg_client
from db.redis_client import redis_client
# 导入队列 Worker（ADR-007：后端进程内单写者）
from services.import_worker import import_worker

# ── 种子数据 ──
from seed_data import SEED_KNOWLEDGE_CHUNKS, SEED_QUESTIONS

# ── 统一错误处理 ──
from shared.errors import DomainError, domain_error_handler, unhandled_exception_handler

# ── D5：进程内指标收集（/metrics，Prometheus 文本格式）──
from shared.metrics import record_request, inc_inflight, render_prometheus

# ── API 路由 ──
from api import (
    chat_router, profile_router, quiz_router, rag_router,
    agents_router, knowledge_router, sessions_router,
    learning_router, sandbox_router, config_router,
    subjects_router, assessment_router, langgraph_router,
    engine_router, teacher_router, multimodal_router,
    tutor_router, auth_router, user_router, admin_router,
    admin_users_router,
    xfyun_router, imports_router, llm_health_router,
    skills_router, tts_router, diagnostic_router, review_router,
    audit_router,
    knowledge_graph_router,
    english_router,
    knowledge_base_router,
    achievement_router,
    resource_router,
    memory_router,
    wrong_questions_router,
    daily_plan_router,
)

# 注：结构化日志已在模块导入期由 setup_structured_logging() 启用（D11），
# 此处不再调用 basicConfig，避免覆盖 JSON formatter 与重复输出。
logger = logging.getLogger("netlearn")


def _seed_vector_db():
    """向向量库写入种子数据（Milvus 或 InMemoryVectorStore）

    INC-03：为每条 chunk 注入 metadata.group（1-26 章节编号），
    单一真源 = agents.kg_dag.chapter_to_group，供 PathPlanner KG-DAG 与
    知识库按 group 过滤使用。幂等由调用方（count==0 才写入）保证。
    """
    from agents.kg_dag import chapter_to_group

    chunks = []
    for i, chunk in enumerate(SEED_KNOWLEDGE_CHUNKS):
        meta = dict(chunk.get("metadata", {}))
        if "group" not in meta:
            meta["group"] = chapter_to_group(meta.get("subject", ""), meta.get("chapter"))
        chunks.append({
            "id": f"chunk_{i}",
            "text": chunk["content"],
            "metadata": meta,
        })
    for i, q in enumerate(SEED_QUESTIONS):
        chunks.append({
            "id": f"question_{i}",
            "text": f"[{q['type']}] {q['text']} 答案: {q['answer']} 来源: {q['source']}",
            "metadata": {
                "subject": q["subject"], "chapter": q["chapter"],
                "group": chapter_to_group(q["subject"], q.get("chapter")),
                "type": "question", "difficulty": q["difficulty"],
                "question_id": q["id"],
            },
        })
    inserted = vector_db.insert("netlearn_kb", chunks)
    logger.info(f"种子数据写入完成，共 {len(chunks)} 个文档，实际插入 {inserted}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动：连接向量库+PG+Redis，写入种子数据"""
    import asyncio
    logger.info("正在初始化数据层...")
    _lifespan_t0 = time.perf_counter()

    # ── 启动期密钥校验（F-005 fail-fast）：生产缺失 AUTH_SECRET / 长度不足即启动失败 ──
    # main.py 在 import 本模块前已调用 _load_dotenv() 加载 .env，故此处可读到 AUTH_SECRET；
    # 生产环境若 AUTH_SECRET 未设置或长度 < 32，将直接 raise 使应用无法启动（fail-closed）。
    from shared.auth import resolve_auth_secret
    try:
        resolve_auth_secret()
    except RuntimeError as _auth_err:
        logger.error("AUTH_SECRET 校验失败，应用拒绝启动：%s", _auth_err)
        raise

    # ── 向量数据库（Milvus 优先，InMemoryVectorStore 回退）─ 同步，先完成 ──
    _vdb_t0 = time.perf_counter()
    vector_db.connect()
    count = vector_db.count("netlearn_kb")
    if count == 0:
        logger.info("向量库为空，写入内置种子数据...")
        _seed_vector_db()
        count = vector_db.count("netlearn_kb")
    logger.info(
        "向量库就绪，共 %d 个文档（Milvus 或 InMemoryVectorStore）；初始化耗时 %.0fms",
        count, (time.perf_counter() - _vdb_t0) * 1000,
    )

    # ── 408 教材自动扩充（pending 标记；实际导入在 import_worker 启动后 enqueue）──
    # 旧实现：本阶段用子进程调 import_textbook.py，而该脚本 __main__ 已改为向本后端
    # HTTP 提交 job；但 lifespan 阶段后端尚未对外服务 → 导入必败、知识库卡在种子量、
    # 且每次冷启动都白跑一个必败子进程（约 30s 冷启动瓶颈之一）。
    # 现改为：仅在此打标记，待下方 import_worker.start() 后再 enqueue，复用与在线导入
    # 一致的进程内单写者（ADR-007）路径，count>=500 后不再重复触发。
    _textbook_import_pending = count < 500

    # ── 非关键组件并行初始化（PG + Redis + Admin 互不依赖） ──
    async def _init_pg():
        try:
            await asyncio.wait_for(
                asyncio.to_thread(pg_client.connect), timeout=5
            )
            logger.info("PostgreSQL 就绪")
        except asyncio.TimeoutError:
            logger.warning("PostgreSQL 连接超时（5s），跳过 PG 降级运行")
            pg_client._enabled = False
        except Exception as e:
            logger.warning(f"PostgreSQL 未启用: {e}")

    async def _init_redis():
        try:
            ok = await asyncio.wait_for(
                asyncio.to_thread(redis_client.connect), timeout=5
            )
            if ok:
                logger.info("Redis 就绪")
            else:
                logger.warning("Redis 未启用")
        except asyncio.TimeoutError:
            logger.warning("Redis 连接超时（5s），跳过 Redis 降级运行")
            redis_client._enabled = False
        except Exception as e:
            logger.warning(f"Redis 未启用: {e}")

    async def _init_admin():
        from db.user_store import ensure_admin
        env = os.environ.get("NETLEARN_ENV", "development").lower()
        admin_pwd = os.environ.get("ADMIN_PASSWORD", "")
        if not admin_pwd:
            if env in ("production", "prod"):
                # 生产环境禁止默认/随机口令：缺失即 fail-fast，避免弱口令上线
                raise RuntimeError(
                    "生产环境必须设置环境变量 ADMIN_PASSWORD（建议由密钥管理器注入强随机口令，长度>=16），"
                    "拒绝以默认/随机口令启动。"
                )
            import secrets as _secrets
            admin_pwd = _secrets.token_urlsafe(16)
            # 注意：仅记录「已生成」，绝不输出明文口令本身
            logger.warning(
                "ADMIN_PASSWORD 未设置，已生成随机管理员密码（重启将失效）。"
                " 生产环境请通过环境变量固定 ADMIN_PASSWORD。"
            )
        # F-004 生产模式强制口令最小长度 16（防弱口令）
        if env in ("production", "prod") and len(admin_pwd) < 16:
            raise RuntimeError(
                f"生产环境 ADMIN_PASSWORD 长度必须 >= 16（当前 {len(admin_pwd)}）。"
                " 请注入足够强的管理员口令。"
            )
        try:
            ensure_admin(
                os.environ.get("ADMIN_USERNAME", "admin"),
                admin_pwd,
            )
            logger.info("管理员账号已就绪（用户名: admin）")
        except Exception as e:
            logger.warning(f"管理员账号初始化失败: {e}")

    await asyncio.gather(_init_pg(), _init_redis(), _init_admin())

    # ── D6：数据库迁移（幂等，仅记录已应用版本）── 在 PG/SQLite 连接后执行
    try:
        from db.migrations import run_migrations
        applied_n = run_migrations()
        if applied_n:
            logger.info("数据库迁移完成，本次新应用 %d 个版本", applied_n)
    except Exception as e:
        logger.warning("数据库迁移执行失败（非阻塞）: %s", e)

    # ── 首次启动时写入演示种子数据（仅非生产环境，避免生产自动创建弱口令演示账户）──
    try:
        env = os.environ.get("NETLEARN_ENV", "development").lower()
        if env not in ("production", "prod"):
            from db.user_store import authenticate
            if authenticate("demo", "demo123456") is None:
                from seed_demo_data import seed_demo_data
                seed_demo_data()
        else:
            logger.info("生产环境跳过演示种子账户写入（demo/demo123456）。")
    except Exception as e:
        logger.warning(f"演示种子数据写入失败（非阻塞）: {e}")

    # ── LLM 凭证检测：无凭证时提示 demo 模式降级（仅警告，不阻塞启动）──
    # 核心链路（画像/资源生成/路径）在无 LLM 时返回内置样例或友好降级提示，不报错。
    # 已配置凭证时不输出任何信息，保持日志整洁。
    try:
        from config import load_config as _load_cfg
        _cfg = _load_cfg()
        _has_llm = (
            bool(_cfg.get("deepseek", {}).get("api_key"))
            or bool(_cfg.get("xfyun", {}).get("api_key"))
            or bool(_cfg.get("xfyun", {}).get("app_id"))
            or bool(_cfg.get("xfyun", {}).get("api_password"))
        )
        if not _has_llm:
            logger.warning(
                "未检测到 LLM 凭证（DEEPSEEK_API_KEY / XF_API_KEY / XF_API_PASSWORD 均未配置），"
                "已进入 demo 模式：智能对话等 LLM 功能返回降级提示，"
                "画像/资源生成/学习路径等核心链路使用内置样例运行。"
                "配置 LLM 凭证后重启即可恢复完整 AI 能力。"
            )
    except Exception:
        pass  # 检测失败不影响启动

    # ── 导入队列 Worker（ADR-007）── 在 yield 前拉起
    # 硬约束：uvicorn 必须 --workers 1，多进程会重新引入多写者(last-writer-wins)
    _workers = int(os.environ.get("UVICORN_WORKERS", os.environ.get("WEB_CONCURRENCY", "1")))
    # 检测命令行参数 --workers N
    import sys
    for i, arg in enumerate(sys.argv):
        if arg == "--workers" and i + 1 < len(sys.argv):
            try:
                _workers = int(sys.argv[i+1])
            except ValueError:
                pass
            break
    if _workers > 1:
        raise RuntimeError(
            f"[import] ADR-007 硬约束违规：workers数量={_workers} (>1)。"
            " 多进程会重新引入多写者(last-writer-wins)，必须 --workers 1 启动。"
        )
    await import_worker.start()

    # OS_course: artifact lifecycle cleanup — periodically purge old session outputs (>7 days)
    _CLEANUP_INTERVAL = 3600  # 1 hour between sweeps
    _SESSION_MAX_AGE = 7 * 86400  # 7 days
    async def _cleanup_old_sessions():
        while True:
            await asyncio.sleep(_CLEANUP_INTERVAL)
            try:
                sessions_dir = os.path.join(os.path.dirname(__file__), "sessions")
                if os.path.isdir(sessions_dir):
                    now = time.time()
                    removed = 0
                    for user_dir in os.listdir(sessions_dir):
                        user_path = os.path.join(sessions_dir, user_dir)
                        if not os.path.isdir(user_path):
                            continue
                        for fname in os.listdir(user_path):
                            fpath = os.path.join(user_path, fname)
                            try:
                                if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > _SESSION_MAX_AGE:
                                    os.remove(fpath)
                                    removed += 1
                            except OSError:
                                pass
                        try:
                            if not os.listdir(user_path):
                                os.rmdir(user_path)
                        except OSError:
                            pass
                    if removed:
                        logger.info("artifact lifecycle: removed %d old session files (>7d)", removed)

                # L3 情景记忆生命周期清理（90 天保留窗口，对标 HKU-DeepTutor 记忆管理）
                try:
                    from db.memory_store import prune_episodes
                    pruned = prune_episodes(retention_days=90)
                    if pruned:
                        logger.info("memory lifecycle: pruned %d episodic records (>90d)", pruned)
                except Exception as _me:
                    logger.debug("memory lifecycle sweep skipped: %s", _me)
            except Exception as _ce:
                logger.debug("artifact cleanup sweep skipped: %s", _ce)
    _cleanup_task = _asyncio.create_task(_cleanup_old_sessions())

    # ── 408 教材自动扩充：经进程内导入队列（ADR-007 单写者），非阻塞后台执行 ──
    if _textbook_import_pending:
        try:
            job_id = await import_worker.submit("textbook", None, {})
            logger.info("已提交教材自动导入任务（后台执行，job=%s）", job_id)
        except Exception as e:
            logger.warning("教材自动导入任务提交失败（非阻塞）: %s", e)

    logger.info(
        "应用启动完成（所有组件就绪）；冷启动总耗时 %.0fms",
        (time.perf_counter() - _lifespan_t0) * 1000,
    )

    yield

    # Cancel artifact cleanup task
    try:
        _cleanup_task.cancel()
    except Exception:
        pass
    # 关闭连接
    await import_worker.stop()
    # P1：释放 httpx 连接池（避免未关闭客户端警告）
    try:
        from db.llm_provider import _close_http_clients
        await _close_http_clients()
    except Exception:
        pass
    vector_db.disconnect()
    try:
        pg_client.disconnect()
    except Exception:
        pass
    try:
        redis_client.disconnect()
    except Exception:
        pass


# ── FastAPI App ──
app = FastAPI(
    title="MARS-408 — 基于 GOMARL 与 FrugalRAG 的 408 考研个性化学习系统",
    description="MARS-408 408 考研个性化学习多智能体系统。\n\n"
                "## 核心架构\n"
                "- 13 个智能体 / 10 节点 LangGraph 多智能体流水线（含 evidence_check 证据校验 + quality_gate 产物验收闸门）\n"
                "- GOMARL 共识引擎（NeuralMixer 神经网络加权融合）\n"
                "- FrugalRAG 检索增强生成（E5 + BM25 + 个性化重排）\n"
                "- 7 种学习资源并行生成\n\n"
                "## 技术栈\n"
                "后端: FastAPI + LangGraph + PyTorch + Milvus\n"
                "前端: Vue 3 + TypeScript + Vite\n"
                "LLM: DeepSeek / 讯飞星火 X2 两通道（P0 不接 Qwen2.5）\n\n"
                "## 安全\n"
                "- 97.8% API 认证覆盖率\n"
                "- JWT HMAC-SHA256 Token\n"
                "- PBKDF2 密码哈希\n"
                "- DOMPurify XSS 防护\n"
                "- 安全响应头 (CSP/HSTS/X-Frame-Options)",
    version="2.0.0",
    lifespan=lifespan,
)

plots_dir = os.path.join(os.path.dirname(__file__), "plots")
os.makedirs(plots_dir, exist_ok=True)
app.mount("/plots", StaticFiles(directory=plots_dir), name="plots")

# 多模态生成产物（.pptx / 视频等）静态服务，供前端/演示下载
media_dir = os.path.join(os.path.dirname(__file__), "media")
os.makedirs(media_dir, exist_ok=True)
app.mount("/media", StaticFiles(directory=media_dir), name="media")

# ── CORS 配置 (D3: production 仅允许 CORS_ALLOW_ORIGINS 白名单；
#    dev 用 allow_origin_regex 放行本机 loopback 与 LAN，覆盖 vite 端口 5173-5181) ──
_cors_env = (
    os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    or os.environ.get("CORS_ORIGINS", "").strip()
)
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()] if _cors_env else []
_cors_kwargs = {
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Authorization", "Content-Type"],
}
if os.environ.get("NETLEARN_ENV", "development").lower() in ("production", "prod"):
    # 生产：仅显式白名单；缺失则不允许任何跨域（最小权限，杜绝通配 *）
    _cors_kwargs["allow_origins"] = _cors_origins
else:
    # 开发：regex 放行 localhost / 127.0.0.1 / IPv6 loopback / 本机 LAN（含 vite 5173-5181）
    # 注意：allow_credentials=True 时不可使用 "*"，故用正则 + 可选显式白名单
    _cors_kwargs["allow_origin_regex"] = (
        r"^https?://(localhost|127\.0\.0\.1|\[::1\]"
        r"|192\.168\.\d{1,3}\.\d{1,3}"
        r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
        r"|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})"
        r"(:(\d{1,5}))?$"
    )
    _cors_kwargs["allow_origins"] = _cors_origins
app.add_middleware(CORSMiddleware, **_cors_kwargs)

# ── GZip 压缩（对所有 ≥1KB 的 API 响应启用，减少传输体积）──
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── D5：指标收集中间件（在途计数 + 按路径计时）── 置于最外层，覆盖全部请求 ──
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    inc_inflight(1)
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        inc_inflight(-1)
        latency = time.perf_counter() - start
        record_request(request.url.path, status, latency)
        logger.info(
            "request %s %s -> %s (%.0fms)",
            request.method, request.url.path, status, latency * 1000,
        )

# ── 安全响应头中间件 (F-016: CSP / X-Frame-Options / HSTS / Permissions-Policy) ──
from fastapi.responses import Response, JSONResponse

# 生产环境（NETLEARN_ENV==production）才强制 HSTS（HTTPS）；
# 开发环境为 http，不发送 HSTS，避免浏览器拒绝本地连接。
_SECURITY_ENV = os.environ.get("NETLEARN_ENV", "development").lower()
_IS_PRODUCTION = _SECURITY_ENV in ("production", "prod")

# 合理默认值：生产构建 Vite 无内联脚本（Vue SFC 编译后独立 .js），
# 开发模式 HMR 需要 unsafe-inline；此处仅生产加固 script-src。
# style-src 保留 unsafe-inline：Vue SFC scoped style 和 Google Fonts 内联依赖。
# 注：完整的 nonce/hash CSP 需服务端动态注入，属后续加固项。
_CSP_PRODUCTION = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "media-src 'self' blob:; "
    "connect-src 'self' ws: wss:; "
    "frame-ancestors 'self';"
)
_CSP_DEV = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "   # Vite HMR 热重载需要内联脚本
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "media-src 'self' blob:; "
    "connect-src 'self' ws: wss:; "
    "frame-ancestors 'self';"
)
_CSP = _CSP_PRODUCTION if _IS_PRODUCTION else _CSP_DEV
# 限制敏感浏览器特性（摄像头/麦克风/地理位置/支付等），降低被滥用于越权采集的风险
_PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), payment=(), usb=(), interest-cohort=()"
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "no-referrer"
    # 浏览器 WASI（/code-lab 的 C/C++ 编译实验室）依赖跨源隔离，
    # 需同时返回 COOP/COEP；与 vite dev server headers 保持一致，
    # 生产网关/反向代理不可移除这两个头（移除后 SharedArrayBuffer 不可用）。
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"

    # /showcase 路径放行 unsafe-inline：评委展示用原型 HTML 含内联脚本，
    # 生产 CSP `script-src 'self'` 会阻断其运行，故对该路径沿用开发 CSP。
    _csp = _CSP
    if _IS_PRODUCTION and request.url.path.startswith("/showcase"):
        _csp = _CSP_DEV

    response.headers["Content-Security-Policy"] = _csp
    response.headers["Permissions-Policy"] = _PERMISSIONS_POLICY
    # 仅生产环境（HTTPS）强制 HSTS；开发环境不发送，避免本地 http 被浏览器拒掉
    if _IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── 请求体大小限制中间件 (F-018: 防超大请求体 / DoS) ──
# 仅拦截带 Content-Length 且超标的请求；chunked/流式（无 Content-Length）不受影响。
_MAX_REQUEST_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", str(50 * 1024 * 1024)))


@app.middleware("http")
async def request_size_limit_middleware(request: Request, call_next) -> Response:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            body_len = int(content_length)
        except ValueError:
            body_len = 0
        if body_len > _MAX_REQUEST_BYTES:
            logger.warning(
                "请求体过大被拒绝 path=%s bytes=%d limit=%d",
                request.url.path, body_len, _MAX_REQUEST_BYTES,
            )
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "PAYLOAD_TOO_LARGE",
                        "message": "请求体过大，请减小上传内容后重试",
                    }
                },
            )
    return await call_next(request)


# ── 统一错误处理 (D-08) ──
# F-017：错误消息脱敏
#   - HTTPException：dev 返回 detail 原文（保持 {"detail": ...} 契约）；
#     production 返回通用文案、保留 status_code，完整 detail 写入结构化日志。
#   - RequestValidationError（422）：dev 返回字段级错误；production 脱敏为通用文案。
#   - 未捕获异常：由 unhandled_exception_handler 统一返回 500 通用文案并记完整堆栈。
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    status_code = exc.status_code
    if _IS_PRODUCTION:
        logger.error(
            "HTTPException status=%s detail=%s path=%s",
            status_code, exc.detail, request.url.path,
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "HTTP_ERROR", "message": "请求处理失败，请稍后重试"}},
        )
    return JSONResponse(status_code=status_code, content={"detail": exc.detail})


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    status_code = getattr(exc, "status_code", 422)
    if _IS_PRODUCTION:
        logger.error(
            "请求参数校验失败 path=%s errors=%s",
            request.url.path, exc.errors(),
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": "VALIDATION_ERROR", "message": "请求参数不合法"}},
        )
    return JSONResponse(status_code=status_code, content={"detail": exc.errors()})


app.add_exception_handler(DomainError, domain_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, request_validation_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ── 注册路由 (统一 /api 前缀) ──
_all_routers = [
    chat_router, profile_router, quiz_router, rag_router,
    agents_router, knowledge_router, sessions_router,
    learning_router, sandbox_router, config_router,
    subjects_router, assessment_router, langgraph_router,
    engine_router, teacher_router, multimodal_router,
    tutor_router, auth_router, user_router, admin_router,
    admin_users_router,
    xfyun_router,
    imports_router,
    llm_health_router,
    skills_router,
    tts_router,
    diagnostic_router,
    review_router,
    audit_router,
    knowledge_graph_router,
    english_router,
    knowledge_base_router,
    achievement_router,
    resource_router,
    memory_router,
    wrong_questions_router,
    daily_plan_router,
]

api_router = APIRouter(prefix="/api")
for r in _all_routers:
    api_router.include_router(r)
app.include_router(api_router)


# ── 健康检查 ──
@app.get("/api/status")
async def status():
    from config import load_config
    cfg = load_config()
    count = vector_db.count("netlearn_kb")
    db_status = "milvus" if vector_db._milvus_connected else "inmemory"
    return {
        "status": "ok",
        "vector_db": db_status,
        "collection_size": count,
        "pg_enabled": cfg.get("postgresql", {}).get("enabled", False),
        "redis_enabled": cfg.get("redis", {}).get("enabled", False),
        "llm_provider": cfg.get("llm_provider", "auto"),
        "llm_available": bool(cfg.get("deepseek", {}).get("api_key") or cfg.get("xfyun", {}).get("app_id")),
    }


# ── 赛题功能状态（供评审/演示查看5项功能就绪情况）──
@app.get("/api/status/competition")
async def competition_status():
    """返回赛题5项功能 + 2项加分项的实现状态"""
    count = vector_db.count("netlearn_kb")
    from db.user_store import get_db_conn
    user_count = 0
    try:
        conn = get_db_conn()
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        user_count = row[0] if row else 0
    except Exception:
        pass

    return {
        "competition": "第十五届中国软件杯 A3 赛题",
        "team": "MARS-408",
        "functions": [
            {"id": "F1", "name": "对话式学习画像构建", "status": "✅ 已实现", "detail": "8维度画像，对话式构建，随学随新", "route": "/chat"},
            {"id": "F2", "name": "多智能体协同资源生成（核心）", "status": "✅ 已实现", "detail": "13个Agent协同，7种资源并行生成（讲解/习题/导图/拓展/PPT/代码/视频）", "route": "/resource"},
            {"id": "F3", "name": "个性化学习路径规划", "status": "✅ 已实现", "detail": "KG-DAG拓扑排序，画像驱动薄弱点优先", "route": "/learning-path"},
            {"id": "F4", "name": "智能辅导（加分项）", "status": "✅ 已实现", "detail": "多模态答疑，文字+图示+语音+视频", "route": "/chat"},
            {"id": "F5", "name": "学习效果评估（加分项）", "status": "✅ 已实现", "detail": "多维度评估报告，热力图+易错点+趋势分析", "route": "/assessment"},
        ],
        "non_functional": [
            {"name": "界面美观+流式输出", "status": "✅", "detail": "玻璃态设计系统，SSE流式推送"},
            {"name": "防幻觉+内容安全", "status": "✅", "detail": "Critic审阅+GOMARL共识+敏感词过滤"},
            {"name": "响应时间+进度追踪", "status": "✅", "detail": "SSE进度推送，异步生成"},
            {"name": "开源声明标注", "status": "✅", "detail": "documents/技术方案文档.md §0"},
        ],
        "stats": {
            "knowledge_base_size": count,
            "user_count": user_count,
            "agent_count": 13,
            "resource_types": 7,
            "profile_dimensions": 8,
        },
    }


# ── D5：Prometheus 指标端点 ──
@app.get("/metrics")
async def metrics():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4")


# ── 前端 SPA 静态资源（上线前检查 P2-1 / ADR-007 Docker 单镜像生产）──
# Dockerfile 已将前端 dist 拷至 ${STATIC_DIR}（默认 /app/static），挂载为根路径 fallback，
# 使单镜像对外暴露 UI；开发环境若 dist 不存在则跳过（仅 API 模式）。
_static_dir = os.environ.get("STATIC_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "dist"
)
if os.path.isdir(_static_dir):
    # 挂载静态资源目录
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="spa_assets")
    # 挂载 showcase 展示页面（HTML 原型文件）
    _showcase_dir = os.path.join(_static_dir, "showcase")
    if os.path.isdir(_showcase_dir):
        app.mount("/showcase", StaticFiles(directory=_showcase_dir), name="showcase")
    # 用中间件处理 SPA 路由：所有 404 的 GET 请求返回 index.html
    from fastapi.responses import FileResponse
    _index_path = os.path.join(_static_dir, "index.html")
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
            return FileResponse(_index_path, headers=headers)
        return response
    logger.info(f"前端 SPA 已挂载: {_static_dir} -> /")
else:
    logger.info(f"前端静态目录不存在（{_static_dir}），跳过 SPA 挂载（仅 API 模式）。")


if __name__ == "__main__":
    import uvicorn
    reload_mode = os.environ.get("UVICORN_RELOAD", "").lower() in ("1", "true", "yes")
    uvicorn.run("main:app", host="127.0.0.1", port=8002, reload=reload_mode, workers=1)
