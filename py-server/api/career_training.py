# ============================================================
# API — 芒得很职·职业素养对抗实训（/api/career/*）
# P0 最窄闭环：场景列表 → 启动 → 逐轮作答 → 结束 → 六维报告
# 与 408 所有路由前缀隔离，互不影响。
# ============================================================

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from typing import Optional

from shared.auth import get_current_user
from services import career_service
from db import career_store
from agents.career_state import DIMENSION_LABELS

logger = logging.getLogger("netlearn.career.api")
router = APIRouter(prefix="/career", tags=["career-training"])

# 维度 key → 中文名（单一真值源：agents.career_state.DIMENSION_LABELS，与前端 CAREER_DIM_LABEL 同源）
def dim_label(d: str) -> str:
    return DIMENSION_LABELS.get(d, d)


# ── 请求模型 ──
class StartRequest(BaseModel):
    scenario_id: str
    difficulty: str = "medium"          # easy/medium/hard
    max_turns: int = 8
    task_id: Optional[str] = None       # 教师任务（自主练习为空）
    phase: Optional[str] = None         # F5: 前后测标记 pre/post（其余值视为未标记）


class AnswerRequest(BaseModel):
    answer: str = Field("", description="学生本轮口头/文字回答")


class EndRequest(BaseModel):
    force: bool = False


class ConsentRequest(BaseModel):
    agreed: bool = True


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="课后简评 1-5 分")
    comment: str = Field("", max_length=500)


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
            phase=req.phase,
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


# ────────────────────────────────────────────────────────────
# 证据链「一页纸」导出（可溯源 · 浏览器另存为 PDF）
# 复用 career_service.get_report；仅渲染真实存在的数据，缺失的 KB 原文溯源
# 字段（chunk_ref）统一标注「溯源：待补全」，绝不编造来源。
# ────────────────────────────────────────────────────────────
_LEVEL_LABEL = {
    "excellent": "优秀", "good": "良好", "average": "一般",
    "weak": "薄弱", "insufficient": "证据不足",
}
_MODE_LABEL = {"normal": "常规", "escalating": "逐步加压", "catfish": "鲶鱼反诘"}
# attention.reason 中文名（与前端 TeacherCareerView.REASON_LABEL 同源；后端只给结构性事实标识）
_REASON_LABEL = {
    "not_started": "未开始", "unfinished": "未完成",
    "no_score": "无评分", "lowest_score": "得分靠后",
}


def _credibility_label(confidence: float) -> str:
    """由评估置信度（0-1，真实字段）映射可信度等级，绝不编造。"""
    try:
        c = float(confidence or 0)
    except (TypeError, ValueError):
        c = 0.0
    if c >= 0.8:
        return "高"
    if c >= 0.5:
        return "中"
    return "低"


def _esc(text) -> str:
    """HTML 转义，避免学生作答内容破坏文档或造成注入。"""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


_EXPORT_CSS = """<style>
* { box-sizing: border-box; }
body { font-family: "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
  color: #1a1a1a; margin: 0; padding: 16px 20px; font-size: 12px; line-height: 1.5; }
@media print {
  body { padding: 6px 10px; font-size: 11px; }
  @page { margin: 9mm; }
  .claim, .turn { page-break-inside: avoid; }
}
h1 { font-size: 17px; margin: 0 0 4px; }
.meta { color: #555; font-size: 11px; margin-bottom: 6px; }
.banner { background: #fff7e6; border: 1px solid #ffd591; border-radius: 6px;
  padding: 6px 10px; font-size: 10.5px; color: #7a4b00; margin-bottom: 10px; }
.overall { font-size: 13px; margin: 4px 0 8px; }
.overall b { font-size: 22px; color: #1677ff; }
.src-tag { font-size: 10px; padding: 1px 7px; border-radius: 9px; background: #f0f0f0; color: #666; }
.section { margin-top: 10px; }
.section > h2 { font-size: 13px; border-left: 3px solid #1677ff; padding-left: 6px; margin: 0 0 6px; }
.claim { border: 1px solid #e8e8e8; border-radius: 6px; padding: 7px 10px; margin-bottom: 7px; }
.claim-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.dim { font-weight: 700; font-size: 13px; }
.score { font-weight: 700; color: #1677ff; }
.score small { font-weight: 400; color: #888; }
.level { font-size: 10px; padding: 1px 6px; border-radius: 8px; background: #f0f0f0; }
.cred { font-size: 10px; color: #666; margin-left: auto; }
.claim-body { margin: 4px 0; }
.trace { border-top: 1px dashed #eee; padding-top: 4px; }
.trace-row { display: flex; gap: 6px; align-items: baseline; margin: 2px 0; }
.tl { flex: 0 0 66px; color: #1677ff; font-weight: 600; font-size: 10.5px; }
.quote { display: inline-block; background: #f6f8ff; border-left: 2px solid #1677ff;
  padding: 1px 6px; border-radius: 3px; margin: 1px 4px 1px 0; font-size: 11px; }
.quote.missing, .kb-ref.missing, .src-agent.missing { background: #fff1f0;
  border-color: #ffa39e; color: #cf1322; }
.qmeta { color: #999; font-size: 9px; margin-left: 3px; }
.kb-ref, .src-agent { display: inline-block; padding: 1px 6px; border-radius: 3px;
  background: #f6ffed; border-left: 2px solid #52c41a; font-size: 11px; }
.tref { color: #999; font-size: 10px; }
.summary { background: #fafafa; border: 1px solid #eee; border-radius: 6px;
  padding: 6px 10px; margin: 4px 0; font-size: 11.5px; }
.sw { display: flex; gap: 12px; }
.sw > div { flex: 1; border: 1px solid #e8e8e8; border-radius: 6px; padding: 6px 10px; }
.sw-h { font-size: 10px; color: #888; margin-bottom: 3px; }
ul { margin: 4px 0; padding-left: 18px; }
.plan { display: flex; gap: 8px; padding: 3px 0; border-bottom: 1px dashed #eee; font-size: 11px; }
.pd { flex: 0 0 70px; font-weight: 600; color: #1677ff; }
.pdo { flex: 1; }
.pf { flex: 0 0 92px; color: #666; text-align: right; }
.plan-encourage { font-size: 11px; color: #666; margin: 6px 0 0; }
.turn { border-bottom: 1px dashed #eee; padding: 3px 0; }
.t-meta { color: #888; font-size: 10px; }
.t-q, .t-a { font-size: 11px; }
.muted { color: #999; }
.footer { margin-top: 10px; border-top: 1px solid #eee; padding-top: 6px; color: #999; font-size: 10px; }
</style>"""


def _render_export_html(report: dict) -> str:
    """把 get_report() 的真实数据渲染为可打印的自包含 HTML 一页纸。

    诚信约束：只渲染真实存在的字段。本实训链路无 KB/向量库检索，故：
    - 来源 Agent 取真实值（career_service 写入的 source_agent），不再"待补全"；
    - 「KB 原文溯源」如实说明无教材库检索，绝不编造 chunk 引用；
    - 新增「情景期望行为」行渲染该维度的 BARS rubric（真实评分量表），让判分依据可溯。
    """
    session_id = _esc(report.get("session_id", ""))
    title = _esc(report.get("title", "") or "（未命名实训）")
    scenario_label = _esc(report.get("scenario_label", ""))
    status = _esc(report.get("status", ""))
    assessment = report.get("assessment") or {}
    overall = assessment.get("overall")
    overall_txt = _esc(overall if overall is not None else "—")
    summary = _esc(assessment.get("summary", "") or "（无）")
    strength = _esc(assessment.get("strength", "") or "（无）")
    weaknesses = assessment.get("weaknesses") or []
    source_tag = "AI 评估" if assessment.get("assessment_source") == "llm" else "规则评估"
    source_tag = _esc(source_tag)

    # ── 六维结论与溯源 ──
    claims = []
    for item in (report.get("evidence_chain") or []):
        label = _esc(item.get("label", "") or item.get("dimension", "") or "维度")
        score = item.get("score")
        score_txt = _esc(score if score is not None else "—")
        level = _esc(_LEVEL_LABEL.get(item.get("level", ""), item.get("level", "") or "—"))
        confidence = item.get("confidence", 0)
        try:
            conf_num = round(float(confidence or 0), 2)
        except (TypeError, ValueError):
            conf_num = 0.0

        rationale = (item.get("rationale", "") or "").strip()
        if rationale:
            rationale = _esc(rationale)
        else:
            rationale = f"「{label}」维度得分 {score_txt}/5（{level}）"

        # 原话溯源：优先 evidence_quotes（学生原话片段），其次 per_turn_evidence 的
        # answer_snippet（"学生第 N 轮说：『…』"），全部取自真实 dialogue_turns。
        quote_parts: list[str] = []
        for q in (item.get("evidence_quotes") or []):
            q = (q or "").strip()
            if q:
                quote_parts.append(f'<span class="quote">「{_esc(q)}」</span>')
        for h in (item.get("per_turn_evidence") or []):
            turn = h.get("turn")
            note = (h.get("note", "") or "").strip()
            snippet = (h.get("answer_snippet", "") or "").strip()
            pol = _esc(h.get("polarity", "") or "")
            if snippet:
                quote_parts.append(
                    f'<span class="quote">「{_esc(snippet)}」'
                    f'<small class="qmeta">学生第{_esc(turn)}轮说 · {pol}</small></span>'
                )
            elif note:
                quote_parts.append(
                    f'<span class="quote">「{_esc(note)}」'
                    f'<small class="qmeta">第{_esc(turn)}轮·{pol}</small></span>'
                )
        if not quote_parts:
            quote_parts.append('<span class="quote missing">溯源：待补全</span>')
        ev_turns = item.get("evidence_turns") or []
        turns_ref = ""
        if ev_turns:
            turns_ref = " 引用自第 " + "、".join(_esc(str(t)) for t in ev_turns) + " 轮"

        # 来源 Agent：真实填充（不再"待补全"）。没有 KB 检索，chunk_ref 仅作 rubric 段落 id。
        src_agent = (item.get("source_agent", "") or "").strip()
        if src_agent:
            turns_label = "、".join(_esc(str(t)) for t in ev_turns)
            src_note = f"证据取自学生第 {turns_label} 轮作答" if turns_label else "证据取自学生作答"
            src_agent_html = (
                f'<span class="src-agent">{_esc(src_agent)}</span>'
                f'<small class="qmeta">{src_note}</small>'
            )
        else:
            src_agent_html = '<span class="src-agent missing">待补全（证据取自学生本轮作答）</span>'

        # 情景期望行为（BARS rubric）：真实评分量表依据，取自情景种子；缺失则诚实标注
        rubric = (item.get("rubric_text", "") or "").strip()
        rubric_html = (
            f'<span class="kb-ref">{_esc(rubric)}</span>'
            if rubric else
            '<span class="kb-ref missing">（该维度未配置 BARS 锚点）</span>'
        )

        claims.append(f"""
        <div class="claim">
          <div class="claim-head">
            <span class="dim">{label}</span>
            <span class="score">{score_txt}<small>/5</small></span>
            <span class="level">{level}</span>
            <span class="cred">可信度：{_credibility_label(confidence)}（{conf_num}）</span>
          </div>
          <div class="claim-body">{rationale}</div>
          <div class="trace">
            <div class="trace-row"><span class="tl">原话溯源</span>{''.join(quote_parts)}<span class="tref">{turns_ref}</span></div>
            <div class="trace-row"><span class="tl">KB 原文溯源</span><span class="kb-ref missing">本实训为情景对抗、无教材库检索；评分依据见「情景期望行为」</span></div>
            <div class="trace-row"><span class="tl">情景期望行为</span>{rubric_html}</div>
            <div class="trace-row"><span class="tl">来源 Agent</span>{src_agent_html}</div>
          </div>
        </div>""")
    claims_html = "\n".join(claims) if claims else '<div class="muted">（暂无六维结论）</div>'

    weak_html = "".join(f"<li>{_esc(w)}</li>" for w in weaknesses) or "<li>（无）</li>"

    # ── 提升路径 ──
    improvement = report.get("improvement") or {}
    plan_parts = []
    for a in (improvement.get("actions") or []):
        dim = _esc(a.get("dimension", "") or "")
        do = _esc(a.get("do", "") or "")
        freq = _esc(a.get("frequency", "") or "")
        plan_parts.append(
            f'<div class="plan"><span class="pd">{dim}</span>'
            f'<span class="pdo">{do}</span><span class="pf">{freq}</span></div>'
        )
    plan_html = "\n".join(plan_parts) if plan_parts else '<div class="muted">（暂无提升路径）</div>'
    encourage = _esc(improvement.get("encouragement", "") or "")
    encourage_html = f'<p class="plan-encourage">{encourage}</p>' if encourage else ""

    # ── 完整对抗记录（可溯源头）──
    replay = []
    for t in (report.get("turns") or []):
        ti = t.get("turn_index")
        mode = _esc(_MODE_LABEL.get(t.get("mode", ""), t.get("mode", "") or ""))
        dim = _esc(t.get("probe_dimension", "") or "")
        q = _esc(t.get("question", "") or "")
        a = _esc(t.get("answer", "") or "")
        replay.append(f"""
        <div class="turn">
          <div class="t-meta">第{_esc(ti)}轮 · {mode} · {dim}</div>
          <div class="t-q"><b>对手：</b>{q}</div>
          <div class="t-a"><b>我：</b>{a}</div>
        </div>""")
    replay_html = "\n".join(replay) if replay else '<div class="muted">（无对话记录）</div>'

    generated = _esc(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>证据链一页纸 · {title}</title>
{_EXPORT_CSS}
</head>
<body>
  <h1>职业素养对抗实训 · 证据链一页纸（可溯源）</h1>
  <div class="meta">会话：{session_id} ｜ 情景：{scenario_label} ｜ 状态：{status} ｜ 评估来源：{source_tag}</div>
  <div class="banner">
    <b>诚信声明：</b>本页每条结论均追溯至「学生原话」+「情景期望行为（BARS rubric）」：前者取自真实作答轮次，
    后者取自情景种子的静态评分量表，二者均为规则/评分驱动（source_type=rule），<b>未做任何 KB/向量库检索</b>。
    故「KB 原文溯源」在此实训架构下不适用（无教材库），<b>未伪造任何 chunk 引用</b>；所有数字与引文均来自真实数据。
  </div>

  <div class="overall">综合得分：<b>{overall_txt}</b> / 5　<span class="src-tag">{source_tag}</span></div>

  <div class="section">
    <h2>一、六维结论与溯源</h2>
    {claims_html}
  </div>

  <div class="section">
    <h2>二、综合评估</h2>
    <p class="summary">{summary}</p>
    <div class="sw">
      <div><div class="sw-h">最突出优点</div><div>{strength}</div></div>
      <div><div class="sw-h">待改进</div><ul>{weak_html}</ul></div>
    </div>
  </div>

  <div class="section">
    <h2>三、针对性提升路径</h2>
    {plan_html}
    {encourage_html}
  </div>

  <div class="section">
    <h2>四、完整对抗记录（可溯源头）</h2>
    {replay_html}
  </div>

  <div class="footer">
    生成时间：{generated}　·　本页由浏览器「另存为 PDF」即可作为一页纸证据报告。诚信优先：缺源必标，绝不杜撰。
  </div>
</body>
</html>"""


@router.get("/session/{session_id}/export-report")
async def export_report(session_id: str, user: dict = Depends(get_current_user)):
    """导出证据链一页纸（自包含 HTML，浏览器另存为 PDF 即得一页纸报告）。"""
    _check_owner(session_id, user)
    try:
        report_data = career_service.get_report(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    html = _render_export_html(report_data)
    return Response(content=html, media_type="text/html; charset=utf-8")


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


# ── 我的任务列表（可按班级过滤；F2：附场景标题与参与进度）──
@router.get("/tasks")
async def list_tasks(class_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    _require_teacher(user)
    tasks = career_store.list_tasks_by_teacher(user["user_id"], class_id)
    scenarios = {s.get("id"): s.get("title", "") for s in career_service.list_scenarios()}
    for t in tasks:
        t["scenario_title"] = scenarios.get(t.get("scenario_id"), "")
        t["stats"] = career_store.task_stats(t["task_id"], user["user_id"])
    return {"tasks": tasks}


# ── 关闭任务（F2：历史数据不动，学生端不再出现）──
@router.post("/tasks/{task_id}/close")
async def close_task(task_id: str, user: dict = Depends(get_current_user)):
    _require_teacher(user)
    try:
        res = career_store.close_task(task_id, user["user_id"])
    except Exception as e:
        logger.exception("关闭任务失败")
        raise HTTPException(status_code=500, detail=f"关闭失败: {e}")
    if not res:
        raise HTTPException(status_code=404, detail="任务不存在或无权操作")
    return res


# ── 学生个体下钻（F1：班内单个学生的全部会话明细）──
@router.get("/classes/{class_id}/students/{user_id}/detail")
async def student_detail(class_id: str, user_id: str, user: dict = Depends(get_current_user)):
    _require_teacher(user)
    try:
        detail = career_store.student_detail(class_id, user["user_id"], user_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("学生明细查询失败")
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")
    if not detail:
        raise HTTPException(status_code=404, detail="班级不存在或无权查看")
    return detail


# ── 学生任务中心（F3：我已绑定班级的开放任务，免手输任务码）──
@router.get("/my-tasks")
async def my_tasks(user: dict = Depends(get_current_user)):
    tasks = career_store.my_tasks(user["user_id"])
    scenarios = {s.get("id"): s.get("title", "") for s in career_service.list_scenarios()}
    for t in tasks:
        t["scenario_title"] = scenarios.get(t.get("scenario_id"), "")
    return {"tasks": tasks}


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
    # 取用户姓名用于花名册匹配（get_current_user 只给 user_id/role，故此处查一次）
    user_name = ""
    try:
        from db import user_store
        u = user_store.get_user_by_id(user["user_id"]) or {}
        user_name = (u.get("display_name") or u.get("username") or "").strip()
    except Exception:
        logger.warning("加入任务时读取用户姓名失败（不影响加入，退回按未绑定行绑定）", exc_info=True)
    bound = career_store.bind_student(task["class_id"], user["user_id"], user_name)
    return {"task_id": task["id"], "scenario_id": task["scenario_id"],
            "scenario_type": task.get("scenario_type", ""),
            "difficulty": task.get("difficulty", "medium"),
            "max_turns": int(task.get("max_turns") or 8),
            "class_id": task["class_id"],
            "roster_bound": bool(bound),
            # 如实回传绑定结果：matched_by=name 表示按姓名命中；first_unbound 表示退回旧行为（可能错位）
            "bound_name": (bound or {}).get("name", ""),
            "bound_match": (bound or {}).get("matched_by", "")}


# ────────────────────────────────────────────────────────────
# F4 个人成长页（学生端）：六维趋势 + 证据金句 + 前后测对比
# ────────────────────────────────────────────────────────────
@router.get("/my-growth")
async def my_growth(user: dict = Depends(get_current_user)):
    """我的成长：全部已完成会话的六维趋势/均分、评估引用过的原话金句、
    pre/post 前后测差值（仅两侧都有已评分会话时才给出，不插值）。"""
    return career_store.growth_profile(user["user_id"])


# ────────────────────────────────────────────────────────────
# F6 知情同意与课后简评（试用伦理 + 满意度数据）
# ────────────────────────────────────────────────────────────
@router.get("/consent")
async def get_consent(user: dict = Depends(get_current_user)):
    """当前用户的同意状态 + 同意书文本（前端据此渲染门禁）。"""
    rec = career_store.get_consent(user["user_id"])
    return {"consent": rec,
            "version": career_store.CONSENT_VERSION,
            "text": career_store.CONSENT_TEXT}


@router.post("/consent")
async def post_consent(req: ConsentRequest, user: dict = Depends(get_current_user)):
    """记录知情同意（agreed=false 也如实记录，便于审计"看过但不同意"）。"""
    try:
        return career_store.record_consent(user["user_id"], req.agreed)
    except Exception as e:
        logger.exception("记录知情同意失败")
        raise HTTPException(status_code=500, detail=f"记录失败: {e}")


@router.post("/session/{session_id}/feedback")
async def post_feedback(session_id: str, req: FeedbackRequest,
                        user: dict = Depends(get_current_user)):
    """课后简评：仅会话本人可提交（教师代填无意义）；每场一条（重复提交更新）。"""
    state = _check_owner(session_id, user)
    if state.get("user_id") != user.get("user_id"):
        raise HTTPException(status_code=403, detail="仅可评价本人的实训会话")
    try:
        return career_store.save_feedback(session_id, user["user_id"],
                                          int(req.rating), (req.comment or "").strip())
    except Exception as e:
        logger.exception("保存课后简评失败")
        raise HTTPException(status_code=500, detail=f"保存失败: {e}")


@router.get("/feedback")
async def list_feedback(class_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    """教师查看本人班级学生的课后简评（按班级归属隔离；可按班级过滤）。"""
    _require_teacher(user)
    return {"feedback": career_store.list_feedback(user["user_id"], class_id)}


# ────────────────────────────────────────────────────────────
# F7 班级报告一页纸导出（对标 session export-report：自包含 HTML）
# ────────────────────────────────────────────────────────────
_CLASS_EXPORT_CSS = """<style>
* { box-sizing: border-box; }
body { font-family: "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
  color: #1a1a1a; margin: 0; padding: 16px 20px; font-size: 12px; line-height: 1.5; }
@media print {
  body { padding: 6px 10px; font-size: 11px; }
  @page { margin: 9mm; }
  tr { page-break-inside: avoid; }
}
h1 { font-size: 17px; margin: 0 0 4px; }
.meta { color: #555; font-size: 11px; margin-bottom: 6px; }
.banner { background: #fff7e6; border: 1px solid #ffd591; border-radius: 6px;
  padding: 6px 10px; font-size: 10.5px; color: #7a4b00; margin-bottom: 10px; }
.section { margin-top: 10px; }
.section > h2 { font-size: 13px; border-left: 3px solid #1677ff; padding-left: 6px; margin: 0 0 6px; }
.sw { display: flex; gap: 12px; flex-wrap: wrap; }
.sw > div { flex: 1; min-width: 120px; border: 1px solid #e8e8e8; border-radius: 6px; padding: 6px 10px; }
.sw-h { font-size: 10px; color: #888; margin-bottom: 3px; }
.sw-v { font-size: 18px; font-weight: 700; color: #1677ff; }
table { width: 100%; border-collapse: collapse; margin-top: 4px; }
th, td { border: 1px solid #e8e8e8; padding: 4px 7px; text-align: left; font-size: 11px; }
th { background: #fafafa; }
.dim { color: #999; font-size: 10px; }
.att { border: 1px solid #e8e8e8; border-radius: 6px; padding: 6px 10px; margin-bottom: 6px; }
.att-h { font-weight: 600; }
.footer { margin-top: 10px; border-top: 1px solid #eee; padding-top: 6px; color: #999; font-size: 10px; }
</style>"""


def _render_class_export_html(dash: dict) -> str:
    """班级学情一页纸：只渲染 class_dashboard 真实返回的数据。

    诚信约束：未完成/无评分一律显示「缺失」，绝不插值编数；
    完成率为真实 finished/student_count；attention 只呈现后端给出的结构性事实。
    """
    class_name = _esc(dash.get("class_name", "") or "（未命名班级）")
    summary = dash.get("summary") or {}
    students = dash.get("students") or []
    attention = dash.get("attention") or []
    dim_labels = {d: dim_label(d) for d in (summary.get("dimension_avg") or {})}

    stat_cards = [
        ("班级人数", summary.get("student_count", len(students))),
        ("已开始", summary.get("started_count", 0)),
        ("已完成", summary.get("finished_count", 0)),
        ("已评分", summary.get("assessed_count", 0)),
        ("完成率", f"{summary.get('completion_rate', 0)}%"),
    ]
    sw_html = "".join(
        f'<div><div class="sw-h">{_esc(k)}</div><div class="sw-v">{_esc(v)}</div></div>'
        for k, v in stat_cards)

    dim_avg = summary.get("dimension_avg") or {}
    dim_html = "、".join(
        f"{_esc(dim_labels.get(d, d))} {_esc(v)}" for d, v in dim_avg.items()) or "暂无已评分数据"

    rows = []
    for s in students:
        dims = s.get("dimension_avg") or {}
        dim_cell = "、".join(f"{_esc(dim_label(d))} {_esc(v)}" for d, v in dims.items()) or "—"
        best = s.get("overall_best")
        rows.append(
            f"<tr><td>{_esc(s.get('student_no') or '—')}</td>"
            f"<td>{_esc(s.get('name') or '—')}"
            f"<span class=\"dim\">{'' if s.get('bound') else '（未加入）'}</span></td>"
            f"<td>{_esc(s.get('session_count', 0))}</td>"
            f"<td>{_esc(s.get('finished_count', 0))}</td>"
            f"<td>{_esc(best if best is not None else '缺失')}</td>"
            f"<td>{dim_cell}</td></tr>")

    att_html = ""
    for a in attention:
        att_html += (f"<div class=\"att\"><span class=\"att-h\">{_esc(a.get('name') or '—')}</span>"
                     f"<span class=\"dim\">（{_esc(_REASON_LABEL.get(a.get('reason', ''), a.get('reason', '')))}）</span>"
                     f"<div class=\"dim\">{_esc(a.get('detail', ''))}</div></div>")
    if not att_html:
        att_html = '<div class="dim">当前无需关注的学生（结构性口径：全员已开始且已完成且有评分）。</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>班级学情报告 — {class_name}</title>{_CLASS_EXPORT_CSS}</head>
<body>
<h1>班级学情报告 — {class_name}</h1>
<div class="meta">导出时间：{_esc(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))} ·
  数据来源：实训会话与系统自动评分记录（真实落库）</div>
<div class="banner">口径说明：本报告为班级级汇总，仅呈现真实记录；未完成或无评分的项显示「缺失」，不作插值。
  如需引用成效数字，请先跑 pilot_evidence_report 取证闸（当前尚未开展真实试用前，不得引用任何条数）。</div>
<div class="section"><h2>班级概览</h2><div class="sw">{sw_html}</div></div>
<div class="section"><h2>六维班级均分</h2><div>{dim_html}</div></div>
<div class="section"><h2>需关注（结构性事实）</h2>{att_html}</div>
<div class="section"><h2>学生明细</h2>
<table><thead><tr><th>学号</th><th>姓名</th><th>会话数</th><th>已完成</th><th>最高 overall</th><th>六维均分</th></tr></thead>
<tbody>{"".join(rows) or '<tr><td colspan="6" class="dim">暂无学生</td></tr>'}</tbody></table></div>
<div class="footer">芒得很职 · 班级学情一页纸（浏览器打印/另存为 PDF 即得报告）</div>
</body></html>"""


@router.get("/classes/{class_id}/export-report")
async def export_class_report(class_id: str, user: dict = Depends(get_current_user)):
    """导出班级学情一页纸（自包含 HTML，浏览器另存为 PDF 即得报告）。"""
    _require_teacher(user)
    dash = career_store.class_dashboard(class_id, user["user_id"])
    if not dash:
        raise HTTPException(status_code=404, detail="班级不存在或无权查看")
    return Response(content=_render_class_export_html(dash),
                    media_type="text/html; charset=utf-8")
