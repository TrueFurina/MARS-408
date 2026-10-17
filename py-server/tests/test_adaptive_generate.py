# ============================================================
# 单元测试：P2 自适应选题 API 层连线（api/quiz.py）
#
# 背景：test_adaptive_quiz.py 已覆盖纯逻辑层
# （filter_questions_for_weak_points / weak_points_from_history /
# detect_weak_points 组合），但 API 层此前零覆盖：
#   - api/quiz.py::_adaptive_candidates 两层数据源与降级契约：
#       1) 语义掌握度 mastery → detect_weak_points；
#       2) mastery 为空 → 答题历史按科目正确率推断；
#       3) 任意异常或无可匹配薄弱点 → 返回 []，调用方回退常规选题。
#   - POST /quiz/generate 端点：normal 模式科目/难度过滤、count 截断、
#     未知科目空信封；adaptive 模式命中薄弱科目；HTTP 层依赖装配。
#
# 设计纪律（与 test_remediation_wiring.py 一脉相承）：
#   - 无 LLM / 无网络 / 无真实 DB 写入：db.memory_store.get_semantic_memory、
#     db.profile_store.get_quiz_history 均以 monkeypatch 替身接管
#     （两者都是被调函数内 import 的模块属性，patch 模块属性即生效）。
#   - config 走真实代码路径，仅 monkeypatch load_config 供数。
#   - random.sample 的不确定性用「科目集合隶属」与「数量」断言化解，
#     不断言具体抽中哪些题。
#
# 运行：python -m pytest tests/test_adaptive_generate.py -v
# ============================================================

import os
import sys

import pytest

# 确保 py-server 根目录在 sys.path，使 `from api import quiz` 等可用
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.unit

import config as config_mod  # noqa: E402
from api.quiz import GenerateQuizRequest, _adaptive_candidates, generate_quiz  # noqa: E402

# ── 防污染预导入（2026-10-17 实测事故修复）──────────────────────────
# _adaptive_candidates / _weak_points_from_history 均在函数体内
# `from db.memory_store import ...` / `from db.profile_store import ...`。
# 若这些模块在 patch 生效期间才被首次导入，其模块级 from-import 绑定
# 可能把测试替身永久抄进自身命名空间（monkeypatch 只撤销模块属性，
# 管不到副本）⇒ 后续测试假红。顶部先导入，确保 patch 只影响模块属性。
import db.memory_store  # noqa: E402,F401
import db.profile_store  # noqa: E402,F401

# ── 题库实况（engines/quiz_engine.py::STEP_QUESTIONS，共 9 题）──
#   computer_network:      hard×1, medium×1
#   data_structures:       medium×3
#   computer_organization: hard×1, easy×1
#   operating_system:      medium×2

TEST_USER = {"user_id": "u_adaptive_test", "role": "student"}


def _patch_config(monkeypatch, threshold: float = 0.6, max_points: int = 3):
    """让 config 两个 remediation getter 走指定阈值（真实代码路径供数）。"""
    monkeypatch.setattr(
        config_mod, "load_config",
        lambda: {"remediation_threshold": threshold, "remediation_max_points": max_points},
    )


def _patch_memory(monkeypatch, mastery: dict | None = None, raises: BaseException | None = None):
    """替身 db.memory_store.get_semantic_memory。

    mastery: 返回 {"mastery": {...}}；raises 非空时读取抛异常（降级路径）。
    """

    def _mem(user_id):
        if raises is not None:
            raise raises
        return {"mastery": mastery if mastery is not None else {}}

    monkeypatch.setattr("db.memory_store.get_semantic_memory", _mem)


def _patch_history(monkeypatch, history: list[dict]):
    """替身 db.profile_store.get_quiz_history（掌握度回退数据源）。"""
    monkeypatch.setattr("db.profile_store.get_quiz_history", lambda user_id: history)


def _req(subject="computer_network", difficulty="medium", count=3, mode="normal") -> GenerateQuizRequest:
    return GenerateQuizRequest(subject=subject, difficulty=difficulty, count=count, mode=mode)


# ════════════════════════════════════════════════════════════
# 1. normal 模式：科目/难度过滤、count 截断、未知科目空信封
# ════════════════════════════════════════════════════════════

async def test_normal_mode_filters_subject_and_difficulty():
    """normal 模式：仅返回所请科目 + 所请难度的题。"""
    resp = await generate_quiz(_req(subject="computer_network", difficulty="hard", count=5), TEST_USER)
    assert resp["total"] == 1  # computer_network 仅 1 道 hard
    assert all(q["subject"] == "computer_network" and q["difficulty"] == "hard"
               for q in resp["questions"])


async def test_normal_mode_count_below_pool():
    """normal 模式：count < 题库量时严格按 count 返回。"""
    resp = await generate_quiz(_req(subject="data_structures", difficulty="medium", count=2), TEST_USER)
    assert resp["total"] == 2  # data_structures 共 3 道 medium，抽 2
    assert all(q["subject"] == "data_structures" for q in resp["questions"])


async def test_normal_mode_difficulty_all_keeps_all_difficulties():
    """normal 模式：difficulty='all' 跳过难度过滤。"""
    resp = await generate_quiz(
        _req(subject="computer_organization", difficulty="all", count=10), TEST_USER)
    assert resp["total"] == 2  # hard×1 + easy×1
    assert {q["difficulty"] for q in resp["questions"]} == {"hard", "easy"}


async def test_unknown_subject_returns_empty_envelope():
    """未知科目：候选与降级双空 → 空信封（questions=[] total=0），不抛错。"""
    resp = await generate_quiz(_req(subject="no_such_subject", count=3), TEST_USER)
    assert resp == {"questions": [], "total": 0, "subject": "no_such_subject"}


# ════════════════════════════════════════════════════════════
# 2. adaptive 模式：薄弱科目命中（两层数据源）
# ════════════════════════════════════════════════════════════

async def test_adaptive_candidates_target_weak_subjects_from_mastery(monkeypatch):
    """数据源①：mastery 低于阈值 → 只出薄弱科目题（不含所请的强科目）。"""
    _patch_config(monkeypatch, threshold=0.6, max_points=3)
    _patch_memory(monkeypatch, mastery={
        "computer_network": 0.3, "operating_system": 0.2, "data_structures": 0.9,
    })
    cands = _adaptive_candidates(
        _req(subject="data_structures", difficulty="all", mode="adaptive"), TEST_USER)
    assert cands, "薄弱科目在题库中应匹配到题"
    subjects = {q.subject for q in cands}
    assert subjects <= {"computer_network", "operating_system"}
    assert "data_structures" not in subjects, "强科目不得被自适应选中"


async def test_adaptive_generate_hits_weak_subjects(monkeypatch):
    """端点级：adaptive 模式下即使请求强科目，也返回薄弱科目题。"""
    _patch_config(monkeypatch, threshold=0.6, max_points=3)
    _patch_memory(monkeypatch, mastery={
        "computer_network": 0.3, "operating_system": 0.2, "data_structures": 0.9,
    })
    resp = await generate_quiz(
        _req(subject="data_structures", difficulty="all", count=10, mode="adaptive"), TEST_USER)
    assert resp["questions"], "薄弱科目题不应为空"
    assert all(q["subject"] in ("computer_network", "operating_system") for q in resp["questions"])


async def test_mastery_empty_falls_back_to_quiz_history(monkeypatch):
    """数据源②：mastery 为空 → 按答题历史正确率推断薄弱科目。"""
    _patch_config(monkeypatch, threshold=0.6, max_points=3)
    _patch_memory(monkeypatch, mastery={})  # 语义掌握度空
    _patch_history(monkeypatch, [
        {"subject": "computer_network", "correct": True, "difficulty": "medium"},
        {"subject": "computer_network", "correct": True, "difficulty": "hard"},
        {"subject": "data_structures", "correct": False, "difficulty": "medium"},
        {"subject": "data_structures", "correct": False, "difficulty": "medium"},
    ])
    cands = _adaptive_candidates(
        _req(subject="computer_network", difficulty="all", mode="adaptive"), TEST_USER)
    assert cands, "历史推断出的薄弱科目应匹配到题"
    assert all(q.subject == "data_structures" for q in cands), \
        "data_structures 正确率 0.0 → 唯一薄弱科目"


async def test_no_weak_points_degrades_to_normal_selection(monkeypatch):
    """两层数据源均无薄弱点 → _adaptive_candidates 返回 [] → 端点回退常规选题。"""
    _patch_config(monkeypatch, threshold=0.6, max_points=3)
    _patch_memory(monkeypatch, mastery={
        "computer_network": 0.95, "data_structures": 0.95, "operating_system": 0.95,
    })
    _patch_history(monkeypatch, [
        {"subject": "data_structures", "correct": True, "difficulty": "medium"},
        {"subject": "data_structures", "correct": True, "difficulty": "medium"},
    ])
    assert _adaptive_candidates(
        _req(subject="data_structures", mode="adaptive"), TEST_USER) == []
    # 端点降级：按所请科目/难度常规选题
    resp = await generate_quiz(
        _req(subject="data_structures", difficulty="medium", count=10, mode="adaptive"), TEST_USER)
    assert resp["total"] == 3
    assert all(q["subject"] == "data_structures" and q["difficulty"] == "medium"
               for q in resp["questions"])


async def test_memory_read_failure_degrades_to_normal_selection(monkeypatch):
    """掌握度读取抛异常 → 异常路径返回 [] → 端点回退常规选题（不 500）。

    降级契约（api/quiz.py:610-612 注释「降级：仅按科目筛选」）：
    候选为空时回退**只按科目过滤，难度过滤被有意丢弃**——
    宁可给本科目其它难度题，不空手而归。
    """
    _patch_config(monkeypatch)
    _patch_memory(monkeypatch, raises=RuntimeError("db down"))
    _patch_history(monkeypatch, [])
    assert _adaptive_candidates(
        _req(subject="computer_network", mode="adaptive"), TEST_USER) == []
    resp = await generate_quiz(
        _req(subject="computer_network", difficulty="medium", count=10, mode="adaptive"), TEST_USER)
    assert resp["total"] == 2  # 降级仅按科目：computer_network 全部 2 题（hard+medium）
    assert all(q["subject"] == "computer_network" for q in resp["questions"])


async def test_normal_mode_difficulty_miss_degrades_to_subject_only():
    """normal 模式：题库无所请难度 → 回退该科目全部题（难度过滤丢弃，非空信封）。"""
    resp = await generate_quiz(_req(subject="computer_network", difficulty="easy", count=10), TEST_USER)
    assert resp["total"] == 2  # computer_network 无 easy 题 → hard+medium 均返回
    assert {q["difficulty"] for q in resp["questions"]} == {"hard", "medium"}


# ════════════════════════════════════════════════════════════
# 3. HTTP 层：端点依赖装配与响应信封
# ════════════════════════════════════════════════════════════

def test_http_layer_adaptive_envelope(client, monkeypatch):
    """POST /quiz/generate?mode=adaptive 经 TestClient 全链：认证/限流依赖 +
    路由 + 响应信封（题目字段含 steps，且 steps 不含答案）。"""
    _patch_config(monkeypatch, threshold=0.6, max_points=3)
    _patch_memory(monkeypatch, mastery={"data_structures": 0.1, "computer_network": 0.95})
    resp = client.post("/api/quiz/generate", json={
        "subject": "computer_network", "difficulty": "all", "count": 3, "mode": "adaptive",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert all(q["subject"] == "data_structures" for q in data["questions"]), \
        "mastery 仅 data_structures 薄弱 → 只出该科题"
    q0 = data["questions"][0]
    for key in ("id", "subject", "chapter", "difficulty", "question_text", "steps"):
        assert key in q0, f"题目字段缺失: {key}"
    assert q0["steps"], "步骤化题目应携带 steps"
    assert all("answer" not in s for s in q0["steps"]), "steps 不得泄漏答案"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
