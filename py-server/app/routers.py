# ============================================================
# app/routers.py — 业务路由注册（M-4 拆分，自 main.py 下沉）
#
# 全部业务路由统一挂到 /api 前缀下。新增 router 时：
#   1) 在 api/__init__.py 导出该 *_router
#   2) 在下方 ALL_ROUTERS 列表中登记
# ⚠️ 顺序即 include 顺序，Starlette 按注册先后匹配路由，首匹配生效；
#    有路径前缀冲突的 router（如 /api/knowledge 与 /api/knowledge-base）
#    必须保持既有先后，调整前请确认没有覆盖。
# ============================================================

from fastapi import APIRouter, FastAPI

from api import (
    achievement_router,
    admin_router,
    admin_users_router,
    agents_router,
    assessment_router,
    audit_router,
    auth_router,
    benchmark_router,
    career_training_router,
    chat_router,
    cn_distinction_router,
    config_router,
    daily_plan_router,
    diagnostic_router,
    engine_router,
    english_router,
    experiments_router,
    imports_router,
    knowledge_base_router,
    knowledge_graph_router,
    knowledge_router,
    langgraph_router,
    learning_router,
    literacy_router,
    llm_health_router,
    memory_router,
    multimodal_router,
    profile_router,
    quiz_router,
    rag_router,
    resource_router,
    review_router,
    sandbox_router,
    sessions_router,
    skills_router,
    subjects_router,
    teacher_router,
    tts_router,
    tutor_router,
    user_router,
    wrong_questions_router,
    xfyun_router,
)

__all__ = ["ALL_ROUTERS", "install", "build_api_router"]

ALL_ROUTERS = [
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
    career_training_router,
    benchmark_router,
    experiments_router,
    literacy_router,
    cn_distinction_router,
]


def build_api_router() -> APIRouter:
    """把所有业务 router 汇总成一个带 /api 前缀的 router。"""
    api_router = APIRouter(prefix="/api")
    for r in ALL_ROUTERS:
        api_router.include_router(r)
    return api_router


def install(app: FastAPI) -> None:
    app.include_router(build_api_router())
