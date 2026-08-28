# ============================================================
# GOMARL — 多智能体共识聚合引擎
# 功能：加权投票 + 一致性校验 + 历史表现追踪 + NeuralMixer
# ============================================================

import json
import logging
import re
from typing import Optional
from dataclasses import dataclass, field

from config import get_gomarl_config
from db.llm_provider import LLMProvider
from db.redis_client import redis_client
from db.pg_client import pg_client

logger = logging.getLogger("netlearn.gomarl")


@dataclass
class AgentResult:
    """单个 Agent 的生成结果"""
    agent_name: str
    content: str
    prompt_used: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class QualityScore:
    """单个 Agent 的质量评分"""
    agent_name: str
    accuracy: float       # 准确性 1-10
    completeness: float   # 完整性 1-10
    adaptability: float   # 适配性 1-10
    overall: float        # 综合分
    notes: str = ""


@dataclass
class ConsensusResult:
    """GOMARL 共识结果"""
    status: str           # "passed" | "flagged" | "regenerate" | "manual_review"
    overall_score: float
    agent_scores: list[QualityScore]
    merged_content: str
    flagged_issues: list[str]
    regenerate_agents: list[str]
    weight_snapshot: dict[str, float]


class GOMARLConsensus:
    """GOMARL 共识聚合引擎：质量评分 → 一致性校验 → 决策

    整合层次：
    1. 质量评分（LLM 评分 + 规则降级）
    2. 知识一致性校验（语义级 E5 向量 + 事实级矛盾对）
    3. 证据冲突消解（FrugalRAG 检索证据 + LLM 裁决）
    4. Neural GroupMixer（PyTorch 神经网络加权混合）
    5. 动态权重（EWMA 历史表现 + 学生画像调整）
    """

    def __init__(self):
        config = get_gomarl_config()
        self.quality_threshold = config.get("quality_threshold", 7)
        self.max_regenerate_rounds = config.get("max_regenerate_rounds", 2)
        self.history_window = config.get("history_window", 5)
        self.default_weight = config.get("default_agent_weight", 1.0)

        self._base_weights = {
            "teacher": 1.0,
            "quizmaster": 0.9,
            "media_designer": 0.85,
            "extension": 0.8,
            "ppt_designer": 0.8,
            "code_practice": 0.85,
        }

        # 真版增量：NeuralMixer + 证据冲突消解
        self._use_neural = config.get("use_neural_mixer", True)
        self._use_evidence = config.get("use_evidence_conflict", True)

        # 真版增量：教学业务规则引擎（报告§3.3.3改进点）
        self._use_teaching_rules = config.get("use_teaching_rules", True)

        # 延迟加载（避免循环导入）
        self._neural_mixer = None
        self._conflict_engine = None
        self._teaching_rules = None

    # ── 公共接口 ──

    async def evaluate(
        self,
        results: list[AgentResult],
        student_profile: dict,
        topic: str,
        round_num: int = 0,
    ) -> ConsensusResult:
        """
        对多个 Agent 结果进行共识评估

        Args:
            results: 各 Agent 的生成结果
            student_profile: 学生画像
            topic: 学习主题
            round_num: 当前轮次

        Returns:
            ConsensusResult: 共识结果
        """
        if round_num >= self.max_regenerate_rounds:
            # 重试耗尽，强制通过 + 标记人工审核
            combined = self._merge_all(results)
            return ConsensusResult(
                status="manual_review",
                overall_score=0,
                agent_scores=[],
                merged_content=combined,
                flagged_issues=["重生成轮数已达上限，建议人工审核"],
                regenerate_agents=[],
                weight_snapshot={},
            )

        # Step 1: 质量评分
        scores = await self._score_all(results, student_profile, topic)
        avg_score = sum(s.overall for s in scores) / len(scores) if scores else 0

        # Step 1.5: 教学业务规则校验（报告§3.3.3 — 约束调度合理性）
        schedule_issues = self._validate_teaching_schedule(results, topic, student_profile)

        # Step 2: 知识一致性校验（真版：语义级 + 证据消解）
        flagged_issues = await self._check_consistency_enhanced(results, topic, student_profile)
        # 合入教学规则校验发现的问题
        flagged_issues.extend(schedule_issues)

        low_scorers = [s for s in scores if s.overall < self.quality_threshold]

        # Step 3: Neural GroupMixer 共识混合（真版增量）
        mixer_result = await self._neural_mix(results, scores, student_profile, topic)
        neural_consensus_score = mixer_result.get("consensus_score", avg_score)

        # Step 4: 决策
        if flagged_issues or low_scorers:
            regenerate = list(set(
                [s.agent_name for s in low_scorers] +
                self._trace_flagged_agents(flagged_issues, results)
            ))

            # 记录表现
            for s in scores:
                pg_client.log_agent_score(s.agent_name, s.overall, "generation",
                                          f"flagged={len(flagged_issues)} issues")

            return ConsensusResult(
                status="regenerate",
                overall_score=neural_consensus_score,
                agent_scores=scores,
                merged_content="",
                flagged_issues=flagged_issues,
                regenerate_agents=regenerate,
                weight_snapshot=mixer_result.get("dynamic_weights", self._get_dynamic_weights()),
            )

        # 通过：合并输出
        combined = self._merge_all(results)
        for s in scores:
            pg_client.log_agent_score(s.agent_name, s.overall, "generation", "passed")

        # 缓存权重到 Redis
        weights = mixer_result.get("dynamic_weights", self._get_dynamic_weights())
        redis_client.cache_agent_weights(weights)

        return ConsensusResult(
            status="passed",
            overall_score=neural_consensus_score,
            agent_scores=scores,
            merged_content=combined,
            flagged_issues=[],
            regenerate_agents=[],
            weight_snapshot=weights,
        )

    # ── 质量评分 ──

    async def _score_all(
        self, results: list[AgentResult], profile: dict, topic: str
    ) -> list[QualityScore]:
        """对每个 Agent 结果打分"""
        scores = []
        for r in results:
            try:
                score = await self._score_single(r, profile, topic)
                scores.append(score)
            except Exception as e:
                logger.warning(f"Agent 评分失败: {r.agent_name} {e}")
                # 降级：默认低分
                scores.append(QualityScore(
                    agent_name=r.agent_name,
                    accuracy=5.0,
                    completeness=5.0,
                    adaptability=5.0,
                    overall=5.0,
                    notes=f"评分失败: {e}",
                ))
        return scores

    async def _score_single(
        self, result: AgentResult, profile: dict, topic: str
    ) -> QualityScore:
        """用 LLM 对单个 Agent 结果评分"""
        scorer = LLMProvider()
        system_prompt = (
            "你是多智能体系统的「质量评审员」。请对以下 Agent 的生成结果进行评分。\n\n"
            "评分维度（1-10分）：\n"
            "1. 准确性(accuracy)：内容是否有事实错误\n"
            "2. 完整性(completeness)：是否覆盖了核心知识点\n"
            "3. 适配性(adaptability)：是否贴合学生画像\n\n"
            "【常见易错点提示】\n"
            "- TCP 面向连接，UDP 无连接\n"
            "- 交换机的数据链路层设备，路由器是网络层设备\n"
            "- HTTP 80端口，HTTPS 443端口\n"
            "- 三次握手顺序：SYN → SYN+ACK → ACK\n\n"
            "输出格式（严格JSON）：\n"
            '{"accuracy": 8, "completeness": 7, "adaptability": 7, "overall": 7.3, "notes": "..."}'
        )

        profile_str = json.dumps(profile, ensure_ascii=False)
        content_preview = result.content[:2000]  # 截断长文本

        user_prompt = (
            f"【主题】{topic}\n"
            f"【学生画像】{profile_str}\n"
            f"【Agent名称】{result.agent_name}\n"
            f"【生成内容】\n{content_preview}"
        )

        try:
            reply = await scorer.text_completion(
                system_prompt, user_prompt, temperature=0.3, max_tokens=300
            )
            # 提取 JSON
            m = re.search(r'\{.*\}', reply, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                return QualityScore(
                    agent_name=result.agent_name,
                    accuracy=data.get("accuracy", 5),
                    completeness=data.get("completeness", 5),
                    adaptability=data.get("adaptability", 5),
                    overall=data.get("overall", 5),
                    notes=data.get("notes", ""),
                )
        except Exception as e:
            logger.warning(f"LLM 评分解析失败: {e}")

        # 降级：基于规则评分
        return QualityScore(
            agent_name=result.agent_name,
            accuracy=6.0,
            completeness=5.0 if len(result.content) < 100 else 7.0,
            adaptability=5.0,
            overall=6.0,
            notes="规则降级评分",
        )

    # ── 教学业务规则校验（报告§3.3.3） ──

    def _validate_teaching_schedule(
        self, results: list[AgentResult], topic: str, student_profile: dict
    ) -> list[str]:
        """教学规则校验——约束调度行为符合408业务逻辑

        改进点:
        1. 校验Agent分配是否匹配知识点课程范围
        2. 校验内容是否违背教学顺序
        3. 基于画像建议优先级调整
        """
        if not self._use_teaching_rules:
            return []

        try:
            from engines.teaching_rules import teaching_rules

            issues = []

            # 1. Agent分配适配性校验
            # 查找与topic匹配的知识点
            topic_id = self._find_topic_id(topic)
            if topic_id:
                # 建议Agent分配
                suggested_agents = teaching_rules.suggest_agent_assignment(topic_id)
                actual_agents = [r.agent_name for r in results]

                # 检查是否有不适合的Agent
                dep = teaching_rules._dependencies.get(topic_id)
                if dep:
                    for agent_name in actual_agents:
                        aff = teaching_rules._agent_affinities.get(agent_name)
                        if aff and dep.course not in aff.preferred_courses:
                            issues.append(
                                f"教学规则: {agent_name} 不擅长 {dep.course} 课程 "
                                f"(擅长: {', '.join(aff.preferred_courses[:2])})"
                            )

                # 2. 前置依赖提示
                prereqs = teaching_rules.get_prerequisites(topic_id)
                if prereqs:
                    prereq_names = []
                    for pid in prereqs:
                        pdep = teaching_rules._dependencies.get(pid)
                        if pdep:
                            prereq_names.append(pdep.topic_name)
                    if prereq_names and student_profile:
                        mastered = set(student_profile.get("mastered_topics", []))
                        unlearned = [n for n in prereq_names if n not in mastered]
                        if unlearned:
                            issues.append(
                                f"教学规则: 前置依赖未覆盖 — "
                                f"{topic} 需要: {', '.join(unlearned)}"
                            )

                # 3. 跨科目关联提示
                cross = teaching_rules.get_cross_subject_prerequisites(topic_id)
                if cross:
                    cross_names = []
                    for cid in cross:
                        cdep = teaching_rules._dependencies.get(cid)
                        if cdep:
                            cross_names.append(f"{cdep.topic_name}({cdep.course})")
                    if cross_names:
                        issues.append(
                            f"教学规则: 跨科目关联 — "
                            f"{topic} 关联: {', '.join(cross_names[:3])}"
                        )

            return issues

        except ImportError:
            logger.info("教学规则引擎未加载")
        except Exception as e:
            logger.warning(f"教学规则校验失败: {e}")

        return []

    def _find_topic_id(self, topic: str) -> str:
        """从topic文本查找匹配的知识点ID"""
        try:
            from engines.teaching_rules import teaching_rules

            # 精确匹配
            for dep_id, dep in teaching_rules._dependencies.items():
                if dep.topic_name == topic or dep_id == topic:
                    return dep_id

            # 关键词模糊匹配
            topic_lower = topic.lower()
            for dep_id, dep in teaching_rules._dependencies.items():
                if dep.topic_name in topic_lower or any(
                    kw in topic_lower for kw in dep.topic_name.split()
                ):
                    return dep_id
        except ImportError:
            pass

        return ""

    # ── 一致性校验 ──

    def _check_consistency(self, results: list[AgentResult]) -> list[str]:
        """基础一致性校验（关键词矛盾检测）"""
        issues = []

        # 预定义矛盾对
        contradiction_patterns = [
            ("面向连接", "无连接", "TCP/UDP 特性矛盾"),
            ("三次握手", "四次握手", "握手次数错误"),
            ("数据链路层设备", "网络层设备", "设备层级混淆"),
            ("80端口", "443端口", "HTTP/HTTPS 端口混淆"),
        ]

        for i, r1 in enumerate(results):
            for j, r2 in enumerate(results):
                if i >= j:
                    continue
                for pattern_a, pattern_b, desc in contradiction_patterns:
                    if pattern_a in r1.content and pattern_b in r2.content:
                        issue = f"矛盾: {r1.agent_name} 提到「{pattern_a}」, "
                        issue += f"{r2.agent_name} 提到「{pattern_b}」({desc})"
                        issues.append(issue)
                    elif pattern_b in r1.content and pattern_a in r2.content:
                        issue = f"矛盾: {r1.agent_name} 提到「{pattern_b}」, "
                        issue += f"{r2.agent_name} 提到「{pattern_a}」({desc})"
                        issues.append(issue)

        return list(set(issues))  # 去重

    def _trace_flagged_agents(
        self, issues: list[str], results: list[AgentResult]
    ) -> list[str]:
        """根据 flagged 的问题追踪出问题的 Agent"""
        flagged = []
        for issue in issues:
            for r in results:
                if r.agent_name in issue:
                    flagged.append(r.agent_name)
        return list(set(flagged))

    # ── 真版增量：增强一致性校验（语义级 + 证据消解） ──

    async def _check_consistency_enhanced(
        self, results: list[AgentResult], topic: str, student_profile: dict
    ) -> list[str]:
        """增强一致性校验（真版：语义级 E5 + 证据消解）

        申报书 Table 2-2 校验层+消解层：
        "✅ 新增：调用 FrugalRAG 检索证据验证冲突"
        "✅ 新增：基于证据的冲突消解算法"
        """
        # 1. 先用基础关键词检测（保留原有逻辑）
        issues = self._check_consistency(results)

        # 2. 真版增量：语义级冲突检测 + 证据消解
        if not self._use_evidence:
            return issues

        try:
            from engines.gomarl_conflict import conflict_engine

            # 构建 Agent 结果格式
            agent_dicts = [
                {"agent_name": r.agent_name, "content": r.content}
                for r in results
            ]

            # 检测 + 消解
            course = student_profile.get("course", "computer_network")
            result = await conflict_engine.check_and_resolve(
                agent_dicts, course=course
            )

            # 将消解结果转为 issue 描述
            for c in result.get("conflicts", []):
                issue = (
                    f"冲突({c['type']}): {c['agent_a']} vs {c['agent_b']} — "
                    f"{c['description']} → 消解: {c['resolution']} "
                    f"(置信度: {c['confidence']:.0%})"
                )
                issues.append(issue)

        except ImportError:
            logger.info("证据冲突消解模块未加载，使用基础校验")
        except Exception as e:
            logger.warning(f"增强一致性校验失败: {e}")

        return list(set(issues))

    # ── 真版增量：Neural GroupMixer ──

    async def _neural_mix(
        self,
        results: list[AgentResult],
        scores: list[QualityScore],
        student_profile: dict,
        topic: str,
    ) -> dict:
        """Neural GroupMixer 共识混合（真版增量）

        申报书 Table 2-2 决策层：
        "改进传统多数投票为加权投票" + NeuralMixer 神经网络
        """
        if not self._use_neural:
            return {"consensus_score": 0, "dynamic_weights": self._get_dynamic_weights()}

        try:
            from engines.gomarl_mixer import neural_mixer

            # 构建 Agent 结果（含质量评分）
            agent_dicts = [
                {
                    "agent_name": r.agent_name,
                    "content": r.content,
                    "score": s.overall,
                }
                for r, s in zip(results, scores)
            ]

            result = await neural_mixer.mix(agent_dicts, student_profile, topic)
            return result

        except ImportError:
            logger.info("NeuralMixer 未加载，使用加权平均")
        except Exception as e:
            logger.warning(f"NeuralMixer 失败: {e}")

        return {"consensus_score": 0, "dynamic_weights": self._get_dynamic_weights()}

    # ── 动态权重 ──

    def _get_dynamic_weights(self) -> dict[str, float]:
        """基于历史表现计算动态权重"""
        weights = {}
        for name, base in self._base_weights.items():
            history = pg_client.get_agent_history(name, self.history_window)
            if history:
                avg_history = sum(history) / len(history)
                # 历史平均分 (1-10) 映射为权重调整因子 (0.5-1.5)
                factor = 0.5 + (avg_history / 10.0)
                weights[name] = base * factor
            else:
                weights[name] = base
        return weights

    # ── 结果合并 ──

    def _merge_all(self, results: list[AgentResult]) -> str:
        """合并所有 Agent 结果"""
        merged = ""
        for r in results:
            merged += f"\n\n---\n## {r.agent_name} 的输出\n\n{r.content}"
        return merged.strip()
