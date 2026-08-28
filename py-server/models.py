# ============================================================
# Pydantic 模型 — 从 main.py 提取，供所有 API 路由共用
# ============================================================

from pydantic import BaseModel, Field
from typing import Optional


# ── 配置 ──

class ConfigResponse(BaseModel):
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    embedding_mode: str = "local"
    llm_provider: str = "deepseek"
    xfyun_api_key: str = ""
    xfyun_app_id: str = ""
    xfyun_base_url: str = "https://spark-api-open.xf-yun.com/x2"
    xfyun_model: str = "spark-x"


# ── 聊天 ──

class ChatSendRequest(BaseModel):
    conv_id: str = ""
    message: str = Field(..., min_length=1, max_length=10000, description="用户消息，最长10000字符")
    history: Optional[list[dict]] = Field(default_factory=list)
    thinking_mode: bool = False
    agent_mode: bool = False

class ChatSendResponse(BaseModel):
    response: str


# ── 画像 ──

class ProfileBuildRequest(BaseModel):
    message: str = Field(..., max_length=5000, description="用户画像描述，最长5000字符")
    history: list[dict] = Field(default_factory=list)
    name: str = Field("", max_length=100)

class ProfileBuildResponse(BaseModel):
    reply: str
    profile: Optional[dict] = None
    completed: bool = False


# ── 答题 ──

class QuizRecord(BaseModel):
    question_id: str = ""
    subject: str = ""
    chapter: str = ""
    question: str = ""
    user_answer: str = ""
    correct_answer: str = ""
    correct: bool
    difficulty: str = "medium"

class QuizSubmitRequest(BaseModel):
    profile: dict
    records: list[QuizRecord]

class QuizSubmitResponse(BaseModel):
    total: int
    correct_count: int
    accuracy: float
    by_subject: dict[str, dict]
    updated_profile: Optional[dict] = None
    suggestions: str = ""


# ── RAG ──

class RAGSearchRequest(BaseModel):
    query: str = Field(..., max_length=5000, description="搜索查询，最长5000字符")
    subject: Optional[str] = None
    course: Optional[str] = None
    top_k: int = Field(5, ge=1, le=50, description="返回结果数量，1-50")

class RAGSearchResult(BaseModel):
    id: str
    content: str
    metadata: dict
    distance: float

class RAGSearchResponse(BaseModel):
    results: list[RAGSearchResult]

class GenerateQuestionsRequest(BaseModel):
    subject: str
    chapter: Optional[str] = None
    question_type: str = "all"
    difficulty: str = "medium"
    count: int = Field(5, ge=1, le=50, description="生成题目数量，1-50")

class GenerateQuestionsResponse(BaseModel):
    questions: list[dict]
    message: Optional[str] = None


# ── Agent ──

class AgentResourceRequest(BaseModel):
    topic: str = Field(..., max_length=2000, description="学习主题，最长2000字符")
    difficulty: str = "medium"
    profile: Optional[dict] = None
    history: list[dict] = Field(default_factory=list, max_length=50)

class AgentResourceResponse(BaseModel):
    teacher_doc: str = ""
    quiz: str = ""
    media_plan: str = ""
    critic_report: str = ""
    status: str = "ok"
    hallucination_warnings: Optional[list[str]] = None
    error: Optional[str] = None  # T-OPT-01：核心生成失败时返回可见错误，不再静默空响应谎称 ok


# ── 知识库 ──

class KnowledgeDocIn(BaseModel):
    content: str
    metadata: dict = Field(default_factory=dict)

class KnowledgeUpsertRequest(BaseModel):
    documents: list[KnowledgeDocIn]

class KnowledgeDeleteRequest(BaseModel):
    ids: list[str]

class KnowledgeListItem(BaseModel):
    id: str
    content: str
    metadata: dict
    distance: Optional[float] = None

class KnowledgeListResponse(BaseModel):
    items: list[KnowledgeListItem]
    total: int

class KnowledgeStatsResponse(BaseModel):
    total_docs: int
    by_subject: dict[str, int]
    by_type: dict[str, int]


# ── 学习路径 ──

class LearningPathRequest(BaseModel):
    profile: Optional[dict] = None
    current_chapter: int = 0
    subject: str = "computer_network"  # 408四科: computer_network / data_structures / computer_organization / operating_system

class LearningPathNode(BaseModel):
    id: str
    name: str
    chapter: int
    status: str
    topics: list[str]

class LearningPathResponse(BaseModel):
    nodes: list[LearningPathNode]
    total: int
    completed: int
    pct: int

class LearningPathWithResourcesResponse(BaseModel):
    nodes: list[dict]
    total: int
    completed: int
    pct: int
    weak_focus_chapters: list[str]
    llm_adjusted: bool = False


# ── 沙箱 ──

class SandboxRequest(BaseModel):
    code: str = Field(..., max_length=50000, description="待执行代码（≤50000字符，防超大 payload DoS）")
    language: str = "python"
    timeout: int = Field(5, ge=1, le=60, description="超时秒数，1-60")

class SandboxResponse(BaseModel):
    output: str
    error: str = ""
    status: str = "ok"


# ── 评估 ──

class AssessmentRequest(BaseModel):
    profile: Optional[dict] = None
    quiz_history: list[dict] = []

class AssessmentResponse(BaseModel):
    mastery: dict = Field(default_factory=dict)
    activity: str = "未知"
    weak_focus: list[str] = Field(default_factory=list)
    trend: str = "未知"
    adjustment: str = ""
    by_subject: dict = Field(default_factory=dict)
    total_questions: int = 0
    overall_accuracy: float = 0
    llm_assessed: bool = False


# ── LangGraph 流式 ──

class LangGraphStreamRequest(BaseModel):
    """LangGraph 多智能体流式请求"""
    message: str
    topic: str = ""
    course: str = "computer_network"
    difficulty: str = "medium"
    profile: Optional[dict] = None
    history: list[dict] = []


# ── 行为上报（P1-4）──

class BehaviorEventItem(BaseModel):
    event_type: str = Field(..., description="dwell / reattempt / resource_click")
    topic: str = Field("", max_length=256)
    duration_ms: int = 0
    resource_type: str = Field("", max_length=64)

class BehaviorReportRequest(BaseModel):
    events: list[BehaviorEventItem] = Field(..., max_length=50)

class BehaviorReportResponse(BaseModel):
    accepted: int
    updated: bool = False
