# -*- coding: utf-8 -*-
"""技能配置持久化回归测试（批8，2026-11-07）

锁定一条**已存在很久却一直静默失效**的缺陷链：

  前端 SkillStudioView 一直提交 memory_access / tools，但
    ① CreateSkillRequest / UpdateSkillRequest 未声明这些字段（Pydantic 默认忽略额外字段）
    ② Skill.to_dict() 未导出 memory_access（详情页「记忆权限」徽章恒不显示）
    ③ Skill.from_dict() 未读 memory_access（导入/导出技能丢权限）
    ④ db skills 表无 tools 等 SKILL.md 字段的列（保存后刷新即丢）
  ⇒ 用户以为设了「无权限」，实际仍是 read_write 读写，属于**安全语义失效**。

本文件把修复后的四环锁住，任何一环被改回去都会红。
"""

import pytest

pytestmark = pytest.mark.unit

META_FIELDS = ("allowed_tools", "disable_model_invocation", "trigger_paths", "tools")


def _skill(**kw):
    from schemas.skills import Skill
    base = dict(name="配置持久化测试", description="批8 回归", system_prompt="你是测试技能。")
    base.update(kw)
    return Skill(**base)


# ── ① schema 投影：to_dict / from_dict ────────────────────────

def test_to_dict_exports_memory_access():
    """to_dict() 必须导出 memory_access —— 漏了会让详情页徽章恒不显示。"""
    raw = _skill(memory_access="none").to_dict()
    assert raw["memory_access"] == "none"


def test_from_dict_keeps_memory_access_and_meta():
    """from_dict(to_dict(x)) 往返不丢权限与工具元数据（导入/导出链路）。"""
    from schemas.skills import Skill
    origin = _skill(
        memory_access="read",
        allowed_tools=["kb_search"],
        disable_model_invocation=True,
        trigger_paths=["tcp/*"],
        tools=[{"type": "function", "function": {"name": "calc"}}],
    )
    restored = Skill.from_dict(origin.to_dict())
    assert restored.memory_access == "read"
    for f in META_FIELDS:
        assert getattr(restored, f) == getattr(origin, f), f


def test_skill_item_out_does_not_filter_memory_access():
    """SkillItemOut 是精确建模的响应模型；不补字段会把 to_dict 的新字段静默过滤。"""
    from api.skills import SkillItemOut
    dumped = SkillItemOut.model_validate(_skill(memory_access="write").to_dict()).model_dump()
    assert dumped["memory_access"] == "write"


# ── ② db 持久化：create / update / 读取 ──────────────────────

def test_db_roundtrip_persists_memory_access_and_meta():
    """db 保存后读回：memory_access 与 4 个 SKILL.md 字段都不能丢。"""
    from db.skill_store import create_skill, get_skill
    saved = create_skill(_skill(
        memory_access="none",
        allowed_tools=["kb_search"],
        disable_model_invocation=True,
        trigger_paths=["tcp/*"],
        tools=[{"type": "function", "function": {"name": "calc"}}],
    ))
    loaded = get_skill(saved.id)
    assert loaded is not None
    assert loaded.memory_access == "none"
    assert loaded.allowed_tools == ["kb_search"]
    assert loaded.disable_model_invocation is True
    assert loaded.trigger_paths == ["tcp/*"]
    assert loaded.tools == [{"type": "function", "function": {"name": "calc"}}]


def test_db_update_persists_changed_config():
    """update 也要写 meta 列，否则编辑保存后刷新仍是旧值。"""
    from db.skill_store import create_skill, get_skill, update_skill
    saved = create_skill(_skill(memory_access="read_write", tools=[{"name": "old"}]))
    loaded = get_skill(saved.id)
    loaded.memory_access = "read"
    loaded.tools = []
    assert update_skill(loaded)

    again = get_skill(saved.id)
    assert again.memory_access == "read"
    assert again.tools == []


def test_meta_from_json_tolerates_legacy_garbage():
    """老库/损坏 JSON 不得抛错：回退空 dict，由 Skill 字段默认值兜底。"""
    from db.skill_store import _meta_from_json
    assert _meta_from_json(None) == {}
    assert _meta_from_json("") == {}
    assert _meta_from_json("{not json") == {}
    assert _meta_from_json("[1,2]") == {}
    assert _meta_from_json('{"tools": [{"name": "t"}]}') == {"tools": [{"name": "t"}]}


# ── ③ API 端到端：请求模型 → 实体 → 持久化 ───────────────────

def test_legacy_table_migration_adds_meta_column():
    """老库（skills 表无 skill_meta_json 列）经 _init_schema 迁移后必须可写。

    生产升级路径：INSERT 语句硬编码了 skill_meta_json 列，若 ALTER 未成功，
    老用户升级后「创建技能」会直接 no such column 报错。此用例锁住该路径。
    """
    from db.skill_store import _get_conn, _init_schema, create_skill, get_skill
    from schemas.skills import Skill

    legacy = """
    CREATE TABLE skills (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        icon TEXT NOT NULL DEFAULT '🤖',
        system_prompt TEXT NOT NULL DEFAULT '',
        llm_channel TEXT NOT NULL DEFAULT 'auto',
        temperature REAL NOT NULL DEFAULT 0.7,
        max_tokens INTEGER NOT NULL DEFAULT 2048,
        kb_ids TEXT NOT NULL DEFAULT '[]',
        rag_enabled INTEGER NOT NULL DEFAULT 1,
        tags TEXT NOT NULL DEFAULT '[]',
        category TEXT NOT NULL DEFAULT 'other',
        version INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'draft',
        memory_access TEXT NOT NULL DEFAULT 'read_write',
        usage_count INTEGER NOT NULL DEFAULT 0,
        user_count INTEGER NOT NULL DEFAULT 0,
        avg_rating REAL NOT NULL DEFAULT 0.0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        published_at TEXT,
        creator_id TEXT NOT NULL DEFAULT '',
        creator_name TEXT NOT NULL DEFAULT '',
        is_official INTEGER NOT NULL DEFAULT 0
    );
    """
    conn = _get_conn()
    conn.execute("DROP TABLE IF EXISTS skills")
    conn.executescript(legacy)
    conn.commit()
    assert "skill_meta_json" not in [
        r[1] for r in conn.execute("PRAGMA table_info(skills)").fetchall()
    ]

    _init_schema(conn)  # 迁移入口（幂等建表 + ALTER 补列）

    assert "skill_meta_json" in [
        r[1] for r in conn.execute("PRAGMA table_info(skills)").fetchall()
    ], "迁移未补列 → 后续 INSERT 必报 no such column"

    saved = create_skill(Skill(name="老库升级", description="迁移", tools=[{"name": "t"}]))
    loaded = get_skill(saved.id)
    assert loaded is not None
    assert loaded.tools == [{"name": "t"}]


def test_api_create_applies_memory_access_and_tools():
    """前端提交的 memory_access/tools 必须真正落库（此前被 Pydantic 静默忽略）。"""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    res = client.post("/api/skills/create", json={
        "name": "API 配置持久化",
        "description": "批8",
        "memory_access": "none",
        "tools": [{"type": "function", "function": {"name": "calc"}}],
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["skill"]["memory_access"] == "none"
    assert body["skill"]["tools"] == [{"type": "function", "function": {"name": "calc"}}]

    # 再 GET 一次，确认不是只在响应里临时拼接
    sid = body["skill"]["id"]
    got = client.get(f"/api/skills/get/{sid}")
    assert got.status_code == 200, got.text
    assert got.json()["skill"]["memory_access"] == "none"


def test_api_update_applies_memory_access():
    """编辑技能时改权限必须生效（此前保存后仍为旧值）。"""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    created = client.post("/api/skills/create", json={
        "name": "API 更新权限", "description": "批8", "memory_access": "read_write",
    }).json()["skill"]

    res = client.post(f"/api/skills/update/{created['id']}", json={"memory_access": "read"})
    assert res.status_code == 200, res.text
    assert res.json()["skill"]["memory_access"] == "read"


@pytest.mark.parametrize("bad", ["all", "rw", "READ", ""])
def test_api_rejects_invalid_memory_access(bad):
    """非法权限值必须 422 —— 不能让任意字符串进库影响运行时权限判定。"""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    res = client.post("/api/skills/create", json={
        "name": f"非法权限-{bad or 'empty'}", "description": "批8", "memory_access": bad,
    })
    assert res.status_code == 422, res.text
