# ============================================================
# 教学业务规则引擎 — 408考研场景化调度约束
#
# 报告§3.3.3改进点:
#   1. 408知识点依赖关系规则（前置→后续）
#   2. 考查权重规则（各章节/知识点在408真题中的出现频率）
#   3. 复习顺序规则（基础→强化→综合→模考）
#   4. Agent调度适配规则（不同教学角色对应不同知识点范围）
#
# 用途：嵌入GoMARL协调智能体，在任务拆分/分配/调度阶段
#       校验教学逻辑合理性，限制违背408业务规律的调度行为
# ============================================================

import logging
from dataclasses import dataclass, field
from typing import Optional

from config import load_config

logger = logging.getLogger("netlearn.teaching_rules")


# ── 数据结构 ──

@dataclass
class TopicDependency:
    """知识点前置依赖关系"""
    topic_id: str          # 知识点ID（与KG节点对应）
    topic_name: str        # 知识点名称
    course: str            # 所属课程
    prerequisites: list[str] = field(default_factory=list)  # 前置知识点ID列表
    exam_weight: float = 0.0  # 考查权重(0-1)，真题出现频率
    difficulty: str = "medium"  # 难度: basic | medium | advanced | comprehensive


@dataclass
class ScheduleValidation:
    """调度校验结果"""
    is_valid: bool
    violations: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    adjusted_order: list[str] = field(default_factory=list)  # 排序后的任务顺序


@dataclass
class AgentTopicAffinity:
    """Agent与知识点范围的适配关系"""
    agent_name: str
    preferred_courses: list[str] = field(default_factory=list)  # 偏好课程
    preferred_difficulty: list[str] = field(default_factory=list)  # 偏好难度
    topic_keywords: list[str] = field(default_factory=list)  # 专属关键词


class TeachingRuleEngine:
    """408考研教学业务规则引擎

    核心功能：
    1. validate_schedule — 校验调度顺序是否符合教学逻辑
    2. get_prerequisites — 获取知识点前置依赖
    3. get_exam_weight — 获取考查权重
    4. suggest_agent_assignment — 建议Agent分配方案
    5. prioritize_by_profile — 基于画像调整优先级
    """

    def __init__(self):
        self._dependencies: dict[str, TopicDependency] = {}
        self._agent_affinities: dict[str, AgentTopicAffinity] = {}
        self._review_order = ["basic", "medium", "advanced", "comprehensive"]

        self._build_408_dependencies()
        self._build_agent_affinities()

    # ── 408知识点依赖关系 ──

    def _build_408_dependencies(self):
        """构建408四科知识点依赖+考查权重"""

        # ── 计算机网络 ──
        cn_deps = [
            TopicDependency("overview", "计算机网络概述", "computer_network",
                          prerequisites=[], exam_weight=0.08, difficulty="basic"),
            TopicDependency("architecture", "体系结构", "computer_network",
                          prerequisites=["overview"], exam_weight=0.12, difficulty="medium"),
            TopicDependency("switching", "分组交换", "computer_network",
                          prerequisites=["overview"], exam_weight=0.05, difficulty="basic"),
            TopicDependency("physical", "物理层", "computer_network",
                          prerequisites=["overview"], exam_weight=0.06, difficulty="basic"),
            TopicDependency("datalink", "数据链路层", "computer_network",
                          prerequisites=["physical"], exam_weight=0.15, difficulty="medium"),
            TopicDependency("csma", "CSMA/CD", "computer_network",
                          prerequisites=["datalink"], exam_weight=0.08, difficulty="medium"),
            TopicDependency("ethernet", "以太网", "computer_network",
                          prerequisites=["datalink"], exam_weight=0.10, difficulty="medium"),
            TopicDependency("vlan", "VLAN", "computer_network",
                          prerequisites=["ethernet"], exam_weight=0.04, difficulty="advanced"),
            TopicDependency("network", "网络层", "computer_network",
                          prerequisites=["datalink"], exam_weight=0.18, difficulty="medium"),
            TopicDependency("ip", "IP协议", "computer_network",
                          prerequisites=["network"], exam_weight=0.12, difficulty="advanced"),
            TopicDependency("arp", "ARP", "computer_network",
                          prerequisites=["network"], exam_weight=0.06, difficulty="medium"),
            TopicDependency("routing", "路由选择", "computer_network",
                          prerequisites=["network"], exam_weight=0.10, difficulty="advanced"),
            TopicDependency("transport", "运输层", "computer_network",
                          prerequisites=["network"], exam_weight=0.20, difficulty="medium"),
            TopicDependency("tcp", "TCP协议", "computer_network",
                          prerequisites=["transport"], exam_weight=0.18, difficulty="advanced"),
            TopicDependency("udp", "UDP协议", "computer_network",
                          prerequisites=["transport"], exam_weight=0.08, difficulty="medium"),
            TopicDependency("app", "应用层", "computer_network",
                          prerequisites=["transport"], exam_weight=0.10, difficulty="medium"),
            TopicDependency("dns", "DNS", "computer_network",
                          prerequisites=["app"], exam_weight=0.05, difficulty="basic"),
            TopicDependency("http", "HTTP", "computer_network",
                          prerequisites=["app"], exam_weight=0.08, difficulty="medium"),
            TopicDependency("security", "网络安全", "computer_network",
                          prerequisites=["app"], exam_weight=0.10, difficulty="advanced"),
            TopicDependency("tls", "SSL/TLS", "computer_network",
                          prerequisites=["security"], exam_weight=0.06, difficulty="advanced"),
            TopicDependency("firewall", "防火墙", "computer_network",
                          prerequisites=["security"], exam_weight=0.04, difficulty="medium"),
            # ── 新增强度：基于导入的PPT课件内容 ──
            # 数据链路层深度
            TopicDependency("csma_ca", "CSMA/CA", "computer_network",
                          prerequisites=["csma"], exam_weight=0.04, difficulty="advanced"),
            TopicDependency("wlan", "无线局域网802.11", "computer_network",
                          prerequisites=["csma_ca"], exam_weight=0.05, difficulty="advanced"),
            TopicDependency("ppp", "PPP协议", "computer_network",
                          prerequisites=["datalink"], exam_weight=0.04, difficulty="medium"),
            TopicDependency("bridge", "网桥", "computer_network",
                          prerequisites=["ethernet"], exam_weight=0.04, difficulty="medium"),
            TopicDependency("stp", "生成树协议", "computer_network",
                          prerequisites=["bridge"], exam_weight=0.03, difficulty="advanced"),
            TopicDependency("switch", "以太网交换机", "computer_network",
                          prerequisites=["bridge"], exam_weight=0.06, difficulty="medium"),
            # 网络层深度
            TopicDependency("icmp", "ICMP", "computer_network",
                          prerequisites=["network"], exam_weight=0.04, difficulty="medium"),
            TopicDependency("rip", "RIP协议", "computer_network",
                          prerequisites=["routing"], exam_weight=0.06, difficulty="medium"),
            TopicDependency("ospf", "OSPF协议", "computer_network",
                          prerequisites=["routing"], exam_weight=0.08, difficulty="advanced"),
            TopicDependency("bgp", "BGP协议", "computer_network",
                          prerequisites=["routing"], exam_weight=0.06, difficulty="advanced"),
            TopicDependency("nat", "NAT", "computer_network",
                          prerequisites=["ip"], exam_weight=0.05, difficulty="medium"),
            TopicDependency("vpn", "VPN", "computer_network",
                          prerequisites=["network"], exam_weight=0.03, difficulty="medium"),
            TopicDependency("ipv6", "IPv6", "computer_network",
                          prerequisites=["ip"], exam_weight=0.08, difficulty="advanced"),
            TopicDependency("sdn", "SDN", "computer_network",
                          prerequisites=["network"], exam_weight=0.04, difficulty="advanced"),
            TopicDependency("mpls", "MPLS", "computer_network",
                          prerequisites=["network"], exam_weight=0.03, difficulty="advanced"),
            # 运输层深度
            TopicDependency("tcp_reliable", "TCP可靠传输", "computer_network",
                          prerequisites=["tcp"], exam_weight=0.10, difficulty="advanced"),
            TopicDependency("tcp_retransmit", "TCP重传机制", "computer_network",
                          prerequisites=["tcp_reliable"], exam_weight=0.08, difficulty="advanced"),
            TopicDependency("tcp_flow", "TCP流量控制", "computer_network",
                          prerequisites=["tcp"], exam_weight=0.08, difficulty="advanced"),
            TopicDependency("tcp_congestion", "TCP拥塞控制", "computer_network",
                          prerequisites=["tcp_flow"], exam_weight=0.15, difficulty="comprehensive"),
            TopicDependency("tcp_handshake", "TCP连接管理", "computer_network",
                          prerequisites=["tcp"], exam_weight=0.10, difficulty="medium"),
            # 应用层深度
            TopicDependency("www", "WWW", "computer_network",
                          prerequisites=["app"], exam_weight=0.04, difficulty="basic"),
            TopicDependency("email", "电子邮件", "computer_network",
                          prerequisites=["app"], exam_weight=0.05, difficulty="medium"),
            TopicDependency("ftp", "FTP", "computer_network",
                          prerequisites=["app"], exam_weight=0.04, difficulty="basic"),
            TopicDependency("dhcp", "DHCP", "computer_network",
                          prerequisites=["app"], exam_weight=0.04, difficulty="medium"),
            TopicDependency("p2p", "P2P", "computer_network",
                          prerequisites=["app"], exam_weight=0.03, difficulty="medium"),
            # 网络安全深度
            TopicDependency("crypto", "密码学", "computer_network",
                          prerequisites=["security"], exam_weight=0.06, difficulty="medium"),
            TopicDependency("digi_sig", "数字签名", "computer_network",
                          prerequisites=["crypto"], exam_weight=0.04, difficulty="advanced"),
            TopicDependency("ipsec", "IPsec", "computer_network",
                          prerequisites=["security"], exam_weight=0.04, difficulty="advanced"),
            TopicDependency("ids", "入侵检测", "computer_network",
                          prerequisites=["firewall"], exam_weight=0.03, difficulty="medium"),
            # 数据结构深度（基于导入的教材内容）
            TopicDependency("b_tree", "B树", "data_structures",
                          prerequisites=["bst"], exam_weight=0.08, difficulty="comprehensive"),
            TopicDependency("heap", "堆", "data_structures",
                          prerequisites=["tree"], exam_weight=0.06, difficulty="advanced"),
            TopicDependency("kmp", "KMP算法", "data_structures",
                          prerequisites=["ds_overview"], exam_weight=0.06, difficulty="advanced"),
            TopicDependency("dijkstra", "Dijkstra最短路径", "data_structures",
                          prerequisites=["graph"], exam_weight=0.08, difficulty="advanced"),
            TopicDependency("prim", "最小生成树", "data_structures",
                          prerequisites=["graph"], exam_weight=0.06, difficulty="advanced"),
            TopicDependency("topo_sort", "拓扑排序", "data_structures",
                          prerequisites=["graph"], exam_weight=0.04, difficulty="medium"),
        ]

        # ── 数据结构 ──
        ds_deps = [
            TopicDependency("ds_overview", "数据结构概述", "data_structures",
                          prerequisites=[], exam_weight=0.05, difficulty="basic"),
            TopicDependency("linked_list", "链表", "data_structures",
                          prerequisites=["ds_overview"], exam_weight=0.10, difficulty="medium"),
            TopicDependency("stack_queue", "栈和队列", "data_structures",
                          prerequisites=["linked_list"], exam_weight=0.12, difficulty="medium"),
            TopicDependency("tree", "树", "data_structures",
                          prerequisites=["linked_list"], exam_weight=0.18, difficulty="medium"),
            TopicDependency("bst", "二叉排序树", "data_structures",
                          prerequisites=["tree"], exam_weight=0.15, difficulty="advanced"),
            TopicDependency("avl", "AVL树", "data_structures",
                          prerequisites=["bst"], exam_weight=0.08, difficulty="advanced"),
            TopicDependency("graph", "图", "data_structures",
                          prerequisites=["tree"], exam_weight=0.15, difficulty="advanced"),
            TopicDependency("sorting", "排序", "data_structures",
                          prerequisites=["stack_queue"], exam_weight=0.20, difficulty="medium"),
            TopicDependency("search", "查找", "data_structures",
                          prerequisites=["sorting"], exam_weight=0.15, difficulty="advanced"),
            TopicDependency("hash", "哈希表", "data_structures",
                          prerequisites=["search"], exam_weight=0.12, difficulty="medium"),
        ]

        # ── 计算机组成原理 ──
        co_deps = [
            TopicDependency("co_overview", "计算机系统概述", "computer_organization",
                          prerequisites=[], exam_weight=0.05, difficulty="basic"),
            TopicDependency("bus", "总线", "computer_organization",
                          prerequisites=["co_overview"], exam_weight=0.10, difficulty="medium"),
            TopicDependency("alu", "运算器", "computer_organization",
                          prerequisites=["bus"], exam_weight=0.15, difficulty="advanced"),
            TopicDependency("cpu", "CPU", "computer_organization",
                          prerequisites=["alu"], exam_weight=0.20, difficulty="advanced"),
            TopicDependency("instruction", "指令系统", "computer_organization",
                          prerequisites=["cpu"], exam_weight=0.12, difficulty="medium"),
            TopicDependency("control_unit", "控制器", "computer_organization",
                          prerequisites=["instruction"], exam_weight=0.15, difficulty="advanced"),
            TopicDependency("memory", "存储器", "computer_organization",
                          prerequisites=["bus"], exam_weight=0.18, difficulty="medium"),
            TopicDependency("cache", "Cache", "computer_organization",
                          prerequisites=["memory"], exam_weight=0.15, difficulty="advanced"),
            TopicDependency("virtual_memory", "虚拟存储器", "computer_organization",
                          prerequisites=["cache"], exam_weight=0.10, difficulty="comprehensive"),
            TopicDependency("io", "I/O系统", "computer_organization",
                          prerequisites=["bus"], exam_weight=0.12, difficulty="medium"),
        ]

        # ── 操作系统 ──
        os_deps = [
            TopicDependency("os_overview", "操作系统概述", "operating_system",
                          prerequisites=[], exam_weight=0.05, difficulty="basic"),
            TopicDependency("process", "进程管理", "operating_system",
                          prerequisites=["os_overview"], exam_weight=0.20, difficulty="medium"),
            TopicDependency("thread", "线程", "operating_system",
                          prerequisites=["process"], exam_weight=0.10, difficulty="medium"),
            TopicDependency("sync", "同步与互斥", "operating_system",
                          prerequisites=["process"], exam_weight=0.18, difficulty="advanced"),
            TopicDependency("deadlock", "死锁", "operating_system",
                          prerequisites=["sync"], exam_weight=0.12, difficulty="advanced"),
            TopicDependency("mem_mgmt", "内存管理", "operating_system",
                          prerequisites=["process"], exam_weight=0.18, difficulty="medium"),
            TopicDependency("paging", "分页/分段", "operating_system",
                          prerequisites=["mem_mgmt"], exam_weight=0.15, difficulty="advanced"),
            TopicDependency("virtual_mem", "虚拟内存", "operating_system",
                          prerequisites=["paging"], exam_weight=0.10, difficulty="comprehensive"),
            TopicDependency("fs", "文件系统", "operating_system",
                          prerequisites=["mem_mgmt"], exam_weight=0.12, difficulty="medium"),
            TopicDependency("io_mgmt", "I/O管理", "operating_system",
                          prerequisites=["fs"], exam_weight=0.08, difficulty="medium"),
        ]

        # 注册全部依赖
        all_deps = cn_deps + ds_deps + co_deps + os_deps
        for dep in all_deps:
            self._dependencies[dep.topic_id] = dep

    # ── Agent适配关系 ──

    def _build_agent_affinities(self):
        """各Agent擅长课程和难度范围"""

        affinities = [
            AgentTopicAffinity("teacher",
                preferred_courses=["computer_network", "data_structures",
                                   "computer_organization", "operating_system"],
                preferred_difficulty=["medium", "advanced"],
                topic_keywords=["讲解", "概念", "原理", "定义", "理解"]),
            AgentTopicAffinity("quizmaster",
                preferred_courses=["computer_network", "data_structures",
                                   "computer_organization", "operating_system"],
                preferred_difficulty=["medium", "advanced", "comprehensive"],
                topic_keywords=["练习", "真题", "模拟题", "考点", "考查"]),
            AgentTopicAffinity("media_designer",
                preferred_courses=["computer_network", "data_structures"],
                preferred_difficulty=["basic", "medium"],
                topic_keywords=["思维导图", "可视化", "动画", "图解"]),
            AgentTopicAffinity("extension",
                preferred_courses=["computer_network", "operating_system"],
                preferred_difficulty=["advanced", "comprehensive"],
                topic_keywords=["拓展", "综合", "跨科目", "关联", "对比"]),
            AgentTopicAffinity("ppt_designer",
                preferred_courses=["computer_network", "data_structures",
                                   "computer_organization", "operating_system"],
                preferred_difficulty=["basic", "medium"],
                topic_keywords=["大纲", "幻灯片", "PPT", "框架", "结构"]),
            AgentTopicAffinity("code_practice",
                preferred_courses=["data_structures", "computer_organization"],
                preferred_difficulty=["medium", "advanced"],
                topic_keywords=["代码", "实操", "编程", "实现", "算法"]),
            # 跨科目关联Agent（报告建议的评估反馈智能体）
            AgentTopicAffinity("assessor",
                preferred_courses=["computer_network", "data_structures",
                                   "computer_organization", "operating_system"],
                preferred_difficulty=["comprehensive"],
                topic_keywords=["评估", "检验", "掌握度", "薄弱", "诊断"]),
        ]

        for aff in affinities:
            self._agent_affinities[aff.agent_name] = aff

    # ── 公共接口 ──

    def get_prerequisites(self, topic_id: str) -> list[str]:
        """获取知识点的前置依赖列表"""
        dep = self._dependencies.get(topic_id)
        if not dep:
            return []
        return dep.prerequisites

    def get_exam_weight(self, topic_id: str) -> float:
        """获取知识点考查权重(0-1)"""
        dep = self._dependencies.get(topic_id)
        if not dep:
            return 0.05  # 默认低权重
        return dep.exam_weight

    def get_difficulty(self, topic_id: str) -> str:
        """获取知识点难度"""
        dep = self._dependencies.get(topic_id)
        if not dep:
            return "medium"
        return dep.difficulty

    def get_cross_subject_prerequisites(self, topic_id: str) -> list[str]:
        """获取跨科目前置依赖

        例如: 虚拟内存(OS) → Cache(CO) → 内存(CO) → 总线(CO)
        这是报告§3.3.3的核心创新：识别跨科目知识依赖
        """
        dep = self._dependencies.get(topic_id)
        if not dep:
            return []

        cross_subject = []
        for prereq_id in dep.prerequisites:
            prereq = self._dependencies.get(prereq_id)
            if prereq and prereq.course != dep.course:
                cross_subject.append(prereq_id)
                # 递归查找跨科前置
                deeper = self.get_cross_subject_prerequisites(prereq_id)
                cross_subject.extend(d for d in deeper if d not in cross_subject)

        return cross_subject

    def validate_schedule(
        self, topic_ids: list[str], student_profile: dict = None
    ) -> ScheduleValidation:
        """校验教学任务调度顺序是否符合408业务逻辑

        检查项:
        1. 前置依赖是否已覆盖
        2. 难度递进是否合理
        3. 跨科目关联是否遗漏
        """
        violations = []
        suggestions = []

        covered = set()
        for tid in topic_ids:
            dep = self._dependencies.get(tid)
            if not dep:
                violations.append(f"未知知识点: {tid}")
                continue

            # 检查前置依赖
            for prereq in dep.prerequisites:
                if prereq not in covered and prereq not in topic_ids:
                    prereq_dep = self._dependencies.get(prereq)
                    if prereq_dep:
                        violations.append(
                            f"前置依赖缺失: {dep.topic_name}({dep.course}) 需要 "
                            f"{prereq_dep.topic_name}({prereq_dep.course})"
                        )
                        suggestions.append(f"建议先学习 {prereq_dep.topic_name}")

            # 检查跨科目前置
            cross = self.get_cross_subject_prerequisites(tid)
            for cs_id in cross:
                cs_dep = self._dependencies.get(cs_id)
                if cs_dep and cs_id not in topic_ids:
                    suggestions.append(
                        f"跨科目关联: {dep.topic_name}({dep.course}) 与 "
                        f"{cs_dep.topic_name}({cs_dep.course}) 有关联，建议补充"
                    )

            covered.add(tid)

        # 重新排序：按依赖关系拓扑排序
        adjusted = self._topological_sort(topic_ids)

        # 基于画像调整优先级
        if student_profile:
            weak_topics = student_profile.get("weak_topics", [])
            if weak_topics:
                # 薄弱知识点提前
                adjusted = self._prioritize_weak_topics(adjusted, weak_topics)

        return ScheduleValidation(
            is_valid=len(violations) == 0,
            violations=violations,
            suggestions=suggestions,
            adjusted_order=adjusted,
        )

    def suggest_agent_assignment(
        self, topic_id: str, resource_type: str = ""
    ) -> list[str]:
        """建议哪些Agent适合处理该知识点

        基于Agent偏好课程、难度、关键词匹配
        """
        dep = self._dependencies.get(topic_id)
        if not dep:
            # 未知知识点：返回所有Agent
            return list(self._agent_affinities.keys())

        candidates = []
        for name, aff in self._agent_affinities.items():
            # 课程匹配
            course_match = dep.course in aff.preferred_courses
            # 难度匹配
            diff_match = dep.difficulty in aff.preferred_difficulty
            # 关键词匹配（资源类型关键词）
            kw_match = any(k in resource_type for k in aff.topic_keywords) if resource_type else True

            # 至少课程匹配就算候选
            if course_match or diff_match:
                candidates.append(name)

        # 排序：课程+难度双匹配优先
        scored = []
        for name in candidates:
            aff = self._agent_affinities[name]
            score = 0
            if dep.course in aff.preferred_courses:
                score += 2
            if dep.difficulty in aff.preferred_difficulty:
                score += 1
            scored.append((score, name))

        scored.sort(reverse=True)
        return [name for _, name in scored]

    def prioritize_by_profile(
        self, topic_ids: list[str], student_profile: dict
    ) -> list[str]:
        """基于学生画像调整知识点优先级

        画像影响因子:
        - weak_topics: 薄弱知识点 → 优先级↑↑
        - mastered_topics: 已掌握知识点 → 优先级↓
        - target_score: 目标分数 → 高目标需更多advanced
        - review_stage: 复习阶段 → 基础→强化→综合→模考
        """
        weak = set(student_profile.get("weak_topics", []))
        mastered = set(student_profile.get("mastered_topics", []))
        stage = student_profile.get("review_stage", "basic")  # basic|strengthen|comprehensive|mock
        target = student_profile.get("target_score", 100)

        # 阶段→难度优先级
        stage_difficulty_priority = {
            "basic": ["basic", "medium"],
            "strengthen": ["medium", "advanced"],
            "comprehensive": ["advanced", "comprehensive"],
            "mock": ["comprehensive", "advanced"],
        }
        preferred_diff = stage_difficulty_priority.get(stage, ["medium", "advanced"])

        scored = []
        for tid in topic_ids:
            dep = self._dependencies.get(tid)
            if not dep:
                scored.append((0, tid))
                continue

            score = dep.exam_weight * 10  # 基础分 = 考查权重

            # 薄弱知识点加分
            if tid in weak or dep.topic_name in weak:
                score += 5.0  # 薄弱知识点优先级大幅提升

            # 已掌握知识点减分
            if tid in mastered or dep.topic_name in mastered:
                score -= 3.0

            # 阶段匹配加分
            if dep.difficulty in preferred_diff:
                score += 2.0

            # 高目标分数 → advanced/comprehensive加分
            if target >= 120 and dep.difficulty in ["advanced", "comprehensive"]:
                score += 1.5

            scored.append((score, tid))

        scored.sort(reverse=True)
        return [tid for _, tid in scored]

    def get_stats(self) -> dict:
        """引擎统计信息"""
        course_counts = {}
        for dep in self._dependencies.values():
            course_counts[dep.course] = course_counts.get(dep.course, 0) + 1

        difficulty_counts = {}
        for dep in self._dependencies.values():
            difficulty_counts[dep.difficulty] = difficulty_counts.get(dep.difficulty, 0) + 1

        return {
            "total_topics": len(self._dependencies),
            "course_distribution": course_counts,
            "difficulty_distribution": difficulty_counts,
            "review_stages": self._review_order,
            "agent_count": len(self._agent_affinities),
            "agents": list(self._agent_affinities.keys()),
            "top_exam_weight_topics": self._get_top_weighted(5),
        }

    def _get_top_weighted(self, n: int) -> list[dict]:
        """获取考查权重最高的N个知识点"""
        sorted_deps = sorted(
            self._dependencies.values(),
            key=lambda d: d.exam_weight,
            reverse=True
        )
        return [
            {"id": d.topic_id, "name": d.topic_name,
             "course": d.course, "weight": d.exam_weight}
            for d in sorted_deps[:n]
        ]

    # ── 内部方法 ──

    def _topological_sort(self, topic_ids: list[str]) -> list[str]:
        """拓扑排序——保证前置依赖在前"""
        result = []
        visited = set()
        visiting = set()

        def visit(tid: str):
            if tid in visited:
                return
            if tid in visiting:
                # 循环依赖，跳过
                return
            visiting.add(tid)

            dep = self._dependencies.get(tid)
            if dep:
                for prereq in dep.prerequisites:
                    if prereq in topic_ids:
                        visit(prereq)

            visiting.remove(tid)
            visited.add(tid)
            result.append(tid)

        for tid in topic_ids:
            visit(tid)

        # 未访问的ID追加末尾
        for tid in topic_ids:
            if tid not in visited:
                result.append(tid)

        return result

    def _prioritize_weak_topics(
        self, ordered: list[str], weak_topics: list[str]
    ) -> list[str]:
        """将薄弱知识点提到队列前面"""
        weak_ids = set()
        for wt in weak_topics:
            # 匹配ID或名称
            if wt in self._dependencies:
                weak_ids.add(wt)
            else:
                for dep_id, dep in self._dependencies.items():
                    if dep.topic_name == wt:
                        weak_ids.add(dep_id)

        prioritized = [t for t in ordered if t in weak_ids]
        remaining = [t for t in ordered if t not in weak_ids]
        return prioritized + remaining


# ── 全局单例 ──

teaching_rules = TeachingRuleEngine()
