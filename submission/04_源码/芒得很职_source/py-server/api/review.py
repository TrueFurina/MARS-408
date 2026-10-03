# ============================================================
# API — 错题复盘（/api/review/*）
# 报告§3.2 前端交互层：「错题复盘模块」
# 功能：错题分类统计、错题重做、关联知识点推送
# ============================================================

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from db.user_store import get_quiz_history, get_profile
from shared.auth import get_current_user

logger = logging.getLogger("netlearn.review")
router = APIRouter(prefix="/review", tags=["review"])


# ── 响应模型 ──

class WrongQuestion(BaseModel):
    id: int
    subject: str
    topic: str
    question: str
    user_answer: str
    correct_answer: str
    error_type: str
    hint: str
    timestamp: str


class SubjectSummary(BaseModel):
    subject: str
    subject_name: str
    total: int
    wrong: int
    accuracy: float
    weak_topics: list[str]


class ReviewSummaryResponse(BaseModel):
    total_questions: int
    total_wrong: int
    overall_accuracy: float
    by_subject: list[SubjectSummary]
    weak_topics: list[str]
    wrong_questions: list[WrongQuestion]
    recommendation: str


# ── 内置回顾题库（用于错题重做）──

REVIEW_QUESTIONS = [
    {"id": 1, "subject": "computer_network", "topic": "TCP",
     "question": "TCP三次握手中，客户端发送的第一个报文是？",
     "options": ["A: SYN", "B: ACK", "C: SYN+ACK", "D: FIN"],
     "answer": "A", "difficulty": "easy",
     "hint": "TCP建立连接时，客户端首先发送SYN报文表示请求连接"},
    {"id": 2, "subject": "computer_network", "topic": "IP地址",
     "question": "以下哪个是A类IP地址的范围？",
     "options": ["A: 0.0.0.0-127.255.255.255", "B: 128.0.0.0-191.255.255.255",
                 "C: 192.0.0.0-223.255.255.255", "D: 224.0.0.0-239.255.255.255"],
     "answer": "A", "difficulty": "easy",
     "hint": "A类地址首位为0，范围从0.0.0.0到127.255.255.255"},
    {"id": 3, "subject": "computer_network", "topic": "CSMA/CD",
     "question": "CSMA/CD协议中，检测到冲突后采用的退避算法是？",
     "options": ["A: 指数退避", "B: 截断二进制指数退避",
                 "C: 线性退避", "D: 随机退避"],
     "answer": "B", "difficulty": "medium",
     "hint": "CSMA/CD使用截断二进制指数退避算法，退避时间为2^k×基本退避时间"},
    {"id": 4, "subject": "data_structures", "topic": "栈",
     "question": "栈的典型特点是？",
     "options": ["A: 先进先出", "B: 先进后出", "C: 随机访问", "D: 双向访问"],
     "answer": "B", "difficulty": "easy",
     "hint": "栈是后进先出(LIFO)的数据结构，类似于一摞盘子"},
    {"id": 5, "subject": "data_structures", "topic": "树",
     "question": "二叉树的前序遍历顺序是？",
     "options": ["A: 左-根-右", "B: 根-左-右", "C: 左-右-根", "D: 根-右-左"],
     "answer": "B", "difficulty": "easy",
     "hint": "前序遍历顺序为：根节点→左子树→右子树"},
    {"id": 6, "subject": "computer_organization", "topic": "存储系统",
     "question": "Cache的地址映射方式不包括？",
     "options": ["A: 直接映射", "B: 全相联映射", "C: 组相联映射", "D: 顺序映射"],
     "answer": "D", "difficulty": "easy",
     "hint": "Cache映射方式有直接映射、全相联映射、组相联映射三种"},
    {"id": 7, "subject": "operating_system", "topic": "进程管理",
     "question": "操作系统中，进程与程序的主要区别是？",
     "options": ["A: 进程是静态的，程序是动态的", "B: 进程是动态的，程序是静态的",
                 "C: 两者都是动态的", "D: 两者都是静态的"],
     "answer": "B", "difficulty": "easy",
     "hint": "程序是静态的指令集合，进程是程序的一次动态执行过程"},
    {"id": 8, "subject": "operating_system", "topic": "页面置换",
     "question": "LRU页面置换算法替换的是？",
     "options": ["A: 最近最少使用的页面", "B: 最近最久未使用的页面",
                 "C: 最先进入的页面", "D: 访问频率最低的页面"],
     "answer": "B", "difficulty": "easy",
     "hint": "LRU(Least Recently Used)替换最近最久未使用的页面"},
]

SUBJECT_NAMES = {
    "computer_network": "计算机网络",
    "data_structures": "数据结构",
    "computer_organization": "计算机组成原理",
    "operating_system": "操作系统",
    # 章节级科目映射
    "overview": "计网-概述", "physical": "计网-物理层", "datalink": "计网-数据链路层",
    "network": "计网-网络层", "transport": "计网-运输层", "application": "计网-应用层", "security": "计网-网络安全",
    "ds_linear": "数据结构-线性表", "ds_stack": "数据结构-栈和队列", "ds_string": "数据结构-串",
    "ds_tree": "数据结构-树与二叉树", "ds_graph": "数据结构-图", "ds_search": "数据结构-查找", "ds_sort": "数据结构-排序",
    "co_overview": "计组-概述", "co_data": "计组-数据表示", "co_memory": "计组-存储系统",
    "co_isa": "计组-指令系统", "co_cpu": "计组-CPU", "co_bus": "计组-总线", "co_io": "计组-输入输出",
    "os_overview": "OS-概述", "os_process": "OS-进程管理", "os_memory": "OS-内存管理",
    "os_file": "OS-文件管理", "os_io": "OS-输入输出",
}


# ── 端点 ──

# 内存缓存：错题复盘统计缓存（60s）
_review_cache: dict = {}
_REVIEW_CACHE_TTL = 60

@router.get("/summary")
async def get_review_summary(user: dict = Depends(get_current_user)):
    """获取错题复盘统计"""
    import time
    user_id = user["user_id"]
    # 缓存检查
    now = time.time()
    cached = _review_cache.get(user_id)
    if cached and (now - cached["ts"]) < _REVIEW_CACHE_TTL:
        return cached["data"]
    quiz_history = get_quiz_history(user_id) or []

    # 按科目统计
    by_subject = {}
    wrong_questions = []

    for i, record in enumerate(quiz_history):
        subj = record.get("subject", "unknown")
        if subj not in by_subject:
            by_subject[subj] = {"total": 0, "wrong": 0, "weak_topics": set()}
        by_subject[subj]["total"] += 1
        if not record.get("correct", True):
            by_subject[subj]["wrong"] += 1
            # 修复：topic 缺失时回退到科目中文名，避免显示"未知"
            topic = record.get("topic") or SUBJECT_NAMES.get(subj, subj)
            by_subject[subj]["weak_topics"].add(topic)
            wrong_questions.append(WrongQuestion(
                id=i, subject=subj, topic=topic,
                question=record.get("question", ""),
                user_answer=record.get("user_answer", ""),
                correct_answer=record.get("correct_answer", ""),
                error_type=record.get("error_type", "unknown"),
                hint=record.get("hint", ""),
                timestamp=record.get("timestamp", ""),
            ))

    total = len(quiz_history)
    total_wrong = len(wrong_questions)
    overall_accuracy = (total - total_wrong) / max(total, 1)

    # 生成科目汇总
    subject_summaries = []
    all_weak_topics = []
    for subj, data in by_subject.items():
        acc = (data["total"] - data["wrong"]) / max(data["total"], 1)
        weak_list = sorted(data["weak_topics"])
        all_weak_topics.extend(weak_list)
        subject_summaries.append(SubjectSummary(
            subject=subj, subject_name=SUBJECT_NAMES.get(subj, subj),
            total=data["total"], wrong=data["wrong"],
            accuracy=round(acc, 2), weak_topics=weak_list,
        ))

    # 生成推荐建议
    if total == 0:
        recommendation = "还没有答题记录，去做一些练习题来发现薄弱点吧！"
    elif overall_accuracy >= 0.8:
        recommendation = "整体掌握良好，建议挑战更高难度题目"
    elif overall_accuracy >= 0.5:
        weak_str = "、".join(all_weak_topics[:5]) if all_weak_topics else "部分知识点"
        recommendation = f"薄弱点集中在{weak_str}，建议针对性复习后重做错题"
    else:
        recommendation = "基础较弱，建议从基础概念开始系统学习，优先补足核心知识点"

    return ReviewSummaryResponse(
        total_questions=total,
        total_wrong=total_wrong,
        overall_accuracy=round(overall_accuracy, 2),
        by_subject=subject_summaries,
        weak_topics=sorted(set(all_weak_topics)),
        wrong_questions=wrong_questions[:20],  # 只返回最近20条
        recommendation=recommendation,
    )


@router.get("/questions/{subject}")
async def get_review_questions(subject: str, user: dict = Depends(get_current_user)):
    """获取指定科目的错题重做题目"""
    # 筛选该科目的题目
    questions = [q for q in REVIEW_QUESTIONS if q["subject"] == subject]
    if not questions:
        raise HTTPException(status_code=404, detail=f"未找到{subject}的回顾题目")

    return {
        "subject": subject,
        "subject_name": SUBJECT_NAMES.get(subject, subject),
        "total": len(questions),
        "questions": [{k: v for k, v in q.items() if k != "answer"} for q in questions],
    }


@router.post("/retry")
async def retry_wrong_question(data: dict, user: dict = Depends(get_current_user)):
    """错题重做提交"""
    from db.user_store import append_quiz_history

    question_id = data.get("question_id")
    user_answer = data.get("answer", "")
    if not question_id:
        raise HTTPException(status_code=400, detail="question_id 不能为空")

    # 查找题目
    question = next((q for q in REVIEW_QUESTIONS if q["id"] == question_id), None)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    correct = user_answer == question["answer"]
    result = {
        "subject": question["subject"],
        "topic": question["topic"],
        "question": question["question"],
        "user_answer": user_answer,
        "correct_answer": question["answer"],
        "correct": correct,
        "error_type": "" if correct else "retry_wrong",
        "hint": question["hint"] if not correct else "",
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }
    append_quiz_history(user["user_id"], [result])

    # L1/L2/L3 三层学情记忆联动（低侵入：错题重做入 L3，供复习闭环追溯）
    try:
        from db import memory_store as _ms
        _ms.append_episode(user["user_id"], "review_retry", {
            "subject": question["subject"],
            "topic": question["topic"],
            "correct": bool(correct),
        })
    except Exception as _me:
        logger.debug(f"复习记忆写入失败(忽略): {_me}")

    return {
        "correct": correct,
        "correct_answer": question["answer"],
        "hint": question["hint"] if not correct else "",
        "message": "回答正确！" if correct else f"回答错误，正确答案是{question['answer']}",
    }