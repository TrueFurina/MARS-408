# ============================================================
# GoMARL 证据冲突消解 — FrugalRAG 证据校验 + 知识一致性
#
# 来源：GoMARL-main 共识机制 + FrugalRAG 检索验证
# 申报书 Table 2-2 第2-3层（✅ 新增改进点）
#
# 功能：
#   1. 知识一致性校验：E5 向量检测 Agent 间语义冲突
#      （替代原有的关键词匹配，升级为语义级检测）
#   2. 证据冲突消解：调用 FrugalRAG 检索外部知识验证冲突
#      （申报书: "调用 FrugalRAG 检索证据验证冲突"）
#   3. 基于证据的冲突修正算法
#      （申报书: "基于证据的冲突消解算法"）
# ============================================================

import logging
import re
import json
from typing import Optional
from dataclasses import dataclass, field

import numpy as np

from db.llm_provider import LLMProvider

logger = logging.getLogger("netlearn.gomarl_conflict")


# ── 1. 知识一致性校验 ──

@dataclass
class Conflict:
    """检测到的冲突"""
    agent_a: str              # Agent A 名称
    agent_b: str              # Agent B 名称
    conflict_type: str        # "semantic" | "factual" | "keyword"
    description: str          # 冲突描述
    claim_a: str              # Agent A 的声明
    claim_b: str              # Agent B 的声明
    evidence: list[dict] = field(default_factory=list)  # FrugalRAG 检索证据
    resolution: str = ""      # 消解结果
    confidence: float = 0.0   # 消修复信度


class ConsistencyChecker:
    """知识一致性校验模块（申报书 Table 2-2 校验层）

    "✅ 新增：调用 FrugalRAG 检索证据验证冲突"

    两级检测：
    1. 语义级：E5 向量余弦相似度，检测语义矛盾
    2. 事实级：预定义矛盾对 + LLM 事实核查
    """

    # 跨 Agent 事实矛盾对：由 _scan_cross_agent 使用，
    # 检测两个 Agent 各自产出正确但互相矛盾的事实声明。
    # 每句独立逗号分割 + 否定词排除，防止互补事实误报。
    _FACTUAL_CONTRADICTIONS = [
        # ── 计算机网络 ──
        {
            "pattern_a": ["面向连接", "连接 oriented", "connection-oriented"],
            "pattern_b": ["无连接", "connectionless", "无连接"],
            "context": "TCP",
            "description": "TCP 是面向连接的，UDP 是无连接的，不能混淆",
        },
        {
            "pattern_a": ["三次握手", "3-way handshake", "三次"],
            "pattern_b": ["四次握手", "4-way handshake", "四次"],
            "context": "TCP连接建立",
            "description": "TCP 建立连接使用三次握手，不是四次",
        },
        {
            "pattern_a": ["四次挥手", "4-way wave", "四次挥手"],
            "pattern_b": ["三次挥手", "三次断开"],
            "context": "TCP连接释放",
            "description": "TCP 释放连接使用四次挥手（半关闭），不是三次",
        },
        {
            "pattern_a": ["数据链路层", "data link layer", "链路层"],
            "pattern_b": ["网络层", "network layer"],
            "context": "设备层级",
            "description": "交换机是数据链路层设备，路由器是网络层设备",
        },
        {
            "pattern_a": ["HTTP(?!S).{0,15}443端口", "443端口.{0,15}HTTP(?!S)"],
            "pattern_b": ["HTTPS.{0,15}80端口", "80端口.{0,15}HTTPS"],
            "context": "HTTP/HTTPS",
            "description": "HTTP 默认 80 端口，HTTPS 默认 443 端口（跨 Agent 端口-协议错配）",
            "denial": ["不是", "而非", "而不是", "并非"],
        },
        {
            "pattern_a": ["FTP控制.{0,15}20端口", "20端口.{0,15}FTP控制"],
            "pattern_b": ["FTP数据.{0,15}21端口", "21端口.{0,15}FTP数据"],
            "context": "FTP",
            "description": "FTP 控制连接端口 21，数据连接端口 20（跨 Agent 端口-功能错配）",
            "denial": ["不是", "而非", "而不是", "并非"],
        },
        {
            "pattern_a": ["53端口", "port 53"],
            "pattern_b": ["80端口", "port 80", "443端口", "port 443"],
            "context": "DNS",
            "description": "DNS 使用 53 端口，默认基于 UDP",
        },
        {
            "pattern_a": ["慢启动", "slow start", "慢开始"],
            "pattern_b": ["拥塞避免", "congestion avoidance"],
            "context": "拥塞控制",
            "description": "慢启动（指数增长）和拥塞避免（线性增长）是TCP拥塞控制的不同阶段",
        },
        {
            "pattern_a": ["A类地址", "A类", "class A"],
            "pattern_b": ["C类地址", "C类", "class C"],
            "context": "IP分类",
            "description": "A类(0-127)和C类(192-223)是不同的IP地址类别",
        },
        # ── 数据结构 ──
        {
            "pattern_a": ["先来先服务", "FCFS", "FIFO"],
            "pattern_b": ["短作业优先", "SJF", "最短作业优先"],
            "context": "调度算法",
            "description": "FCFS 和 SJF 是不同的调度算法，不能混为一谈",
        },
        {
            "pattern_a": ["时间复杂度O(n)", "O(n)"],
            "pattern_b": ["时间复杂度O(log n)", "O(log n)", "O(logn)"],
            "context": "算法复杂度",
            "description": "不同算法的时间复杂度不同，O(n)和O(log n)差异显著",
        },
        {
            "pattern_a": ["二叉树", "binary tree"],
            "pattern_b": ["二叉搜索树", "二叉排序树", "BST"],
            "context": "树结构",
            "description": "二叉搜索树(BST)是二叉树的一种特例，有左<根<右的性质",
        },
        {
            "pattern_a": ["稳定排序", "稳定"],
            "pattern_b": ["不稳定排序", "不稳定"],
            "context": "排序算法",
            "description": "排序算法的稳定性：冒泡/插入/归并稳定；快速/选择/堆不稳定",
        },
        {
            "pattern_a": ["深度优先", "DFS", "depth-first"],
            "pattern_b": ["广度优先", "BFS", "breadth-first"],
            "context": "图遍历",
            "description": "DFS(深度优先)使用栈，BFS(广度优先)使用队列",
        },
        # ── 操作系统 ──
        {
            "pattern_a": ["虚拟内存", "virtual memory", "虚拟存储"],
            "pattern_b": ["物理内存", "physical memory", "实存"],
            "context": "内存管理",
            "description": "虚拟内存和物理内存是不同概念，不能混淆",
        },
        {
            "pattern_a": ["分页", "paging", "页式"],
            "pattern_b": ["分段", "segmentation", "段式"],
            "context": "内存管理",
            "description": "分页和分段是两种不同的内存管理方式",
        },
        {
            "pattern_a": ["信号量", "semaphore", "PV操作"],
            "pattern_b": ["互斥锁", "mutex", "mutual exclusion"],
            "context": "进程同步",
            "description": "信号量(PV操作)和互斥锁是不同的同步机制",
        },
        {
            "pattern_a": ["死锁预防", "prevention"],
            "pattern_b": ["死锁避免", "avoidance", "银行家算法"],
            "context": "死锁",
            "description": "死锁预防和死锁避免是不同的处理策略",
        },
        # ── 计算机组成原理 ──
        {
            "pattern_a": ["原码", "sign-magnitude"],
            "pattern_b": ["补码", "two's complement"],
            "context": "数据表示",
            "description": "原码和补码是有符号数的不同编码方式",
        },
        {
            "pattern_a": ["统一编址", "memory-mapped"],
            "pattern_b": ["独立编址", "port-mapped", "I/O独立编址"],
            "context": "I/O编址",
            "description": "统一编址和独立编址是两种不同的 I/O 编址方式",
        },
    ]

    # 语义相似度阈值
    _SEMANTIC_CONFLICT_THRESHOLD = 0.3  # 低于此值可能存在语义不一致
    _SEMANTIC_SAME_THRESHOLD = 0.85     # 高于此值认为内容相似

    # 事实级错误规则（精确、防误报）
    # 每条规则用「正则窗口」匹配错误断言，并排除含否定/对比说明的句子。
    # 仅保留方向明确的易错点；纯对比型（分页/分段、信号量/互斥锁等）交由语义层处理。
    _FACTUAL_ERROR_RULES = [
        {
            "description": "TCP 建立连接使用三次握手，不是四次握手",
            "error_regex": [r"(建立连接|连接建立|tcp).{0,12}四次握手",
                            r"握手建立.{0,8}四次握手"],
            "denial": ["不是", "而非", "而不是", "并非", "没有", "不能", "不可", "无需"],
            "correct": "三次握手",
        },
        {
            "description": "TCP 释放连接使用四次挥手，不是三次挥手",
            "error_regex": [r"(释放连接|连接释放|断开连接|tcp).{0,12}三次挥手",
                            r"挥手释放.{0,8}三次挥手"],
            "denial": ["不是", "而非", "而不是", "并非", "不能", "不可"],
            "correct": "四次挥手",
        },
        {
            "description": "交换机是数据链路层设备，不是网络层设备",
            "error_regex": [r"交换机.{0,10}(是|位于|属于|在|工作).{0,3}网络层",
                            r"交换机.{0,10}network layer"],
            "denial": ["不是", "而非", "而不是", "并非"],
            "correct": "数据链路层",
        },
        {
            "description": "路由器是网络层设备，不是数据链路层设备",
            "error_regex": [r"路由器.{0,10}(是|位于|属于|在|工作).{0,3}数据链路层",
                            r"路由器.{0,10}data link layer", r"路由器.{0,10}链路层"],
            "denial": ["不是", "而非", "而不是", "并非"],
            "correct": "网络层",
        },
        {
            "description": "HTTP 默认 80 端口，HTTPS 默认 443 端口",
            "error_regex": [r"http(?!s).{0,10}(默认|是|端口|使用|为).{0,3}443",
                            r"https.{0,10}(默认|是|端口|使用|为).{0,3}80"],
            "denial": ["不是", "而非", "而不是"],
            "correct": "HTTP=80 / HTTPS=443",
        },
        {
            "description": "DNS 使用 53 端口（默认 UDP），不是 80/443",
            "error_regex": [r"dns.{0,10}(默认|是|端口|使用|为).{0,3}(80|443)"],
            "denial": ["不是", "而非", "而不是"],
            "correct": "53 端口",
        },
        {
            "description": "UDP 是无连接的，不是面向连接的",
            "error_regex": [r"udp.{0,10}面向连接", r"udp.{0,10}connection.?oriented"],
            "denial": ["不是", "而非", "而不是", "并非"],
            "correct": "无连接",
        },
        {
            "description": "TCP 是面向连接的，不是无连接的",
            "error_regex": [r"tcp.{0,10}无连接", r"tcp.{0,10}connectionless"],
            "denial": ["不是", "而非", "而不是", "并非"],
            "correct": "面向连接",
        },
    ]

    def __init__(self):
        self._llm = LLMProvider()

    def check(
        self,
        agent_results: list[dict],
        agent_embeddings: np.ndarray = None,
    ) -> list[Conflict]:
        """检测 Agent 间的知识冲突（事实错误 + 跨 Agent 矛盾 + 语义分歧）。

        事实级：单 Agent 内精确单句匹配（见 _scan_factual），避免把
        跨 Agent 的互补正确事实误判为矛盾。
        跨 Agent 矛盾：两个 Agent 各自产出正确但互相矛盾的事实声明。
        语义级：E5 向量余弦相似度（跨 Agent）。
        """
        conflicts: list[Conflict] = []
        n = len(agent_results)

        # 1. 事实级错误检测（单 Agent 内，精确低误报）
        for r in agent_results:
            conflicts.extend(
                self._scan_factual(r.get("agent_name", ""), r.get("content", ""))
            )

        # 2. 跨 Agent 矛盾对检测（逗号分割句子，防止互补事实误报）
        for i in range(n):
            for j in range(i + 1, n):
                cross = self._scan_cross_agent(
                    agent_results[i], agent_results[j],
                )
                if cross:
                    conflicts.append(cross)

        # 3. 语义级冲突检测（E5 向量相似度，跨 Agent）
        if agent_embeddings is not None:
            for i in range(n):
                for j in range(i + 1, n):
                    if i >= len(agent_embeddings) or j >= len(agent_embeddings):
                        continue
                    r_a = agent_results[i]
                    r_b = agent_results[j]
                    semantic = self._check_semantic(
                        r_a["agent_name"], r_b["agent_name"],
                        r_a.get("content", ""), r_b.get("content", ""),
                        agent_embeddings[i], agent_embeddings[j],
                    )
                    if semantic:
                        conflicts.append(semantic)

        return conflicts

    @staticmethod
    def _split_sentences_local(text: str) -> list[str]:
        """按中英文句末标点及逗号切分文本为句子（过滤空串）。

        逗号分割可防止 "路由器工作在网络层，交换机工作在数据链路层"
        这类互补正确事实被跨逗号的错误正则窗口误判为矛盾。
        """
        if not text:
            return []
        parts = re.split(r"(?<=[。！？!?；;\n，,])", text)
        return [p.strip() for p in parts if p and p.strip()]

    def _scan_factual(self, agent_name: str, content: str) -> list[Conflict]:
        """事实级错误检测（精确、低误报）。

        仅当某 Agent 的单句内出现「错误断言正则」且不含否定/对比说明时，
        才记为一条事实错误（agent_b=knowledge_base 表示与权威知识不符）。
        方向明确的易错点用正则窗口匹配，避免“交换机/路由器”等互补事实误报。
        """
        if not content:
            return []
        out: list[Conflict] = []
        for rule in self._FACTUAL_ERROR_RULES:
            denial = rule.get("denial", [])
            for sent in self._split_sentences_local(content):
                sl = sent.lower()
                if not any(re.search(rx, sl) for rx in rule["error_regex"]):
                    continue
                # 含否定/对比说明（如“而不是四次握手”）→ 属正确辨析，跳过
                if any(d in sl for d in denial):
                    continue
                out.append(Conflict(
                    agent_a=agent_name,
                    agent_b="knowledge_base",
                    conflict_type="factual",
                    description=rule["description"],
                    claim_a=sent[:200],
                    claim_b=f"正确应为: {rule['correct']}",
                    confidence=0.85,
                ))
                break  # 同一条规则对同一 Agent 至多记一次
        return out

    def _scan_cross_agent(self, r_a: dict, r_b: dict) -> Optional[Conflict]:
        """跨 Agent 矛盾对检测：若 Agent A 的某句包含模式组 A 且 Agent B 的某句
        包含模式组 B，则两条声明的组合构成事实矛盾。

        使用逗号分割的单句匹配 + 否定词排除，与 _scan_factual 的防误报策略一致。
        """
        content_a = r_a.get("content", "")
        content_b = r_b.get("content", "")
        if not content_a or not content_b:
            return None

        sentences_a = self._split_sentences_local(content_a)
        sentences_b = self._split_sentences_local(content_b)

        for pair in self._FACTUAL_CONTRADICTIONS:
            denial = pair.get("denial",
                ["不是", "而非", "而不是", "并非", "不能", "不可"])
            # 检查 Agent A 是否有句子命中 pattern_a
            hit_a = None
            for s in sentences_a:
                sl = s.lower()
                if any(re.search(pa, sl, re.IGNORECASE) for pa in pair["pattern_a"]):
                    if not any(d in sl for d in denial):
                        hit_a = s[:200]
                        break
            if not hit_a:
                continue
            # 检查 Agent B 是否有句子命中 pattern_b
            hit_b = None
            for s in sentences_b:
                sl = s.lower()
                if any(re.search(pb, sl, re.IGNORECASE) for pb in pair["pattern_b"]):
                    if not any(d in sl for d in denial):
                        hit_b = s[:200]
                        break
            if not hit_b:
                continue
            # 两个 Agent 都命中了矛盾对 — 这不是互补事实，而是真矛盾
            return Conflict(
                agent_a=r_a.get("agent_name", ""),
                agent_b=r_b.get("agent_name", ""),
                conflict_type="factual",
                description=f"[跨Agent矛盾] {pair['description']}",
                claim_a=hit_a,
                claim_b=hit_b,
                confidence=0.80,
            )
        return None

    def _check_semantic(self, name_a: str, name_b: str,
                        content_a: str, content_b: str,
                        emb_a: np.ndarray, emb_b: np.ndarray) -> Optional[Conflict]:
        """语义级冲突检测（E5 向量相似度）"""
        # 余弦相似度
        sim = float(np.dot(emb_a, emb_b) / (
            np.linalg.norm(emb_a) * np.linalg.norm(emb_b) + 1e-8
        ))

        # 如果两个 Agent 都有实质内容但相似度很低，可能存在语义冲突
        if (len(content_a) > 100 and len(content_b) > 100 and
                sim < self._SEMANTIC_CONFLICT_THRESHOLD):
            return Conflict(
                agent_a=name_a,
                agent_b=name_b,
                conflict_type="semantic",
                description=f"语义相似度过低({sim:.2f})，可能存在内容矛盾",
                claim_a=content_a[:200] + "...",
                claim_b=content_b[:200] + "...",
                confidence=0.5,
            )

        return None


# ── 2. 证据冲突消解 ──

_CONFLICT_RESOLUTION_PROMPT = """你是多智能体共识系统的「冲突消解器」。

检测到以下 Agent 之间的知识冲突：

冲突描述：{conflict_description}
Agent A ({agent_a}) 的观点：
{claim_a}

Agent B ({agent_b}) 的观点：
{claim_b}

FrugalRAG 检索到的外部知识证据：
{evidence}

请基于证据消解冲突：
1. 判断哪个 Agent 的观点更符合证据
2. 如果两者都有部分正确，给出综合修正
3. 如果证据不足以判断，标记为"需人工审核"

输出格式（JSON）：
{{
    "resolution": "A正确" | "B正确" | "综合修正" | "需人工审核",
    "corrected_content": "修正后的内容（如果是综合修正）",
    "evidence_support": "证据支持说明",
    "confidence": 0.0-1.0
}}"""


class EvidenceConflictResolver:
    """证据冲突消解模块（申报书 Table 2-2 消解层）

    "✅ 新增：基于证据的冲突消解算法"
    "利用 FrugalRAG 检索结果作为外部知识源，对 Agent 之间的知识冲突进行验证与修正"

    流程：
    1. 提取冲突关键词
    2. 调用 FrugalRAG 检索外部知识
    3. LLM 基于证据判断哪个 Agent 正确
    4. 生成修正内容
    """

    def __init__(self):
        self._llm = LLMProvider()
        self._checker = ConsistencyChecker()

    async def resolve(
        self,
        conflicts: list[Conflict],
        course: str = "computer_network",
    ) -> list[Conflict]:
        """消解所有冲突

        Args:
            conflicts: 检测到的冲突列表
            course: 课程（用于 FrugalRAG 检索）

        Returns:
            消解后的冲突列表（含 resolution 和 evidence）
        """
        if not conflicts:
            return []

        resolved = []
        for conflict in conflicts:
            try:
                # 1. 提取冲突关键词作为检索查询
                search_query = self._extract_conflict_keywords(conflict)

                # 2. 调用 FrugalRAG 检索证据
                evidence = await self._retrieve_evidence(search_query, course)
                conflict.evidence = evidence

                # 3. LLM 基于证据消解
                resolution = await self._llm_resolve(conflict, evidence)
                conflict.resolution = resolution.get("resolution", "需人工审核")
                conflict.confidence = resolution.get("confidence", 0.5)

                # 4. 如果需要修正，保存修正内容
                if resolution.get("corrected_content"):
                    conflict.resolution += f"\n\n修正内容：{resolution['corrected_content']}"

                resolved.append(conflict)

            except Exception as e:
                logger.warning(f"冲突消解失败: {conflict.description} - {e}")
                conflict.resolution = "消解失败，需人工审核"
                conflict.confidence = 0.0
                resolved.append(conflict)

        return resolved

    def _extract_conflict_keywords(self, conflict: Conflict) -> str:
        """从冲突中提取检索关键词"""
        # 优先使用冲突描述中的上下文
        desc = conflict.description

        # 提取中文关键词
        keywords = re.findall(r'[\u4e00-\u9fff]+', desc)
        # 提取英文术语
        keywords += re.findall(r'[A-Za-z]{2,}', desc)

        # 加上两个 Agent 声明的关键词
        keywords += re.findall(r'[\u4e00-\u9fff]+', conflict.claim_a)[:5]
        keywords += re.findall(r'[A-Za-z]{2,}', conflict.claim_a)[:5]

        if not keywords:
            return conflict.description

        return " ".join(keywords[:10])  # 取前10个关键词

    async def _retrieve_evidence(self, query: str, course: str) -> list[dict]:
        """调用 FrugalRAG 检索证据"""
        try:
            from engines.frugal_rag import frugal_rag
            chunks = await frugal_rag.retrieve(query, course, top_k=3)
            return [
                {
                    "text": c.get("text", "")[:300],
                    "score": c.get("score", 0),
                    "source": c.get("metadata", {}).get("chapter_name", ""),
                }
                for c in chunks
            ]
        except Exception as e:
            logger.warning(f"证据检索失败: {e}")
            return []

    async def _llm_resolve(self, conflict: Conflict, evidence: list[dict]) -> dict:
        """LLM 基于证据消解冲突"""
        # 格式化证据
        if evidence:
            evidence_text = "\n".join(
                f"[{i+1}] (相关度: {e['score']:.2f}) {e['text']}"
                for i, e in enumerate(evidence)
            )
        else:
            evidence_text = "（未检索到相关证据）"

        prompt = _CONFLICT_RESOLUTION_PROMPT.format(
            conflict_description=conflict.description,
            agent_a=conflict.agent_a,
            agent_b=conflict.agent_b,
            claim_a=conflict.claim_a[:500],
            claim_b=conflict.claim_b[:500],
            evidence=evidence_text,
        )

        try:
            reply = await self._llm.text_completion(
                "你是多智能体冲突消解专家，擅长基于证据判断事实对错。",
                prompt,
                temperature=0.3,
                max_tokens=500,
            )

            # 提取 JSON
            m = re.search(r'\{.*\}', reply, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception as e:
            logger.warning(f"LLM 冲突消解失败: {e}")

        return {
            "resolution": "需人工审核",
            "corrected_content": "",
            "evidence_support": "LLM 消解失败",
            "confidence": 0.3,
        }


# ── 3. 完整的冲突检测+消解流程 ──

class ConflictResolutionEngine:
    """完整的冲突检测与消解引擎

    整合 ConsistencyChecker + EvidenceConflictResolver
    """

    def __init__(self):
        self.checker = ConsistencyChecker()
        self.resolver = EvidenceConflictResolver()

    async def check_and_resolve(
        self,
        agent_results: list[dict],
        course: str = "computer_network",
        agent_embeddings: np.ndarray = None,
    ) -> dict:
        """
        检测并消解 Agent 间冲突

        Returns:
        {
            "total_conflicts": int,
            "resolved": int,
            "unresolved": int,
            "conflicts": list[dict],    # 冲突详情
            "overall_consistency": float,  # 整体一致性 0-1
        }
        """
        # 1. 检测冲突
        conflicts = self.checker.check(agent_results, agent_embeddings)

        if not conflicts:
            return {
                "total_conflicts": 0,
                "resolved": 0,
                "unresolved": 0,
                "conflicts": [],
                "overall_consistency": 1.0,
            }

        # 2. 消解冲突
        resolved_conflicts = await self.resolver.resolve(conflicts, course)

        # 3. 统计
        resolved_count = sum(1 for c in resolved_conflicts
                            if c.resolution and "需人工审核" not in c.resolution)
        unresolved = len(resolved_conflicts) - resolved_count

        # 4. 计算整体一致性
        n_agents = len(agent_results)
        max_possible = n_agents * (n_agents - 1) / 2
        consistency = 1.0 - (len(resolved_conflicts) / max(max_possible, 1))

        return {
            "total_conflicts": len(resolved_conflicts),
            "resolved": resolved_count,
            "unresolved": unresolved,
            "conflicts": [
                {
                    "agent_a": c.agent_a,
                    "agent_b": c.agent_b,
                    "type": c.conflict_type,
                    "description": c.description,
                    "resolution": c.resolution,
                    "confidence": c.confidence,
                    "evidence": [
                        {"text": e.get("text", ""), "score": float(e.get("score", 0) or 0), "source": e.get("source", "")}
                        for e in c.evidence
                    ],
                    "evidence_count": len(c.evidence),
                }
                for c in resolved_conflicts
            ],
            "overall_consistency": consistency,
        }


# 全局单例
consistency_checker = ConsistencyChecker()
conflict_resolver = EvidenceConflictResolver()
conflict_engine = ConflictResolutionEngine()
