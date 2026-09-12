# ============================================================
# API — 芒得很职·职业素养对抗实训（/api/career/*）
# P0 最窄闭环：场景列表 → 启动 → 逐轮作答 → 结束 → 六维报告
# 与 408 所有路由前缀隔离，互不影响。
# ============================================================

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from shared.auth import get_current_user
from services import career_service
from db import career_store

logger = logging.getLogger("netlearn.career.api")
router = APIRouter(prefix="/career", tags=["career-training"])


# ── 请求模型 ──
class StartRequest(BaseModel):
    scenario_id: str
    difficulty: str = "medium"          # easy/medium/hard
    max_turns: int = 8
    task_id: Optional[str] = None       # 教师任务（自主练习为空）


class AnswerRequest(BaseModel):
    answer: str = Field("", description="学生本轮口头/文字回答")


class EndRequest(BaseModel):
    force: bool = False


class ClassCreateRequest(BaseModel):
    class_name: str = Field(..., min_length=1, max_length=128)


class StudentsImportRequest(BaseModel):
    roster: str = Field(..., description="粘贴文本，每行『学号 姓名』或『姓名』，空格分隔")


class TaskCreateRequest(BaseModel):
    class_id: str
    scenario_id: str
    difficulty: str = "medium"
    max_turns: int = 8
    due_at: Optional[str] = None


class TaskJoinRequest(BaseModel):
    join_code: str = Field(..., min_length=4, max_length=16)


def _check_owner(session_id: str, user: dict) -> dict:
    state = career_store.get_session_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="实训会话不存在")
    if state.get("user_id") != user.get("user_id") and user.get("role") not in ("admin", "teacher"):
        raise HTTPException(status_code=403, detail="无权访问他人实训会话")
    return state


def _require_teacher(user: dict) -> dict:
    """P4 教师端点角色校验：teacher/admin 放行，student 403"""
    if user.get("role") not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="仅教师/管理员可操作")
    return user


def _parse_roster(text: str) -> list[dict]:
    """『学号 姓名』或『姓名』逐行解析；跳过空行与表头"""
    out = []
    for line in (text or "").splitlines():
        parts = line.strip().split(None, 1)
        if not parts:
            continue
        if len(parts) == 2 and not parts[0].isdigit():
            # 首列不是纯数字 → 视为整行是姓名
            out.append({"student_no": "", "name": line.strip()})
        elif len(parts) == 2:
            out.append({"student_no": parts[0], "name": parts[1].strip()})
        else:
            out.append({"student_no": "", "name": parts[0]})
    return out


# ── 场景列表 ──
@router.get("/scenarios")
async def scenarios(user: dict = Depends(get_current_user)):
    return {"scenarios": career_service.list_scenarios()}


# ── 启动一场实训 ──
@router.post("/session/start")
async def start(req: StartRequest, user: dict = Depends(get_current_user)):
    try:
        return await career_service.start_session(
            user_id=user["user_id"], scenario_id=req.scenario_id,
            difficulty=req.difficulty, max_turns=req.max_turns, task_id=req.task_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("启动实训失败")
        raise HTTPException(status_code=500, detail=f"启动失败: {e}")


# ── 推进一轮 ──
@router.post("/session/{session_id}/answer")
async def answer(session_id: str, req: AnswerRequest, user: dict = Depends(get_current_user)):
    _check_owner(session_id, user)
    try:
        return await career_service.answer_turn(session_id, req.answer)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("作答推进失败")
        raise HTTPException(status_code=500, detail=f"处理失败: {e}")


# ── 主动结束并出报告 ──
@router.post("/session/{session_id}/end")
async def end(session_id: str, req: EndRequest, user: dict = Depends(get_current_user)):
    _check_owner(session_id, user)
    try:
        return await career_service.end_session(session_id, force=req.force)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("结束实训失败")
        raise HTTPException(status_code=500, detail=f"结束失败: {e}")


# ── 获取报告（含完整对话与证据链）──
@router.get("/session/{session_id}/report")
async def report(session_id: str, user: dict = Depends(get_current_user)):
    _check_owner(session_id, user)
    try:
        return career_service.get_report(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 我的实训历史 ──
@router.get("/sessions")
async def my_sessions(user: dict = Depends(get_current_user)):
    return {"sessions": career_service.list_my_sessions(user["user_id"])}


# ────────────────────────────────────────────────────────────
# P4 教师端：班级 / 花名册 / 任务（任务码）/ 班级看板
# ────────────────────────────────────────────────────────────

# ── 建班 ──
@router.post("/classes")
async def create_class(req: ClassCreateRequest, user: dict = Depends(get_current_user)):
    _require_teacher(user)
    try:
        return career_store.create_class(user["user_id"], req.class_name.strip())
    except Exception as e:
        logger.exception("建班失败")
        raise HTTPException(status_code=500, detail=f"建班失败: {e}")


# ── 我的班级列表 ──
@router.get("/classes")
async def list_classes(user: dict = Depends(get_current_user)):
    _require_teacher(user)
    return {"classes": career_store.list_classes_by_teacher(user["user_id"])}


# ── 导入花名册（粘贴文本）──
@router.post("/classes/{class_id}/students")
async def import_students(class_id: str, req: StudentsImportRequest,
                          user: dict = Depends(get_current_user)):
    _require_teacher(user)
    try:
        students = _parse_roster(req.roster)
        if not students:
            raise HTTPException(status_code=400, detail="花名册解析为空，请检查格式（每行『学号 姓名』）")
        n = career_store.add_students(class_id, user["user_id"], students)
        return {"imported": n, "students": career_store.list_students(class_id, user["user_id"])}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("花名册导入失败")
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")


# ── 花名册查看 ──
@router.get("/classes/{class_id}/students")
async def get_students(class_id: str, user: dict = Depends(get_current_user)):
    _require_teacher(user)
    try:
        return {"students": career_store.list_students(class_id, user["user_id"])}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── 发任务（生成任务码）──
@router.post("/tasks")
async def create_task(req: TaskCreateRequest, user: dict = Depends(get_current_user)):
    _require_teacher(user)
    try:
        task = career_store.create_task(
            user["user_id"], req.class_id, req.scenario_id,
            difficulty=req.difficulty, max_turns=req.max_turns, due_at=req.due_at)
        sc = next((s for s in career_service.list_scenarios()
                   if s.get("id") == req.scenario_id), {})
        task["scenario_title"] = sc.get("title", "")
        return task
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("发任务失败")
        raise HTTPException(status_code=500, detail=f"发任务失败: {e}")


# ── 我的任务列表（可按班级过滤）──
@router.get("/tasks")
async def list_tasks(class_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_teacher(user)
    return {"tasks": career_store.list_tasks_by_teacher(user["user_id"], class_id)}


# ── 班级学情看板 ──
@router.get("/classes/{class_id}/dashboard")
async def class_dashboard(class_id: str, user: dict = Depends(get_current_user)):
    _require_teacher(user)
    dash = career_store.class_dashboard(class_id, user["user_id"])
    if not dash:
        raise HTTPException(status_code=404, detail="班级不存在或无权查看")
    return dash


# ── 学生凭任务码加入 ──
@router.post("/task/join")
async def join_task(req: TaskJoinRequest, user: dict = Depends(get_current_user)):
    task = career_store.get_task_by_code(req.join_code)
    if not task:
        raise HTTPException(status_code=404, detail="任务码无效")
    bound = career_store.bind_student(task["class_id"], user["user_id"])
    return {"task_id": task["id"], "scenario_id": task["scenario_id"],
            "scenario_type": task.get("scenario_type", ""),
            "difficulty": task.get("difficulty", "medium"),
            "max_turns": int(task.get("max_turns") or 8),
            "class_id": task["class_id"], "roster_bound": bound}
