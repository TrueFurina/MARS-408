# ============================================================
# app/lifespan.py — 应用生命周期编排（M-4 拆分，自 main.py 下沉）
#
# 启动顺序是有意为之的全部内容：check_auth → workers 守卫 → vector_db
# → (PG/Redis/Admin 并行) → migrations → demo seed → LLM 凭证检查 → import_worker
# → 会话清理任务 → 教材自动导入。任何重排序都可能引入竞态或冷启动失败，
# 改动前请先把「为什么是这个顺序」讲清楚。
# （ADR-007 单写者守卫曾在 workers 启动前才执行＝写完 schema 才拦；现已上移到
#   第一次写入（向量库播种）之前，详见 lifespan() 内注释。）
# ============================================================

import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.env import logger
from db.milvus_client import vector_db
from db.pg_client import pg_client
from db.redis_client import redis_client
# 导入队列 Worker（ADR-007：后端进程内单写者）
from services.import_worker import import_worker
# ── 种子数据 ──
from seed_data import SEED_KNOWLEDGE_CHUNKS, SEED_QUESTIONS


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


async def _init_vector_db() -> int:
    """初始化向量库并返回文档数（count==0 时才写种子数据）。"""
    t0 = time.perf_counter()
    vector_db.connect()
    count = vector_db.count("netlearn_kb")
    if count == 0:
        logger.info("向量库为空，写入内置种子数据...")
        _seed_vector_db()
        count = vector_db.count("netlearn_kb")
    logger.info(
        "向量库就绪，共 %d 个文档（Milvus 或 InMemoryVectorStore）；初始化耗时 %.0fms",
        count, (time.perf_counter() - t0) * 1000,
    )
    return count


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
    from services.user_service import ensure_admin
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
    admin_user = os.environ.get("ADMIN_USERNAME", "admin")
    try:
        ensure_admin(admin_user, admin_pwd)
        logger.info("管理员账号已就绪（用户名: %s）", admin_user)
    except Exception as e:
        # 生产环境：管理员是唯一特权入口，创建失败 = 系统无人可管，
        # 与 AUTH_SECRET / 口令长度两道 gate 口径一致 → fail-fast（拒绝「零管理员」上线）。
        # 非生产环境保留降级：本地只读库等场景不应阻断开发调试。
        if env in ("production", "prod"):
            raise RuntimeError(
                f"生产环境管理员账号初始化失败，拒绝以「零管理员」状态启动: {e}"
            ) from e
        logger.warning("管理员账号初始化失败（非生产环境，降级启动）: %s", e)


async def _run_migrations():
    # ── D6：数据库迁移（幂等，仅记录已应用版本）── 在 PG/SQLite 连接后执行
    try:
        from db.migrations import run_migrations
        applied_n = run_migrations()
        if applied_n:
            logger.info("数据库迁移完成，本次新应用 %d 个版本", applied_n)
    except Exception as e:
        logger.warning("数据库迁移执行失败（非阻塞）: %s", e)


async def _seed_demo_data():
    # ── 首次启动时写入演示种子数据（仅非生产环境，避免生产自动创建弱口令演示账户）──
    # 演示账号/口令以 seed_demo_data 的 DEMO_USERNAME / DEMO_PASSWORD 为唯一真值源。
    # 此处不得再写字面量：一是防止漂移（改了口令却漏改幂等探测 → 每次启动重复播种），
    # 二是避免把凭据明文回显进日志（原生产分支日志含明文口令）。
    try:
        env = os.environ.get("NETLEARN_ENV", "development").lower()
        if env not in ("production", "prod"):
            from services.user_service import authenticate
            from seed_demo_data import DEMO_PASSWORD, DEMO_USERNAME, seed_demo_data
            if authenticate(DEMO_USERNAME, DEMO_PASSWORD) is None:
                seed_demo_data()
        else:
            logger.info("生产环境跳过演示种子账户写入。")
    except Exception as e:
        logger.warning(f"演示种子数据写入失败（非阻塞）: {e}")


async def _check_llm_credentials():
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
    except Exception as _e:
        logger.debug("LLM 凭证检测失败（不影响启动）: %s", _e)  # 检测失败不影响启动


def _assert_single_worker():
    """ADR-007 单写者硬约束：workers > 1 直接拒绝启动。

    多进程会重新引入多写者（last-writer-wins），环境守卫（UVICORN_WORKERS /
    WEB_CONCURRENCY）与命令行 --workers N 两种形式都要拦。
    """
    import sys
    workers = int(os.environ.get("UVICORN_WORKERS", os.environ.get("WEB_CONCURRENCY", "1")))
    for i, arg in enumerate(sys.argv):
        if arg == "--workers" and i + 1 < len(sys.argv):
            try:
                workers = int(sys.argv[i+1])
            except ValueError as _e:
                logger.debug("--workers 参数非整数，使用默认 workers=1: %s", _e)
            break
    if workers > 1:
        raise RuntimeError(
            f"[import] ADR-007 硬约束违规：workers数量={workers} (>1)。"
            " 多进程会重新引入多写者(last-writer-wins)，必须 --workers 1 启动。"
        )


async def _artifact_lifecycle_loop():
    """OS_course artifact lifecycle cleanup — 周期性清理旧会话产物（>7 天）。

    同时负责 L3 情景记忆生命周期（90 天保留窗口，对标 HKU-DeepTutor 记忆管理）。
    """
    cleanup_interval = 3600  # 1 hour between sweeps
    session_max_age = 7 * 86400  # 7 days
    while True:
        await asyncio.sleep(cleanup_interval)
        try:
            sessions_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sessions")
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
                            if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > session_max_age:
                                os.remove(fpath)
                                removed += 1
                        except OSError as _e:
                            logger.debug("清理旧会话文件失败，跳过: %s", _e)
                    try:
                        if not os.listdir(user_path):
                            os.rmdir(user_path)
                    except OSError as _e:
                        logger.debug("清理空用户目录失败，跳过: %s", _e)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动：连接向量库+PG+Redis，写入种子数据"""
    logger.info("正在初始化数据层...")
    _lifespan_t0 = time.perf_counter()

    # ── 启动期密钥校验（F-005 fail-fast）：生产缺失 AUTH_SECRET / 长度不足即启动失败 ──
    # app.env.bootstrap() 在 import 本模块前已加载 .env，故此处可读到 AUTH_SECRET；
    # 生产环境若 AUTH_SECRET 未设置或长度 < 32，将直接 raise 使应用无法启动（fail-closed）。
    from shared.auth import resolve_auth_secret
    try:
        resolve_auth_secret()
    except RuntimeError as _auth_err:
        logger.error("AUTH_SECRET 校验失败，应用拒绝启动：%s", _auth_err)
        raise

    # ── ADR-007 单写者硬约束：必须在任何写操作之前完成校验 ──
    # 原先放在 migrations / demo seed 之后：守卫要防的恰恰是"多进程同时写"，
    # 却在已经写完整套 schema + 演示账户之后才拦下，等于事后验尸。
    # 上移到此处（密钥校验之后、向量库播种之前）= 在第一次写入之前拒绝。
    _assert_single_worker()

    # ── 向量数据库（Milvus 优先，InMemoryVectorStore 回退）─ 同步，先完成 ──
    count = await _init_vector_db()

    # ── 408 教材自动扩充（pending 标记；实际导入在 import_worker 启动后 enqueue）──
    # 旧实现：本阶段用子进程调 import_textbook.py，而该脚本 __main__ 已改为向本后端
    # HTTP 提交 job；但 lifespan 阶段后端尚未对外服务 → 导入必败、知识库卡在种子量、
    # 且每次冷启动都白跑一个必败子进程（约 30s 冷启动瓶颈之一）。
    # 现改为：仅在此打标记，待下方 import_worker.start() 后再 enqueue，复用与在线导入
    # 一致的进程内单写者（ADR-007）路径，count>=500 后不再重复触发。
    textbook_import_pending = count < 500

    # ── 非关键组件并行初始化（PG + Redis + Admin 互不依赖） ──
    await asyncio.gather(_init_pg(), _init_redis(), _init_admin())

    await _run_migrations()
    await _seed_demo_data()
    await _check_llm_credentials()

    # ── 导入队列 Worker（ADR-007）── 在 yield 前拉起
    await import_worker.start()

    cleanup_task = asyncio.create_task(_artifact_lifecycle_loop())

    # ── 408 教材自动扩充：经进程内导入队列（ADR-007 单写者），非阻塞后台执行 ──
    if textbook_import_pending:
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
        cleanup_task.cancel()
    except Exception as _e:
        logger.debug("取消 artifact 清理任务失败（忽略）: %s", _e)
    # 关闭连接
    await import_worker.stop()
    # P1：释放 httpx 连接池（避免未关闭客户端警告）
    try:
        from db.llm_provider import _close_http_clients
        await _close_http_clients()
    except Exception as _e:
        logger.debug("释放 httpx 连接池失败（忽略）: %s", _e)
    vector_db.disconnect()
    try:
        pg_client.disconnect()
    except Exception as _e:
        logger.debug("关闭 PG 连接失败（忽略）: %s", _e)
    try:
        redis_client.disconnect()
    except Exception as _e:
        logger.debug("关闭 Redis 连接失败（忽略）: %s", _e)
