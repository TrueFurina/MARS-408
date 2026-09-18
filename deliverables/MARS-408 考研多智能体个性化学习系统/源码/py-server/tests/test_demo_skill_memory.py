# ============================================================
# P2③ 端到端验证：Demo 技能读取薄弱学情 + 回写行为记忆
#
# 覆盖：
#   - Demo 技能模板 weak-point-expert 存在（408 专属）
#   - 端到端：构造薄弱学情 → execute(use_memory) → 注入薄弱词
#     → 回写 skill_run 事件（plugin_id 可追踪）
#   - 权限联动：memory_access=read 时注入但写回被阻止
# 依赖：SQLite 临时隔离（conftest），自定义捕获 mock LLM。
# ============================================================

import pytest

pytestmark = pytest.mark.unit


def _install_capturing_llm(monkeypatch, runtime, captured: dict):
    """patch 技能运行时持有的 LLM 实例属性（比类方法 patch 更健壮，不受
    全量环境下其他测试对 LLMProvider.chat 类方法的 patch 顺序影响）。
    注意：实例属性无方法绑定机制，函数签名不含 self。"""
    llm = runtime._get_llm(None)  # 惰性创建/复用实例（demo 技能 llm_channel=auto）

    async def _fake_chat(messages, *args, **kwargs):
        captured["messages"] = messages
        return {"choices": [{"message": {"role": "assistant", "content": "mock 讲解完成"}}]}

    async def _fake_tc(system_prompt, user_prompt, *args, **kwargs):
        captured["text_prompt"] = user_prompt
        return "mock llm response"

    monkeypatch.setattr(llm, "chat", _fake_chat)
    monkeypatch.setattr(llm, "text_completion", _fake_tc)


def test_demo_skill_template_exists():
    """Demo 技能模板 weak-point-expert 存在（408 专属）"""
    from db.skill_store import _BUILTIN_TEMPLATES
    ids = [t.id for t in _BUILTIN_TEMPLATES]
    assert "weak-point-expert" in ids


def _create_demo_skill() -> None:
    """测试前置：从模板创建 weak-point-expert 技能（模板≠已创建技能）"""
    from schemas.skills import Skill
    from db.skill_store import create_skill, get_skill
    if get_skill("weak-point-expert") is None:
        create_skill(Skill(
            id="weak-point-expert",
            name="薄弱点专项讲解师",
            description="Demo 技能：读取薄弱学情 + 回写行为记忆",
            system_prompt="你是 408 薄弱点讲解专家，请结合学生薄弱点讲解。",
            memory_access="read_write",
        ))


def test_demo_skill_reads_weak_points(monkeypatch):
    """端到端：技能执行注入薄弱学情 + 回写 skill_run 事件"""
    import asyncio
    from db import memory_store as ms
    from engines.skill_plugin_runtime import SkillPluginRuntime

    _create_demo_skill()
    conn = ms._get_conn()
    conn.execute("DELETE FROM memory_l3_episodic")
    conn.commit()
    # build_memory_context 从 mastery(<0.5) 提取薄弱 → 需同时设置掌握度矩阵
    ms.save_semantic_memory("u_demo", weak_points=["TCP拥塞控制"], mastery={"TCP拥塞控制": 0.3})

    captured: dict = {}
    runtime = SkillPluginRuntime("weak-point-expert")
    _install_capturing_llm(monkeypatch, runtime, captured)

    output = asyncio.run(runtime.execute(
        user_input="讲讲我的薄弱点",
        user_id="u_demo",
        session_id="s1",
        use_memory=True,
        memory_access="read_write",
    ))

    # 1) 薄弱学情注入验证：技能上下文含薄弱词（L2 记忆 → 注入 prompt）
    all_text = str(captured.get("messages", "")) + str(captured.get("text_prompt", ""))
    assert "TCP拥塞控制" in all_text, "薄弱学情未注入技能上下文"

    # 2) 行为记忆回写验证：L3 出现 skill_run 事件（plugin_id 可追踪）
    eps = ms.get_episodes("u_demo", event_type="skill_run", limit=5)
    assert len(eps) >= 1, "执行后未回写 skill_run 事件"
    ev = eps[0].get("event") or {}
    assert ev.get("plugin_id") == "weak-point-expert", "skill_run 事件未带 plugin_id 溯源"


def test_demo_skill_read_only_no_writeback(monkeypatch):
    """权限联动：memory_access=read 时注入薄弱学情但写回被阻止"""
    import asyncio
    from db import memory_store as ms
    from engines.skill_plugin_runtime import SkillPluginRuntime

    _create_demo_skill()
    conn = ms._get_conn()
    conn.execute("DELETE FROM memory_l3_episodic")
    conn.commit()
    ms.save_semantic_memory("u_demo_ro", weak_points=["AVL平衡树"], mastery={"AVL平衡树": 0.3})

    captured: dict = {}
    runtime = SkillPluginRuntime("weak-point-expert")
    _install_capturing_llm(monkeypatch, runtime, captured)

    asyncio.run(runtime.execute(
        user_input="讲讲",
        user_id="u_demo_ro",
        session_id="s2",
        use_memory=True,
        memory_access="read",  # 只读权限（P2② 权限联动）
    ))

    # 注入仍发生（read 允许读）
    all_text = str(captured.get("messages", "")) + str(captured.get("text_prompt", ""))
    assert "AVL平衡树" in all_text, "read 权限应允许注入薄弱学情"

    # 写回被阻止：无 skill_run 事件
    eps = ms.get_episodes("u_demo_ro", event_type="skill_run", limit=5)
    assert len(eps) == 0, "read 权限不应回写行为事件"
