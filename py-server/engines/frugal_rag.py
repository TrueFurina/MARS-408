# ============================================================
# FrugalRAG — 节俭检索增强生成引擎
# E5 向量检索 + 余弦阈值过滤 + BM25 融合排序
# ============================================================

import asyncio
import hashlib
import logging
import os
import re
import time
from typing import Optional

import numpy as np

from config import get_frugal_config
from db.milvus_client import vector_db
from db.redis_client import redis_client
from db.embedder import embed_text, embed_batch
from db.local_cache import LocalLRUCache

logger = logging.getLogger("netlearn.frugal_rag")


# ── Reranker 重排模型（多路召回后的精排） ──

class Reranker:
    """Cross-encoder 重排模型，对 BM25+向量 的候选结果做精排"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        self._model = None
        self._model_name = model_name

    def _load(self):
        if self._model is not None or getattr(self, "_disabled", False):
            return
        try:
            # 离线优先：本机无外网，禁止 HuggingFace 下载。
            # 否则每次检索都会因连接超时反复重试约 90s，并同步阻塞事件循环，
            # 导致 LangGraph 协作流（retriever→rerank）卡死、整个后端无响应。
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self._model_name)
            logger.info(f"Reranker 模型加载: {self._model_name}")
        except Exception as e:
            self._disabled = True  # 永久禁用，避免后续请求重复尝试下载
            logger.warning(f"Reranker 加载失败（降级为无重排，已禁用）: {e}")

    def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """对候选列表做 Cross-encoder 重排"""
        if not candidates:
            return candidates
        self._load()
        if self._model is None:
            return candidates[:top_k]

        pairs = [(query, c.get("text", "")) for c in candidates]
        try:
            scores = self._model.predict(pairs)
            for i, c in enumerate(candidates):
                c["_reranker_score"] = float(scores[i])
            candidates.sort(key=lambda x: x.get("_reranker_score", 0), reverse=True)
            logger.info(f"Reranker 重排: {len(candidates)}→{top_k}")
        except Exception as e:
            logger.warning(f"Reranker 预测失败: {e}")
        return candidates[:top_k]


_reranker = Reranker()


# ── BM25 关键词检索 ──

class BM25Scorer:
    """轻量 BM25 实现，用于关键词级检索"""

    def __init__(self):
        self.k1 = 1.5
        self.b = 0.75

    def score(self, query: str, documents: list[str]) -> list[float]:
        """对一组文档计算 BM25 分数"""
        query_terms = self._tokenize(query)
        doc_tokens = [self._tokenize(d) for d in documents]
        total_docs = len(documents)

        # 计算 DF
        df = {}
        for terms in doc_tokens:
            for term in set(terms):
                df[term] = df.get(term, 0) + 1

        # 平均文档长度
        avgdl = np.mean([len(t) for t in doc_tokens]) if doc_tokens else 1

        scores = []
        for doc_terms in doc_tokens:
            score = 0.0
            doc_len = len(doc_terms)
            term_freq = {}
            for term in doc_terms:
                term_freq[term] = term_freq.get(term, 0) + 1

            for term in query_terms:
                if term not in term_freq:
                    continue
                tf = term_freq[term]
                df_t = df.get(term, 0)
                idf = np.log((total_docs - df_t + 0.5) / (df_t + 0.5) + 1.0)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / avgdl)
                score += idf * numerator / denominator
            scores.append(score)

        # 归一化
        max_score = max(scores) if scores else 1.0
        return [s / max_score if max_score > 0 else 0.0 for s in scores]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """简单分词（中文按字 + 英文按词）"""
        # 英文分词
        words = re.findall(r'[a-zA-Z0-9_]+', text.lower())
        # 中文按字
        chinese = re.findall(r'[\u4e00-\u9fff]', text)
        return words + chinese


_bm25 = BM25Scorer()


# ── 模板/脚手架 chunk 降权 ──
# 知识库中存在一批"章节级模板" chunk（如"本知识点属于…定义、基本概念和核心要素…"
# "本节学习目标" "本章小结"），它们与实质内容共享同一 subject 标签，会在融合排序时
# 挤占真正含事实的 chunk。两类需降权：
#  (A) 导论/提纲式占位（"本知识点属于…"/"计算机网络是互连的…"等，不含可检索事实 token）；
#  (B) 近重复"助学标签"包裹（【考点速记】/【易错辨析】/【关键术语】/【典型例题】等前缀把同一内容复制多份，
#       造成 BM25 词面蹭高、挤出实质 chunk）。
# 经核验：100% 的此类 chunk 都包裹了某条干净 chunk 的正文（子串包含），降权不会丢失唯一事实。
# 纯规则、不依赖模型，E5 缺失的 BM25-only 降级路径同样受益。
_BOILERPLATE_PAT = re.compile(
    r"本知识点属于|本节学习目标|本章小结|本章学习要求|知识点总结|基本概念(和|与)核心"
    r"|^计算机网络是互连的|^OSI七层模型|^分组交换采用存储转发|^物理层的主要任务|^信道复用技术"
    r"|^【(考点速记|易错辨析|关键术语|典型例题|本章导学|知识拓展|真题精讲|速记口诀|避坑指南)】"
)


def _boilerplate_factor(text: str) -> float:
    """模板/近重复包裹 chunk 惩罚系数：命中 → 0.4，否则 1.0。

    仅在文本明显是"提纲式占位"或"助学标签包裹的近重复"而非"含事实定义"时降权，避免误伤实质内容。
    """
    if text and _BOILERPLATE_PAT.search(text):
        return 0.4
    return 1.0


# ── FrugalRAG 主类 ──

class FrugalRAG:
    """FrugalRAG Lite 检索引擎"""

    def __init__(self):
        config = get_frugal_config()
        self.top_k = config.get("top_k", 5)
        self.cosine_threshold = config.get("cosine_threshold", 0.65)
        self.bm25_weight = config.get("bm25_weight", 0.3)
        self.vector_weight = config.get("vector_weight", 0.7)
        self.max_rewrite_rounds = config.get("max_rewrite_rounds", 2)

        # 缓存 key 前缀
        self._cache_prefix = "frugalrag:"

        # 进程内检索结果缓存（Redis 不可用时的本地兜底）。
        # 默认不启用 Redis（开发/演示/单机路径），若不补本地缓存，
        # 每次重复查询都会重跑整条管线（E5+向量+BM25+融合+重排）。
        # 容量/ TTL 可通过环境变量覆盖；语义与 Redis 缓存一致
        # （仅缓存 query+course 且 student_profile 为空的结果）。
        _max = int(os.environ.get("FRUGAL_CACHE_MAX", "1024"))
        _ttl = float(os.environ.get("FRUGAL_CACHE_TTL", "1800"))
        self._local_cache = LocalLRUCache(max_size=_max, ttl=_ttl)

    # ── 课程 subject 映射 ──

    # 种子数据中 subject 字段 → 课程名的映射
    _COURSE_SUBJECTS = {
        "computer_network": [
            "overview", "architecture", "switching", "physical",
            "datalink", "csma", "ethernet", "vlan", "network",
            "ip", "arp", "routing", "transport", "tcp", "udp",
            "application", "dns", "http", "ftp", "dhcp",
            "security", "ssl", "firewall", "attack",
            "crypto", "hash", "signature", "certificate",
            "ddos", "web_attack", "ids", "vpn",
        ],
        "data_structures": [
            "ds_linear", "ds_stack", "ds_queue",
            "ds_string", "ds_tree", "ds_graph",
            "ds_search", "ds_sort",
        ],
        "computer_organization": [
            "co_overview", "co_data", "co_memory",
            "co_isa", "co_cpu", "co_bus", "co_io",
        ],
        "operating_system": [
            "os_overview", "os_process", "os_memory",
            "os_file", "os_io",
        ],
    }

    def _get_course_subjects(self, course: str) -> list[str]:
        """获取课程对应的 subject 列表"""
        return self._COURSE_SUBJECTS.get(course, [])

    # ── 公共接口 ──

    async def retrieve(
        self,
        query: str,
        course: str = "computer_network",
        top_k: Optional[int] = None,
        enable_cache: bool = True,
        student_profile: Optional[dict] = None,
        use_kg_enhance: bool = True,
    ) -> list[dict]:
        """
        核心检索接口
        query: 用户查询文本
        course: 课程标识
        top_k: 返回文档数，默认配置值
        enable_cache: 是否使用 Redis 缓存
        student_profile: 学生画像（报告§3.4.2个性化排序），可选
        use_kg_enhance: 是否使用知识图谱增强检索

        返回: [{id, text, score, metadata, _rerank_adjustment}, ...]
        """
        k = top_k or self.top_k
        start_time = time.time()

        # 知识图谱增强：用知识图谱中的相关实体扩展查询
        enhanced_query = query
        if use_kg_enhance:
            try:
                from agents.knowledge_graph import search_kg_entities
                related = search_kg_entities(query, subject=course)
                if related.get("entities"):
                    names = [e["name"] for e in related["entities"][:5]]
                    enhanced_query = f"{query} {' '.join(names)}"
                    logger.info(f"KG 增强查询: {query} → {enhanced_query[:80]}")
            except Exception as e:
                logger.debug(f"KG 增强跳过: {e}")

        # 缓存检查（优先 Redis；Redis 不可用/未命中时，回退进程内本地缓存）
        cache_key = self._cache_key(query, course)
        cached = None
        cache_src = ""
        if enable_cache and redis_client.is_enabled:
            cached = redis_client.get_json(cache_key)
            if cached is not None:
                cache_src = "redis"
        if cached is None and enable_cache and student_profile is None:
            cached = self._local_cache.get(cache_key)
            if cached is not None:
                cache_src = "local"
        if cached is not None:
            logger.info(
                f"FrugalRAG 命中缓存[{cache_src}]: query_len={len(query)}, "
                f"命中 {len(cached)} chunks"
            )
            return cached

        # 1. E5 向量化（放到线程池，避免阻塞事件循环）
        try:
            query_vec = await asyncio.to_thread(embed_text, query)
        except Exception as e:
            # ═══ BM25-only 降级守卫（2026-07-12 加固）═══
            # E5 离线/模型缺失时绝不静默归零：退化为纯 BM25 词频检索
            # （不依赖任何模型，只吃原始文本），保住 FrugalRAG 双路语义，
            # 保证"基于课程资料作答"在离线环境仍能命中知识片段。
            logger.error(f"E5 embedding 失败: {e}")
            logger.warning("E5 不可用，降级为 BM25-only 检索（纯词频，不依赖模型）")
            try:
                docs, _total = await asyncio.to_thread(
                    vector_db.get_all_with_texts, "netlearn_kb", 0, 100000
                )
                texts = [d["content"] for d in docs]
                bm25_scores = await asyncio.to_thread(_bm25.score, query, texts)
                ranked = sorted(
                    zip(docs, bm25_scores), key=lambda x: x[1], reverse=True
                )
                fallback = []
                for d, s in ranked[:k]:
                    if s > 0:
                        fallback.append({
                            "id": d["id"],
                            "text": d["content"],
                            "score": float(s) * _boilerplate_factor(d.get("content", "")),
                            "metadata": d["metadata"],
                            "_bm25_score": float(s),
                            "_degraded": True,
                        })
                if fallback:
                    logger.info(
                        f"BM25-only 降级检索命中 {len(fallback)} chunks (top_k={k})"
                    )
                    return fallback
                logger.warning("BM25-only 降级检索无命中")
            except Exception as e2:
                logger.error(f"BM25 降级检索也失败: {e2}")
            return []

        # 2. 向量检索：放入线程池避免 InMemoryVectorStore 全量扫描阻塞事件循环
        import functools as _ft
        candidates = await asyncio.to_thread(
            _ft.partial(
                vector_db.search,
                collection_name="netlearn_kb",
                query_vector=query_vec,
                top_k=k * 6,
            )
        )
        # 软性课程过滤：优先保留命中本课程 subject 的片段；
        # 但若过滤后为空（如英文/歧义查询的最近片段属于其它课程），
        # 则回退到全局 top-k，绝不因过滤而返回 0 结果。
        course_subjects = self._get_course_subjects(course)
        if course_subjects:
            subject_matched = [c for c in candidates if
                c.get("metadata", {}).get("subject", "") in course_subjects
                or c.get("metadata", {}).get("course", "") == course]
            if subject_matched:
                candidates = subject_matched

        if not candidates:
            logger.info(f"FrugalRAG 无检索结果: course={course}, query_len={len(query)}")
            return []

        # 3. 余弦相似度阈值过滤
        filtered = [c for c in candidates if c.get("score", 0) >= self.cosine_threshold]
        if not filtered:
            # 阈值太严，放宽到 top-k 分数
            filtered = candidates[:k]

        # 4. BM25 关键词匹配（P3：放线程池，避免纯 Python 双重循环阻塞事件循环）
        doc_texts = [c.get("text", "") for c in filtered]
        bm25_scores = await asyncio.to_thread(_bm25.score, query, doc_texts)

        # 5. 加权融合排序（含模板/脚手架 chunk 降权）
        for i, chunk in enumerate(filtered):
            vs = chunk.get("score", 0)
            bs = bm25_scores[i]
            chunk["_vector_score"] = vs
            chunk["_bm25_score"] = bs
            chunk["score"] = (
                self.vector_weight * vs + self.bm25_weight * bs
            ) * _boilerplate_factor(chunk.get("text", ""))

        filtered.sort(key=lambda x: x["score"], reverse=True)

        # 6. 个性化重排（报告§3.4.2）
        if student_profile:
            filtered = self._personalized_rerank(filtered, course, student_profile)

        result = filtered[:k]

        # 7. Reranker 精排（多路召回后的 Cross-encoder 重排）
        if result:
            result = _reranker.rerank(query, result, top_k=k)

        # 写入缓存（无 profile 时才缓存，避免画像个性化结果污染通用缓存）
        # Redis 可用 → 写入 Redis；否则写入进程内本地缓存兜底。
        if enable_cache and not student_profile:
            if redis_client.is_enabled:
                redis_client.set_json(cache_key, result, ttl=1800)
            else:
                self._local_cache.set(cache_key, result)

        elapsed = (time.time() - start_time) * 1000
        logger.info(
            f"FrugalRAG 检索完成: {len(result)}/{len(candidates)} chunks, "
            f"top1_score={result[0]['score']:.3f}, {elapsed:.0f}ms"
        )
        return result

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量向量化文档（用于写入 Milvus）"""
        return embed_batch(texts)

    def embed_query(self, query: str) -> list[float]:
        """向量化查询文本"""
        return embed_text(query)

    def _personalized_rerank(
        self,
        chunks: list[dict],
        course: str,
        student_profile: dict,
    ) -> list[dict]:
        """个性化检索重排（报告§3.4.2）

        画像因子 → 排序调整：
        1. weak_topics: 薄弱知识点 → +0.15（优先看薄弱内容）
        2. mastered_topics: 已掌握知识点 → -0.10（降低已掌握内容）
        3. exam_weight: 高考查权重 → +0.10×weight（真题常考优先）
        4. review_stage: 复习阶段→难度匹配 → 基础阶段偏好basic, 强化偏好medium/advanced

        重排逻辑:
        - 找到 chunk 对应的 teaching_rules topic_id
        - 根据画像因子叠加调整分数
        - 重新排序
        """
        try:
            from engines.teaching_rules import teaching_rules
        except ImportError:
            logger.warning("teaching_rules 未导入，跳过个性化重排")
            return chunks

        weak_topics = set(student_profile.get("weak_topics", []))
        mastered_topics = set(student_profile.get("mastered_topics", []))
        review_stage = student_profile.get("review_stage", "basic")
        target_score = student_profile.get("target_score", 100)

        # 阶段→偏好难度映射
        stage_difficulty_map = {
            "basic": {"basic": 0.05, "medium": 0.02, "advanced": -0.02, "comprehensive": -0.03},
            "strengthen": {"basic": -0.02, "medium": 0.03, "advanced": 0.05, "comprehensive": -0.01},
            "comprehensive": {"basic": -0.03, "medium": 0.02, "advanced": 0.04, "comprehensive": 0.06},
            "mock": {"basic": -0.04, "medium": -0.01, "advanced": 0.03, "comprehensive": 0.07},
        }
        difficulty_adjust = stage_difficulty_map.get(review_stage, {})

        for chunk in chunks:
            original_score = chunk["score"]
            adjustment = 0.0
            reasons = []

            # 从 chunk metadata 提取知识点信息
            text = chunk.get("text", "")
            metadata = chunk.get("metadata", {})

            # 尝试匹配 teaching_rules 中的知识点
            topic_id = self._match_chunk_to_topic(text, metadata, course)

            if topic_id:
                dep = teaching_rules._dependencies.get(topic_id)

                if dep:
                    # 1. 薄弱知识点加成
                    if topic_id in weak_topics or dep.topic_name in weak_topics:
                        adjustment += 0.15
                        reasons.append("weak_topic_boost")

                    # 2. 已掌握知识点减权
                    if topic_id in mastered_topics or dep.topic_name in mastered_topics:
                        adjustment -= 0.10
                        reasons.append("mastered_topic_reduce")

                    # 3. 考查权重加成（exam_weight * 系数）
                    if dep.exam_weight > 0:
                        adjustment += dep.exam_weight * 0.10
                        reasons.append(f"exam_weight({dep.exam_weight:.2f})")

                    # 4. 难度匹配复习阶段
                    diff_adj = difficulty_adjust.get(dep.difficulty, 0)
                    if diff_adj:
                        adjustment += diff_adj
                        reasons.append(f"difficulty_match({dep.difficulty})")

                    # 5. 高目标分数 → advanced/comprehensive 微增
                    if target_score >= 120 and dep.difficulty in ("advanced", "comprehensive"):
                        adjustment += 0.02
                        reasons.append("high_target_boost")

            # 应用调整
            chunk["score"] = original_score + adjustment
            chunk["_rerank_adjustment"] = adjustment
            chunk["_rerank_reasons"] = reasons

        # 重新排序
        chunks.sort(key=lambda x: x["score"], reverse=True)

        reranked_count = sum(1 for c in chunks if c.get("_rerank_adjustment", 0) != 0)
        logger.info(
            f"个性化重排: {reranked_count}/{len(chunks)} chunks 受画像影响, "
            f"stage={review_stage}, weak={len(weak_topics)}, mastered={len(mastered_topics)}"
        )

        return chunks

    def _match_chunk_to_topic(
        self,
        text: str,
        metadata: dict,
        course: str,
    ) -> Optional[str]:
        """将检索结果 chunk 匹配到 teaching_rules 知识点

        匹配策略:
        1. metadata.topic_id（精确）
        2. metadata.chapter_name → topic name 模糊匹配
        3. text 关键词 → topic name 关键词匹配
        """
        try:
            from engines.teaching_rules import teaching_rules
        except ImportError:
            return None

        # 策略1: metadata 直接有 topic_id 或 subject（种子数据用 subject 字段）
        topic_id = metadata.get("topic_id") or metadata.get("subject")
        if topic_id and topic_id in teaching_rules._dependencies:
            return topic_id

        # 策略2: chapter 或 chapter_name 匹配 topic_name
        chapter = metadata.get("chapter", "") or metadata.get("chapter_name", "")
        if chapter:
            for tid, dep in teaching_rules._dependencies.items():
                if dep.course == course and chapter in dep.topic_name:
                    return tid
                # 反向匹配（topic_name 在 chapter 中）
                if dep.topic_name in chapter:
                    return tid

        # 策略3: text 关键词模糊匹配
        text_lower = text.lower()
        best_match = None
        best_score = 0

        for tid, dep in teaching_rules._dependencies.items():
            if dep.course != course:
                continue
            # 计算关键词命中数
            keywords = dep.topic_name.split()
            hits = sum(1 for kw in keywords if kw in text_lower)
            score = hits / max(len(keywords), 1)
            if score > best_score and score >= 0.5:
                best_score = score
                best_match = tid

        return best_match

    def _cache_key(self, query: str, course: str) -> str:
        """生成缓存键"""
        h = hashlib.sha256(f"{course}:{query}".encode()).hexdigest()[:12]
        return f"{self._cache_prefix}{h}"

    def clear_cache(self) -> None:
        """清空检索缓存（知识库导入/变更后调用，避免服务陈旧结果）。

        同时清空进程内本地缓存；若 Redis 可用则批量删除 frugalrag:* 键。
        """
        self._local_cache.clear()
        if redis_client.is_enabled:
            try:
                keys = redis_client._client.keys(f"{self._cache_prefix}*")
                if keys:
                    redis_client._client.delete(*keys)
            except Exception as e:  # noqa: BLE001
                logger.warning("清空 Redis 检索缓存失败（非阻塞）: %s", e)
        logger.info("FrugalRAG 检索缓存已清空")


# ── 检索结果格式化工具 ──

def format_retrieval_for_llm(chunks: list[dict], max_chars: int = 2000) -> str:
    """将检索结果格式化为 LLM context 文本"""
    if not chunks:
        return "（未检索到相关知识）"

    lines = ["【参考知识库】"]
    total_chars = 0

    for i, chunk in enumerate(chunks):
        text = chunk.get("text", "")
        source = chunk.get("metadata", {}).get("chapter_name", "未知")
        score = chunk.get("score", 0)

        prefix = f"\n### 参考 {i+1} (相关度: {score:.2f}, 来源: {source})\n"
        content = f"{prefix}{text}\n"

        if total_chars + len(content) > max_chars:
            content = f"{prefix}{text[:max_chars - total_chars - len(prefix) - 20]}...\n"
            lines.append(content)
            break

        lines.append(content)
        total_chars += len(content)

    return "".join(lines)


# 全局单例
frugal_rag = FrugalRAG()
