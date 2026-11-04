# -*- coding: utf-8 -*-
"""契约 top5 的响应形状守卫（2026-11-02 契约缺口审计 A 类）。

目的不是「跑通」，而是**锁形状**：这些端点此前无 `response_model`，响应是裸 dict，
前端只能以 `<any>` 消费。补模型后若产出方字段被增/删/改名，本测试立刻红——
而不是让 FastAPI **静默过滤**掉模型外字段（实测：200 但字段消失，不报错）。

来源：deliverables/engineering-assurance/contract-gap-A-class-2026-11-02.md
"""
import pytest

pytestmark = pytest.mark.usefixtures("mock_auth")


def test_subjects_shape(client):
    r = client.get("/api/subjects")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"subjects", "knowledge_graph"}
    assert body["subjects"], "科目不得为空"
    for key, info in body["subjects"].items():
        assert set(info) == {"name", "chapters"}, f"科目 {key} 形状漂移: {set(info)}"

    kg = body["knowledge_graph"]
    assert set(kg) == {"nodes", "edges"}
    if kg["nodes"]:
        assert set(kg["nodes"][0]) == {"id", "label", "group"}
    if kg["edges"]:
        assert set(kg["edges"][0]) == {"source", "target"}


def test_achievement_shape(client):
    r = client.get("/api/achievement/list")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"total", "unlocked_count", "achievements", "stats"}
    assert body["total"] == len(body["achievements"])

    item_keys = {
        "id", "name", "description", "icon", "category", "color",
        "unlocked", "unlockedAt", "progress", "progressLabel",
    }
    for a in body["achievements"]:
        # unlockedAt 必须**始终出现**（未解锁为 null）——这正是补模型后的行为变化
        assert set(a) == item_keys, f"成就 {a.get('id')} 形状漂移: {set(a)}"
        assert a["category"] in {"milestone", "practice", "knowledge", "streak", "master"}


def test_review_summary_shape(client):
    r = client.get("/api/review/summary")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "total_questions", "total_wrong", "overall_accuracy",
        "by_subject", "weak_topics", "wrong_questions", "recommendation",
    }


def test_step_questions_shape(client):
    r = client.get("/api/quiz/step-questions")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"questions", "total"}
    assert body["total"] == len(body["questions"])
    assert body["questions"], "步骤题不得为空"
    for q in body["questions"]:
        assert set(q) == {
            "id", "subject", "chapter", "difficulty", "question_text", "step_count",
        }, f"题目 {q.get('id')} 形状漂移: {set(q)}"


def test_students_overview_shape(client):
    r = client.get("/api/teacher/students/overview")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "total_students", "active_today", "avg_mastery", "avg_progress", "students",
    }
    for s in body["students"]:
        assert set(s) == {"id", "name", "progress", "mastery", "last_active"}


def test_openapi_declares_response_schemas():
    """OpenAPI 层守卫：五个端点必须声明具体 200 schema（不是空 {}）。

    防的是「有人把 response_model 摘掉」——此时上面的形状测试可能仍绿
    （dict 照旧返回），但前端类型生成会退回 any。
    """
    from main import app

    spec = app.openapi()
    targets = {
        "/api/subjects": "SubjectsResponse",
        "/api/achievement/list": "AchievementListResponse",
        "/api/review/summary": "ReviewSummaryResponse",
        "/api/quiz/step-questions": "StepQuestionListResponse",
        "/api/teacher/students/overview": "StudentsOverviewResponse",
    }
    for path, model in targets.items():
        schema = spec["paths"][path]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        ref = schema.get("$ref", "")
        assert ref.endswith("/" + model), f"{path} 的 200 schema 不是 {model}：{schema}"
