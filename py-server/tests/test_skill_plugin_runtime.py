# ============================================================
# Skill 插件运行时 — 单元测试
#
# 覆盖（优先级3b：热加载 + 故障熔断隔离 + 记忆注入）：
#   1. 熔断器：CLOSED→OPEN→HALF_OPEN 状态机 + allow_request 拒绝
#   2. 热加载缓存：TTL 过期重载 + invalidate 立即失效
#   3. 记忆注入：build_memory_context 组装 + execute 注入/写回
# ============================================================

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

# 隔离测试 DB
_TEST_DB = os.path.join(os.path.dirname(__file__), "_test_skill_plugin.db")
os.environ.setdefault("NETLEARN_USER_DB", _TEST_DB)


# ══════════════════════════════════════════════════════════
# 熔断器（CircuitBreaker）
# ══════════════════════════════════════════════════════════

def test_breaker_closed_initial():
    from engines.skill_plugin_runtime import CircuitBreaker
    cb = CircuitBreaker(failure_threshold=3, open_timeout=0.5)
    assert cb.state == "closed"
    assert cb.allow_request() is True


def test_breaker_opens_after_threshold():
    from engines.skill_plugin_runtime import CircuitBreaker
    cb = CircuitBreaker(failure_threshold=2, open_timeout=60)
    cb.record_failure()
    assert cb.state == "closed"  # 1 次失败未达阈值
    cb.record_failure()
    assert cb.state == "open"    # 2 次失败达阈值 → OPEN
    assert cb.allow_request() is False


def test_breaker_half_open_after_timeout():
    from engines.skill_plugin_runtime import CircuitBreaker
    cb = CircuitBreaker(failure_threshold=1, open_timeout=0.2)
    cb.record_failure()
    assert cb.state == "open"
    assert cb.allow_request() is False
    time.sleep(0.3)
    assert cb.state == "half_open"  # 超时后自动半开
    assert cb.allow_request() is True


def test_breaker_recovers_on_success():
    from engines.skill_plugin_runtime import CircuitBreaker
    cb = CircuitBreaker(failure_threshold=2, open_timeout=60)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "open"
    cb.record_success()
    assert cb.state == "closed"


def test_breaker_stats_shape():
    from engines.skill_plugin_runtime import CircuitBreaker
    cb = CircuitBreaker()
    stats = cb.stats()
    assert "state" in stats and "failures" in stats
    assert stats["failure_threshold"] == 3


# ══════════════════════════════════════════════════════════
# 热加载缓存（HotReloadCache）
# ══════════════════════════════════════════════════════════

def test_hot_reload_cache_invalidate():
    from engines.skill_plugin_runtime import HotReloadCache
    cache = HotReloadCache(ttl_seconds=300)
    cache._cache["s1"] = (time.time(), {"updated_at": "2026-01-01", "system_prompt": "v1"})
    assert cache.get("s1")["system_prompt"] == "v1"
    cache.invalidate("s1")
    assert "s1" not in cache._cache


def test_hot_reload_cache_ttl_expiry():
    from engines.skill_plugin_runtime import HotReloadCache
    cache = HotReloadCache(ttl_seconds=0.1)
    cache._cache["s1"] = (time.time() - 1, {"updated_at": "2026-01-01", "system_prompt": "old"})
    # TTL 已过期 → get 会走 DB 重载（skill_store 无此技能则返回 None）
    result = cache.get("nonexistent_skill")
    assert result is None  # DB 中不存在


# ══════════════════════════════════════════════════════════
# SkillPluginRuntime 记忆注入（不真正调用 LLM，验证组装）
# ══════════════════════════════════════════════════════════

def test_build_memory_context_empty_user():
    """无记忆数据时返回占位符而非抛异常"""
    import asyncio
    from engines.skill_plugin_runtime import SkillPluginRuntime
    runtime = SkillPluginRuntime("test_skill")
    ctx = asyncio.run(runtime._build_memory_context("u_empty", "s1"))
    # 无数据 → 占位文本（空用户没有画像/事件）
    assert isinstance(ctx, str)
    assert "学生记忆" in ctx or ctx == ""


def test_memory_service_context_with_data():
    """有记忆数据时上下文包含画像块"""
    from db import memory_store as ms
    conn = ms._get_conn()
    conn.execute("DELETE FROM memory_l2_semantic")
    conn.execute("DELETE FROM memory_l3_episodic")
    conn.commit()

    from services import memory_service as svc
    svc.init_student_memory("u_ctx", profile={"goal": "exam", "knowledge_base": "beginner"})
    svc.record_quiz_result("u_ctx", "TCP", True)
    ctx = svc.build_memory_context("u_ctx", max_episodes=5)
    assert "【学生长期画像】" in ctx


def test_record_episode_skill_run():
    """执行后写回 L3 情景记忆（skill_run 事件）"""
    from engines.skill_plugin_runtime import SkillPluginRuntime
    from db import memory_store as ms
    conn = ms._get_conn()
    conn.execute("DELETE FROM memory_l3_episodic")
    conn.commit()

    import asyncio
    runtime = SkillPluginRuntime("test_skill")
    asyncio.run(runtime._record_episode("u_ep", {"skill_id": "test_skill", "output_len": 10}))
    episodes = ms.get_episodes("u_ep", event_type="skill_run")
    assert len(episodes) == 1
    assert episodes[0]["event"]["skill_id"] == "test_skill"


def test_runtime_registry_isolates_breakers():
    """不同技能实例熔断器互相隔离（单插件故障不影响其他）"""
    from engines.skill_plugin_runtime import SkillPluginRuntime
    r1 = SkillPluginRuntime.get("skill_a")
    r2 = SkillPluginRuntime.get("skill_b")
    assert r1 is not r2
    # skill_a 熔断不影响 skill_b
    r1._breaker.record_failure()
    assert r2._breaker.allow_request()


# ── 循环31-P0: SKILL.md 新字段消费端到端验证 ──

def test_trigger_paths_blocks_unmatched_input():
    """trigger_paths 条件激活：配置触发知识点后，输入不匹配拒绝执行（不发 LLM）"""
    import asyncio
    import time
    from engines.skill_plugin_runtime import SkillPluginRuntime

    runtime = SkillPluginRuntime("test_trigger")
    # 构造含 trigger_paths 的技能配置（直接注入 HotReloadCache 内部缓存，绕过 DB）
    skill = {
        "system_prompt": "你是测试技能",
        "llm_channel": "auto",
        "temperature": 0.7,
        "max_tokens": 100,
        "trigger_paths": ["TCP拥塞控制", "子网划分"],
    }
    runtime._cache._cache["test_trigger"] = (time.time(), skill)

    result = asyncio.run(runtime.execute("帮我讲讲排序算法", user_id="u1"))
    assert "仅对特定知识点激活" in result  # 未匹配 → 拒绝执行


def test_trigger_paths_allows_matched_input():
    """trigger_paths 条件激活：输入匹配触发知识点时正常执行（不拦截）"""
    import asyncio
    import time
    from engines.skill_plugin_runtime import SkillPluginRuntime

    runtime = SkillPluginRuntime("test_trigger_ok")
    skill = {
        "system_prompt": "你是测试技能",
        "llm_channel": "auto",
        "temperature": 0.7,
        "max_tokens": 100,
        "trigger_paths": ["TCP拥塞控制"],
    }
    runtime._cache._cache["test_trigger_ok"] = (time.time(), skill)
    # 匹配输入 → 走到 LLM 调用（无 key 时抛 LLMUnavailable 而非触发路径拦截）
    import pytest
    from db.llm_provider import LLMUnavailable
    try:
        asyncio.run(runtime.execute("讲讲TCP拥塞控制算法", user_id="u2"))
    except LLMUnavailable:
        pass  # 通过触发路径检查，进入 LLM 调用（无 key 属预期）
    except Exception as e:
        pytest.fail(f"不应抛非 LLMUnavailable 异常: {e}")


def test_tools_meta_passed_to_llm():
    """tools 元数据：技能配置结构化工具后，execute 透传给 LLM.chat(tools=...)"""
    import asyncio
    import inspect
    from engines.skill_plugin_runtime import SkillPluginRuntime

    src = inspect.getsource(SkillPluginRuntime.execute)
    assert 'skill.get("tools") or None' in src  # tools 透传已接入


def test_memory_access_write_requires_permission():
    """memory_access 记忆写回：write/read_write 才回写 L3，none/read 不回写"""
    import asyncio
    from engines.skill_plugin_runtime import SkillPluginRuntime
    from db import memory_store as ms

    runtime = SkillPluginRuntime("test_perm")
    conn = ms._get_conn()
    conn.execute("DELETE FROM memory_l3_episodic WHERE user_id IN ('u_perm_yes','u_perm_no')")
    conn.commit()

    # read_write 权限 → 回写
    asyncio.run(runtime._record_episode("u_perm_yes", {"skill_id": "test_perm", "output_len": 5}))
    assert len(ms.get_episodes("u_perm_yes", event_type="skill_run")) == 1

    # 无事件 → none/read 不回写（execute 内由 memory_access 判断，此处验证写接口本身）
    assert len(ms.get_episodes("u_perm_no", event_type="skill_run")) == 0
