# ============================================================
# API — 多 Agent 协作与资源生成（/api/agents/*）
# 已迁移：deps → db.llm_provider + db.milvus_client + utils.safety
# ============================================================

import asyncio
import json as json_mod
import logging
import random
import re

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from shared.sse_guard import sse_disconnect_guard

from db.llm_provider import LLMProvider
from db.milvus_client import vector_db
from utils.safety import filter_sensitive, check_hallucination
from shared.content_safety import audit_output  # P1-7：统一输出内容安全审核
from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota
from shared.prompt_guard import sanitize_user_input, wrap_untrusted  # F-015：轻量提示注入防护
from models import (
    AgentResourceRequest, AgentResourceResponse,
)

logger = logging.getLogger("netlearn.agents")
# F-011：多智能体资源生成端点统一鉴权 + 每用户 LLM 配额（429）
router = APIRouter(
    prefix="/agents", tags=["agents"],
    dependencies=[Depends(require_llm_quota)],
)

COLLECTION_NAME = "netlearn_kb"
@router.post("/generate-resource", response_model=AgentResourceResponse)
async def generate_resource(req: AgentResourceRequest, user: dict = Depends(get_current_user)):
    """多智能体资源生成：Teacher + QuizMaster + MediaDesigner + Critic 流水线"""
    # F-015：话题作为用户输入先做净化；外部检索结果用 wrap_untrusted 隔离
    safe_topic = sanitize_user_input(req.topic)
    knowledge_context = ""

    # L1/L2/L3 三层学情记忆注入（低侵入：记忆薄弱点并入检索，资源生成个性化）
    memory_ctx = ""
    try:
        user_id = user.get("user_id") or user.get("id") or ""
        if user_id:
            from services.memory_service import build_memory_context
            memory_ctx = build_memory_context(user_id, session_id=None, max_episodes=4)
    except Exception as _me:
        logger.debug(f"资源生成记忆注入失败(降级): {_me}")

    try:
        from engines.frugal_rag import frugal_rag
        import asyncio as _asyncio
        query = safe_topic
        if memory_ctx and memory_ctx != "【学生记忆】暂无历史学习数据":
            import re as _re
            weak_block = _re.search(r"薄弱[：:]\s*(.+?)(?:\n|$)", memory_ctx)
            if weak_block:
                weak_terms = [w.strip() for w in weak_block.group(1).split(",") if w.strip()][:3]
                if weak_terms:
                    query = f"{safe_topic} {' '.join(weak_terms)}"
        query_emb = await _asyncio.to_thread(frugal_rag.embed_query, query)
        results = await _asyncio.to_thread(vector_db.search, COLLECTION_NAME, query_emb, 5)
        if results:
            knowledge_context = wrap_untrusted("\n".join(r["text"] for r in results)[:2000])
    except Exception as e:  # T-OPT-01：知识库检索失败→降级空上下文，但必须记录
        logger.warning("知识库检索失败，降级为空上下文: %s", e)

    profile_info = ""
    if req.profile:
        p = req.profile
        profile_info = f" 学习风格:{p.get('learning_style','reading')} 基础:{p.get('knowledge_base','beginner')}"
    if memory_ctx and memory_ctx != "【学生记忆】暂无历史学习数据":
        profile_info += f" 学情记忆:{memory_ctx[:300]}"

    from prompts import (
        PLANNER_PROMPT, TEACHER_PROMPT, QUIZMASTER_PROMPT,
        MEDIA_AGENT_PROMPT, CRITIC_PROMPT,
    )

    llm = LLMProvider()

    planner_user = f"知识点: {safe_topic}，难度: {req.difficulty}{profile_info}\n\n知识库参考:\n{knowledge_context}"
    planner = await llm.text_completion(PLANNER_PROMPT, planner_user)

    tasks = {"teacher": "", "quizmaster": "", "media": ""}
    if planner:
        try:
            # PLANNER_PROMPT 输出格式: ---TEACHER_TASK---\n[content]\n---QUIZ_TASK--- ...
            sections = re.split(r'---([A-Z_]+)---\s*\n', planner)
            for i in range(1, len(sections) - 1, 2):
                key = sections[i].strip().upper()
                val = sections[i + 1].strip() if i + 1 < len(sections) else ""
                if key == "TEACHER_TASK":
                    tasks["teacher"] = val
                elif key == "QUIZ_TASK":
                    tasks["quizmaster"] = val
                elif key == "MEDIA_TASK":
                    tasks["media"] = val
        except Exception as e:  # T-OPT-01：规划结果解析失败→用默认任务，但必须记录
            logger.warning("规划结果解析失败，使用默认任务: %s", e)

    teacher_task = tasks.get("teacher") or f"请根据{safe_topic}生成一份知识点讲解文档"
    quiz_task = tasks.get("quizmaster") or f"请根据{safe_topic}生成10道练习题（含选择题、填空题、计算题）"
    media_task = tasks.get("media") or f"请为{safe_topic}设计一份思维导图大纲"

    async def _safe_call(prompt, user_prompt, name="agent"):
        try:
            return await llm.text_completion(prompt, user_prompt)
        except Exception as e:  # T-OPT-01：LLM 调用失败必须记录，禁止静默返回空
            logger.error("Agent[%s] LLM 调用失败: %s", name, e)
            return ""

    teacher_doc, quiz, media_plan = await asyncio.gather(
        _safe_call(TEACHER_PROMPT, teacher_task, name="teacher"),
        _safe_call(QUIZMASTER_PROMPT, quiz_task, name="quizmaster"),
        _safe_call(MEDIA_AGENT_PROMPT, media_task, name="media"),
    )

    # Critic 审阅实际生成的教学文档（而非占位符"..."）
    critic_review_content = (
        f"请审阅以下内容:\n\n"
        f"【教学文档】\n{teacher_doc[:3000] if teacher_doc else '(生成失败)'}\n\n"
        f"请对{safe_topic}的教学质量和准确性进行评估"
    )
    critic_report = await _safe_call(CRITIC_PROMPT, critic_review_content)

    # ── GOMARL 共识评估 + Agent 辩论 ──
    _hallu_warnings: list[str] = []  # P1-7: 提前初始化，供 GOMARL/审核链共用
    debate_used = False
    try:
        from engines.gomarl import GOMARLConsensus, AgentResult
        gomarl = GOMARLConsensus()
        agent_results = [
            AgentResult(agent_name="teacher", content=teacher_doc or ""),
            AgentResult(agent_name="quizmaster", content=quiz or ""),
            AgentResult(agent_name="media_designer", content=media_plan or ""),
        ]
        consensus = await gomarl.evaluate(agent_results, req.profile or {}, safe_topic)
        if consensus.status == "passed" and consensus.flagged_issues:
            # 有轻微问题但已通过——记录即可
            for issue in consensus.flagged_issues:
                _hallu_warnings.append(f"[GOMARL] {issue}")
        elif consensus.status == "regenerate" and len(consensus.regenerate_agents) == 2:
            # 两个 Agent 冲突 → 启动辩论协议
            from engines.agent_debate import agent_debate
            debate_contents = {}
            for r in agent_results:
                if r.agent_name in consensus.regenerate_agents:
                    debate_contents[r.agent_name] = r.content
            debate_result = await agent_debate.debate(
                agent_contents=debate_contents,
                topic=safe_topic,
                student_profile=req.profile or {},
                conflict_issues=consensus.flagged_issues,
            )
            if debate_result.issues_resolved > 0:
                # 用辩论精炼后的内容替换原结果
                for name, refined in debate_result.refined_content.items():
                    if name == "teacher" and refined:
                        teacher_doc = refined
                    elif name == "quizmaster" and refined:
                        quiz = refined
                    elif name == "media_designer" and refined:
                        media_plan = refined
                debate_used = True
                critic_review_content = (
                    f"请审阅经辩论精炼后的内容:\n\n"
                f"【教学文档】\n{teacher_doc[:3000]}\n\n"
                f"请对{safe_topic}的教学质量和准确性进行评估"
                )
                critic_report = await _safe_call(CRITIC_PROMPT, critic_review_content)
    except Exception as e:
        logger.warning(f"GOMARL/辩论评估失败（非阻塞）: {e}")

    # 内容安全全链路审核（P1-7）：敏感词 + 讯飞合规 + 幻觉检查
    teacher_doc, _n = await audit_output(teacher_doc, "agents/generate-resource/teacher")
    _hallu_warnings.extend(_n)
    quiz, _n = await audit_output(quiz, "agents/generate-resource/quiz")
    _hallu_warnings.extend(_n)
    media_plan, _n = await audit_output(media_plan, "agents/generate-resource/media")
    _hallu_warnings.extend(_n)
    if critic_report:
        critic_report, _n = await audit_output(critic_report, "agents/generate-resource/critic")
        _hallu_warnings.extend(_n)

    # T-OPT-01：核心三 Agent 全空→明确报错而非谎称 ok；部分失败→partial
    core_ok = bool(teacher_doc and quiz and media_plan)
    if core_ok:
        _status, _error = "ok", None
    elif teacher_doc or quiz or media_plan:
        _status, _error = "partial", "部分教学智能体生成失败（LLM 服务异常），已记录日志"
    else:
        _status, _error = "error", "核心教学智能体生成失败（LLM 服务异常），请检查 X2/DeepSeek 通道"
    if _error:
        logger.error("generate_resource 状态=%s: %s", _status, _error)
    return AgentResourceResponse(
        teacher_doc=teacher_doc,
        quiz=quiz,
        media_plan=media_plan,
        critic_report=critic_report,
        status=_status,
        hallucination_warnings=_hallu_warnings if _hallu_warnings else None,
        error=_error,
    )


@router.post("/generate-resource/stream")
async def generate_resource_stream(req: AgentResourceRequest, request: Request, user: dict = Depends(get_current_user)):
    """资源生成流水线 SSE 流式输出（带超时保护）"""
    async def event_stream():
        yield f"data: {json_mod.dumps({'type': 'status', 'content': 'retrieving', 'message': '正在检索知识库...'})}\n\n"

        # F-015：话题净化 + 外部检索内容包裹隔离
        safe_topic = sanitize_user_input(req.topic)
        knowledge_context = ""
        try:
            from engines.frugal_rag import frugal_rag
            import asyncio as _asyncio
            query_emb = await _asyncio.to_thread(frugal_rag.embed_query, safe_topic)
            results = await _asyncio.to_thread(vector_db.search, COLLECTION_NAME, query_emb, 5)
            if results:
                knowledge_context = wrap_untrusted("\n".join(r["text"] for r in results)[:2000])
        except Exception as e:  # T-OPT-01：流式版知识库检索失败→降级空上下文，必须记录
            logger.warning("stream 知识库检索失败，降级为空上下文: %s", e)

        yield f"data: {json_mod.dumps({'type': 'status', 'content': 'planning', 'message': '规划Agent正在分析...'})}\n\n"
        from prompts import PLANNER_PROMPT, TEACHER_PROMPT, QUIZMASTER_PROMPT, MEDIA_AGENT_PROMPT, CRITIC_PROMPT

        llm = LLMProvider()

        planner_user = f"知识点: {safe_topic}，难度: {req.difficulty}\n知识库参考:\n{knowledge_context}"
        try:
            planner = await asyncio.wait_for(llm.text_completion(PLANNER_PROMPT, planner_user), timeout=30)
        except asyncio.TimeoutError:
            planner = ""
            yield f"data: {json_mod.dumps({'type': 'error', 'content': '规划超时，跳过规划直接生成'})}\n\n"

        if not planner:
            planner = f"已为「{safe_topic}」完成学习规划分析。"

        teacher_task = f"请根据{safe_topic}生成一份知识点讲解文档"
        quiz_task = f"请根据{safe_topic}生成10道练习题（含选择题、填空题、计算题、简答题等多种题型）"
        media_task = f"请为{safe_topic}设计一份思维导图大纲"

        try:
            sections = re.split(r'---([A-Z_]+)---\s*\n', planner)
            for i in range(1, len(sections) - 1, 2):
                key = sections[i].strip().upper()
                val = sections[i + 1].strip() if i + 1 < len(sections) else ""
                if key == "TEACHER_TASK":
                    teacher_task = val
                elif key == "QUIZ_TASK":
                    quiz_task = val
                elif key == "MEDIA_TASK":
                    media_task = val
        except Exception as e:  # T-OPT-01：流式版规划解析失败→用默认任务，必须记录
            logger.warning("stream 规划结果解析失败，使用默认任务: %s", e)

        async def _emit_and_capture(prompt, user_prompt, tag, label):
            """调用 LLM，yield SSE 事件，返回生成的文本"""
            yield f"data: {json_mod.dumps({'type': 'status', 'content': tag, 'message': f'{label}正在生成...'})}\n\n"
            try:  # T-OPT-01：LLM 失败→发错误事件并日志，而非让流静默崩溃
                text = await llm.text_completion(prompt, user_prompt)
            except Exception as e:
                logger.error("stream Agent[%s] LLM 调用失败: %s", tag, e)
                yield f"data: {json_mod.dumps({'type': 'error', 'content': f'{label}生成失败：{e}', 'agent': tag})}\n\n"
                return
            if text:
                # P1-7：输出内容安全审核（敏感词 + 讯飞合规 + 幻觉检查）
                text, audit_notes = await audit_output(text, f"agents/generate-resource/stream/{tag}")
                if audit_notes:
                    yield f"data: {json_mod.dumps({'type': 'safety_alert', 'content': '; '.join(audit_notes), 'agent': tag})}\n\n"
                yield f"data: {json_mod.dumps({'type': 'content', 'content': text, 'agent': tag})}\n\n"

        # 依次调用教学Agent、出题Agent、媒体Agent，并捕获生成的内容
        _gens = {}
        for _tag, _prompt, _task, _label in [
            ("teacher", TEACHER_PROMPT, teacher_task, "教学Agent"),
            ("quizmaster", QUIZMASTER_PROMPT, quiz_task, "出题Agent"),
            ("media", MEDIA_AGENT_PROMPT, media_task, "媒体Agent"),
        ]:
            _gen = _emit_and_capture(_prompt, _task, _tag, _label)
            _result_lines = []
            async for _ev in _gen:
                yield _ev
                # 从 SSE data 中提取 content 字段，拼回结果文本
                if _ev.startswith("data: ") and '"content":' in _ev:
                    try:
                        _parsed = json_mod.loads(_ev[6:])
                        if _parsed.get("type") == "content":
                            _result_lines.append(_parsed["content"])
                    except Exception as e:  # T-OPT-01：SSE data 解析失败仅记录，不影响流
                        logger.debug("stream SSE data 解析跳过: %s", e)
            _gens[_tag] = "".join(_result_lines)

        teacher_doc = _gens.get("teacher", "")
        quiz = _gens.get("quizmaster", "")
        media_plan = _gens.get("media", "")

        # Critic 审阅：使用实际生成的内容进行审阅
        critic_input_parts = []
        if teacher_doc:
            critic_input_parts.append(f"【教学文档】\n{teacher_doc[:3000]}")
        if quiz:
            critic_input_parts.append(f"【练习题】\n{quiz[:2000]}")
        if media_plan:
            critic_input_parts.append(f"【媒体大纲】\n{media_plan[:2000]}")
        critic_report = ""
        if critic_input_parts:
            critic_prompt = (
                f"请审阅以下关于「{safe_topic}」的教学内容质量和准确性，"
                f"指出事实性错误或可以改进的地方：\n\n"
                + "\n\n".join(critic_input_parts)
            )
            try:
                critic_report = await llm.text_completion(CRITIC_PROMPT, critic_prompt)
            except Exception as e:  # T-OPT-01：审阅失败→降级跳过，但必须记录
                logger.warning("stream Critic 审阅失败，降级跳过: %s", e)

        # P1-7：审阅报告也做输出审核
        _critic_text = critic_report or '审阅完成'
        _critic_text, _c_notes = await audit_output(_critic_text, "agents/generate-resource/stream/critic")
        if _c_notes:
            yield f"data: {json_mod.dumps({'type': 'safety_alert', 'content': '; '.join(_c_notes), 'agent': 'critic'})}\n\n"
        yield f"data: {json_mod.dumps({'type': 'content', 'content': _critic_text, 'agent': 'critic'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse_disconnect_guard(request, event_stream()), media_type="text/event-stream")


@router.post("/generate-extension")
async def generate_extension(req: AgentResourceRequest, user: dict = Depends(get_current_user)):
    """生成课外拓展阅读材料"""
    from prompts import EXTENSION_AGENT_PROMPT
    llm = LLMProvider()
    result = await llm.text_completion(
        EXTENSION_AGENT_PROMPT,
        f"请为{sanitize_user_input(req.topic)}（难度: {req.difficulty}）生成课外拓展阅读材料",
    )
    hallucination_warnings = []
    if result:
        # P1-7：统一输出内容安全审核
        result, hallucination_warnings = await audit_output(result, "agents/generate-extension")
    return {"extension_doc": result or "", "hallucination_warnings": hallucination_warnings}


@router.post("/generate-ppt")
async def generate_ppt(req: AgentResourceRequest, user: dict = Depends(get_current_user)):
    """生成PPT幻灯片大纲（赛题功能2：≥5种资源类型含PPT）"""
    from prompts import PPT_AGENT_PROMPT
    llm = LLMProvider()
    profile_info = ""
    if req.profile:
        p = req.profile
        profile_info = f" 学习风格:{p.get('learning_style','reading')} 基础:{p.get('knowledge_base','beginner')}"
    result = await llm.text_completion(
        PPT_AGENT_PROMPT,
        f"请为{sanitize_user_input(req.topic)}（难度: {req.difficulty}{profile_info}）生成PPT幻灯片大纲",
    )
    # P1-7：统一输出内容安全审核
    if result:
        result, _ = await audit_output(result, "agents/generate-ppt")
    return {"ppt_outline": result or ""}


@router.post("/generate-code-practice")
async def generate_code_practice(req: AgentResourceRequest, user: dict = Depends(get_current_user)):
    """生成代码实操案例（赛题功能2：≥5种资源类型含代码实操案例）"""
    from prompts import CODE_PRACTICE_AGENT_PROMPT
    llm = LLMProvider()
    profile_info = ""
    if req.profile:
        p = req.profile
        profile_info = f" 学习风格:{p.get('learning_style','reading')} 基础:{p.get('knowledge_base','beginner')}"
    result = await llm.text_completion(
        CODE_PRACTICE_AGENT_PROMPT,
        f"请为{sanitize_user_input(req.topic)}（难度: {req.difficulty}{profile_info}）生成代码实操案例",
    )
    hallucination_warnings = []
    if result:
        # P1-7：统一输出内容安全审核
        result, hallucination_warnings = await audit_output(result, "agents/generate-code-practice")
    return {"code_practice": result or "", "hallucination_warnings": hallucination_warnings}
