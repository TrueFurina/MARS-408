# ============================================================
# API — 答题（/api/quiz/*）
# ============================================================

import random
import logging
import json as json_mod
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from models import QuizSubmitRequest, QuizSubmitResponse, RemediationItem
from services.remediation import detect_weak_points
from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota
from services.user_service import save_profile, get_profile, add_wrong_question
from db.llm_provider import LLMProvider
from engines.quiz_engine import STEP_QUESTIONS, error_analyzer, weak_point_tracker, StepResult, filter_questions_for_weak_points, weak_points_from_history

logger = logging.getLogger("netlearn.quiz")
router = APIRouter(prefix="/quiz", tags=["quiz"])

LEARNING_STYLE_CHOICES = ["visual", "reading", "kinesthetic", "auditory"]
KNOWLEDGE_LEVELS = ["beginner", "intermediate", "advanced"]
WEAK_POINT_KEYS = ["概念理解", "子网划分", "协议细节", "计算", "综合应用"]


def _merge_profile(profile: dict, records: list[dict]) -> dict:
    """合并答题记录到学生画像"""
    updated = profile.copy()

    by_subject = {}
    for r in records:
        subj = r.get("subject", "unknown")
        if subj not in by_subject:
            by_subject[subj] = {"total": 0, "correct": 0}
        by_subject[subj]["total"] += 1
        if r.get("correct"):
            by_subject[subj]["correct"] += 1

    total, correct = sum(v["total"] for v in by_subject.values()), sum(v["correct"] for v in by_subject.values())
    accuracy = correct / max(total, 1)

    weak = updated.get("weak_points", "")
    if accuracy < 0.5 and "概念理解" not in weak:
        updated["weak_points"] = f"{weak},概念理解".strip(",")

    if accuracy > 0.8 and updated.get("knowledge_base", "beginner") == "beginner":
        updated["knowledge_base"] = "intermediate"
    elif accuracy > 0.9:
        updated["knowledge_base"] = "advanced"

    # 难度偏好自适应：根据答题表现动态调整
    current_diff = updated.get("preferred_difficulty", "medium")
    if accuracy > 0.85 and current_diff in ("easy", "medium"):
        updated["preferred_difficulty"] = "hard"
    elif accuracy < 0.4 and current_diff in ("medium", "hard"):
        updated["preferred_difficulty"] = "easy"
    elif accuracy >= 0.4 and accuracy <= 0.85 and current_diff != "medium":
        updated["preferred_difficulty"] = "medium"

    updated["recent_accuracy"] = round(accuracy, 3)

    return updated


# ── P1 闭环触发：答题后薄弱知识点自动讲解 ──
# 复用 weak-point-expert 官方技能（id 固定），通过 SkillPluginRuntime 触发，
# 与 api/skills.py 的 /run-with-memory 端点保持一致的实例化与按 id 加载模式。

WEAK_POINT_EXPERT_ID = "weak-point-expert"


def _resolve_weak_expert_skill(get_skill, get_template) -> Optional[dict]:
    """解析 weak-point-expert 技能配置：优先已 seed 的官方技能，缺失时回退模板。

    返回运行时可直接使用的技能 dict（含 system_prompt / llm_channel / temperature /
    max_tokens / memory_access 等字段）；均未命中返回 None（调用方据此降级）。
    """
    try:
        skill = get_skill(WEAK_POINT_EXPERT_ID)
        if skill is not None:
            d = skill.to_dict()
            if d.get("system_prompt"):
                d.setdefault("memory_access", "read_write")
                d.setdefault("trigger_paths", [])
                d.setdefault("tools", [])
                return d
    except Exception as _e:
        logger.debug(f"读取 weak-point-expert 官方技能失败(回退模板): {_e}")

    try:
        tmpl = get_template(WEAK_POINT_EXPERT_ID)
        if tmpl is not None:
            cfg = tmpl.default_config or {}
            return {
                "id": tmpl.id,
                "name": tmpl.name,
                "system_prompt": tmpl.system_prompt_template or "",
                "llm_channel": cfg.get("llm_channel", "auto"),
                "temperature": cfg.get("temperature", 0.6),
                "max_tokens": cfg.get("max_tokens", 1500),
                "memory_access": "read_write",
                "trigger_paths": [],
                "tools": [],
            }
    except Exception as _e:
        logger.debug(f"读取 weak-point-expert 模板失败(降级): {_e}")

    return None


def _fill_subject_into_prompt(system_prompt: str, knowledge_point: str) -> str:
    """将技能模板中的 {{subject}} 占位符替换为具体知识点名称。

    SkillPluginRuntime.execute 不做 Jinja 风格占位符替换，需调用方手动替换；
    替换后的 prompt 通过 execute(system_prompt_override=...) 注入，
    不再直接写入运行时热加载缓存（避免触碰私有成员 _cache._cache）。
    """
    if "{{subject}}" in system_prompt:
        return system_prompt.replace("{{subject}}", knowledge_point)
    return system_prompt


async def _generate_remediation(user_id: str) -> list[RemediationItem]:
    """P1 闭环触发核心：读取掌握度 → 检测薄弱点 → 触发讲解，返回补救项列表。

    严格可降级：任何异常（LLM 不可用、记忆/技能缺失、熔断器打开）都对应项
    explanation=None 并继续，绝不抛出、绝不改变 quiz_submit 的既有返回字段。
    mastery_json 缺失/空 → 返回空列表。
    """
    from config import get_remediation_threshold, get_remediation_max_points
    from db.memory_store import get_semantic_memory
    from engines.skill_plugin_runtime import SkillPluginRuntime
    from db.skill_store import get_skill, get_template

    threshold = get_remediation_threshold()
    max_points = get_remediation_max_points()
    if max_points <= 0:
        return []

    # 1) 读取掌握度矩阵
    try:
        mem = get_semantic_memory(user_id)
        mastery = mem.get("mastery") or {}
    except Exception as _e:
        logger.debug(f"读取掌握度失败(降级，跳过闭环讲解): {_e}")
        return []

    # 2) 纯检测（无 LLM）
    weak_points = detect_weak_points(mastery, threshold, max_points)
    if not weak_points:
        return []

    # 3) 解析技能配置（官方技能优先，模板回退）
    skill_dict = _resolve_weak_expert_skill(get_skill, get_template)

    results: list[RemediationItem] = []
    for kp in weak_points:
        item = RemediationItem(knowledge_point=kp, explanation=None)
        try:
            if skill_dict is None:
                raise ValueError(f"技能 {WEAK_POINT_EXPERT_ID} 未注册（官方技能未 seed 且无模板）")

            runtime = SkillPluginRuntime.get(WEAK_POINT_EXPERT_ID)

            # 渲染 {{subject}} 后通过 execute 的 system_prompt_override 注入，
            # 不再触碰运行时私有缓存（_cache._cache）。
            system_prompt = _fill_subject_into_prompt(
                skill_dict.get("system_prompt", ""), kp
            )

            explanation = await runtime.execute(
                user_input=(
                    f"请结合我的学情记忆，针对知识点「{kp}」进行薄弱点专项讲解："
                    "先讲清核心概念，再指出常见易错点，给出一道典型例题并解析，"
                    "最后给出针对性复习建议。"
                ),
                user_id=user_id,
                session_id="",
                use_memory=True,        # 注入 L1/L2/L3 学情记忆（个性化）
                memory_access="read_write",
                system_prompt_override=system_prompt,
            )
            item.explanation = explanation or None
        except Exception as _e:
            logger.warning(f"薄弱点讲解生成失败(降级，不影响答题回写): kp={kp}, err={_e}")
            item.explanation = None
        results.append(item)
    return results


@router.post("/submit", response_model=QuizSubmitResponse)
async def quiz_submit(req: QuizSubmitRequest, user: dict = Depends(get_current_user)):
    """提交答题记录，更新学生画像"""
    if not req.records:
        raise HTTPException(status_code=400, detail="答题记录不能为空")

    total = len(req.records)
    correct_count = sum(1 for r in req.records if r.correct)
    accuracy = correct_count / total if total > 0 else 0

    by_subject = {}
    for r in req.records:
        subj = r.subject or "unknown"
        if subj not in by_subject:
            by_subject[subj] = {"total": 0, "correct": 0}
        by_subject[subj]["total"] += 1
        if r.correct:
            by_subject[subj]["correct"] += 1

    for k, v in by_subject.items():
        v["accuracy"] = round(v["correct"] / max(v["total"], 1), 3)

    updated_profile = _merge_profile(req.profile, [r.model_dump() for r in req.records])

    # 持久化更新后的画像到用户存储（赛题要求：画像随学随新）
    try:
        existing = get_profile(user["user_id"])
        if existing:
            merged = {**existing, **updated_profile}
            save_profile(user["user_id"], merged)
        else:
            save_profile(user["user_id"], updated_profile)
    except Exception as e:
        logger.warning(f"画像持久化失败: {e}")

    # L1/L2/L3 三层学情记忆回写（对标 HKU-DeepTutor 记忆解耦，低侵入）：
    # L2 掌握度按科目更新 + L3 情景记录答题事件（答题→记忆→画像→推送闭环）
    try:
        from services.memory_service import record_quiz_result
        from db import memory_store as _ms

        user_id = user["user_id"]
        for r in req.records:
            topic = (r.subject or "unknown")
            record_quiz_result(
                user_id, topic,
                correct=bool(r.correct),
                difficulty=getattr(r, "difficulty", "medium") or "medium",
                mastery_delta=0.05,
            )
        # L3 批量记录本次答题事件摘要
        _ms.append_episodes_batch(
            user_id, "quiz_session",
            [{"correct": bool(r.correct), "subject": r.subject or "unknown",
              "difficulty": getattr(r, "difficulty", "medium") or "medium"}
             for r in req.records],
        )
    except Exception as e:
        logger.debug(f"三层记忆回写失败(忽略): {e}")

    # 自动错题本：答错的题目自动加入错题本
    try:
        for r in req.records:
            if not r.correct:
                q_dict = r.model_dump()
                add_wrong_question(
                    user_id, q_dict, r.user_answer,
                    error_type="quiz_wrong",
                )
    except Exception as e:
        logger.debug(f"错题本自动入库失败(忽略): {e}")

    # LLM 驱动的画像智能更新（补充启发式规则的不足）
    try:
        from prompts import QUIZ_PROFILE_UPDATE_PROMPT
        llm = LLMProvider()
        profile_json = json_mod.dumps(updated_profile, ensure_ascii=False)
        records_json = json_mod.dumps([r.model_dump() for r in req.records], ensure_ascii=False)
        user_in = f"当前画像: {profile_json}\n答题记录: {records_json}"
        llm_result = await llm.text_completion(QUIZ_PROFILE_UPDATE_PROMPT, user_in)
        if llm_result:
            import re as _re
            m = _re.search(r'\{.*\}', llm_result, _re.DOTALL)
            if m:
                llm_profile = json_mod.loads(m.group(0))
                merged = {**updated_profile, **llm_profile}
                save_profile(user["user_id"], merged)
                updated_profile = merged
    except Exception as e:
        logger.warning(f"LLM画像更新失败（非阻塞）: {e}")

    if accuracy < 0.4:
        suggestions = (
            f"本次共答 {total} 题，正确率 {accuracy*100:.0f}%，基础需要加强。"
            "建议回到教材阅读模式，巩固基本概念后再来答题。"
        )
    elif accuracy < 0.7:
        suggestions = (
            f"本次共答 {total} 题，正确率 {accuracy*100:.0f}%，有一定基础但仍有提升空间。"
            f"建议重点复习：{list(by_subject.keys())} 章节的薄弱知识点。"
        )
    else:
        suggestions = (
            f"本次共答 {total} 题，正确率 {accuracy*100:.0f}%，表现不错！"
            "建议挑战更高难度题目，或进入下一章节学习。"
        )

    # P1 闭环触发：检测薄弱知识点并触发 weak-point-expert 自动讲解（严格可降级）。
    # 任何失败都返回 explanation=None 的 remediation 项或空列表，绝不破坏既有响应字段。
    try:
        remediation = await _generate_remediation(user["user_id"])
    except Exception as _e:
        logger.warning(f"闭环讲解整体降级(不影响答题回写): {_e}")
        remediation = []

    return QuizSubmitResponse(
        total=total, correct_count=correct_count,
        accuracy=round(accuracy, 3), by_subject=by_subject,
        updated_profile=updated_profile, suggestions=suggestions,
        remediation=remediation,
    )


# ── 步骤拆解题库 API ──

from pydantic import BaseModel


class StepAnswerRequest(BaseModel):
    """提交单步答案"""
    question_id: str
    step_index: int
    answer: str


class StepAnswerResponse(BaseModel):
    """单步反馈"""
    correct: bool
    hint: str = ""
    error_type: str = ""
    next_step: int = -1
    finished: bool = False


class StepQuestionResponse(BaseModel):
    """步骤化题目"""
    id: str
    subject: str
    chapter: str
    difficulty: str
    question_text: str
    total_steps: int
    current_step: int
    step_name: str
    step_description: str
    step_type: str
    options: list[str] = []


@router.get("/step-questions")
async def get_step_questions(subject: str = "", user: dict = Depends(get_current_user)):
    """获取步骤化题目列表"""
    questions = STEP_QUESTIONS
    if subject:
        questions = [q for q in questions if q.subject == subject]
    return {
        "questions": [
            {
                "id": q.id,
                "subject": q.subject,
                "chapter": q.chapter,
                "difficulty": q.difficulty,
                "question_text": q.question_text,
                "step_count": len(q.steps),
            }
            for q in questions
        ],
        "total": len(questions),
    }


@router.get("/step-questions/{question_id}")
async def get_step_question_detail(question_id: str, user: dict = Depends(get_current_user)):
    """获取步骤化题目详情（第一步）"""
    q = next((q for q in STEP_QUESTIONS if q.id == question_id), None)
    if not q:
        raise HTTPException(404, "题目不存在")
    if not q.steps:
        raise HTTPException(500, "题目数据异常：无步骤")
    first = q.steps[0]
    return StepQuestionResponse(
        id=q.id, subject=q.subject, chapter=q.chapter,
        difficulty=q.difficulty, question_text=q.question_text,
        total_steps=len(q.steps), current_step=0,
        step_name=first.step_name, step_description=first.description,
        step_type=first.check_type, options=first.options,
    )


@router.post("/step-questions/{question_id}/answer")
async def submit_step_answer(question_id: str, req: StepAnswerRequest, user: dict = Depends(get_current_user)):
    """提交单步答案，返回正误+提示+下一步"""
    q = next((q for q in STEP_QUESTIONS if q.id == question_id), None)
    if not q:
        raise HTTPException(404, "题目不存在")

    if req.step_index < 0 or req.step_index >= len(q.steps):
        raise HTTPException(400, "步骤索引无效")

    step = q.steps[req.step_index]
    correct = req.answer.strip() == step.answer.strip()

    step_result = StepResult(
        step_index=req.step_index,
        step_name=step.step_name,
        correct=correct,
        user_answer=req.answer,
        correct_answer=step.answer,
        error_type=step.error_type_if_wrong if not correct else "correct",
        hint=step.hint_on_error if not correct else "回答正确！",
    )

    next_step = req.step_index + 1 if req.step_index + 1 < len(q.steps) else -1
    finished = next_step == -1

    if finished:
        # 题目完成，记录薄弱点
        all_results = [step_result]  # 简化：只记录当前步骤
        for i in range(req.step_index):
            all_results.append(StepResult(step_index=i, step_name=q.steps[i].step_name, correct=True))
        error_analyzer.analyze(all_results)
        weak_point_tracker.record_error(q, all_results, user["user_id"])

        # P2 拓展闭环回写：步骤化答题完成后同步更新 L2 语义掌握度，
        # 使自适应选题(mode=adaptive) 对真实用户也能针对薄弱科目出题。
        # 此前仅更新 WeakPointTracker（无 redis 时仅内存、重启即丢），未写语义掌握度，
        # 导致真实用户 adaptive 永远静默回退到所请科目；演示账号因启动预置 31 条历史才看似正常。
        try:
            from services.memory_service import record_quiz_result
            overall_correct = bool(step_result.correct)
            record_quiz_result(
                user["user_id"], q.subject,
                correct=overall_correct,
                difficulty=q.difficulty,
                mastery_delta=0.05,
            )
        except Exception as _me:
            logger.debug("步骤化答题掌握度回写失败(忽略): %s", _me)

    return StepAnswerResponse(
        correct=correct,
        hint=step_result.hint,
        error_type=step_result.error_type,
        next_step=next_step,
        finished=finished,
    )


@router.get("/weak-points")
async def get_weak_points(subject: str = "", user: dict = Depends(get_current_user)):
    """获取用户薄弱知识点（答题追踪 + L2 记忆薄弱点聚合）"""
    weak = weak_point_tracker.get_weak_topics(user["user_id"], subject)

    # L1/L2/L3 三层学情记忆聚合（低侵入：L2 记忆薄弱点并入返回）
    memory_weak_extra = []
    try:
        from db.memory_store import get_semantic_memory
        mem = get_semantic_memory(user["user_id"])
        existing_concepts = {w.concept for w in weak}
        for wp in mem.get("weak_points", []):
            if wp and wp not in existing_concepts:
                memory_weak_extra.append({
                    "subject": subject or "unknown",
                    "chapter": "",
                    "concept": wp,
                    "error_type": "memory",
                    "count": 1,
                    "mastered": False,
                })
    except Exception as _me:
        logger.debug(f"薄弱点记忆聚合失败(降级): {_me}")

    return {
        "weak_points": [
            {
                "subject": w.subject,
                "chapter": w.chapter,
                "concept": w.concept,
                "error_type": w.error_type,
                "count": w.count,
                "mastered": w.mastered,
            }
            for w in weak
        ] + memory_weak_extra,
        "total": len(weak) + len(memory_weak_extra),
    }


@router.get("/history")
async def get_quiz_history(user: dict = Depends(get_current_user)):
    """获取答题历史记录"""
    from services.user_service import get_quiz_history as _get_history
    records = _get_history(user["user_id"])
    total = len(records)
    correct = sum(1 for r in records if r.get("correct"))
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / max(total, 1), 3),
        "records": records[-50:],  # 最近50条
    }


# ── 出题生成 ──

class GenerateQuizRequest(BaseModel):
    subject: str = "computer_network"
    difficulty: str = "medium"
    count: int = 3
    mode: str = "normal"  # "normal"=常规按科目/难度；"adaptive"=优先针对用户薄弱科目


def _weak_points_from_history(user_id: str, threshold: float) -> list[str]:
    """语义掌握度为空时的回退：读答题历史，按科目聚合正确率，正确率低于阈值者视为薄弱。
    返回已归一化的规范科目列表（network/transport/… → computer_network/…）。"""
    try:
        from db.profile_store import get_quiz_history
        history = get_quiz_history(user_id) or []
        return weak_points_from_history(history, threshold)
    except Exception:
        return []


def _adaptive_candidates(req: GenerateQuizRequest, user: dict) -> list:
    """自适应选题：读该用户掌握度矩阵 → detect_weak_points → 按薄弱科目过滤题库。

    两层数据源、严格可降级：
      1) 优先用语义记忆 mastery（由 quiz/submit 回写，键可能为中文/网络分层命名）；
      2) mastery 为空时回退到答题历史 user_quiz_history 按科目正确率推断薄弱科目；
      3) 任意异常或无可匹配薄弱点 → 返回空列表，调用方回退常规选题。
    薄弱点科目经 normalize_subject 归一化后再与题库 subject 匹配。
    """
    try:
        from config import get_remediation_threshold, get_remediation_max_points
        from db.memory_store import get_semantic_memory
        mem = get_semantic_memory(user.get("user_id", "")) or {}
        mastery = mem.get("mastery") or {}
        weak_points = detect_weak_points(
            mastery, get_remediation_threshold(), get_remediation_max_points()
        )
        if not weak_points:
            # 回退：语义掌握度为空（如演示账号），用答题历史按科目正确率推断薄弱科目
            weak_points = _weak_points_from_history(
                user.get("user_id", ""), get_remediation_threshold()
            )
        if not weak_points:
            return []
        return filter_questions_for_weak_points(weak_points, req.difficulty)
    except Exception as _e:
        logger.debug("自适应选题降级（常规选题）: %s", _e)
        return []


@router.post("/generate")
async def generate_quiz(req: GenerateQuizRequest, user: dict = Depends(require_llm_quota)):
    """根据科目/难度生成练习题；mode='adaptive' 时优先针对用户薄弱科目出题。"""
    if req.mode == "adaptive":
        candidates = _adaptive_candidates(req, user)
    else:
        candidates = [q for q in STEP_QUESTIONS if q.subject == req.subject]
        if req.difficulty != "all":
            candidates = [q for q in candidates if q.difficulty == req.difficulty]

    if not candidates:
        # 降级：仅按科目筛选
        candidates = [q for q in STEP_QUESTIONS if q.subject == req.subject]
        if not candidates:
            return {"questions": [], "total": 0, "subject": req.subject}

    # 随机选取
    selected = random.sample(candidates, min(req.count, len(candidates)))
    questions = []
    for q in selected:
        questions.append({
            "id": q.id,
            "subject": q.subject,
            "chapter": q.chapter,
            "difficulty": q.difficulty,
            "question_text": q.question_text,
            "steps": [{"step_name": s.step_name, "description": s.description,
                       "check_type": s.check_type, "options": s.options}
                      for s in q.steps],
        })

    # OS_course: snapshot generated quiz for immutability
    try:
        import json as _json, os as _os, hashlib as _hl
        snap_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), 'data', 'quiz_snapshots')
        _os.makedirs(snap_dir, exist_ok=True)
        snap_key = _hl.sha256(_json.dumps(questions, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
        snap_path = _os.path.join(snap_dir, f'{req.subject}_{snap_key}.json')
        with open(snap_path, 'w', encoding='utf-8') as _sf:
            _json.dump({'subject': req.subject, 'difficulty': req.difficulty, 'questions': questions,
                        'user_id': user.get('user_id', ''), 'generated_at': __import__('datetime').datetime.now().isoformat()},
                       _sf, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug("quiz snapshot write skipped (non-blocking): %s", e)

    return {"questions": questions, "total": len(questions), "subject": req.subject}
