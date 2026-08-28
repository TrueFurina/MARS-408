# ============================================================
# FrugalRAG 检索查询优化模块（SFT 风格）
#
# 来源：FrugalRAG-main (ICLR 2026) ReAct 框架适配
# 申报书 Table 2-1 第1-3层 + 第8层
#
# 诚实说明（代码审查 2026-07-04）：
#   本模块通过「LLM prompt 工程」实现 SFT 风格的检索查询优化，
#   Lite 版不执行任何真实模型微调——仓库内不存在 SFT 训练代码。
#   代码以精心设计的提示词让 LLM 生成优化查询，模拟 SFT 训练后模型的行为。
#   生产版可将 LLMQueryOptimizer 替换为真实 SFT 模型（调用接口保持不变）。
#
# 功能：
#   1. 查询预处理（regex 去噪 + 关键词提取）
#   2. LLM 查询优化（prompt 驱动的检索 query 生成，非模型微调）
#   3. 多轮迭代检索（ReAct：搜索 → 观察 → 再搜索）
#   4. 检索结果融合排序（BM25 + 向量加权）
# ============================================================

import logging
import re
from typing import Optional

from db.llm_provider import LLMProvider
from engines.frugal_rag import frugal_rag, format_retrieval_for_llm

logger = logging.getLogger("netlearn.frugal_sft")


# ── 1. 查询预处理 ──

class QueryPreprocessor:
    """查询预处理模块（申报书 Table 2-1 输入层）"""

    # 噪声模式
    _NOISE_PATTERNS = [
        (r"^(请问|帮我|我想知道|能不能|可以|麻烦|请)\s*", ""),
        (r"(呢|啊|呀|吧|嘛|哦|哈)+[？?]?$", ""),
        (r"(的|了)+[？?]$", "？"),
        (r"\s{2,}", " "),
    ]

    # 408 学科关键词词典
    _DOMAIN_KEYWORDS = {
        "data_structures": ["链表", "栈", "队列", "树", "图", "排序", "查找", "哈希", "堆", "二叉树", "AVL", "红黑树", "B树", "图遍历", "最短路径", "最小生成树"],
        "computer_network": ["TCP", "UDP", "HTTP", "HTTPS", "IP", "DNS", "ARP", "ICMP", "路由", "交换机", "网关", "三次握手", "四次挥手", "拥塞控制", "滑动窗口", "CSMA/CD", "MAC", "VLAN"],
        "operating_system": ["进程", "线程", "调度", "互斥", "同步", "死锁", "内存管理", "虚拟内存", "分页", "分段", "文件系统", "I/O", "中断", "管道", "信号量", "PV操作"],
        "computer_organization": ["指令", "流水线", "Cache", "虚拟存储", "总线", "I/O", "中断", "寻址", "补码", "浮点数", "ALU", "寄存器", "控制器", "存储器"],
    }

    def preprocess(self, query: str, course: str = "") -> str:
        """对用户查询进行分词、去噪、补全"""
        cleaned = query.strip()

        # 去除口语噪声
        for pattern, replacement in self._NOISE_PATTERNS:
            cleaned = re.sub(pattern, replacement, cleaned)

        # 补全问号
        if cleaned and cleaned[-1] not in "？?。.!！":
            cleaned += "？"

        return cleaned.strip()

    def extract_keywords(self, query: str, course: str = "") -> list[str]:
        """提取查询中的领域关键词"""
        keywords = []

        # 展开所有领域关键词
        all_keywords = set()
        for kws in self._DOMAIN_KEYWORDS.values():
            all_keywords.update(kws)

        # 如果指定了课程，优先匹配该课程
        if course and course in self._DOMAIN_KEYWORDS:
            for kw in self._DOMAIN_KEYWORDS[course]:
                if kw.lower() in query.lower():
                    keywords.append(kw)
        else:
            for kw in all_keywords:
                if kw.lower() in query.lower():
                    keywords.append(kw)

        return keywords

    def assess_complexity(self, query: str) -> str:
        """评估问题复杂度（简单/中等/复杂）

        简单问题：概念定义类，可直接回答，无需检索
        中等问题：需要检索1-2次
        复杂问题：需要多轮检索+推理
        """
        keywords = self.extract_keywords(query)
        word_count = len(query)

        # 简单：单一关键词 + 短查询（定义类）
        if len(keywords) <= 1 and word_count < 20:
            return "simple"

        # 复杂：多个关键词 + 长查询（对比/分析类）
        if len(keywords) >= 3 or word_count > 50:
            return "complex"

        return "medium"


# ── 2. LLM 查询优化（SFT 风格，prompt 工程，非模型微调） ──

# ReAct 提示词（模拟 SFT 训练后的查询生成策略；Lite 版无真实 SFT 训练）
_SFT_QUERY_PROMPT = """你是检索增强生成系统的「查询优化器」。

学生问题：{question}
学科：{course}
已检索信息：{previous_context}

请生成一个优化的检索查询，用于从知识库中检索最相关的知识片段。

要求：
1. 提取问题中的核心概念和关键术语
2. 如果有已检索信息，结合上下文生成更精准的子查询
3. 查询应包含领域专业术语（如"三次握手"而非"连接过程"）
4. 输出格式：只输出查询文本，不要其他内容

示例：
问题："TCP建立连接的过程是什么？" → 查询："TCP 三次握手 SYN SYN-ACK ACK 连接建立"
问题："为什么需要四次挥手而不是三次？" → 查询："TCP 四次挥手 FIN 连接终止 半关闭状态 原因"
"""

# 答案提取提示词
_ANSWER_PROMPT = """你是408考研辅导老师。基于以下检索到的知识，回答学生的问题。

学生问题：{question}
学科：{course}

检索到的知识：
{context}

要求：
1. 回答必须基于检索到的知识，不要编造
2. 使用清晰的 Markdown 格式
3. 如果检索知识不足以完整回答，明确指出哪些部分需要补充
4. 408考研重点知识要突出标注
"""


class LLMQueryOptimizer:
    """检索查询优化器（SFT 风格，基于 LLM prompt 工程）

    申报书 Table 2-1 第一阶段。

    诚实说明：本类通过精心设计的提示词让 LLM 生成优化的检索查询，
    模拟 SFT 训练后模型的检索行为。Lite 版未执行真实 SFT 微调，
    仓库内不存在 SFT 训练代码。生产环境可替换为实际 SFT 模型
    （对外接口：generate_search_query / generate_answer 保持不变）。
    """

    def __init__(self):
        self._llm = LLMProvider()

    async def generate_search_query(
        self,
        question: str,
        course: str = "computer_network",
        previous_results: list[dict] = None,
    ) -> str:
        """生成优化的检索查询（LLM prompt 驱动，模拟 SFT 风格策略）"""
        # 构建上下文
        if previous_results:
            ctx_parts = []
            for i, r in enumerate(previous_results[-3:]):  # 最近3条
                text = r.get("text", "")[:200]
                ctx_parts.append(f"[{i+1}] {text}")
            previous_context = "\n".join(ctx_parts)
        else:
            previous_context = "（首次检索，无上下文）"

        prompt = _SFT_QUERY_PROMPT.format(
            question=question,
            course=course,
            previous_context=previous_context,
        )

        try:
            query = await self._llm.text_completion(
                "你是检索查询优化专家。",
                prompt,
                temperature=0.3,
                max_tokens=100,
            )
            # 清理输出
            query = query.strip().strip('"').strip("'")
            if not query:
                query = question  # 降级为原始问题
            return query
        except Exception as e:
            logger.warning(f"SFT 查询生成失败，降级为原始问题: {e}")
            return question

    async def generate_answer(
        self,
        question: str,
        course: str,
        retrieved_chunks: list[dict],
    ) -> str:
        """基于检索结果生成最终答案"""
        context = format_retrieval_for_llm(retrieved_chunks)
        prompt = _ANSWER_PROMPT.format(
            question=question,
            course=course,
            context=context,
        )

        try:
            answer = await self._llm.text_completion(
                "你是408考研辅导老师，擅长用清晰的语言解释计算机概念。",
                prompt,
                temperature=0.5,
                max_tokens=1500,
            )
            return answer or "（生成答案失败）"
        except Exception as e:
            logger.error(f"答案生成失败: {e}")
            return f"答案生成失败: {e}"


# ── 3. 多轮迭代检索（ReAct 框架） ──

class ReActRetriever:
    """ReAct 多轮迭代检索器

    模拟 FrugalRAG 的 ReAct 框架：
    Thought → Action(search) → Observation → Thought → ... → Finish(answer)

    对应 FrugalRAG-main 的 search_r1_client.py 推理流程
    """

    def __init__(self):
        self.preprocessor = QueryPreprocessor()
        self.sft_generator = LLMQueryOptimizer()
        self.max_iters = 3  # 最大检索轮数

    async def retrieve_with_reasoning(
        self,
        question: str,
        course: str = "computer_network",
        top_k: int = 5,
        student_profile: Optional[dict] = None,
    ) -> dict:
        """
        ReAct 式多轮检索

        返回:
        {
            "answer": str,           # 最终答案
            "trajectory": list,      # 检索轨迹
            "total_searches": int,   # 总检索次数
            "coverage": float,       # 覆盖率
            "all_chunks": list,      # 所有检索到的 chunks
        }
        """
        # 预处理
        cleaned_question = self.preprocessor.preprocess(question, course)
        complexity = self.preprocessor.assess_complexity(cleaned_question)

        # ── 真版增量：知识图谱扩展（报告§3.4.1） ──
        # 检索前先查KG，获取关联知识点用于跨科目扩展
        kg_expansion = self._expand_with_knowledge_graph(cleaned_question, course)

        trajectory = []
        all_chunks = []
        all_texts = set()  # 去重用
        total_searches = 0

        # 记录KG扩展结果到轨迹
        if kg_expansion["related_topics"]:
            trajectory.append({
                "iteration": 0,
                "type": "kg_expansion",
                "query": cleaned_question,
                "thought": f"知识图谱扩展：发现 {len(kg_expansion['related_topics'])} 个关联知识点",
                "related_topics": kg_expansion["related_topics"],
                "cross_subject": kg_expansion["cross_subject"],
                "prerequisites": kg_expansion["prerequisites"],
            })

        # 简单问题：直接检索1次
        if complexity == "simple":
            max_iters = 1
        elif complexity == "medium":
            max_iters = 2
        else:
            max_iters = self.max_iters

        for iteration in range(max_iters):
            # Step 1: 生成优化查询（SFT 策略）
            search_query = await self.sft_generator.generate_search_query(
                cleaned_question, course, all_chunks
            )

            # ── 真版增量：KG扩展查询增强 ──
            # 首轮检索时，如有跨科目关联则生成额外子查询
            extra_queries = []
            if iteration == 0 and kg_expansion["cross_subject"]:
                # 为跨科目关联知识点生成子查询
                cross_info = kg_expansion["cross_subject"]
                for cs in cross_info[:2]:  # 最多2个跨科目子查询
                    cs_name = cs.get("name", "")
                    cs_course = cs.get("course", "")
                    if cs_name and cs_course:
                        extra_queries.append(
                            f"{cs_name} {cs_course} 关联 {cleaned_question}"
                        )

            trajectory.append({
                "iteration": iteration + 1,
                "type": "search",
                "query": search_query,
                "thought": f"第{iteration+1}轮检索：{'首次检索' if iteration == 0 else '基于前序结果补充检索'}",
            })

            # Step 2: 执行检索
            chunks = await frugal_rag.retrieve(search_query, course, top_k=top_k, student_profile=student_profile)

            # ── 真版增量：执行KG扩展的跨科目子查询 ──
            for eq in extra_queries:
                eq_course = self._infer_course_from_query(eq)
                eq_chunks = await frugal_rag.retrieve(eq, eq_course, top_k=3)
                for c in eq_chunks:
                    text = c.get("text", "")[:100]
                    if text not in all_texts:
                        all_texts.add(text)
                        new_chunks_from_eq = [c]  # 临时标记
                        all_chunks.append(c)
                        total_searches += 1

                trajectory.append({
                    "iteration": iteration + 1,
                    "type": "cross_subject_search",
                    "query": eq,
                    "course": eq_course,
                    "thought": f"跨科目关联检索：{eq}",
                    "chunks_found": len(eq_chunks),
                })
                extra_queries = []  # 只在首轮执行

            # 去重
            new_chunks = []
            for c in chunks:
                text = c.get("text", "")[:100]
                if text not in all_texts:
                    all_texts.add(text)
                    new_chunks.append(c)

            all_chunks.extend(new_chunks)
            total_searches += 1

            trajectory.append({
                "iteration": iteration + 1,
                "type": "observation",
                "chunks_found": len(new_chunks),
                "top_score": new_chunks[0]["score"] if new_chunks else 0,
                "sources": [c.get("metadata", {}).get("chapter_name", "") for c in new_chunks[:3]],
            })

            # Step 3: 检查是否需要继续（停止决策）
            if iteration < max_iters - 1 and new_chunks:
                coverage = self._compute_coverage(cleaned_question, all_chunks)
                if coverage >= 0.75:  # 覆盖率足够，停止
                    trajectory.append({
                        "iteration": iteration + 1,
                        "type": "thought",
                        "thought": f"覆盖率 {coverage:.0%} 已达标，停止检索，生成答案",
                    })
                    break
            elif not new_chunks:
                trajectory.append({
                    "iteration": iteration + 1,
                    "type": "thought",
                    "thought": "无新检索结果，停止检索",
                })
                break

        # Step 4: 生成最终答案
        final_coverage = self._compute_coverage(cleaned_question, all_chunks)
        answer = await self.sft_generator.generate_answer(
            cleaned_question, course, all_chunks
        )

        trajectory.append({
            "iteration": len(trajectory) + 1,
            "type": "finish",
            "answer_length": len(answer),
            "coverage": final_coverage,
        })

        return {
            "answer": answer,
            "trajectory": trajectory,
            "total_searches": total_searches,
            "coverage": final_coverage,
            "all_chunks": all_chunks,
            "complexity": complexity,
            "cleaned_question": cleaned_question,
        }

    def _compute_coverage(self, question: str, chunks: list[dict]) -> float:
        """计算检索覆盖率 — 关键词匹配率

        修正版：只计算匹配的关键词比例作为检索覆盖率。
        不编造无数学意义的"精确率"公式。
        """
        # 提取问题关键词
        keywords = self.preprocessor.extract_keywords(question)
        if not keywords:
            # 降级：按词切分
            keywords = [w for w in re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', question) if len(w) > 1]

        if not keywords:
            return 0.5  # 无法评估，保守给中等分

        # 合并所有检索文本
        all_text = " ".join(c.get("text", "") for c in chunks).lower()

        # 计算匹配的关键词比例（这是检索覆盖率的正确定义）
        covered = sum(1 for kw in keywords if kw.lower() in all_text)
        coverage = covered / len(keywords)

        return coverage

    # ── 真版增量：知识图谱扩展（报告§3.4.1） ──

    def _expand_with_knowledge_graph(self, question: str, course: str) -> dict:
        """知识图谱约束扩展——跨科目关联检索支撑

        报告§3.4.1创新点：
        "加入学科知识图谱约束，解决跨科目多跳检索精准度问题"

        逻辑：
        1. 从教学规则引擎查找与query匹配的知识点
        2. 获取其前置依赖和关联知识点
        3. 发现跨科目关联，生成扩展检索建议
        """
        result = {
            "matched_topic": None,
            "related_topics": [],
            "cross_subject": [],
            "prerequisites": [],
        }

        try:
            from engines.teaching_rules import teaching_rules

            # 查找匹配的知识点
            topic_id = None
            topic_lower = question.lower()

            # 精确匹配
            for dep_id, dep in teaching_rules._dependencies.items():
                if dep.topic_name in topic_lower or dep_id in topic_lower:
                    topic_id = dep_id
                    break

            # 关键词模糊匹配
            if not topic_id:
                for dep_id, dep in teaching_rules._dependencies.items():
                    # 检查知识点名称的每个词是否出现在query中
                    terms = dep.topic_name.split()
                    matched_terms = sum(1 for t in terms if t in topic_lower)
                    if matched_terms >= max(1, len(terms) // 2):
                        topic_id = dep_id
                        break

            if not topic_id:
                return result

            dep = teaching_rules._dependencies.get(topic_id)
            result["matched_topic"] = {
                "id": topic_id,
                "name": dep.topic_name,
                "course": dep.course,
                "exam_weight": dep.exam_weight,
                "difficulty": dep.difficulty,
            }

            # 获取前置依赖
            prereqs = teaching_rules.get_prerequisites(topic_id)
            prereq_details = []
            for pid in prereqs:
                pdep = teaching_rules._dependencies.get(pid)
                if pdep:
                    prereq_details.append({
                        "id": pid, "name": pdep.topic_name,
                        "course": pdep.course,
                    })
            result["prerequisites"] = prereq_details

            # 获取同一课程的关联知识点（KG edges）
            # 从seed_data的KNOWLEDGE_GRAPH edges查找
            related = []
            try:
                from seed_data import KNOWLEDGE_GRAPH
                edges = KNOWLEDGE_GRAPH.get("edges", [])
                for edge in edges:
                    if edge["source"] == topic_id:
                        related.append({"id": edge["target"], "name": "", "course": ""})
                    elif edge["target"] == topic_id:
                        related.append({"id": edge["source"], "name": "", "course": ""})

                # 补充详细信息
                for r in related:
                    rdep = teaching_rules._dependencies.get(r["id"])
                    if rdep:
                        r["name"] = rdep.topic_name
                        r["course"] = rdep.course
            except ImportError:
                pass

            # 补充从教学规则找到的关联知识点
            if dep.course == course:
                # 同课程中exam_weight较高的知识点
                for other_id, other_dep in teaching_rules._dependencies.items():
                    if other_dep.course == course and other_id != topic_id:
                        if other_dep.exam_weight >= 0.15:
                            if other_id not in [r["id"] for r in related]:
                                related.append({
                                    "id": other_id,
                                    "name": other_dep.topic_name,
                                    "course": other_dep.course,
                                    "exam_weight": other_dep.exam_weight,
                                })

            result["related_topics"] = related

            # 获取跨科目关联
            cross_ids = teaching_rules.get_cross_subject_prerequisites(topic_id)
            cross_details = []
            for cid in cross_ids:
                cdep = teaching_rules._dependencies.get(cid)
                if cdep and cdep.course != dep.course:
                    cross_details.append({
                        "id": cid, "name": cdep.topic_name,
                        "course": cdep.course,
                    })
            result["cross_subject"] = cross_details

        except ImportError:
            logger.info("教学规则引擎未加载，KG扩展跳过")
        except Exception as e:
            logger.warning(f"KG扩展失败: {e}")

        return result

    def _infer_course_from_query(self, query: str) -> str:
        """从查询文本推断课程"""
        # 基于关键词判断课程
        course_keywords = {
            "computer_network": ["TCP", "UDP", "IP", "HTTP", "DNS", "网络", "协议",
                                "握手", "路由", "传输", "以太网", "OSI", "端口"],
            "data_structures": ["链表", "栈", "队列", "树", "图", "排序",
                               "查找", "哈希", "二叉", "算法", "遍历"],
            "computer_organization": ["CPU", "总线", "指令", "存储", "Cache",
                                      "运算", "控制器", "寻址", "内存", "寄存器"],
            "operating_system": ["进程", "线程", "调度", "死锁", "分页",
                                "内存管理", "文件系统", "同步", "互斥", "虚拟"],
        }

        query_lower = query.lower()
        best_course = "computer_network"  # 默认
        best_score = 0

        for course, keywords in course_keywords.items():
            score = sum(1 for kw in keywords if kw.lower() in query_lower)
            if score > best_score:
                best_score = score
                best_course = course

        return best_course


# 全局单例
query_preprocessor = QueryPreprocessor()
sft_query_generator = LLMQueryOptimizer()
react_retriever = ReActRetriever()
