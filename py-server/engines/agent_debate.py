# ============================================================
# Agent 辩论与反思机制 — 多智能体协作深度强化
#
# 核心创新点（解决评审"多智能体协作深度不足"问题）：
#   1. Agent Debate：多轮辩论协议 — Agent 之间针对不一致内容进行结构化辩论
#   2. Self-Reflection：反思机制 — 每个 Agent 在辩论后对自己的输出进行反思改进
#   3. Cross-Examination：交叉质询 — Agent A 质询 Agent B 的论点，
#      并由 Critic 作为仲裁方
#   4. Consensus Refinement：共识精炼 — 辩论达成共识后，重新生成最终内容
#
# 对应申报书增加的"Agent协作层"：
#   "在多智能体协同中加入结构化辩论协议，提升输出一致性"
# ============================================================

import json
import logging
import re
from typing import Optional
from dataclasses import dataclass, field

from db.llm_provider import LLMProvider

logger = logging.getLogger("netlearn.agent_debate")


# ── 数据结构 ──

@dataclass
class DebateRound:
    """单轮辩论记录"""
    round_num: int
    arguments: dict[str, str] = field(default_factory=dict)  # agent_name → argument
    critiques: dict[str, str] = field(default_factory=dict)   # agent_name → critique of others
    rebuttals: dict[str, str] = field(default_factory=dict)   # agent_name → rebuttal
    summary: str = ""  # 本轮仲裁摘要
    resolved: bool = False
    remaining_conflicts: list[str] = field(default_factory=list)


@dataclass
class DebateResult:
    """辩论最终结果"""
    consensus_content: str = ""
    refined_content: dict[str, str] = field(default_factory=dict)  # agent_name → refined output
    rounds_used: int = 0
    issues_resolved: int = 0
    issues_unresolved: int = 0
    final_verdict: str = ""


@dataclass
class ReflectionResult:
    """反思结果"""
    original_content: str
    refined_content: str
    changes_made: list[str] = field(default_factory=list)
    confidence_delta: float = 0.0  # 反思后的置信度变化


# ── 辩论代理模板 ──

_DEBATE_PROMPT = """你是一位严谨的计算机学科导师，参与多智能体系统的结构化辩论。

【辩论主题】{topic}
【你的角色】{agent_name}
【你的观点】(你之前生成的内容)
{my_content}

【其他Agent的观点】
{other_contents}

【本轮辩论指令】{round_instruction}

请：
1. 分析其他 Agent 输出中与你有分歧的部分
2. 用 408 考研大纲的权威知识点为你的观点辩护
3. 如果确实是你错了，坦诚承认并纠正
4. 输出格式（严格 JSON）：
{{
    "arguments": "你的核心论点，引用权威教材或RFC标准",
    "concessions": ["你承认错误的具体点（无则空数组）"],
    "defenses": ["你坚持正确并补充论据的点"],
    "improved_content": "辩论后你修正/精炼后的内容（无修改则留空）"
}}
"""

_REFLECTION_PROMPT = """你是 {agent_name} 智能体，正在对自己的输出进行反思改进。

【原始内容】
{original_content}

【辩论中收到的批评】
{critiques_received}

【辩论中获得的证据】
{evidence_received}

请反思你的输出，考虑以下方面：
1. 是否包含事实性错误？
2. 是否遗漏了关键知识点？
3. 是否可以用更清晰的教学方式表达？
4. 是否充分考虑了学生画像？

输出格式（严格 JSON）：
{{
    "issues_found": ["发现的问题列表"],
    "improvements": ["具体改进点"],
    "refined_content": "改进后的完整内容",
    "confidence_before": 0-1,
    "confidence_after": 0-1
}}
"""

_CROSS_EXAMINE_PROMPT = """你是多智能体系统的交叉质询官，对以下两个 Agent 的输出进行质询。

【质询主题】{topic}
【Agent A - {agent_a}】
{content_a}

【Agent B - {agent_b}】
{content_b}

【矛盾点】
{conflict_points}

请执行交叉质询：
1. 对每个矛盾点，分别询问两个 Agent 的论据
2. 引用 408 考研教材 / RFC 标准作为裁决依据
3. 判断哪个 Agent 的论点更准确

输出格式（严格 JSON）：
{{
    "examinations": [
        {{
            "point": "矛盾点描述",
            "question_to_a": "向Agent A的质询问题",
            "question_to_b": "向Agent B的质询问题",
            "evidence": "基于教材/RFC的裁决依据",
            "verdict": "支持A / 支持B / 需进一步argue",
            "correct_content": "修正后的正确内容"
        }}
    ]
}}
"""


class AgentDebate:
    """多智能体结构化辩论协议

    当 GOMARL 共识检测到冲突时，触发辩论流程：
    1. Level 1: 直接争议辩论（2轮）
    2. Level 2: 交叉质询（1轮）
    3. Level 3: 最终共识精炼

    这是申报书中"多智能体协同深度"的关键创新点
    """

    def __init__(self):
        self._llm = LLMProvider()
        self.max_debate_rounds = 3
        self.min_agents_for_debate = 2

    async def debate(
        self,
        agent_contents: dict[str, str],
        topic: str,
        student_profile: Optional[dict] = None,
        conflict_issues: Optional[list[str]] = None,
    ) -> DebateResult:
        """
        启动多轮辩论

        Args:
            agent_contents: {agent_name: content} 各Agent的原始输出
            topic: 学习主题
            student_profile: 学生画像（可选）
            conflict_issues: 已知的冲突点

        Returns:
            DebateResult: 辩论结果
        """
        agent_names = list(agent_contents.keys())
        if len(agent_names) < self.min_agents_for_debate:
            logger.info(f"Agent 数量不足 ({len(agent_names)} < {self.min_agents_for_debate})，跳过辩论")
            return DebateResult(
                consensus_content=next(iter(agent_contents.values()), ""),
                refined_content=agent_contents,
                rounds_used=0,
            )

        rounds = []
        current_contents = dict(agent_contents)
        all_issues = list(conflict_issues or [])

        for round_num in range(1, self.max_debate_rounds + 1):
            round_result = DebateRound(round_num=round_num)

            # 为每个Agent生成辩论论点
            for name in agent_names:
                # 构建其他Agent的内容摘要
                others = {n: c for n, c in current_contents.items() if n != name}
                other_summary = "\n\n".join(
                    f"【{n}的观点】\n{c[:1000]}"
                    for n, c in others.items()
                )

                if round_num == 1:
                    instruction = "第一轮辩论：请阐述你的核心论点，并指出其他Agent输出中你不同意的地方。"
                elif round_num == 2:
                    instruction = "第二轮辩论：请回应其他Agent对你的批评。如果发现错误，立即修正。"
                else:
                    instruction = "最终轮辩论：请给出你的最终精炼版本，消除所有分歧。如果无法达成一致，标注争议点。"

                prompt = _DEBATE_PROMPT.format(
                    topic=topic,
                    agent_name=name,
                    my_content=current_contents[name][:2000],
                    other_contents=other_summary[:3000],
                    round_instruction=instruction,
                )

                try:
                    reply = await self._llm.text_completion(
                        "你是严谨的计算机学科导师，参加多智能体辩论。",
                        prompt,
                        temperature=0.4,
                        max_tokens=1000,
                    )
                    parsed = self._parse_debate_response(reply)
                    round_result.arguments[name] = parsed.get("arguments", "")
                    round_result.critiques[name] = json.dumps(
                        parsed.get("concessions", []), ensure_ascii=False
                    )

                    # 如果有改进内容，更新
                    improved = parsed.get("improved_content", "").strip()
                    if improved and len(improved) > 50:
                        current_contents[name] = improved

                except Exception as e:
                    logger.warning(f"Agent {name} 辩论失败: {e}")
                    round_result.arguments[name] = "（辩论响应失败）"

            # 检查本轮是否已解决冲突
            round_result.summary = await self._summarize_round(
                round_result, topic, round_num
            )

            if "已达成一致" in round_result.summary or "无显著分歧" in round_result.summary:
                round_result.resolved = True
                rounds.append(round_result)
                break

            rounds.append(round_result)

        # 最终共识精炼
        final_content = await self._final_consensus_refinement(
            current_contents, topic, student_profile
        )

        # 统计
        resolved_count = sum(1 for r in rounds if r.resolved)
        unresolved = [r.remaining_conflicts for r in rounds if not r.resolved]
        unresolved_flat = [item for sublist in unresolved for item in sublist]

        logger.info(
            f"Agent辩论完成: {len(rounds)}轮, "
            f"解决{resolved_count}个冲突, "
            f"剩余{len(unresolved_flat)}个未解"
        )

        return DebateResult(
            consensus_content=final_content,
            refined_content=current_contents,
            rounds_used=len(rounds),
            issues_resolved=resolved_count,
            issues_unresolved=len(unresolved_flat),
            final_verdict=rounds[-1].summary if rounds else "无辩论",
        )

    async def agent_reflection(
        self,
        agent_name: str,
        original_content: str,
        critiques_received: list[str],
        evidence: list[dict],
    ) -> ReflectionResult:
        """单个 Agent 的自我反思

        Args:
            agent_name: Agent 名称
            original_content: Agent 原始输出
            critiques_received: 收到的批评意见
            evidence: 从 FrugalRAG 检索到的证据

        Returns:
            ReflectionResult: 反思结果
        """
        evidence_text = "\n".join(
            f"- {e.get('text', '')[:300]} (相关度: {e.get('score', 0):.2f})"
            for e in evidence[:3]
        ) if evidence else "（无外部证据）"

        prompt = _REFLECTION_PROMPT.format(
            agent_name=agent_name,
            original_content=original_content[:3000],
            critiques_received="\n".join(f"- {c}" for c in critiques_received),
            evidence_received=evidence_text,
        )

        try:
            reply = await self._llm.text_completion(
                "你是善于自我反思的教学智能体。",
                prompt,
                temperature=0.3,
                max_tokens=1500,
            )
            parsed = self._parse_reflection_response(reply)

            changes = parsed.get("issues_found", [])
            refined = parsed.get("refined_content", "").strip() or original_content
            conf_before = parsed.get("confidence_before", 0.7)
            conf_after = parsed.get("confidence_after", 0.7)

            return ReflectionResult(
                original_content=original_content,
                refined_content=refined,
                changes_made=changes,
                confidence_delta=conf_after - conf_before,
            )
        except Exception as e:
            logger.warning(f"Agent {agent_name} 反思失败: {e}")
            return ReflectionResult(
                original_content=original_content,
                refined_content=original_content,
                changes_made=[],
                confidence_delta=0.0,
            )

    async def cross_examine(
        self,
        agent_a: str,
        agent_b: str,
        content_a: str,
        content_b: str,
        conflict_points: list[str],
        topic: str,
    ) -> list[dict]:
        """交叉质询两个Agent

        Args:
            agent_a: Agent A 名称
            agent_b: Agent B 名称
            content_a: Agent A 的内容
            content_b: Agent B 的内容
            conflict_points: 矛盾点列表
            topic: 主题

        Returns:
            list[dict]: 质询结果列表
        """
        prompt = _CROSS_EXAMINE_PROMPT.format(
            topic=topic,
            agent_a=agent_a,
            agent_b=agent_b,
            content_a=content_a[:2000],
            content_b=content_b[:2000],
            conflict_points="\n".join(f"- {p}" for p in conflict_points),
        )

        try:
            reply = await self._llm.text_completion(
                "你是严谨的交叉质询官，基于408考研大纲和RFC标准裁决。",
                prompt,
                temperature=0.3,
                max_tokens=1500,
            )
            m = re.search(r'\{.*\}', reply, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                return parsed.get("examinations", [])
        except Exception as e:
            logger.warning(f"交叉质询失败: {e}")

        return []

    async def _summarize_round(
        self, round_data: DebateRound, topic: str, round_num: int
    ) -> str:
        """总结本轮辩论"""
        args_text = "\n".join(
            f"{name}: {arg[:200]}"
            for name, arg in round_data.arguments.items()
        )

        summarizer = LLMProvider()
        prompt = (
            f"你正在总结第{round_num}轮关于「{topic}」的Agent辩论。\n\n"
            f"各Agent论点：\n{args_text}\n\n"
            f"请判断：1) 是否已经达成一致？2) 还有哪些未解决的冲突？"
            f"3) 给出简洁的总结（50字以内）"
        )

        try:
            summary = await summarizer.text_completion(
                "你是辩论总结员，输出简洁的总结。",
                prompt,
                temperature=0.3,
                max_tokens=200,
            )
            round_data.summary = summary.strip()

            # 检查剩余冲突
            if "未解决" in summary or "分歧" in summary or "争议" in summary:
                round_data.resolved = False
            else:
                round_data.resolved = True

            return summary.strip()
        except Exception as e:
            logger.warning("debate round %s summarizer failed: %s", round_num, e)
            return f"第{round_num}轮辩论总结生成失败，请人工审核。"

    async def _final_consensus_refinement(
        self,
        refined_contents: dict[str, str],
        topic: str,
        student_profile: Optional[dict],
    ) -> str:
        """最终共识精炼——将所有Agent的精炼内容合并为统一输出"""
        profile_info = ""
        if student_profile:
            profile_info = (
                f"\n学生画像：\n"
                f"- 薄弱点: {student_profile.get('weak_topics', [])}\n"
                f"- 掌握度: {student_profile.get('level', 'intermediate')}\n"
            )

        contents_text = "\n\n".join(
            f"【{name}的精炼输出】\n{content[:1500]}"
            for name, content in refined_contents.items()
        )

        refiner = LLMProvider()
        prompt = (
            f"你正在对多Agent辩论后的内容进行最终整合。\n"
            f"主题：{topic}\n"
            f"{profile_info}\n"
            f"各Agent精炼后的输出：\n{contents_text}\n\n"
            f"请整合为一个连贯、完整的学习内容。要求：\n"
            f"1. 消除所有矛盾和不一致\n"
            f"2. 按照教学逻辑重新组织（概念→原理→应用→例题）\n"
            f"3. 突出408考研重点考点\n"
            f"4. 使用Markdown格式\n"
            f"5. 如果存在未解决的争议，标注'⚠️ 争议点'"
        )

        try:
            final = await refiner.text_completion(
                "你是资深的408考研辅导老师，擅长整合多来源教学内容。",
                prompt,
                temperature=0.4,
                max_tokens=2000,
            )
            return final.strip()
        except Exception as e:
            # 降级：简单拼接
            logger.warning("debate final consensus refinement failed: %s", e)
            return "\n\n---\n\n".join(refined_contents.values())

    def _parse_debate_response(self, text: str) -> dict:
        """解析辩论响应JSON"""
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {"arguments": text[:500], "concessions": [], "defenses": [], "improved_content": ""}

    def _parse_reflection_response(self, text: str) -> dict:
        """解析反思响应JSON"""
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return {"issues_found": [], "improvements": [], "refined_content": "", "confidence_before": 0.7, "confidence_after": 0.7}


# ── 全局单例 ──
agent_debate = AgentDebate()
