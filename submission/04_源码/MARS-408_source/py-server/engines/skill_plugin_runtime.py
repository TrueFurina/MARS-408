# ============================================================
# Skill 插件运行时 — 热加载 + 故障熔断隔离 + 学情记忆注入
#
# 设计目标（优先级3b：完善 SkillMarket 插件生态）：
#   1. 热加载：技能配置更新后无需重启服务即生效（按 updated_at 失效缓存）
#   2. 单插件故障熔断隔离：某技能连续失败 → 熔断该技能，不影响其他技能/系统
#   3. 插件独立读写学情记忆：执行前注入 L1/L2/L3 记忆上下文，
#      执行后自动写回 L3 情景记忆（解耦智能体内部记忆耦合）
#
# 低侵入：纯新增模块，不改动 GOMARL/FrugalRAG/Agent辩论/规则引擎核心。
# ============================================================

import json
import logging
import threading
import time
from typing import Optional
from dataclasses import dataclass, field

from db.skill_store import get_skill
from db.llm_provider import LLMProvider

logger = logging.getLogger("netlearn.skill_plugin")


# ══════════════════════════════════════════════════════════
# 熔断器（Circuit Breaker）
# ══════════════════════════════════════════════════════════

class CircuitBreaker:
    """单技能熔断器：连续失败 N 次 → OPEN 熔断 M 秒 → HALF_OPEN 试探 → 恢复

    状态机: CLOSED(正常) → OPEN(熔断) → HALF_OPEN(半开试探) → CLOSED/OPEN
    """

    def __init__(self, failure_threshold: int = 3, open_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.open_timeout = open_timeout
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            # OPEN 状态超时后自动转 HALF_OPEN（懒判断）
            if self._state == "open" and time.time() - self._opened_at >= self.open_timeout:
                self._state = "half_open"
            return self._state

    def allow_request(self) -> bool:
        """是否允许请求通过：CLOSED/HALF_OPEN 放行，OPEN 拒绝"""
        st = self.state
        if st == "open":
            return False
        return True

    def record_success(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._state = "open"
                self._opened_at = time.time()
                self._failures = 0
                logger.warning(f"Skill 熔断器触发: {self.failure_threshold} 次连续失败 → OPEN")

    def reset(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failures = 0

    def stats(self) -> dict:
        return {
            "state": self.state,
            "failures": self._failures,
            "failure_threshold": self.failure_threshold,
            "open_timeout": self.open_timeout,
        }


# ══════════════════════════════════════════════════════════
# 热加载缓存（按 updated_at 失效）
# ══════════════════════════════════════════════════════════

class HotReloadCache:
    """技能配置热加载缓存：key=skill_id, 依赖 updated_at 版本对比

    技能被 update 后 updated_at 变化 → 下一次 get 自动重载最新配置。
    锁保护并发访问，线程安全。
    """

    def __init__(self, ttl_seconds: float = 300.0):
        self._cache: dict[str, tuple[str, dict]] = {}  # skill_id -> (updated_at, skill_dict)
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def get(self, skill_id: str) -> Optional[dict]:
        """读取技能配置；缓存失效或缺失时从 DB 重载"""
        with self._lock:
            cached = self._cache.get(skill_id)
            if cached:
                cached_at, cached_skill = cached
                # TTL 过期 → 重载
                if time.time() - cached_at < self._ttl:
                    return cached_skill
                self._cache.pop(skill_id, None)

        # 从 DB 加载（锁外，避免持锁 DB IO）
        skill = get_skill(skill_id)
        if skill is None:
            return None
        skill_dict = skill.to_dict() if hasattr(skill, "to_dict") else vars(skill)

        # 二次校验：缓存期间是否已被其他线程更新
        with self._lock:
            existing = self._cache.get(skill_id)
            if existing and existing[1].get("updated_at", "") > skill_dict.get("updated_at", ""):
                return existing[1]
            self._cache[skill_id] = (time.time(), skill_dict)
        return skill_dict

    def invalidate(self, skill_id: str) -> None:
        with self._lock:
            self._cache.pop(skill_id, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


# ══════════════════════════════════════════════════════════
# Skill 插件运行时
# ══════════════════════════════════════════════════════════

class SkillPluginRuntime:
    """技能插件运行时：热加载配置 + 熔断隔离 + 学情记忆注入/写回

    用法（对现有 skill_agent 的低侵入增强，可替换 SkillAgent 直接使用）：
        runtime = SkillPluginRuntime(skill_id)
        result = await runtime.execute(user_input, user_id, session_id, use_memory=True)
    """

    _registry: dict[str, "SkillPluginRuntime"] = {}
    _registry_lock = threading.Lock()

    def __init__(self, skill_id: str,
                 failure_threshold: int = 3,
                 open_timeout: float = 60.0):
        self.skill_id = skill_id
        self._cache = HotReloadCache()
        self._breaker = CircuitBreaker(failure_threshold, open_timeout)
        self._llm: Optional[LLMProvider] = None

    @staticmethod
    def validate_tool_url(url: str, allowed_domains: Optional[set] = None) -> str:
        """插件工具 URL 域名白名单校验（循环9-P1：防 SSRF，调研结论落地）

        参考 Coze 插件「同插件工具同域名」域隔离设计：
          - 仅允许 http/https + 白名单域名
          - 校验失败抛 URLLimitError，调用方降级
        """
        from shared.url_guard import validate_url
        return validate_url(url, allowed_domains)

    @classmethod
    def get(cls, skill_id: str) -> "SkillPluginRuntime":
        """获取（或创建）技能运行时实例，实例级熔断状态隔离（单插件故障不影响其他插件）"""
        with cls._registry_lock:
            if skill_id not in cls._registry:
                cls._registry[skill_id] = cls(skill_id)
            return cls._registry[skill_id]

    def _get_llm(self, provider_name: Optional[str]) -> LLMProvider:
        """惰性创建 LLMProvider（按技能配置的通道）"""
        if self._llm is None:
            self._llm = LLMProvider(provider_name=provider_name)
        return self._llm

    # ── 学情记忆注入（低侵入：可选开启，默认关闭保持原行为） ──

    async def _build_memory_context(self, user_id: str, session_id: str) -> str:
        """组装 L1/L2/L3 记忆上下文提示块（复用 services.memory_service）"""
        try:
            from services.memory_service import build_memory_context
            return build_memory_context(user_id, session_id=session_id or None, max_episodes=8)
        except Exception as e:
            logger.warning(f"记忆上下文组装失败(降级为空): {e}")
            return ""

    async def _record_episode(self, user_id: str, event: dict) -> None:
        """执行后写回 L3 情景记忆（P2①：改用标准化写接口 write_plugin_event）"""
        try:
            from services.memory_service import write_plugin_event
            write_plugin_event(
                user_id=user_id,
                plugin_id=self.skill_id,
                event_type="skill_run",  # 保持与既有事件类型兼容
                topic=event.get("topic", ""),
                payload={"skill_id": self.skill_id, **event},
            )
        except Exception as e:
            logger.debug(f"技能情景记忆写回失败(忽略): {e}")

    # ── 主执行入口（带熔断 + 记忆） ──

    async def execute(
        self,
        user_input: str,
        user_id: str = "",
        session_id: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_memory: bool = False,
        memory_access: str = "read_write",
    ) -> str:
        """执行技能

        Args:
            user_input: 用户输入
            user_id: 用户 ID（记忆读写 + 使用日志）
            session_id: 会话 ID（L1 工作记忆关联）
            temperature / max_tokens: 覆盖参数
            use_memory: 是否注入 L1/L2/L3 学情记忆（默认 False 保持原行为）
            memory_access: 技能记忆权限（P2②：none/read/write/read_write，
                写回行为事件需含 write 权限）

        Returns:
            str: 技能输出

        Raises:
            CircuitOpenError: 熔断器处于 OPEN 状态
            ValueError: 技能不存在
        """
        # 熔断检查
        if not self._breaker.allow_request():
            from db.skill_store import get_skill as _gs
            skill = _gs(self.skill_id)
            raise CircuitOpenError(
                f"技能 {self.skill_id} 暂不可用（熔断中，稍后重试）"
                f" | 技能名: {skill.name if skill else '未知'}"
            )

        # 热加载配置
        skill = self._cache.get(self.skill_id)
        if skill is None:
            raise ValueError(f"技能不存在: {self.skill_id}")

        # SKILL.md 对齐字段消费（循环8-P1）
        # trigger_paths 条件激活：配置了触发路径/知识点时，用户输入需匹配才执行
        trigger_paths = skill.get("trigger_paths") or []
        if trigger_paths:
            matched = any(tp.lower() in user_input.lower() for tp in trigger_paths)
            if not matched:
                logger.info(
                    f"Skill 条件激活未命中: skill={self.skill_id}, "
                    f"trigger_paths={trigger_paths}, input={user_input[:50]}"
                )
                return f"该技能仅对特定知识点激活（触发条件: {'、'.join(trigger_paths[:5])}），当前输入不匹配。"

        system_prompt = skill.get("system_prompt") or "你是一个有用的 AI 助手。"

        # allowed_tools 工具白名单：技能声明后，约束系统提示词仅允许白名单内工具
        allowed_tools = skill.get("allowed_tools") or []
        if allowed_tools:
            system_prompt += (
                f"\n\n【工具白名单约束】本次执行仅允许使用以下工具: {'、'.join(allowed_tools[:10])}。"
                "禁止调用白名单以外的任何工具。"
            )

        messages = [{"role": "system", "content": system_prompt}]

        # 记忆注入：追加记忆上下文到 system prompt 之后（不污染用户输入）
        if use_memory and user_id:
            memory_ctx = await self._build_memory_context(user_id, session_id)
            if memory_ctx:
                messages[0]["content"] = (
                    f"{system_prompt}\n\n—— 以下为学生学情记忆（L1/L2/L3），供个性化参考 ——\n{memory_ctx}"
                )

        messages.append({"role": "user", "content": user_input})

        provider_name = skill.get("llm_channel") if skill.get("llm_channel", "auto") != "auto" else None
        llm = self._get_llm(provider_name)

        start = time.time()
        try:
            response = await llm.chat(
                messages=messages,
                temperature=temperature if temperature is not None else skill.get("temperature", 0.7),
                max_tokens=max_tokens if max_tokens is not None else skill.get("max_tokens", 2048),
                tools=skill.get("tools") or None,  # 循环12-P1：结构化工具元数据驱动 LLM 选工具
            )
            output = response or ""
            self._breaker.record_success()
        except Exception as e:
            self._breaker.record_failure()
            logger.error(f"Skill 插件执行失败(已计入熔断): skill_id={self.skill_id}, err={e}")
            raise

        latency_ms = int((time.time() - start) * 1000)

        # 使用日志 + 记忆写回（尽力而为，不阻塞主流程）
        if user_id:
            try:
                from db.skill_store import log_usage, increment_skill_usage
                from schemas.skills import SkillUsage
                usage = SkillUsage(
                    skill_id=self.skill_id, user_id=user_id, session_id=session_id,
                    input_text=user_input, output_text=output, latency_ms=latency_ms,
                )
                log_usage(usage)
                increment_skill_usage(self.skill_id, user_id)
            except Exception as e:
                logger.debug(f"技能使用日志失败(忽略): {e}")

            if use_memory and memory_access in ("write", "read_write"):
                await self._record_episode(user_id, {
                    "input_len": len(user_input),
                    "output_len": len(output),
                    "latency_ms": latency_ms,
                })

        return output

    def invalidate_cache(self) -> None:
        """技能配置更新后调用，立即失效热加载缓存"""
        self._cache.invalidate(self.skill_id)

    def reset_breaker(self) -> None:
        """手动重置熔断器"""
        self._breaker.reset()

    def get_status(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "breaker": self._breaker.stats(),
        }


class CircuitOpenError(RuntimeError):
    """熔断器 OPEN 状态错误"""
