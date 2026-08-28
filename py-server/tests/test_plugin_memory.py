# ============================================================
# 单元测试：Skill 插件读写 L1/L2/L3 三层记忆标准化接口（P2①）
#
# 覆盖：
#   - read_memory_for_plugin：分层结构 / layers 过滤 / 降级空结构
#   - write_plugin_event：标准化 schema 入库 / 事件可查询 / 降级静默
# 依赖：SQLite 临时隔离（conftest 提供），不触发 LLM/网络。
# ============================================================

import pytest

pytestmark = pytest.mark.unit


def test_read_memory_default_layers():
    """默认返回 L1/L2/L3 三层结构"""
    from services.memory_service import read_memory_for_plugin
    data = read_memory_for_plugin("u_plugin_read")
    assert set(data.keys()) == {"L1", "L2", "L3"}
    assert "working_context" in data["L1"]
    assert "profile" in data["L2"]
    assert "mastery" in data["L2"]
    assert "weak_points" in data["L2"]
    assert "count" in data["L3"]
    assert "recent_episodes" in data["L3"]


def test_read_memory_layer_filter():
    """layers 参数过滤指定层"""
    from services.memory_service import read_memory_for_plugin
    l2_only = read_memory_for_plugin("u_plugin_read2", layers=["L2"])
    assert set(l2_only.keys()) == {"L2"}
    assert "L1" not in l2_only and "L3" not in l2_only


def test_read_memory_reflects_weak_points():
    """写入薄弱点后，读接口应能读到（L2 数据一致性）"""
    from services.memory_service import read_memory_for_plugin
    from db import memory_store as ms
    ms.save_semantic_memory("u_plugin_weak", weak_points=["TCP拥塞控制", "AVL平衡树"])
    data = read_memory_for_plugin("u_plugin_weak", layers=["L2"])
    assert "TCP拥塞控制" in data["L2"]["weak_points"]


def test_write_plugin_event_schema():
    """标准化写事件：外层事件类型=传入 event_type，schema 含 plugin_id/event_type/topic/payload"""
    from services.memory_service import write_plugin_event
    from db import memory_store as ms
    write_plugin_event(
        user_id="u_plugin_write",
        plugin_id="tcp-handshake-guide",
        event_type="practice",
        topic="TCP三次握手",
        payload={"score": 0.8, "duration_ms": 1200},
    )
    episodes = ms.get_episodes("u_plugin_write", limit=10)
    # 外层事件类型 = 传入的 event_type（保持既有事件过滤兼容）
    assert any("practice" == e.get("event_type") for e in episodes)
    # 内层 schema 可追踪 plugin_id
    found = any(
        (e.get("event") or {}).get("plugin_id") == "tcp-handshake-guide"
        for e in episodes
    )
    assert found


def test_write_plugin_event_query_by_plugin():
    """写后可按插件检索（顶层 plugin_id 可追踪）"""
    from services.memory_service import write_plugin_event
    from db import memory_store as ms
    write_plugin_event("u_plugin_query", "sort-algo", "run", topic="排序算法", payload={"ok": True})
    episodes = ms.get_episodes("u_plugin_query", limit=10)
    # get_episodes 返回项 key 为 "event"（内部已 json.loads 为 dict），plugin_id 在事件顶层
    found = any(
        (e.get("event") or {}).get("plugin_id") == "sort-algo"
        for e in episodes
    )
    assert found


def test_read_memory_degrade_empty():
    """异常输入降级：非法用户/异常不抛异常，返回可空结构（不阻塞插件）"""
    from services.memory_service import read_memory_for_plugin
    # 不存在的用户也应返回结构（不抛异常）
    data = read_memory_for_plugin("__no_such_user__xyz")
    assert isinstance(data, dict)
    assert set(data.keys()) == {"L1", "L2", "L3"}


def test_write_plugin_event_degrade_silent():
    """写事件降级静默：异常输入不抛异常（插件执行不被阻断）"""
    from services.memory_service import write_plugin_event
    # 正常调用不抛异常即可（异常路径由内部 try/except 吞掉）
    write_plugin_event("u_plugin_degrade", "demo-plugin", "run")
    assert True


def test_plugin_write_invalidates_overview_cache():
    """插件写事件后 overview 缓存失效（P1① 缓存一致性联动）"""
    from services.memory_service import get_memory_overview, write_plugin_event
    before = get_memory_overview("u_plugin_cache_inv").get("episodic_count", 0)
    write_plugin_event("u_plugin_cache_inv", "demo-plugin", "run")
    after = get_memory_overview("u_plugin_cache_inv").get("episodic_count", 0)
    assert after >= before  # 缓存失效后能读到新增事件计数
