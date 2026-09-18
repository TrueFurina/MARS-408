# ============================================================
# 图数据库抽象层 — 知识点依赖关系存储
#
# 支持两种后端：
#   1. Neo4j（生产环境，需安装 neo4j Python 驱动 + 运行 Neo4j 服务）
#   2. 内存 DAG（开发回退，基于 kg_dag.py 的静态依赖关系）
#
# 报告§3.5 混合知识库层：「结构化资源库 + 图数据库 + 向量库」
# ============================================================

import logging
import os
from typing import Optional, list as ListType

logger = logging.getLogger("netlearn.graph_db")

# ── 全局实例 ──
_graph_db = None


def get_graph_db():
    """获取图数据库实例（单例，延迟初始化）"""
    global _graph_db
    if _graph_db is None:
        # 优先尝试 Neo4j
        neo4j_uri = os.environ.get("NEO4J_URI", "")
        if neo4j_uri:
            try:
                _graph_db = Neo4jGraphDB(neo4j_uri)
                logger.info("图数据库: Neo4j 已连接")
            except Exception as e:
                logger.warning(f"Neo4j 连接失败，回退内存 DAG: {e}")
                _graph_db = MemoryGraphDB()
        else:
            logger.info("图数据库: 使用内存 DAG（设置 NEO4J_URI 可启用 Neo4j）")
            _graph_db = MemoryGraphDB()
    return _graph_db


# ════════════════════════════════════════════════
# 抽象接口
# ════════════════════════════════════════════════

class GraphDB:
    """图数据库抽象基类"""

    def get_prerequisites(self, topic_id: str) -> list[str]:
        """获取某个知识点的前置依赖知识点列表"""
        raise NotImplementedError

    def get_dependents(self, topic_id: str) -> list[str]:
        """获取依赖某个知识点的后续知识点列表"""
        raise NotImplementedError

    def get_learning_path(self, subject: str, weak_topics: list[str]) -> list[dict]:
        """根据薄弱知识点生成学习路径"""
        raise NotImplementedError

    def search_by_keyword(self, keyword: str) -> list[dict]:
        """关键词搜索知识点"""
        raise NotImplementedError

    def get_all_topics(self, subject: str = None) -> list[dict]:
        """获取所有知识点（可选按科目过滤）"""
        raise NotImplementedError


# ════════════════════════════════════════════════
# 内存 DAG 实现（开发回退）
# ════════════════════════════════════════════════

class MemoryGraphDB(GraphDB):
    """基于 kg_dag.py 的内存 DAG 实现"""

    def __init__(self):
        from agents.kg_dag import (
            SUBJECT_GROUP_MAP, GROUP_PREREQS, SUBJECT_GROUP_SPAN,
            SUBJECT_KEYWORD_MAP, chapter_to_group,
        )
        self._subject_group_map = SUBJECT_GROUP_MAP
        self._group_prereqs = GROUP_PREREQS
        self._subject_group_span = SUBJECT_GROUP_SPAN
        self._subject_keyword_map = SUBJECT_KEYWORD_MAP
        self._chapter_to_group = chapter_to_group

        # 内置知识点名称映射
        self._topic_names = {
            1: "计算机网络概述", 2: "物理层", 3: "数据链路层",
            4: "网络层", 5: "运输层", 6: "应用层", 7: "网络安全",
            8: "线性表", 9: "栈和队列", 10: "串", 11: "树与二叉树",
            12: "图", 13: "查找", 14: "排序",
            15: "计算机系统概述", 16: "数据表示与运算", 17: "存储系统",
            18: "指令系统", 19: "CPU", 20: "总线", 21: "输入输出系统",
            22: "操作系统概述", 23: "进程管理", 24: "内存管理",
            25: "文件管理", 26: "输入输出管理",
        }

    def _topic_id_to_name(self, topic_id: str) -> str:
        """将 topic_id 转换为可读名称"""
        try:
            g = int(topic_id.replace("group_", ""))
            return self._topic_names.get(g, topic_id)
        except (ValueError, AttributeError):
            return topic_id

    def get_prerequisites(self, topic_id: str) -> list[str]:
        g = self._topic_id_to_group(topic_id)
        prereq_groups = self._group_prereqs.get(g, [])
        return [f"group_{p}" for p in prereq_groups]

    def get_dependents(self, topic_id: str) -> list[str]:
        g = self._topic_id_to_group(topic_id)
        dependents = []
        for group_id, prereqs in self._group_prereqs.items():
            if g in prereqs:
                dependents.append(f"group_{group_id}")
        return dependents

    def get_learning_path(self, subject: str, weak_topics: list[str]) -> list[dict]:
        from agents.kg_dag import chapter_to_group
        path = []
        seen = set()

        # 将薄弱知识点转换为 group
        weak_groups = set()
        for t in weak_topics:
            g = self._subject_group_map.get(t)
            if g:
                weak_groups.add(g)

        # 按 group 顺序生成路径
        for g in range(1, 27):
            if g in seen:
                continue
            name = self._topic_names.get(g, f"第{g}章")
            is_weak = g in weak_groups
            path.append({
                "group": g,
                "name": name,
                "is_weak": is_weak,
                "priority": "high" if is_weak else "normal",
            })
            seen.add(g)

        return path

    def search_by_keyword(self, keyword: str) -> list[dict]:
        results = []
        for g, name in self._topic_names.items():
            if keyword.lower() in name.lower():
                results.append({"group": g, "name": name, "type": "topic"})
        return results

    def get_all_topics(self, subject: str = None) -> list[dict]:
        results = []
        for g in range(1, 27):
            name = self._topic_names.get(g, f"第{g}章")
            # 根据 group 范围判断科目
            topic_subject = None
            if g <= 7:
                topic_subject = "computer_network"
            elif g <= 14:
                topic_subject = "data_structures"
            elif g <= 21:
                topic_subject = "computer_organization"
            else:
                topic_subject = "operating_system"

            if subject and topic_subject != subject:
                continue
            prereqs = [self._topic_names.get(p, "") for p in self._group_prereqs.get(g, [])]
            results.append({
                "group": g,
                "name": name,
                "subject": topic_subject,
                "prerequisites": prereqs,
            })
        return results

    @staticmethod
    def _topic_id_to_group(topic_id: str) -> int:
        try:
            return int(topic_id.replace("group_", ""))
        except (ValueError, AttributeError):
            return 1


# ════════════════════════════════════════════════
# Neo4j 实现（生产环境）
# ════════════════════════════════════════════════

class Neo4jGraphDB(GraphDB):
    """Neo4j 图数据库实现"""

    def __init__(self, uri: str = None):
        from neo4j import GraphDatabase
        uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        user = os.environ.get("NEO4J_USER", "neo4j")
        password = os.environ.get("NEO4J_PASSWORD", "")
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._init_schema()

    def _init_schema(self):
        """初始化图数据库约束"""
        with self._driver.session() as session:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE")

    def close(self):
        self._driver.close()

    def get_prerequisites(self, topic_id: str) -> list[str]:
        with self._driver.session() as session:
            result = session.run(
                "MATCH (t:Topic {id: $id})-[r:HAS_PREREQUISITE]->(pre:Topic) "
                "RETURN pre.id AS id ORDER BY pre.group",
                id=topic_id
            )
            return [r["id"] for r in result]

    def get_dependents(self, topic_id: str) -> list[str]:
        with self._driver.session() as session:
            result = session.run(
                "MATCH (t:Topic {id: $id})<-[r:HAS_PREREQUISITE]-(dep:Topic) "
                "RETURN dep.id AS id ORDER BY dep.group",
                id=topic_id
            )
            return [r["id"] for r in result]

    def get_learning_path(self, subject: str, weak_topics: list[str]) -> list[dict]:
        with self._driver.session() as session:
            # 按科目获取所有知识点，按依赖关系拓扑排序
            result = session.run(
                "MATCH (t:Topic) WHERE t.subject = $subject "
                "OPTIONAL MATCH (t)-[:HAS_PREREQUISITE]->(pre:Topic) "
                "RETURN t.id AS id, t.name AS name, t.group AS group, "
                "collect(pre.id) AS prerequisites "
                "ORDER BY t.group",
                subject=subject
            )
            path = []
            weak_set = set(weak_topics)
            for r in result:
                is_weak = r["id"] in weak_set
                path.append({
                    "group": r["group"],
                    "name": r["name"],
                    "is_weak": is_weak,
                    "priority": "high" if is_weak else "normal",
                })
            return path

    def search_by_keyword(self, keyword: str) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(
                "MATCH (t:Topic) WHERE t.name CONTAINS $keyword "
                "RETURN t.id AS id, t.name AS name, t.group AS group "
                "LIMIT 20",
                keyword=keyword
            )
            return [{"group": r["group"], "name": r["name"], "type": "topic"} for r in result]

    def get_all_topics(self, subject: str = None) -> list[dict]:
        query = "MATCH (t:Topic) "
        params = {}
        if subject:
            query += "WHERE t.subject = $subject "
            params["subject"] = subject
        query += "OPTIONAL MATCH (t)-[:HAS_PREREQUISITE]->(pre:Topic) "
        query += "RETURN t.id AS id, t.name AS name, t.group AS group, "
        query += "t.subject AS subject, collect(pre.id) AS prerequisites "
        query += "ORDER BY t.group"

        with self._driver.session() as session:
            result = session.run(query, **params)
            return [{
                "id": r["id"], "name": r["name"],
                "group": r["group"], "subject": r["subject"],
                "prerequisites": r["prerequisites"],
            } for r in result]

    def import_from_kg_dag(self):
        """从 kg_dag.py 导入知识点依赖关系到 Neo4j"""
        from agents.kg_dag import SUBJECT_GROUP_MAP, GROUP_PREREQS

        subject_names = {
            "computer_network": "计算机网络", "data_structures": "数据结构",
            "computer_organization": "计算机组成原理", "operating_system": "操作系统",
        }
        topic_names = {
            1: "计算机网络概述", 2: "物理层", 3: "数据链路层",
            4: "网络层", 5: "运输层", 6: "应用层", 7: "网络安全",
            8: "线性表", 9: "栈和队列", 10: "串", 11: "树与二叉树",
            12: "图", 13: "查找", 14: "排序",
            15: "计算机系统概述", 16: "数据表示与运算", 17: "存储系统",
            18: "指令系统", 19: "CPU", 20: "总线", 21: "输入输出系统",
            22: "操作系统概述", 23: "进程管理", 24: "内存管理",
            25: "文件管理", 26: "输入输出管理",
        }

        with self._driver.session() as session:
            # 创建知识点节点
            for g in range(1, 27):
                subject = "computer_network" if g <= 7 else \
                         "data_structures" if g <= 14 else \
                         "computer_organization" if g <= 21 else \
                         "operating_system"
                session.run(
                    "MERGE (t:Topic {id: $id}) "
                    "SET t.name = $name, t.group = $group, t.subject = $subject",
                    id=f"group_{g}", name=topic_names[g], group=g, subject=subject
                )

            # 创建依赖关系
            for g, prereqs in GROUP_PREREQS.items():
                for p in prereqs:
                    session.run(
                        "MATCH (t:Topic {id: $tid}), (pre:Topic {id: $pid}) "
                        "MERGE (t)-[:HAS_PREREQUISITE]->(pre)",
                        tid=f"group_{g}", pid=f"group_{p}"
                    )

            logger.info(f"Neo4j 已导入 {len(topic_names)} 个知识点节点")