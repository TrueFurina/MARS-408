"""AI Skills 创新创作平台 — 数据模型定义

技能(Skill)的生命周期：
  draft → published → archived
       → draft（编辑后重新发布）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SkillStatus(str, Enum):
    """技能状态"""
    DRAFT = "draft"           # 草稿（未发布）
    PUBLISHED = "published"   # 已发布（在市场中可见）
    ARCHIVED = "archived"     # 已归档（下架，不可用）


class SkillCategory(str, Enum):
    """技能分类"""
    TEACHING = "teaching"     # 教学讲解
    QUIZ = "quiz"             # 出题练习
    DIAGNOSIS = "diagnosis"   # 诊断评估
    GUIDE = "guide"           # 学习引导
    CODE = "code"             # 代码实践
    MINDMAP = "mindmap"       # 思维导图
    OTHER = "other"           # 其他


SKILL_CATEGORY_LABELS = {
    SkillCategory.TEACHING: "教学讲解",
    SkillCategory.QUIZ: "出题练习",
    SkillCategory.DIAGNOSIS: "诊断评估",
    SkillCategory.GUIDE: "学习引导",
    SkillCategory.CODE: "代码实践",
    SkillCategory.MINDMAP: "思维导图",
    SkillCategory.OTHER: "其他",
}


@dataclass
class Skill:
    """技能核心数据模型"""
    name: str                                  # 技能名称
    description: str                           # 技能描述
    id: str = ""                               # UUID（空则自动生成）
    icon: str = "🤖"                           # 图标（emoji）

    # AI 配置
    system_prompt: str = ""                    # System Prompt（核心）
    llm_channel: str = "auto"                  # LLM 通道: deepseek / xfyun / qwen / auto
    temperature: float = 0.7                   # 温度 0.0-1.0
    max_tokens: int = 2048                     # 最大输出长度

    # 知识库绑定
    kb_ids: list[str] = field(default_factory=list)   # 绑定的知识库 ID 列表
    rag_enabled: bool = True                   # 是否启用 RAG 检索

    # 元数据
    tags: list[str] = field(default_factory=list)     # 标签
    category: str = SkillCategory.OTHER.value  # 分类
    version: int = 1                           # 版本号
    status: str = SkillStatus.DRAFT.value      # 状态

    # 记忆权限（P2②：插件读写学情记忆的权限控制）
    #   none=禁用记忆 / read=可读不可写 / write=可写不可读 / read_write=读写
    memory_access: str = "read_write"          # 默认读写（保持 run-with-memory 行为兼容）

    # SKILL.md 对齐字段（循环7-P1：调研 Claude Code Skills 结构化格式落地）
    #   allowed_tools: 技能运行期间预授权工具白名单（对应 allowed-tools，防越权）
    #   disable_model_invocation: 为 true 时仅手动触发，禁止模型自动调用
    #   trigger_paths: 条件激活（gitignore 风格路径/知识点匹配，可对接 408 知识图谱）
    allowed_tools: list[str] = field(default_factory=list)
    disable_model_invocation: bool = False
    trigger_paths: list[str] = field(default_factory=list)

    # 结构化工具元数据（循环12-P1：元数据驱动 LLM 选工具，对齐 Coze 设计）
    #   每个工具为 OpenAI function schema: {name, description, parameters}
    #   LLM 按元数据准确选工具；tools 比 allowed_tools 更细粒度（含参数 schema）
    tools: list[dict] = field(default_factory=list)

    # 统计
    usage_count: int = 0                       # 总调用次数
    user_count: int = 0                        # 使用人数
    avg_rating: float = 0.0                    # 平均评分

    # 时间戳
    created_at: str = ""                       # 创建时间
    updated_at: str = ""                       # 更新时间
    published_at: Optional[str] = None         # 发布时间

    # 归属
    creator_id: str = ""                       # 创建者用户 ID
    creator_name: str = ""                     # 创建者用户名（冗余，方便展示）
    is_official: bool = False                  # 是否为官方技能

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "system_prompt": self.system_prompt,
            "llm_channel": self.llm_channel,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "kb_ids": self.kb_ids,
            "rag_enabled": self.rag_enabled,
            "tags": self.tags,
            "category": self.category,
            "category_label": SKILL_CATEGORY_LABELS.get(
                SkillCategory(self.category), self.category
            ),
            "version": self.version,
            "status": self.status,
            "usage_count": self.usage_count,
            "user_count": self.user_count,
            "avg_rating": round(self.avg_rating, 1),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "published_at": self.published_at,
            "creator_id": self.creator_id,
            "creator_name": self.creator_name,
            "is_official": self.is_official,
            # SKILL.md 对齐字段
            "allowed_tools": self.allowed_tools,
            "disable_model_invocation": self.disable_model_invocation,
            "trigger_paths": self.trigger_paths,
            "tools": self.tools,
        }

    @staticmethod
    def from_dict(data: dict) -> Skill:
        return Skill(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            icon=data.get("icon", "🤖"),
            system_prompt=data.get("system_prompt", ""),
            llm_channel=data.get("llm_channel", "auto"),
            temperature=float(data.get("temperature", 0.7)),
            max_tokens=int(data.get("max_tokens", 2048)),
            kb_ids=data.get("kb_ids", []),
            rag_enabled=bool(data.get("rag_enabled", True)),
            tags=data.get("tags", []),
            category=data.get("category", SkillCategory.OTHER.value),
            version=int(data.get("version", 1)),
            status=data.get("status", SkillStatus.DRAFT.value),
            usage_count=int(data.get("usage_count", 0)),
            user_count=int(data.get("user_count", 0)),
            avg_rating=float(data.get("avg_rating", 0.0)),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            published_at=data.get("published_at"),
            creator_id=data.get("creator_id", ""),
            creator_name=data.get("creator_name", ""),
            is_official=bool(data.get("is_official", False)),
            allowed_tools=data.get("allowed_tools", []),
            disable_model_invocation=bool(data.get("disable_model_invocation", False)),
            trigger_paths=data.get("trigger_paths", []),
            tools=data.get("tools", []),
        )


@dataclass
class SkillTemplate:
    """技能模板 — 预设的 Prompt 模板，用户可基于此快速创建技能"""
    name: str                                  # 模板名称
    description: str                           # 模板描述
    id: str = ""                               # 模板 ID（空则自动生成）
    category: str = SkillCategory.OTHER.value  # 分类
    icon: str = "📦"                           # 图标
    system_prompt_template: str = ""           # 含 {{variable}} 占位符的模板
    default_config: dict = field(default_factory=dict)  # 默认 LLM 配置
    sort_order: int = 0                        # 排序权重

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "category_label": SKILL_CATEGORY_LABELS.get(
                SkillCategory(self.category), self.category
            ),
            "icon": self.icon,
            "system_prompt_template": self.system_prompt_template,
            "default_config": self.default_config,
            "sort_order": self.sort_order,
        }


@dataclass
class SkillRating:
    """技能评价"""
    skill_id: str
    user_id: str
    id: str = ""                               # UUID（空则自动生成）
    user_name: str = ""
    rating: int = 5                            # 1-5 星
    comment: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "skill_id": self.skill_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "rating": self.rating,
            "comment": self.comment,
            "created_at": self.created_at,
        }


@dataclass
class SkillUsage:
    """技能使用日志"""
    skill_id: str
    user_id: str
    id: str = ""                               # UUID（空则自动生成）
    session_id: str = ""
    input_text: str = ""
    output_text: str = ""
    tokens_used: int = 0
    latency_ms: int = 0
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "skill_id": self.skill_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "input_text": self.input_text[:200],  # 截断保护隐私
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "created_at": self.created_at,
        }