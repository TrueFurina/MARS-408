# ============================================================
# Skill Agent — AI Skills 技能运行时
# 根据技能配置（system_prompt, llm_channel, temperature 等）
# 调用 LLMProvider 执行，并记录使用日志
# ============================================================

import logging
import re
import time
from typing import Optional

from db.llm_provider import LLMProvider
from db.skill_store import get_skill, log_usage, increment_skill_usage
from schemas.skills import SkillUsage

logger = logging.getLogger("netlearn.skill_agent")


class SkillAgent:
    """技能运行时 Agent

    根据技能配置调用 LLM，支持自定义 system_prompt、LLM 通道、温度等参数。
    OS_course 借鉴：内置 regex 参数提取快捷通道，LLM 不可用时仍可提取关键参数。
    """

    # OS_course: regex shortcuts for common skill parameters (LLM-unavailable fallback)
    _REGEX_PARAMS: dict[str, list[tuple[str, str]]] = {
        "ppt": [(r"slides?\s*[:：]?\s*(\d+)", "slide_count"),
                (r"(\d+)\s*(?:页|幻灯片|slides)", "slide_count"),
                (r"theme\s*[:：]?\s*(\w+)", "theme")],
        "image": [(r"(?:width|宽度|宽)\s*[:：]?\s*(\d+)", "width"),
                  (r"(?:height|高度|高)\s*[:：]?\s*(\d+)", "height"),
                  (r"style\s*[:：]?\s*(\w+)", "style")],
        "video": [(r"(?:duration|时长|长度)\s*[:：]?\s*(\d+)", "duration_sec"),
                  (r"(?:fps|帧率)\s*[:：]?\s*(\d+)", "fps"),
                  (r"resolution\s*[:：]?\s*(\d+x\d+)", "resolution")],
    }

    @classmethod
    def extract_params_regex(cls, skill_name: str, user_input: str) -> dict:
        """Regex-based parameter extraction for common skill types.
        Deterministic fallback when LLM is unavailable (OS_course pattern)."""
        params: dict = {}
        skill_lower = skill_name.lower()
        for skill_key, patterns in cls._REGEX_PARAMS.items():
            if skill_key in skill_lower:
                for pattern, key in patterns:
                    m = re.search(pattern, user_input, re.IGNORECASE)
                    if m:
                        try:
                            params[key] = int(m.group(1)) if m.group(1).isdigit() else m.group(1)
                        except ValueError:
                            params[key] = m.group(1)
        return params

    def __init__(self, skill_id: str):
        self.skill_id = skill_id
        self._skill = None

    async def _load_skill(self):
        """加载技能配置（延迟加载，支持缓存）"""
        if self._skill is None:
            self._skill = get_skill(self.skill_id)
            if self._skill is None:
                raise ValueError(f"技能不存在: {self.skill_id}")
        return self._skill

    async def execute(
        self,
        user_input: str,
        user_id: str = "",
        session_id: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """执行技能

        Args:
            user_input: 用户输入
            user_id: 用户 ID（用于日志记录）
            session_id: 会话 ID（用于日志记录）
            temperature: 覆盖技能配置的温度（可选）
            max_tokens: 覆盖技能配置的最大输出长度（可选）

        Returns:
            str: 技能输出
        """
        skill = await self._load_skill()

        # 构建消息
        system_prompt = skill.system_prompt or "你是一个有用的 AI 助手。"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        # 确定 LLM 通道
        provider_name = skill.llm_channel if skill.llm_channel != "auto" else None

        # 构建 LLMProvider
        llm = LLMProvider(provider_name=provider_name)

        # 执行调用
        start_time = time.time()
        try:
            response = await llm.chat(
                messages=messages,
                temperature=temperature if temperature is not None else skill.temperature,
                max_tokens=max_tokens if max_tokens is not None else skill.max_tokens,
            )
            latency_ms = int((time.time() - start_time) * 1000)
            output_text = response or ""
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            output_text = ""
            logger.error(f"技能执行失败: skill_id={self.skill_id}, error={e}")
            raise

        # 记录使用日志
        if user_id:
            try:
                usage = SkillUsage(
                    skill_id=self.skill_id,
                    user_id=user_id,
                    session_id=session_id,
                    input_text=user_input,
                    output_text=output_text,
                    latency_ms=latency_ms,
                )
                log_usage(usage)
                increment_skill_usage(self.skill_id, user_id)
            except Exception as e:
                logger.warning(f"技能使用日志记录失败: {e}")

        return output_text

    async def stream_execute(
        self,
        user_input: str,
        user_id: str = "",
        session_id: str = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """流式执行技能（生成器）

        Args:
            user_input: 用户输入
            user_id: 用户 ID
            session_id: 会话 ID
            temperature: 覆盖温度（可选）
            max_tokens: 覆盖最大输出长度（可选）

        Yields:
            str: 流式输出片段
        """
        skill = await self._load_skill()

        system_prompt = skill.system_prompt or "你是一个有用的 AI 助手。"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        provider_name = skill.llm_channel if skill.llm_channel != "auto" else None
        llm = LLMProvider(provider_name=provider_name)

        full_output = ""
        start_time = time.time()

        try:
            async for chunk in llm.stream_chat(
                messages=messages,
                temperature=temperature if temperature is not None else skill.temperature,
                max_tokens=max_tokens if max_tokens is not None else skill.max_tokens,
            ):
                full_output += chunk
                yield chunk
        except Exception as e:
            logger.error(f"技能流式执行失败: skill_id={self.skill_id}, error={e}")
            raise
        finally:
            latency_ms = int((time.time() - start_time) * 1000)
            # 异步记录日志
            if user_id and full_output:
                try:
                    usage = SkillUsage(
                        skill_id=self.skill_id,
                        user_id=user_id,
                        session_id=session_id,
                        input_text=user_input,
                        output_text=full_output,
                        latency_ms=latency_ms,
                    )
                    log_usage(usage)
                    increment_skill_usage(self.skill_id, user_id)
                except Exception as e:
                    logger.warning(f"技能使用日志记录失败: {e}")


# ── 便捷函数 ──


async def execute_skill(
    skill_id: str,
    user_input: str,
    user_id: str = "",
    session_id: str = "",
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """便捷函数：一步执行技能"""
    agent = SkillAgent(skill_id)
    return await agent.execute(
        user_input=user_input,
        user_id=user_id,
        session_id=session_id,
        temperature=temperature,
        max_tokens=max_tokens,
    )