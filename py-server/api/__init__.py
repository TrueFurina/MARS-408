# API routers — mounted by main.py
from api.chat import router as chat_router
from api.profile import router as profile_router
from api.quiz import router as quiz_router
from api.rag import router as rag_router
from api.agents import router as agents_router
from api.knowledge import router as knowledge_router
from api.imports import imports_router
from api.sessions import router as sessions_router
# D-05: learning.py 拆分为 5 个独立路由文件
from api.learning_path import router as learning_router
from api.sandbox import router as sandbox_router
from api.config_routes import router as config_router
from api.subjects import router as subjects_router
from api.assessment import router as assessment_router
from api.langgraph import router as langgraph_router
from api.engine import router as engine_router
from api.teacher import router as teacher_router
from api.multimodal import router as multimodal_router
from api.tutor import router as tutor_router
from api.auth import router as auth_router
from api.user import router as user_router
from api.admin import router as admin_router
from api.admin_users import router as admin_users_router
from api.xfyun import router as xfyun_router
from api.llm_health import router as llm_health_router
from api.skills import router as skills_router
from api.cn_distinction import router as cn_distinction_router
from api.tts import router as tts_router
from api.diagnostic import router as diagnostic_router
from api.review import router as review_router
from api.audit import router as audit_router
from api.knowledge_graph import router as knowledge_graph_router
from api.english import router as english_router
from api.knowledge_base import router as knowledge_base_router

from api.achievement import router as achievement_router
from api.resource import router as resource_router
from api.memory import router as memory_router
from api.wrong_questions import router as wrong_questions_router
from api.daily_plan import router as daily_plan_router

__all__ = [
    "chat_router", "profile_router", "quiz_router", "rag_router",
    "agents_router", "knowledge_router", "sessions_router",
    "learning_router", "sandbox_router", "config_router",
    "subjects_router", "assessment_router", "langgraph_router",
    "engine_router", "teacher_router", "multimodal_router",
    "tutor_router", "auth_router", "user_router", "admin_router",
    "admin_users_router",
    "xfyun_router", "imports_router", "llm_health_router",
    "skills_router",
    "tts_router",
    "diagnostic_router",
    "review_router",
    "audit_router",
"knowledge_graph_router",
    "english_router",
    "knowledge_base_router",
    "achievement_router",
    "resource_router",
    "memory_router",
    "wrong_questions_router",
    "daily_plan_router",
]
