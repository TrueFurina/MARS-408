# ============================================================
# FrugalRAG 停止决策 — 启发式覆盖率停止 + 查询重写
#
# 来源：FrugalRAG-main GRPO 训练管线 (ICLR 2026) 的思路适配
# 申报书 Table 2-1 第6-7层
#
# 诚实说明（代码审查 2026-07-04）：
#   本模块是「基于覆盖率的规则/启发式停止决策」，并非 GRPO 强化学习。
#   仓库内不存在 GRPO 训练代码——停止逻辑本质是覆盖率阈值判断
#   （简单问题阈值 0.6 / 中等 0.7 / 复杂 0.8），并按历史做 EWMA 阈值自适应。
#   命名为 "GRPO 风格" 仅表示设计思路借鉴了 FrugalRAG 的 GRPO 停止策略，
#   不含任何策略梯度、奖励建模或环境交互。
#
# 功能：
#   1. 启发式停止决策：基于检索覆盖率的动态阈值停止策略
#   2. 查询重写：当检索不足时，基于上下文重写查询
#   3. 覆盖率评估：关键词匹配率（retrieved vs question）
#   4. 动态阈值：根据问题复杂度 + 历史表现调整停止阈值（EWMA）
#   5. 少样本适配：LoRA 配置接口（申报书第9层，仅配置，不训练）
# ============================================================

import logging
import re
from typing import Optional
from dataclasses import dataclass, field

from db.llm_provider import LLMProvider
from engines.frugal_rag import frugal_rag
from engines.frugal_rag_sft import query_preprocessor

logger = logging.getLogger("netlearn.frugal_stop")


# ── 1. RL 停止决策模块 ──

@dataclass
class StopDecision:
    """停止决策结果"""
    should_stop: bool          # 是否停止检索
    confidence: float          # 置信度 0-1
    coverage: float            # 当前覆盖率
    reason: str                # 决策原因
    threshold_used: float      # 使用的阈值
    efficiency_score: float    # 效率评分（覆盖率 × 检索效率因子，非 RL 奖励）


class HeuristicStopDecision:
    """启发式停止决策模块（GRPO 风格思路，非强化学习）

    申报书 Table 2-1 第二阶段：
    "RL 停止决策模块 — 学习何时停止检索（核心算法）— GRPO 强化学习算法"

    诚实说明：本模块是规则/启发式实现，不含 GRPO 训练或任何强化学习。
    原始 FrugalRAG 使用 GRPO 训练 LLM 学习停止策略（状态-动作-奖励），
    本模块以覆盖率阈值判断替代——设计思路借鉴 GRPO 停止策略，但无策略梯度。

    决策逻辑（启发式，非学习）：
    - 简单问题：覆盖率 > 0.6 即停止（1轮足够）
    - 中等问题：覆盖率 > 0.7 停止（最多2轮）
    - 复杂问题：覆盖率 > 0.8 停止（最多3轮）
    - 动态阈值：基于历史检索效果的 EWMA 自适应调整
    """

    def __init__(self):
        # 基础阈值（按复杂度）
        self._base_thresholds = {
            "simple": 0.60,
            "medium": 0.70,
            "complex": 0.80,
        }

        # 动态阈值历史（EWMA）
        self._threshold_ewma = {
            "simple": 0.60,
            "medium": 0.70,
            "complex": 0.80,
        }
        self._ewma_alpha = 0.1  # EWMA 平滑系数
        self._decision_history: list[dict] = []

        # 检索效率惩罚系数（GRPO 奖励中的效率项）
        self.efficiency_penalty = 0.05  # 每多一轮检索扣 5%

    def decide(
        self,
        question: str,
        course: str,
        current_chunks: list[dict],
        iteration: int,
        max_iterations: int,
    ) -> StopDecision:
        """决策：是否停止检索

        Args:
            question: 原始问题
            course: 课程
            current_chunks: 当前所有检索到的 chunks
            iteration: 当前轮次 (0-indexed)
            max_iterations: 最大轮次

        Returns:
            StopDecision
        """
        # 评估复杂度
        complexity = query_preprocessor.assess_complexity(question)

        # 计算覆盖率
        coverage = self._compute_coverage(question, current_chunks)

        # 获取动态阈值
        threshold = self._get_dynamic_threshold(complexity, iteration)

        # 计算效率评分（覆盖率 × 检索效率因子；注意：非 RL 奖励，仅启发式指标）
        efficiency = 1.0 - (iteration * self.efficiency_penalty)
        efficiency_score = coverage * efficiency

        # 决策逻辑
        if iteration >= max_iterations - 1:
            # 达到最大轮次，强制停止
            return StopDecision(
                should_stop=True,
                confidence=0.5,
                coverage=coverage,
                reason=f"达到最大检索轮次({max_iterations})，强制停止",
                threshold_used=threshold,
                efficiency_score=efficiency_score,
            )

        if coverage >= threshold:
            # 覆盖率达标，停止
            confidence = min(coverage, 0.95)
            return StopDecision(
                should_stop=True,
                confidence=confidence,
                coverage=coverage,
                reason=f"覆盖率 {coverage:.0%} >= 阈值 {threshold:.0%}（{complexity}），停止检索",
                threshold_used=threshold,
                efficiency_score=efficiency_score,
            )

        if not current_chunks or coverage < 0.1:
            # 检索结果太少，但可能有检索问题，继续尝试
            if iteration < max_iterations - 1:
                return StopDecision(
                    should_stop=False,
                    confidence=0.3,
                    coverage=coverage,
                    reason=f"覆盖率过低({coverage:.0%})，尝试查询重写后继续",
                    threshold_used=threshold,
                    efficiency_score=efficiency_score,
                )

        # 未达标，继续
        return StopDecision(
            should_stop=False,
            confidence=0.4,
            coverage=coverage,
            reason=f"覆盖率 {coverage:.0%} < 阈值 {threshold:.0%}，继续检索",
            threshold_used=threshold,
            efficiency_score=efficiency_score,
        )

    def update_threshold(self, complexity: str, final_coverage: float, was_good: bool):
        """根据最终结果更新动态阈值（基于历史效果的 EWMA 自适应，非在线学习）

        Args:
            complexity: 问题复杂度
            final_coverage: 最终覆盖率
            was_good: 最终答案质量是否良好
        """
        if was_good and final_coverage < self._threshold_ewma[complexity]:
            # 好答案但覆盖率低于阈值 → 降低阈值（可以更早停止）
            adjustment = -0.02
        elif not was_good and final_coverage >= self._threshold_ewma[complexity]:
            # 差答案但覆盖率达标 → 提高阈值（需要更多检索）
            adjustment = 0.03
        else:
            adjustment = 0

        # EWMA 更新
        old = self._threshold_ewma[complexity]
        new_val = old + self._ewma_alpha * (old + adjustment - old)
        # 限制范围
        self._threshold_ewma[complexity] = max(0.4, min(0.9, new_val))

        if adjustment != 0:
            logger.info(
                f"GRPO 阈值更新: {complexity} {old:.2f} → {self._threshold_ewma[complexity]:.2f} "
                f"(adjustment={adjustment:+.2f})"
            )

        # 记录历史
        self._decision_history.append({
            "complexity": complexity,
            "coverage": final_coverage,
            "good": was_good,
            "threshold": self._threshold_ewma[complexity],
        })

        # 只保留最近 50 条
        if len(self._decision_history) > 50:
            self._decision_history = self._decision_history[-50:]

    def _get_dynamic_threshold(self, complexity: str, iteration: int) -> float:
        """获取动态阈值"""
        base = self._threshold_ewma.get(complexity, 0.70)
        # 随轮次递减（越往后越容易停止）
        decay = 0.05 * iteration
        return max(0.4, base - decay)

    def _compute_coverage(self, question: str, chunks: list[dict]) -> float:
        """计算检索覆盖率"""
        keywords = query_preprocessor.extract_keywords(question)
        if not keywords:
            keywords = [w for w in re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', question) if len(w) > 1]

        if not keywords or not chunks:
            return 0.0

        all_text = " ".join(c.get("text", "") for c in chunks).lower()
        covered = sum(1 for kw in keywords if kw.lower() in all_text)
        return covered / len(keywords)

    def get_stats(self) -> dict:
        """获取停止决策统计"""
        if not self._decision_history:
            return {"total_decisions": 0}

        total = len(self._decision_history)
        good = sum(1 for d in self._decision_history if d["good"])
        avg_coverage = sum(d["coverage"] for d in self._decision_history) / total

        return {
            "total_decisions": total,
            "good_rate": good / total,
            "avg_coverage": avg_coverage,
            "thresholds": dict(self._threshold_ewma),
        }


# ── 2. 查询重写模块 ──

_REWRITE_PROMPT = """你是检索系统的「查询重写器」。

原始问题：{question}
学科：{course}
之前的检索查询：{previous_queries}
之前检索到的片段（前200字）：
{previous_snippets}

问题：之前的检索查询没有找到足够相关的知识。请重写查询，尝试不同的角度。

重写策略：
1. 如果之前用的是概念名，尝试用定义描述（如"三次握手"→"TCP连接建立过程 SYN SYN-ACK"）
2. 如果之前用的是英文术语，尝试中文描述
3. 如果之前太具体，尝试更宽泛的查询
4. 如果之前太宽泛，尝试更具体的查询
5. 提取之前检索片段中的新关键词

只输出重写后的查询文本，不要其他内容。"""


class QueryRewriter:
    """查询重写模块（申报书 Table 2-1 重写层）

    当检索结果不足时，基于上下文重写查询
    对应 FrugalRAG 的 query rewriting 机制
    """

    def __init__(self):
        self._llm = LLMProvider()
        self._max_rewrites = 2  # 最大重写次数

    async def rewrite(
        self,
        question: str,
        course: str,
        previous_queries: list[str],
        previous_chunks: list[dict],
    ) -> Optional[str]:
        """重写查询

        Returns:
            重写后的查询，或 None 表示无法重写
        """
        if len(previous_queries) >= self._max_rewrites:
            logger.info("查询重写次数已达上限")
            return None

        # 构建上下文
        snippets = []
        for c in previous_chunks[-3:]:  # 最近3条
            text = c.get("text", "")[:200]
            snippets.append(text)
        previous_snippets = "\n---\n".join(snippets) if snippets else "（无）"

        prompt = _REWRITE_PROMPT.format(
            question=question,
            course=course,
            previous_queries=" | ".join(previous_queries[-3:]),
            previous_snippets=previous_snippets,
        )

        try:
            rewritten = await self._llm.text_completion(
                "你是检索查询重写专家。",
                prompt,
                temperature=0.4,
                max_tokens=100,
            )
            rewritten = rewritten.strip().strip('"').strip("'")

            if rewritten and rewritten != previous_queries[-1]:
                logger.info(f"查询重写: '{previous_queries[-1]}' → '{rewritten}'")
                return rewritten
        except Exception as e:
            logger.warning(f"查询重写失败: {e}")

        return None


# ── 3. 少样本适配模块（LoRA 接口） ──

class LoRAAdapter:
    """少样本适配模块（申报书 Table 2-1 适配层）

    "少样本适配模块 — 快速适配新的课程领域 — 低秩适配 (LoRA) 技术"

    提供 LoRA 微调的配置接口和训练数据生成：
    - 500 条标注样本即可完成学科适配
    - 使用 LoRA 微调 E5 嵌入模型
    """

    def __init__(self):
        self.lora_config = {
            "target_modules": ["query", "value", "key", "dense"],
            "r": 8,                    # 秩
            "lora_alpha": 16,          # 缩放因子
            "lora_dropout": 0.1,
            "bias": "none",
            "task_type": "FEATURE_EXTRACTION",
        }
        self.training_config = {
            "num_samples": 500,        # 申报书: "仅需500条标注样本"
            "epochs": 3,
            "batch_size": 8,
            "learning_rate": 1e-4,
            "warmup_steps": 50,
        }

    def generate_training_data_template(self, course: str, samples: list[dict]) -> list[dict]:
        """生成 LoRA 训练数据模板

        Args:
            course: 课程名
            samples: 原始样本 [{question, answer, relevant_chunks}]

        Returns:
            训练数据格式
        """
        training_data = []
        for s in samples:
            training_data.append({
                "query": s.get("question", ""),
                "positive_passages": [c.get("text", "") for c in s.get("relevant_chunks", [])[:2]],
                "negative_passages": [],  # 负样本（后续填充）
                "course": course,
            })
        return training_data

    def get_lora_config(self) -> dict:
        """获取 LoRA 配置"""
        return {
            "lora": self.lora_config,
            "training": self.training_config,
            "description": "使用500条标注样本通过LoRA微调E5嵌入模型，实现快速学科适配",
        }


# ── 4. 完整的 FrugalRAG 真版检索流程 ──

class FrugalRAGFull:
    """FrugalRAG 真版完整检索流程

    整合 LLM 查询优化(SFT风格) + 启发式停止决策 + 查询重写 + LoRA 适配接口

    对应申报书 Table 2-1 全部9层模块
    """

    def __init__(self):
        from engines.frugal_rag_sft import LLMQueryOptimizer, ReActRetriever
        self.sft = LLMQueryOptimizer()
        self.stop_decision = HeuristicStopDecision()
        self.rewriter = QueryRewriter()
        self.lora = LoRAAdapter()
        self.retriever = ReActRetriever()

    async def retrieve_full(
        self,
        question: str,
        course: str = "computer_network",
        top_k: int = 5,
        student_profile: Optional[dict] = None,
    ) -> dict:
        """完整的 FrugalRAG 检索流程

        流程：
        1. 查询预处理
        2. LLM 生成优化查询（SFT 风格，prompt 工程）
        3. 向量检索 + BM25 融合
        4. 启发式停止决策（覆盖率阈值，非 RL）
        5. 如未停止 → 查询重写 → 回到步骤2
        6. 最终答案生成

        Returns:
        {
            "answer": str,
            "trajectory": list,      # 完整检索轨迹
            "all_chunks": list,      # 所有检索结果
            "stop_decisions": list,  # 每轮停止决策
            "coverage": float,       # 最终覆盖率
            "total_searches": int,   # 总检索次数
            "rewrites": int,         # 查询重写次数
            "complexity": str,       # 问题复杂度
        }
        """
        # 1. 预处理
        cleaned = query_preprocessor.preprocess(question, course)
        complexity = query_preprocessor.assess_complexity(cleaned)

        max_iters = {"simple": 1, "medium": 2, "complex": 3}.get(complexity, 2)

        trajectory = []
        all_chunks = []
        all_texts = set()
        queries_used = []
        stop_decisions = []
        rewrites = 0

        for iteration in range(max_iters):
            # 2. SFT 生成优化查询
            search_query = await self.sft.generate_search_query(
                cleaned, course, all_chunks
            )
            queries_used.append(search_query)

            trajectory.append({
                "iteration": iteration + 1,
                "type": "search_query",
                "query": search_query,
                "source": "sft_generated" if iteration > 0 else "sft_initial",
            })

            # 3. 检索
            chunks = await frugal_rag.retrieve(search_query, course, top_k=top_k, student_profile=student_profile)

            # 去重
            new_chunks = []
            for c in chunks:
                text_key = c.get("text", "")[:100]
                if text_key not in all_texts:
                    all_texts.add(text_key)
                    new_chunks.append(c)
            all_chunks.extend(new_chunks)

            trajectory.append({
                "iteration": iteration + 1,
                "type": "observation",
                "new_chunks": len(new_chunks),
                "total_chunks": len(all_chunks),
                "top_score": new_chunks[0]["score"] if new_chunks else 0,
            })

            # 4. RL 停止决策
            decision = self.stop_decision.decide(
                cleaned, course, all_chunks, iteration, max_iters
            )
            stop_decisions.append({
                "iteration": iteration + 1,
                "should_stop": decision.should_stop,
                "coverage": decision.coverage,
                "threshold": decision.threshold_used,
                "reason": decision.reason,
                "efficiency_score": decision.efficiency_score,
            })

            trajectory.append({
                "iteration": iteration + 1,
                "type": "stop_decision",
                "should_stop": decision.should_stop,
                "coverage": decision.coverage,
                "reason": decision.reason,
            })

            if decision.should_stop:
                break

            # 5. 查询重写（如果未停止）
            if iteration < max_iters - 1:
                rewritten = await self.rewriter.rewrite(
                    cleaned, course, queries_used, new_chunks
                )
                if rewritten:
                    queries_used.append(rewritten)
                    rewrites += 1
                    trajectory.append({
                        "iteration": iteration + 1,
                        "type": "query_rewrite",
                        "original": search_query,
                        "rewritten": rewritten,
                    })
                    # 用重写后的查询重新检索
                    chunks2 = await frugal_rag.retrieve(rewritten, course, top_k=top_k, student_profile=student_profile)
                    new_chunks2 = []
                    for c in chunks2:
                        text_key = c.get("text", "")[:100]
                        if text_key not in all_texts:
                            all_texts.add(text_key)
                            new_chunks2.append(c)
                    all_chunks.extend(new_chunks2)

                    trajectory.append({
                        "iteration": iteration + 1,
                        "type": "observation_rewrite",
                        "new_chunks": len(new_chunks2),
                    })

        # 6. 生成答案
        final_coverage = self.stop_decision._compute_coverage(cleaned, all_chunks)
        answer = await self.sft.generate_answer(cleaned, course, all_chunks)

        trajectory.append({
            "iteration": len(trajectory) + 1,
            "type": "finish",
            "answer_length": len(answer),
            "final_coverage": final_coverage,
            "total_chunks": len(all_chunks),
        })

        # 收集个性化重排统计
        rerank_adjustments = [
            {
                "chunk_id": c.get("id", ""),
                "adjustment": c.get("_rerank_adjustment", 0),
                "reasons": c.get("_rerank_reasons", []),
            }
            for c in all_chunks
            if c.get("_rerank_adjustment", 0) != 0
        ]

        return {
            "answer": answer,
            "trajectory": trajectory,
            "all_chunks": all_chunks,
            "stop_decisions": stop_decisions,
            "coverage": final_coverage,
            "total_searches": len(queries_used),
            "rewrites": rewrites,
            "complexity": complexity,
            "cleaned_question": cleaned,
            "personalized_rerank": {
                "applied": bool(student_profile),
                "affected_chunks": len(rerank_adjustments),
                "adjustments": rerank_adjustments,
                "profile_summary": {
                    "weak_topics": list(student_profile.get("weak_topics", [])) if student_profile else [],
                    "mastered_topics": list(student_profile.get("mastered_topics", [])) if student_profile else [],
                    "review_stage": student_profile.get("review_stage", "basic") if student_profile else None,
                    "target_score": student_profile.get("target_score", 100) if student_profile else None,
                } if student_profile else None,
            },
        }


# 全局单例
stop_decision = HeuristicStopDecision()
query_rewriter = QueryRewriter()
lora_adapter = LoRAAdapter()
frugal_rag_full = FrugalRAGFull()
