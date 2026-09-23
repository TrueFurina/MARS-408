# ============================================================
# API — 职业素养测评（对照实验载体模块）
# 六维软素养行为题：前后测（pre/post）+ 维度分档计分 + 班级聚合
# 口径：软素养行为题无标准答案，采用维度分档计分（非对错制）
# ============================================================

import json
import logging
import os
import sqlite3
import threading
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("netlearn.literacy")

router = APIRouter(prefix="/literacy", tags=["literacy-assessment"])

# ------------------------------------------------------------
# 六维素养定义（与 MARS-408 / miaoda 双轨统一口径）
# ------------------------------------------------------------
DIMENSIONS = ["表达逻辑", "抗压应变", "方案拆解", "协作沟通", "技术汇报", "问题解决"]

# ------------------------------------------------------------
# 题库：10 题职业素养行为题（选项按分档降序排列，index 0 = 最优解 = 10 分）
# ------------------------------------------------------------
QUESTION_BANK = [
    {"id": 1, "dim": "协作沟通", "type": "单选题",
     "stem": "项目立项会上，你和另一位同学对技术方案各执一词，气氛开始僵持。最合适的做法是：",
     "options": [
         "组织双方面对面沟通，聚焦项目目标对齐方案优劣，达成共识",
         "私下找指导老师评理，让老师裁决谁对谁错",
         "会上坚持己见不松口，用嗓门和态度压住对方",
         "表面妥协接受对方方案，会后消极执行敷衍了事"]},
    {"id": 2, "dim": "抗压应变", "type": "多选题",
     "stem": "答辩前彩排时，你发现 PPT 有三处数据错误，评委即将入场。你会优先做哪些事？（多选）",
     "options": [
         "立即修正错误数据并核对来源，同步更新讲稿口径",
         "评估修改耗时，来不及改的页面准备口头说明话术",
         "假装没看见，赌评委不会注意到细节",
         "把责任推给做 PPT 的队友，要求他当场返工"]},
    {"id": 3, "dim": "表达逻辑", "type": "单选题",
     "stem": "向非技术背景的评委介绍你的 AI 项目，对方频频露出疑惑表情。最合适的调整是：",
     "options": [
         "用生活化类比讲清核心价值，再按需补充细节",
         "放慢语速把同样的术语再重复一遍",
         "跳过项目背景直接展示代码实现细节",
         "提前结束陈述，把时间留给下一组"]},
    {"id": 4, "dim": "问题解决", "type": "单选题",
     "stem": "你负责的模块在上线前一晚发现严重 Bug，修复估计超期。最合适的处理是：",
     "options": [
         "立即评估影响范围，向领导汇报风险与可选方案，共同决策",
         "隐瞒问题连夜硬修，赌能在 deadline 前修好",
         "直接上线带 Bug 的版本，等用户投诉再说",
         "申请把责任推给测试环节，证明不是自己的问题"]},
    {"id": 5, "dim": "协作沟通", "type": "单选题",
     "stem": "群面讨论中你的方案被两位组员接连否定，你明显感到被动。最合适的回应是：",
     "options": [
         "快速提炼共识点，将方案融合后提出折中建议",
         "沉默退出让其余组员继续，避免再被否定",
         "逐条反驳两位组员的观点，证明自己更正确",
         "转向支持被否定的另一个方案，立刻站队多数"]},
    {"id": 6, "dim": "技术汇报", "type": "单选题",
     "stem": "你的实验数据没有达到预期指标，导师要求下周汇报进展。最合适的呈现方式是：",
     "options": [
         "如实呈现数据，分析根因并给出改进计划",
         "挑选好看的数据放大展示，回避未达标部分",
         "推迟汇报，等数据变好再约时间",
         "把数据不达标归因于设备条件，证明非人为因素"]},
    {"id": 7, "dim": "方案拆解", "type": "单选题",
     "stem": "临近期末，你同时面对课程大作业、竞赛截止和实习面试准备。最合适的优先级策略是：",
     "options": [
         "评估各事项的截止时间与影响，主动沟通调整，必要时请求支援",
         "按事情找上你的顺序逐个应付",
         "全部押注最重要的竞赛，其余事项直接放弃",
         "熬通宵把所有事情挤在同一晚完成"]},
    {"id": 8, "dim": "抗压应变", "type": "判断题",
     "stem": "项目复盘中，当众承认自己负责模块的失误会影响团队对你的评价，因此复盘时应该尽量淡化自己的问题。",
     "options": [
         "错误——主动承认问题，复盘失误原因并提出防范措施才是正确做法",
         "正确——职场中保护自己的形象比复盘更重要"],
     "correct_option": 0},
    {"id": 9, "dim": "表达逻辑", "type": "单选题",
     "stem": "导师当面质疑你论文中数据的真实性，情绪比较激动。最合适的应对是：",
     "options": [
         "说明数据来源与处理逻辑，请导师指出具体疑点，现场核对",
         "情绪对抗，要求导师先道歉再谈数据",
         "立刻全部撤回数据，承认自己造假以平息事态",
         "不当场回应，事后找其他老师诉委屈"]},
    {"id": 10, "dim": "问题解决", "type": "单选题",
     "stem": "加入新团队后你发现项目用的是你完全没接触过的技术栈。最合适的行动是：",
     "options": [
         "制定学习计划，梳理项目文档，主动请教关键模块负责人",
         "要求团队更换到你熟悉的技术栈",
         "只做分配到的边缘任务，回避不熟悉的核心模块",
         "照抄网上相似项目的代码，能跑就行不深究原理"]},
]

# 选项分档：index 0 → 10 分，1 → 7，2 → 4，3 → 1
_OPTION_SCORES = [10, 7, 4, 1]


def _score_answer(q: dict, option_index: int) -> int:
    """按选项 index 给分档分；判断题仅 2 个选项，0=10/1=1。"""
    if option_index < 0 or option_index >= len(q["options"]):
        return 0
    if q.get("correct_option") is not None:  # 判断题：correct_option=0 → 10 分
        return 10 if option_index == q["correct_option"] else 1
    return _OPTION_SCORES[option_index] if option_index < len(_OPTION_SCORES) else 0


# ------------------------------------------------------------
# 数据层：SQLite（复用 user_store 的连接模式）
# 路径惰性解析：全量测试时其他用例可能先导入本模块，
# 导入期固化 env 路径会导致测试库指向错位（测试间污染）
# ------------------------------------------------------------
_DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "literacy.db")
os.makedirs(os.path.dirname(_DEFAULT_DB), exist_ok=True)

_conn: Optional[sqlite3.Connection] = None
_conn_path: Optional[str] = None
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    global _conn, _conn_path
    db_path = os.environ.get("NETLEARN_LITERACY_DB") or _DEFAULT_DB
    if _conn is None or _conn_path != db_path:
        with _lock:
            if _conn is None or _conn_path != db_path:
                old = _conn
                _conn = sqlite3.connect(db_path, check_same_thread=False)
                _conn.row_factory = sqlite3.Row
                _conn_path = db_path
                _init_schema(_conn)
                if old is not None:
                    try:
                        old.close()
                    except Exception:
                        pass
    return _conn


def _init_schema(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS literacy_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL DEFAULT '',
            class_name TEXT NOT NULL DEFAULT '',
            phase TEXT NOT NULL DEFAULT 'pre',          -- pre / post
            answers_json TEXT NOT NULL DEFAULT '[]',    -- [{qid, option_index}]
            dim_scores_json TEXT NOT NULL DEFAULT '{}', -- {维度: 分数}
            total_score REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_literacy_user_phase ON literacy_attempts(user_id, phase)")
    conn.commit()


# ------------------------------------------------------------
# Pydantic 模型
# ------------------------------------------------------------
class LiteracySubmitRequest(BaseModel):
    phase: str = "pre"            # pre / post
    class_name: str = ""
    user_name: str = ""
    user_id: str = ""             # 无 token 时由前端传登录用户 ID（课堂场景）
    answers: list                 # [{qid: int, option_index: int}]


class LiteracyClassReportRequest(BaseModel):
    class_name: str


# ------------------------------------------------------------
# 路由
# ------------------------------------------------------------
@router.get("/questions")
async def get_questions():
    """获取素养测评题库（学生端答题页）。"""
    return {"total": len(QUESTION_BANK), "dimensions": DIMENSIONS,
            "questions": [{"id": q["id"], "dim": q["dim"], "type": q["type"],
                           "stem": q["stem"], "options": q["options"]} for q in QUESTION_BANK]}


@router.post("/submit")
async def submit_literacy(
    req: LiteracySubmitRequest,
    authorization: Optional[str] = Header(default=None),
):
    """提交素养测评：分档计分 → 六维得分 → 落库（pre/post 各一次）。

    user_id 解析顺序：Bearer token（登录态）→ 请求体 user_id（课堂场景）→ demo 兜底。
    此前硬编码 demo 导致同班学生互相覆盖（并发试测实锤，46 人课堂不可用）。
    """
    uid = "demo"
    if authorization and authorization.startswith("Bearer "):
        try:
            from shared.auth import verify_token
            uid = verify_token(authorization[len("Bearer "):])["sub"]
        except Exception:
            pass
    if uid == "demo" and req.user_id.strip():
        uid = req.user_id.strip()
    if req.phase not in ("pre", "post"):
        raise HTTPException(status_code=422, detail="phase 必须为 pre 或 post")
    qmap = {q["id"]: q for q in QUESTION_BANK}
    if not req.answers:
        raise HTTPException(status_code=422, detail="answers 不能为空")

    dim_scores = {d: [] for d in DIMENSIONS}
    per_q = []
    for a in req.answers:
        q = qmap.get(a.get("qid"))
        if not q:
            raise HTTPException(status_code=422, detail=f"题目不存在: {a.get('qid')}")
        s = _score_answer(q, int(a.get("option_index", -1)))
        dim_scores[q["dim"]].append(s)
        per_q.append({"qid": q["id"], "dim": q["dim"], "score": s})

    # 维度分 = 该维度题目均分 ×10（保持百分制口径）
    final_dims = {d: round(sum(v) / len(v) * 10, 1) if v else 0 for d, v in dim_scores.items()}
    answered_dims = [v for v in final_dims.values() if v > 0]
    total = round(sum(answered_dims) / len(answered_dims), 1) if answered_dims else 0

    uid = uid  # 已在上方按 token → 请求体 → demo 解析
    conn = _get_conn()
    with _lock:
        # 同一用户同 phase 允许多次作答（取最新）——先清旧记录保持一对一
        conn.execute("DELETE FROM literacy_attempts WHERE user_id=? AND phase=?", (uid, req.phase))
        conn.execute(
            "INSERT INTO literacy_attempts (user_id, user_name, class_name, phase, answers_json, dim_scores_json, total_score) VALUES (?,?,?,?,?,?,?)",
            (uid, req.user_name, req.class_name, req.phase,
             json.dumps(req.answers, ensure_ascii=False),
             json.dumps(final_dims, ensure_ascii=False), total))
        conn.commit()

    return {"total_score": total, "dim_scores": final_dims,
            "per_question": per_q, "phase": req.phase,
            "message": "提交成功，成绩已计入档案"}


@router.get("/report/{user_id}")
async def get_report(user_id: str):
    """个人素养报告：pre/post 六维对比（前后测差值）。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM literacy_attempts WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()
    by_phase = {r["phase"]: r for r in rows}
    if not by_phase:
        raise HTTPException(status_code=404, detail="该学生暂无测评记录")

    def _dim(r):
        return json.loads(r["dim_scores_json"]) if r else {}

    pre, post = _dim(by_phase.get("pre")), _dim(by_phase.get("post"))
    delta = {d: round((post.get(d, 0) - pre.get(d, 0)), 1) if post and pre else None
             for d in DIMENSIONS} if (pre and post) else None
    return {
        "user_id": user_id,
        "pre": {"total": by_phase["pre"]["total_score"] if "pre" in by_phase else None, "dims": pre},
        "post": {"total": by_phase["post"]["total_score"] if "post" in by_phase else None, "dims": post},
        "delta": delta,
        "dimensions": DIMENSIONS,
    }


@router.post("/class-report")
async def get_class_report(req: LiteracyClassReportRequest):
    """教师端班级六维聚合：全班 pre/post 均值 + 逐人明细。"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM literacy_attempts WHERE class_name=? ORDER BY user_id, created_at DESC",
        (req.class_name,)).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="该班级暂无测评记录")

    students, seen = [], set()
    agg = {"pre": {d: [] for d in DIMENSIONS}, "post": {d: [] for d in DIMENSIONS}}
    for r in rows:
        if r["user_id"] in seen:
            continue  # 每人取最新
        seen.add(r["user_id"])
        dims = json.loads(r["dim_scores_json"])
        students.append({"user_id": r["user_id"], "user_name": r["user_name"],
                         "phase": r["phase"], "total": r["total_score"], "dims": dims})
        if r["phase"] in agg:
            for d in DIMENSIONS:
                if dims.get(d, 0) > 0:
                    agg[r["phase"]][d].append(dims[d])

    def _avg(v):
        return round(sum(v) / len(v), 1) if v else None

    return {
        "class_name": req.class_name,
        "student_count": len(students),
        "class_avg": {p: {d: _avg(v) for d, v in dims.items()} for p, dims in agg.items()},
        "students": students,
        "dimensions": DIMENSIONS,
    }
