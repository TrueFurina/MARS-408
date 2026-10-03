# ============================================================
# app/status.py — 运维端点（M-4 拆分，自 main.py 下沉）
#
#   GET /api/status              健康探针（D5：显式化静默降级）
#   GET /api/status/competition  赛题 5 项功能 + 加分项就绪状态
#   GET /metrics                 Prometheus 文本格式指标（D5）
# ============================================================

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from app.env import logger
from db.milvus_client import vector_db
from db.pg_client import pg_client
from db.redis_client import redis_client
from shared.metrics import render_prometheus

__all__ = ["install", "status", "competition_status", "metrics"]


async def status():
    """系统健康探针（D5：停止硬编码 "ok"，显式化静默降级）。

    - status: "ok" 仅当所有「已配置启用」的核心能力实际可用；任一意图启用却回落/失败 → "degraded"
    - health: 各组件真实状态（vector_db / postgresql / redis / embedding / llm）
    - degraded_reasons: 人类可读的降级原因列表（空列表表示全绿）
    约定：未配置的组件（如开发环境未启用 Milvus）视为「不要求」，不计入降级。
    """
    from config import load_config
    from db import embedder
    cfg = load_config()

    # 探针自身永不抛异常：健康端点是故障时的生命线，若组件故障时探针先 500，
    # 编排系统会误判实例不可用而反复重启。组件探测失败 == 降级原因之一。
    probe_failures: list[str] = []

    # ── 向量库 ──
    milvus_cfg_enabled = bool(cfg.get("milvus", {}).get("enabled", False))
    milvus_connected = bool(getattr(vector_db, "_milvus_connected", False))
    vector_db_mode = "milvus" if milvus_connected else "inmemory"
    try:
        count = vector_db.count("netlearn_kb")
    except Exception as e:  # noqa: BLE001 — 探针必须吞异常改走降级通道
        count = 0
        probe_failures.append(f"vector_db: 健康探测失败({type(e).__name__})")

    # ── PostgreSQL（意图启用却未连上 / 回落 SQLite 兜底 → 降级）──
    pg_cfg_enabled = bool(cfg.get("postgresql", {}).get("enabled", False))
    pg_enabled = bool(getattr(pg_client, "is_enabled", False))
    pg_fallback = bool(getattr(pg_client, "is_fallback", False))

    # ── Redis（意图启用却未连上 → 降级）──
    redis_cfg_enabled = bool(cfg.get("redis", {}).get("enabled", False))
    redis_enabled = bool(getattr(redis_client, "is_enabled", False))

    # ── 嵌入（E5 静默回落零向量占位计数 + 模型是否已加载）──
    embedding_model = embedder.EMBED_MODEL_NAME
    embedding_loaded = embedder._e5_model is not None
    embedding_fallback = int(getattr(vector_db, "embedding_fallback_count", 0))

    # ── LLM（核心能力，无可用凭证 → 资源生成不可用）──
    llm_provider_name = cfg.get("llm_provider", "auto")
    llm_available = bool(
        cfg.get("deepseek", {}).get("api_key")
        or cfg.get("xfyun", {}).get("app_id")
    )

    # ── 计算总体状态（仅「意图启用却未达成」才计为降级）──
    degraded_reasons: list[str] = []
    if milvus_cfg_enabled and not milvus_connected:
        degraded_reasons.append(
            "vector_db: 已配置 Milvus 但未连接，回落内存存储（重启即丢失）"
        )
    if pg_cfg_enabled and not pg_enabled:
        degraded_reasons.append("postgresql: 已配置但未连接（数据层降级）")
    elif pg_cfg_enabled and pg_fallback:
        degraded_reasons.append("postgresql: 已配置但回落本地 SQLite 兜底（非主库）")
    if redis_cfg_enabled and not redis_enabled:
        degraded_reasons.append("redis: 已配置但未连接（缓存/部分限流降级）")
    if embedding_fallback > 0:
        degraded_reasons.append(
            f"embedding: {embedding_fallback} 个文档因 E5 失败使用零向量占位，检索质量下降"
        )
    if not llm_available:
        degraded_reasons.append("llm: 未配置任何可用供应商凭证（资源生成不可用）")
    degraded_reasons.extend(probe_failures)

    overall = "degraded" if degraded_reasons else "ok"

    return {
        "status": overall,
        "degraded_reasons": degraded_reasons,
        "health": {
            "vector_db": {
                "mode": vector_db_mode,
                "milvus_configured": milvus_cfg_enabled,
                "milvus_connected": milvus_connected,
                "collection_size": count,
            },
            "postgresql": {
                "configured": pg_cfg_enabled,
                "enabled": pg_enabled,
                "fallback_sqlite": pg_fallback,
            },
            "redis": {
                "configured": redis_cfg_enabled,
                "enabled": redis_enabled,
            },
            "embedding": {
                "model": embedding_model,
                "loaded": embedding_loaded,
                "fallback_zero_docs": embedding_fallback,
            },
            "llm": {
                "provider": llm_provider_name,
                "available": llm_available,
            },
        },
    }


def _profile_dimension_count() -> int:
    """画像维度数 —— 取唯一真值源，禁止再硬编码。

    权威定义在 ``agents.career_state.DIMENSIONS``（英文 key + DIMENSION_LABELS 中文名）。
    此处刻意延迟导入并保持轻量（该模块不引入 torch），失败时返回 -1 而不是猜一个数字：
    宁可让守护测试报错，也不要对外宣称一个未经源证的数值（见 CLAUDE.md 诚信红线）。
    """
    try:
        from agents.career_state import DIMENSIONS  # 延迟导入：避免影响应用启动路径

        return len(DIMENSIONS)
    except Exception as e:  # noqa: BLE001
        logger.warning("读取画像维度真值源失败，返回 -1 而非占位数字: %s", e)
        return -1


async def competition_status():
    """返回赛题5项功能 + 2项加分项的实现状态"""
    count = vector_db.count("netlearn_kb")
    from services.user_service import get_db_conn
    user_count = 0
    try:
        conn = get_db_conn()
        row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        user_count = row[0] if row else 0
    except Exception as e:
        logger.warning("competition_status 读取用户总数失败，返回 0: %s", e)

    return {
        "competition": "2026 福建高校「火山杯」Agent 创新大赛",
        "team": "芒得很职",
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
            # 画像维度必须从唯一真值源派生：本分支权威定义在 agents.career_state.DIMENSIONS。
            # 曾硬编码为 8（旧版 408 学情画像遗留），与本线口径不符 ⇒ 改为派生，杜绝再漂移。
            "profile_dimensions": _profile_dimension_count(),
        },
    }


async def metrics():
    return PlainTextResponse(render_prometheus(), media_type="text/plain; version=0.0.4")


def install(app: FastAPI) -> None:
    app.get("/api/status")(status)
    app.get("/api/status/competition")(competition_status)
    app.get("/metrics")(metrics)
