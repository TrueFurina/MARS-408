# ============================================================
# 单元测试：P1 闭环触发 API 连线（api/quiz.py + config getters）
#
# 背景：services/remediation.py::detect_weak_points（纯函数）已有 12 例覆盖，
# 但 API 层连线此前零覆盖：
#   - config.get_remediation_threshold / get_remediation_max_points（默认/覆盖/非法回退）
#   - api/quiz.py::_generate_remediation 六条降级路径（max_points<=0 / 掌握度读取失败 /
#     无薄弱点 / 技能缺失 / runtime 异常 / 正常产出）
#   - quiz_submit 集成（响应含 remediation 字段；整体失败降级为 []）
#
# 设计纪律（与 test_remediation.py 一脉相承）：
#   - 无 LLM / 无网络 / 无真实 DB 写入：db.memory_store.get_semantic_memory、
#     db.skill_store.get_skill/get_template、engines.skill_plugin_runtime.
#     SkillPluginRuntime 全部以 monkeypatch 替身接管（_generate_remediation
#     的这些依赖均为函数内 import，patch 模块属性即生效）。
#   - config 两个 getter 走真实代码路径，仅 monkeypatch load_config 供数。
#
# 运行：python -m pytest tests/test_remediation_wiring.py -v
# ============================================================

import os
import sys
from types import SimpleNamespace

import pytest

# 确保 py-server 根目录在 sys.path，使 `from api import quiz` 等可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.unit

import config as config_mod  # noqa: E402
from api import quiz as quiz_api  # noqa: E402
from models import RemediationItem  # noqa: E402

# ── 防污染预导入（2026-10-17 实测事故修复）──────────────────────────
# 下列模块在**模块级** from-import 了本文件 patch 的符号：
#   engines.skill_plugin_runtime: from db.skill_store import get_skill
#   agents.skill_agent:            from db.skill_store import get_skill, ...
#   shared/container、services/import_worker、api/config_routes、
#   api/llm_health:                from config import load_config
# 若某模块在 patch 生效期间才被【首次导入】，它的模块级绑定会把测试替身
# （lambda/假函数）永久抄进自身命名空间——monkeypatch 只撤销模块属性，
# 管不到已绑定的副本 ⇒ 后续测试（如 test_demo_skill_memory 的
# SkillPluginRuntime.execute）拿到替身 → "技能不存在" 假失败。
# 在模块顶部先导入，确保这些绑定是原版函数，patch 只影响模块属性。
import engines.skill_plugin_runtime  # noqa: E402,F401
import agents.skill_agent  # noqa: E402,F401
import shared.container  # noqa: E402,F401
import services.import_worker  # noqa: E402,F401
import api.config_routes  # noqa: E402,F401
import api.llm_health  # noqa: E402,F401
import db.memory_store  # noqa: E402,F401
import db.skill_store  # noqa: E402,F401


# ── 辅助：fake 技能 / 模板 / 运行时 ──

def _fake_skill(system_prompt: str = "你是薄弱点讲解专家，请讲清 {{subject}}。"):
    """替身 db.skill_store.get_skill 返回值：需提供 .to_dict()。"""
    return SimpleNamespace(to_dict=lambda: {
        "id": "weak-point-expert",
        "name": "薄弱点专项讲解师",
        "system_prompt": system_prompt,
        "memory_access": "read_write",
    })


def _fake_template(system_prompt_template: str = "模板讲解 {{subject}} 的核心概念。"):
    """替身 db.skill_store.get_template 返回值（模板回退路径）。"""
    return SimpleNamespace(
        id="weak-point-expert",
        name="薄弱点专项讲解师(模板)",
        system_prompt_template=system_prompt_template,
        default_config={"llm_channel": "auto", "temperature": 0.6, "max_tokens": 1500},
    )


class _FakeRuntime:
    """替身技能运行时实例：记录 execute 调用，按预设行为返回/抛错。

    behavior 可为：异常实例（抛出）/ 可调用异步函数（await 后返回，
    用于并发屏障测试）/ 其他值（作为讲解文本返回）。
    """

    def __init__(self):
        self.calls: list[dict] = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        behavior = _FakeRuntimeCls.behavior
        if isinstance(behavior, BaseException):
            raise behavior
        if callable(behavior):
            return await behavior(**kwargs)
        return behavior


class _FakeRuntimeCls:
    """替身 engines.skill_plugin_runtime.SkillPluginRuntime。

    _generate_remediation 以 `SkillPluginRuntime.get(id)` 类方法取实例，
    故替身同样提供类方法 get；behavior 为 BaseException 时 execute 抛出，
    为可调用异步函数时 await 调用，否则作为讲解文本返回。
    """

    behavior = "针对该薄弱知识点的标准讲解内容"
    instance: _FakeRuntime | None = None

    @classmethod
    def get(cls, skill_id):
        if cls.instance is None:
            cls.instance = _FakeRuntime()
        return cls.instance

    @classmethod
    def reset(cls, behavior="针对该薄弱知识点的标准讲解内容"):
        cls.behavior = behavior
        cls.instance = None


def _patch_remediation_deps(monkeypatch, *, config=None, memory=None,
                            memory_raises=None, skill=None, template=None,
                            runtime_behavior="针对该薄弱知识点的标准讲解内容"):
    """统一装配 _generate_remediation 的全部外部依赖替身。

    Args:
        config: load_config 返回值（None → 不含 remediation 键，走默认值）
        memory: get_semantic_memory 返回值（需含 mastery 键）
        memory_raises: 非 None 时 get_semantic_memory 抛出该异常
        skill: get_skill 返回值（None → 官方技能缺失）
        template: get_template 返回值（None → 模板缺失）
        runtime_behavior: 假 runtime 的 execute 行为（异常实例 → 抛出）
    """
    cfg = dict(config or {})
    monkeypatch.setattr(config_mod, "load_config", lambda: cfg)

    def _mem(user_id):
        if memory_raises is not None:
            raise memory_raises
        return memory if memory is not None else {}

    monkeypatch.setattr("db.memory_store.get_semantic_memory", _mem)
    monkeypatch.setattr("db.skill_store.get_skill", lambda skill_id: skill)
    monkeypatch.setattr("db.skill_store.get_template", lambda tid: template)
    _FakeRuntimeCls.reset(runtime_behavior)
    monkeypatch.setattr("engines.skill_plugin_runtime.SkillPluginRuntime", _FakeRuntimeCls)


# ════════════════════════════════════════════════════════════
# 1. config getters（config.py:344-357）
# ════════════════════════════════════════════════════════════

def test_remediation_threshold_default():
    """配置缺失时阈值默认 0.6。"""
    monkey = pytest.MonkeyPatch()
    monkey.setattr(config_mod, "load_config", lambda: {})
    try:
        assert config_mod.get_remediation_threshold() == 0.6
    finally:
        monkey.undo()


def test_remediation_threshold_override():
    """配置显式覆盖阈值（含字符串数字，float() 可解析）。"""
    monkey = pytest.MonkeyPatch()
    monkey.setattr(config_mod, "load_config", lambda: {"remediation_threshold": "0.75"})
    try:
        assert config_mod.get_remediation_threshold() == pytest.approx(0.75)
    finally:
        monkey.undo()


def test_remediation_threshold_invalid_falls_back():
    """非法阈值（非数字字符串 / None）回退 0.6，不抛异常。"""
    monkey = pytest.MonkeyPatch()
    monkey.setattr(config_mod, "load_config", lambda: {"remediation_threshold": "abc"})
    try:
        assert config_mod.get_remediation_threshold() == 0.6
    finally:
        monkey.undo()
    monkey.setattr(config_mod, "load_config", lambda: {"remediation_threshold": None})
    try:
        assert config_mod.get_remediation_threshold() == 0.6
    finally:
        monkey.undo()


def test_remediation_max_points_default():
    """配置缺失时单次最多讲解 3 个薄弱点。"""
    monkey = pytest.MonkeyPatch()
    monkey.setattr(config_mod, "load_config", lambda: {})
    try:
        assert config_mod.get_remediation_max_points() == 3
    finally:
        monkey.undo()


def test_remediation_max_points_override():
    """配置显式覆盖 max_points（含字符串数字）。"""
    monkey = pytest.MonkeyPatch()
    monkey.setattr(config_mod, "load_config", lambda: {"remediation_max_points": "5"})
    try:
        assert config_mod.get_remediation_max_points() == 5
    finally:
        monkey.undo()


def test_remediation_max_points_invalid_falls_back():
    """非法 max_points 回退 3；0 / 负数为合法值原样返回（由调用方关闭闭环）。"""
    monkey = pytest.MonkeyPatch()
    monkey.setattr(config_mod, "load_config", lambda: {"remediation_max_points": "not-a-number"})
    try:
        assert config_mod.get_remediation_max_points() == 3
    finally:
        monkey.undo()
    monkey.setattr(config_mod, "load_config", lambda: {"remediation_max_points": 0})
    try:
        assert config_mod.get_remediation_max_points() == 0
    finally:
        monkey.undo()
    monkey.setattr(config_mod, "load_config", lambda: {"remediation_max_points": -2})
    try:
        assert config_mod.get_remediation_max_points() == -2
    finally:
        monkey.undo()


# ════════════════════════════════════════════════════════════
# 2. _generate_remediation 降级路径（api/quiz.py:123-188）
# ════════════════════════════════════════════════════════════

async def test_max_points_zero_returns_empty_without_touching_memory(monkeypatch):
    """max_points<=0（闭环关闭）→ 早退 []，且不读取掌握度。

    注意：断言必须用「记录型」探针而非抛出型——_generate_remediation 对
    掌握度读取异常有 try/except 降级，抛出型探针会被吞掉、无法区分早退与降级。
    """
    _patch_remediation_deps(monkeypatch, config={"remediation_max_points": 0})

    called: list[str] = []

    def _spy(user_id):
        called.append(user_id)
        return {}

    monkeypatch.setattr("db.memory_store.get_semantic_memory", _spy)
    assert await quiz_api._generate_remediation("u1") == []
    assert called == [], "max_points<=0 时应早退，不应读取语义记忆"


async def test_max_points_negative_returns_empty(monkeypatch):
    """负数 max_points 同样关闭闭环。"""
    _patch_remediation_deps(monkeypatch, config={"remediation_max_points": -3})

    called: list[str] = []

    def _spy(user_id):
        called.append(user_id)
        return {}

    monkeypatch.setattr("db.memory_store.get_semantic_memory", _spy)
    assert await quiz_api._generate_remediation("u1") == []
    assert called == []


async def test_mastery_read_failure_returns_empty(monkeypatch):
    """掌握度读取异常 → 降级 []（绝不向 quiz_submit 抛错）。"""
    _patch_remediation_deps(
        monkeypatch, memory_raises=RuntimeError("db down"))
    assert await quiz_api._generate_remediation("u1") == []


async def test_missing_or_empty_mastery_returns_empty(monkeypatch):
    """mastery 缺失 / 为空 dict → []。"""
    _patch_remediation_deps(monkeypatch, memory={"profile": {}})
    assert await quiz_api._generate_remediation("u1") == []
    _patch_remediation_deps(monkeypatch, memory={"mastery": {}})
    assert await quiz_api._generate_remediation("u1") == []
    _patch_remediation_deps(monkeypatch, memory={"mastery": None})
    assert await quiz_api._generate_remediation("u1") == []


async def test_no_weak_points_returns_empty(monkeypatch):
    """全部知识点掌握度不低于阈值 → 无薄弱点 → []（不触发任何讲解）。"""
    _patch_remediation_deps(
        monkeypatch,
        config={"remediation_threshold": 0.6},
        memory={"mastery": {"tcp": 0.9, "ip": 0.6}},  # 等于阈值不算薄弱
        skill=_fake_skill(), template=_fake_template(),
    )
    assert await quiz_api._generate_remediation("u1") == []
    # 未实例化假 runtime ⇒ 未触发讲解
    assert _FakeRuntimeCls.instance is None


async def test_threshold_from_config_respected(monkeypatch):
    """阈值取自 config getter：0.9 阈值下 0.85 的点也算薄弱。"""
    _patch_remediation_deps(
        monkeypatch,
        config={"remediation_threshold": 0.9, "remediation_max_points": 3},
        memory={"mastery": {"tcp": 0.85, "ip": 0.95}},
        skill=_fake_skill(), template=_fake_template(),
    )
    items = await quiz_api._generate_remediation("u1")
    assert [it.knowledge_point for it in items] == ["tcp"]


async def test_skill_and_template_missing_yields_none_explanations(monkeypatch):
    """官方技能与模板均缺失 → 每项 explanation=None，且不实例化 runtime。"""
    _patch_remediation_deps(
        monkeypatch,
        memory={"mastery": {"tcp": 0.2, "ip": 0.3}},
        skill=None, template=None,
    )
    items = await quiz_api._generate_remediation("u1")
    assert [it.knowledge_point for it in items] == ["tcp", "ip"]  # 升序
    assert all(it.explanation is None for it in items)
    assert _FakeRuntimeCls.instance is None


async def test_runtime_failure_yields_none_explanation_but_keeps_item(monkeypatch):
    """runtime.execute 抛错 → 该项 explanation=None，其余项不受影响。"""
    _patch_remediation_deps(
        monkeypatch,
        memory={"mastery": {"tcp": 0.2}},
        skill=_fake_skill(), template=_fake_template(),
        runtime_behavior=RuntimeError("llm circuit open"),
    )
    items = await quiz_api._generate_remediation("u1")
    assert len(items) == 1
    assert items[0].knowledge_point == "tcp"
    assert items[0].explanation is None


async def test_happy_path_fills_explanations_in_weakness_order(monkeypatch):
    """正常路径：每个薄弱点产出 explanation（按掌握度升序、受 max_points 截断）。"""
    _patch_remediation_deps(
        monkeypatch,
        config={"remediation_threshold": 0.6, "remediation_max_points": 2},
        memory={"mastery": {"a": 0.5, "b": 0.1, "c": 0.3, "ok": 0.8}},
        skill=_fake_skill(), template=_fake_template(),
        runtime_behavior="标准讲解内容",
    )
    items = await quiz_api._generate_remediation("u1")
    # b(0.1) < c(0.3) < a(0.5)，截断到 2 个；ok(0.8) 不薄弱
    assert [it.knowledge_point for it in items] == ["b", "c"]
    assert all(it.explanation == "标准讲解内容" for it in items)
    assert len(_FakeRuntimeCls.instance.calls) == 2


async def test_execute_kwargs_passthrough(monkeypatch):
    """execute 收到 user_id / use_memory=True / memory_access=read_write / session_id=""。"""
    _patch_remediation_deps(
        monkeypatch,
        memory={"mastery": {"tcp": 0.2}},
        skill=_fake_skill(), template=_fake_template(),
    )
    await quiz_api._generate_remediation("u_test_passthrough")
    calls = _FakeRuntimeCls.instance.calls
    assert len(calls) == 1
    kw = calls[0]
    assert kw["user_id"] == "u_test_passthrough"
    assert kw["session_id"] == ""
    assert kw["use_memory"] is True
    assert kw["memory_access"] == "read_write"
    assert "tcp" in kw["user_input"]


async def test_subject_placeholder_filled_in_system_prompt(monkeypatch):
    """技能 system_prompt 的 {{subject}} 占位符在 execute 前被替换为知识点名。"""
    _patch_remediation_deps(
        monkeypatch,
        memory={"mastery": {"tcp": 0.2}},
        skill=_fake_skill("你是专家，讲解 {{subject}} 的薄弱点。"),
        template=_fake_template(),
    )
    await quiz_api._generate_remediation("u1")
    kw = _FakeRuntimeCls.instance.calls[0]
    prompt = kw["system_prompt_override"]
    assert "{{subject}}" not in prompt
    assert "tcp" in prompt


async def test_template_fallback_used_when_skill_missing(monkeypatch):
    """官方技能缺失 → 回退模板；模板 system_prompt 同样走占位符替换。"""
    _patch_remediation_deps(
        monkeypatch,
        memory={"mastery": {"tcp": 0.2}},
        skill=None,
        template=_fake_template("模板：讲清 {{subject}}。"),
    )
    items = await quiz_api._generate_remediation("u1")
    assert items[0].explanation == "针对该薄弱知识点的标准讲解内容"
    kw = _FakeRuntimeCls.instance.calls[0]
    assert "{{subject}}" not in kw["system_prompt_override"]
    assert "tcp" in kw["system_prompt_override"]


async def test_empty_explanation_normalized_to_none(monkeypatch):
    """execute 返回空串 → explanation 归一化为 None（or None 兜底）。"""
    _patch_remediation_deps(
        monkeypatch,
        memory={"mastery": {"tcp": 0.2}},
        skill=_fake_skill(), template=_fake_template(),
        runtime_behavior="",
    )
    items = await quiz_api._generate_remediation("u1")
    assert items[0].explanation is None


# ── OpenAI 格式 dict 响应提取（2026-10-17 实测事故修复） ──
# SkillPluginRuntime.execute 透传 LLMProvider.chat 的原始响应 dict
# （{"choices":[{"message":{"content": ...}}]}），而 RemediationItem.
# explanation 类型为 Optional[str]。直赋会把整个 dict 塞进 API 响应
# （Pydantic 序列化告警 + 前端拿到非字符串），必须在消费边界提取纯文本。
# 本组用例对未修复实现应为红灯（test-first ground truth）。

_OPENAI_STYLE = {
    "choices": [{"message": {"role": "assistant", "content": "这是薄弱点讲解正文"}}]
}


async def test_dict_response_extracted_to_text(monkeypatch):
    """execute 返回 OpenAI 格式 dict → explanation 提取为纯文本。"""
    _patch_remediation_deps(
        monkeypatch,
        memory={"mastery": {"tcp": 0.2}},
        skill=_fake_skill(), template=_fake_template(),
        runtime_behavior=_OPENAI_STYLE,
    )
    items = await quiz_api._generate_remediation("u1")
    assert items[0].explanation == "这是薄弱点讲解正文"


async def test_malformed_dict_response_yields_none(monkeypatch):
    """execute 返回结构不符的 dict → explanation=None（降级，不泄漏原始结构）。"""
    _patch_remediation_deps(
        monkeypatch,
        memory={"mastery": {"tcp": 0.2}},
        skill=_fake_skill(), template=_fake_template(),
        runtime_behavior={"unexpected": "shape"},
    )
    items = await quiz_api._generate_remediation("u1")
    assert items[0].explanation is None


def test_extract_llm_text_helper_directly():
    """_extract_llm_text 边界：None / str / 空串 / dict / 非 str content。"""
    f = quiz_api._extract_llm_text
    assert f(None) is None
    assert f("文本") == "文本"
    assert f("") is None
    assert f(_OPENAI_STYLE) == "这是薄弱点讲解正文"
    assert f({"unexpected": 1}) is None
    assert f({"choices": [{"message": {"content": None}}]}) is None
    assert f({"choices": [{"message": {"content": 42}}]}) is None
    assert f({"choices": "not-a-list"}) is None
    assert f([1, 2, 3]) is None  # 非 dict 非 str → 降级 None


# ── 并发生成（2026-10-17 冒烟实测：3 薄弱点串行 await 实测 24.2s） ──
# 串行实现下每个 execute 依次等待 LLM，N 个薄弱点耗时≈N×单次；
# 并发实现下总耗时≈单次。用「同时在途屏障」做确定性判定（不依赖时钟）：
# 全部 N 个 execute 同时在途才放行 —— 串行实现下首调用永久等待 →
# wait_for 超时 → 红灯；并发实现下齐步放行 → 绿灯。

async def test_remediation_generates_concurrently(monkeypatch):
    """3 个薄弱点的讲解必须并发生成（屏障不到齐即超时）。"""
    import asyncio

    n_points = 3
    in_flight = 0
    release = asyncio.Event()

    async def _barriered(**kwargs):
        nonlocal in_flight
        in_flight += 1
        if in_flight >= n_points:
            release.set()
        await release.wait()  # 串行实现下此处永久挂起
        return "并发讲解内容"

    _patch_remediation_deps(
        monkeypatch,
        memory={"mastery": {"a": 0.1, "b": 0.2, "c": 0.3}},
        skill=_fake_skill(), template=_fake_template(),
        runtime_behavior=_barriered,
    )
    items = await asyncio.wait_for(quiz_api._generate_remediation("u1"), timeout=15)
    # gather 保序：按掌握度升序
    assert [it.knowledge_point for it in items] == ["a", "b", "c"]
    assert all(it.explanation == "并发讲解内容" for it in items)


async def test_concurrent_generation_keeps_per_item_degradation(monkeypatch):
    """并发下一个 execute 抛错不影响其他项（逐项降级语义保持）。"""
    import asyncio

    async def _mixed(**kwargs):
        if "「b」" in kwargs["user_input"]:
            raise RuntimeError("单点失败")
        return "正常讲解"

    _patch_remediation_deps(
        monkeypatch,
        memory={"mastery": {"a": 0.1, "b": 0.2, "c": 0.3}},
        skill=_fake_skill(), template=_fake_template(),
        runtime_behavior=_mixed,
    )
    items = await asyncio.wait_for(quiz_api._generate_remediation("u1"), timeout=15)
    assert [it.knowledge_point for it in items] == ["a", "b", "c"]
    assert [it.explanation for it in items] == ["正常讲解", None, "正常讲解"]


# ════════════════════════════════════════════════════════════
# 3. quiz_submit 集成（api/quiz.py:298-311）
# ════════════════════════════════════════════════════════════

def _submit_client(monkeypatch):
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def test_quiz_submit_response_includes_remediation(monkeypatch):
    """quiz_submit 响应含 remediation 字段，内容来自 _generate_remediation。"""

    async def _fake_gen(user_id):
        assert user_id  # 传入的是请求用户 id
        return [RemediationItem(knowledge_point="tcp", explanation="讲解内容")]

    monkeypatch.setattr(quiz_api, "_generate_remediation", _fake_gen)
    resp = _submit_client(monkeypatch).post(
        "/api/quiz/submit",
        json={"profile": {}, "records": [{"subject": "network", "correct": False}]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["remediation"] == [
        {"knowledge_point": "tcp", "explanation": "讲解内容"}
    ]


def test_quiz_submit_remediation_failure_degrades_to_empty(monkeypatch):
    """_generate_remediation 整体抛错 → 降级 remediation=[]，答题响应仍 200。"""

    async def _boom(user_id):
        raise RuntimeError("闭环讲解整体失败")

    monkeypatch.setattr(quiz_api, "_generate_remediation", _boom)
    resp = _submit_client(monkeypatch).post(
        "/api/quiz/submit",
        json={"profile": {}, "records": [{"subject": "network", "correct": True}]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["remediation"] == []
    # 既有响应字段不受影响
    assert data["total"] == 1
    assert data["correct_count"] == 1
