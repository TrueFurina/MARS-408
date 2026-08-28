# ============================================================
# 资源生成集群 (Generator Cluster) — 7 Agent 并行
#
# 并行调用 7 个资源生成子 Agent:
#   1. Teacher       — 讲解文档 (text_completion)
#   2. QuizMaster    — 题库生成 (text_completion)
#   3. MindMap       — 思维导图  (4步流水线: 检索→骨架→标注掌握度→渲染)
#   4. Extension     — 拓展阅读 (text_completion)
#   5. CodePractice  — 代码实操 (text_completion)
#   6. PPTOutline    — PPT大纲  (text_completion)
#   7. VideoScript   — 视频脚本 (text_completion, Lite降级版)
#
# 每个子 Agent 都从 FrugalRAG 检索结果中获取参考知识。
# 生成后由 GOMARL 共识 + Critic 审阅做质量保障。
# ============================================================

import asyncio
import logging
from typing import Optional

from agents.state import AgentState
from db.llm_provider import LLMProvider
from engines.frugal_rag import format_retrieval_for_llm
from engines.gomarl import GOMARLConsensus, AgentResult
from prompts import (
    TEACHER_PROMPT, QUIZMASTER_PROMPT,
    EXTENSION_AGENT_PROMPT,
)
from agents.mindmap import generate_mindmap
from agents.code_practice import generate_code_practice
from agents.ppt_outline import generate_ppt_outline
from agents.video_script import generate_video_script

logger = logging.getLogger("netlearn.generator")


async def generator_cluster_node(state: AgentState) -> AgentState:
    """并行调用 7 个资源生成 Agent + GOMARL 共识"""
    state["status"] = "generating"
    state["current_agent"] = "generator_cluster"

    plan = state.get("plan", {})
    profile = state.get("student_profile", {})
    topic = state.get("topic_label") or state.get("topic", "")
    chunks = state.get("retrieved_chunks", [])
    diagnosis = state.get("diagnosis", {})
    # L1/L2/L3 三层学情记忆（低侵入注入：由 api/langgraph.py 经 build_memory_context 组装后写入 state）
    # 此前 4 个专用资源 Agent（mindmap/code/pppt/video）未被传入，导致记忆注入在编排层失效（死代码）。
    memory_context = state.get("memory_context") or ""

    # 构建知识上下文 (所有子 Agent 共享)
    knowledge_context = format_retrieval_for_llm(chunks, max_chars=3000)

    llm = LLMProvider()

    # ── 构建简单 text_completion Agent 的用户提示 ──
    teacher_prompt = _build_agent_prompt("teacher", plan, profile, knowledge_context, diagnosis, memory_context)
    quiz_prompt = _build_agent_prompt("quizmaster", plan, profile, knowledge_context, diagnosis, memory_context)
    extension_prompt = _build_agent_prompt("extension", plan, profile, knowledge_context, diagnosis, memory_context)

    # ── 7 个并行任务 ──
    # 3 个简单 text_completion (返回 str)
    teacher_task = llm.text_completion(
        TEACHER_PROMPT, teacher_prompt, temperature=0.7, max_tokens=2000
    )
    quiz_task = llm.text_completion(
        QUIZMASTER_PROMPT, quiz_prompt, temperature=0.7, max_tokens=2000
    )
    extension_task = llm.text_completion(
        EXTENSION_AGENT_PROMPT, extension_prompt, temperature=0.7, max_tokens=1500
    )

    # 4 个专用 Agent 函数 (各自管理 prompt + LLM 调用)
    mindmap_task = generate_mindmap(
        topic=topic, profile=profile,
        knowledge_context=knowledge_context, llm=llm, max_depth=4,
        memory_context=memory_context,
    )
    code_task = generate_code_practice(
        topic=topic, profile=profile,
        knowledge_context=knowledge_context, llm=llm,
        task_instruction=plan.get("code_task", ""),
        memory_context=memory_context,
    )
    ppt_task = generate_ppt_outline(
        topic=topic, profile=profile,
        knowledge_context=knowledge_context, llm=llm,
        task_instruction=plan.get("ppt_task", ""),
        memory_context=memory_context,
    )
    video_task = generate_video_script(
        topic=topic, profile=profile,
        knowledge_context=knowledge_context, llm=llm,
        task_instruction=plan.get("video_task", ""),
        memory_context=memory_context,
    )

    # ── 等待全部完成（T-OPT-02 并行调度）──
    # 7 个 Agent 任务并行 dispatch；return_exceptions=True 保证单 Agent 失败
    # 不影响整体（异常由下方 _unwrap_result 转为安全降级文案，绝不静默空响应）。
    # 各 LLM 调用自身有超时/重试；如需更硬的上限可包一层
    # asyncio.wait_for(..., timeout=N) 统一截断长尾。
    results = await asyncio.gather(
        teacher_task, quiz_task, extension_task,
        mindmap_task, code_task, ppt_task, video_task,
        return_exceptions=True,
    )

    # 解包结果
    teacher_doc = _unwrap_result(results[0], "Teacher")
    quiz = _unwrap_result(results[1], "QuizMaster")
    extension = _unwrap_result(results[2], "Extension")
    mindmap_result = _unwrap_mindmap(results[3])
    code_practice = _unwrap_result(results[4], "CodePractice")
    ppt_outline = _unwrap_result(results[5], "PPT")
    video_script = _unwrap_result(results[6], "VideoScript")

    # ── 写回状态 ──
    state["teacher_doc"] = teacher_doc
    state["quiz"] = quiz
    state["extension"] = extension
    state["code_practice"] = code_practice
    state["ppt_outline"] = ppt_outline
    state["video_script"] = video_script

    # 真实 .pptx 文件生成（赛题多模态硬性要求：原系统仅产出大纲文本/结构，无真实文件）
    try:
        from agents.ppt_builder import build_pptx
        # P1-2：build_pptx 为 CPU 密集型（python-pptx 写盘），放到默认线程池执行，
        # 避免阻塞 asyncio 事件循环导致整个资源生成流水线卡死。
        loop = asyncio.get_running_loop()
        _ppt_file = await loop.run_in_executor(None, build_pptx, topic, ppt_outline, profile)
        if _ppt_file.get("ok"):
            state["ppt_file"] = _ppt_file
            logger.info(f"[Generator] PPT文件已生成: {_ppt_file['filename']} ({_ppt_file['slide_count']}页)")
        else:
            state["ppt_file"] = None
            logger.warning(f"[Generator] PPT文件生成失败: {_ppt_file.get('error')}")
    except Exception as _e:
        state["ppt_file"] = None
        logger.error(f"[Generator] PPT文件生成异常: {_e}")

    # 真实数字人视频生成（P1-5②：防卡死封装）
    # 讯飞数字人为异步轮询（最长 ~5min）。若直接 await，会阻塞整个资源生成响应。
    # 用 wait_for 限制主流程最多等待 20s，超时即降级为脚本（video_file=None），
    # 不阻塞主流程；完整视频仍可在「讯飞AI工坊」面板按需异步获取。
    try:
        from agents.media_generator import generate_real_video
        _video_result = await asyncio.wait_for(
            generate_real_video(topic, video_script, profile), timeout=20
        )
        if _video_result.get("ok"):
            state["video_file"] = _video_result
            logger.info(f"[Generator] 数字人视频已生成: task_id={_video_result.get('task_id', '')}")
        else:
            state["video_file"] = None
            logger.info(f"[Generator] 数字人视频降级为脚本: {_video_result.get('error', '')}")
    except asyncio.TimeoutError:
        state["video_file"] = None
        logger.warning("[Generator] 数字人视频生成超过 20s 仍未完成，降级为脚本（不阻塞主流程）")
    except Exception as _ve:
        state["video_file"] = None
        logger.error(f"[Generator] 数字人视频生成异常: {_ve}")

    # 思维导图: 写入 mindmap 字段 + 兼容 media_plan
    if mindmap_result:
        state["mindmap"] = mindmap_result.to_dict()
        state["media_plan"] = mindmap_result.markdown or ""  # 向后兼容
        logger.info(f"[Generator] 思维导图: {mindmap_result.stats.total}个知识点, "
                     f"薄弱{mindmap_result.stats.weak}, 未学{mindmap_result.stats.unlearned}")
    else:
        state["mindmap"] = None
        state["media_plan"] = ""

    # ── GOMARL 共识 (7 个 Agent 结果) ──
    consensus_results = [
        AgentResult(agent_name="teacher", content=teacher_doc, prompt_used=TEACHER_PROMPT),
        AgentResult(agent_name="quizmaster", content=quiz, prompt_used=QUIZMASTER_PROMPT),
        AgentResult(
            agent_name="mindmap",
            content=mindmap_result.markdown if mindmap_result else "",
            prompt_used="mindmap_pipeline",
        ),
        AgentResult(agent_name="extension", content=extension, prompt_used=EXTENSION_AGENT_PROMPT),
        AgentResult(agent_name="code_practice", content=code_practice, prompt_used="code_practice"),
        AgentResult(agent_name="ppt_outline", content=ppt_outline, prompt_used="ppt_outline"),
        AgentResult(agent_name="video_script", content=video_script, prompt_used="video_script"),
    ]

    gomarl = GOMARLConsensus()
    consensus_result = await gomarl.evaluate(
        consensus_results, profile, topic,
        round_num=state.get("regenerate_round", 0),
    )

    state["consensus"] = {
        "status": consensus_result.status,
        "overall_score": consensus_result.overall_score,
        "flagged_issues": consensus_result.flagged_issues,
        "regenerate_agents": consensus_result.regenerate_agents,
        "merged_content": consensus_result.merged_content,
    }

    return state


def _build_agent_prompt(
    agent_type: str,
    plan: dict,
    profile: dict,
    knowledge_context: str,
    diagnosis: dict,
    memory_context: str = "",
) -> str:
    """为 text_completion 类子 Agent 构建用户提示

    用于 teacher / quizmaster / extension 三个简单 Agent。
    mindmap / code_practice / ppt_outline / video_script 有各自的 prompt 构建逻辑。
    """
    prompt_parts = [
        f"【学习主题】{plan.get('topic', '未指定')}",
        f"【所属章节】{plan.get('chapter', '未知')}",
        f"【难度】{plan.get('difficulty', 'medium')}",
    ]

    # L1/L2/L3 三层学情记忆（低侵入注入：memory_service.build_memory_context 组装）
    if memory_context and memory_context != "【学生记忆】暂无历史学习数据":
        prompt_parts.append(f"【历史学情记忆（L1会话/L2长期画像/L3情景事件）】\n{memory_context[:600]}")

    # Agent 特定任务
    task_map = {
        "teacher": plan.get("teacher_task", "生成知识点讲解文档"),
        "quizmaster": plan.get("quiz_task", "生成练习题"),
        "extension": plan.get("extension_task", "生成课外拓展阅读材料"),
    }
    prompt_parts.append(f"【任务指令】{task_map.get(agent_type, '')}")

    # 学生画像
    if profile:
        style = profile.get("learning_style", "reading")
        level = profile.get("knowledge_base", "beginner")
        prompt_parts.append(f"【学生画像】学习风格: {style}, 基础水平: {level}")
        weak = profile.get("weak_points", "")
        if weak:
            prompt_parts.append(f"【薄弱点】{weak}（请重点覆盖）")

    # 诊断报告摘要
    if diagnosis:
        focus = diagnosis.get("recommended_focus", [])
        if focus:
            prompt_parts.append(f"【推荐聚焦】{', '.join(focus[:3])}")

    # 知识库上下文
    if knowledge_context:
        prompt_parts.append(f"\n{knowledge_context}")

    # 输出格式提醒
    if agent_type == "teacher":
        prompt_parts.append("\n请先输出 ---TEACHER_START---，然后生成讲解内容。")
    elif agent_type == "quizmaster":
        prompt_parts.append("\n请先输出 ---QUIZ_START---，然后生成题目（含答案和解析）。")
    elif agent_type == "extension":
        prompt_parts.append("\n请先输出 ---EXTENSION_START---，然后生成拓展阅读材料。")

    return "\n\n".join(prompt_parts)


def _unwrap_result(result, agent_name: str) -> str:
    """处理 asyncio.gather 的异常结果 (返回 str 的 Agent)"""
    if isinstance(result, Exception):
        logger.error(f"{agent_name} 生成失败: {result}")
        return f"## {agent_name} 生成失败\n\n生成过程中出现错误: {str(result)}"
    return str(result) if result else ""


def _unwrap_mindmap(result) -> Optional[object]:
    """处理思维导图 Agent 的结果 (返回 MindMapResult 或 None)"""
    from schemas.mindmap import MindMapResult

    if isinstance(result, Exception):
        logger.error(f"MindMap 生成失败: {result}")
        return None
    if result is None:
        return None
    if isinstance(result, MindMapResult):
        return result
    logger.warning(f"MindMap 返回了意外类型: {type(result)}")
    return None
