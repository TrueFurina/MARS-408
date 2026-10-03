# ============================================================
# API — 入学测评诊断（/api/diagnostic/*）
# 报告§3.2 前端交互层：「入学测评模块」
# 功能：诊断式初始画像构建，覆盖四科知识点掌握度评估
# ============================================================

import json
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from seed_data import SEED_KNOWLEDGE_CHUNKS, SEED_QUESTIONS
from shared.auth import get_current_user

logger = logging.getLogger("netlearn.diagnostic")
router = APIRouter(prefix="/diagnostic", tags=["diagnostic"])

# ── 诊断题库（四科各5题，覆盖核心知识点）──
DIAGNOSTIC_QUESTIONS = [
    # 计算机网络
    {"id": "d_cn_1", "subject": "computer_network", "subject_name": "计算机网络",
     "question": "TCP三次握手中，客户端发送的第一个报文是？",
     "options": ["A: SYN", "B: ACK", "C: SYN+ACK", "D: FIN"],
     "answer": "A", "difficulty": "easy", "topic": "TCP"},
    {"id": "d_cn_2", "subject": "computer_network", "subject_name": "计算机网络",
     "question": "以下哪个是A类IP地址的范围？",
     "options": ["A: 0.0.0.0-127.255.255.255", "B: 128.0.0.0-191.255.255.255",
                 "C: 192.0.0.0-223.255.255.255", "D: 224.0.0.0-239.255.255.255"],
     "answer": "A", "difficulty": "easy", "topic": "IP地址"},
    {"id": "d_cn_3", "subject": "computer_network", "subject_name": "计算机网络",
     "question": "OSI参考模型共有几层？",
     "options": ["A: 4层", "B: 5层", "C: 7层", "D: 8层"],
     "answer": "C", "difficulty": "easy", "topic": "体系结构"},
    {"id": "d_cn_4", "subject": "computer_network", "subject_name": "计算机网络",
     "question": "CSMA/CD协议中，检测到冲突后采用的退避算法是？",
     "options": ["A: 指数退避", "B: 截断二进制指数退避",
                 "C: 线性退避", "D: 随机退避"],
     "answer": "B", "difficulty": "medium", "topic": "CSMA/CD"},
    {"id": "d_cn_5", "subject": "computer_network", "subject_name": "计算机网络",
     "question": "TCP拥塞控制中，慢启动阶段拥塞窗口的增长方式是？",
     "options": ["A: 线性增长", "B: 指数增长", "C: 对数增长", "D: 固定值"],
     "answer": "B", "difficulty": "medium", "topic": "拥塞控制"},

    # 数据结构
    {"id": "d_ds_1", "subject": "data_structures", "subject_name": "数据结构",
     "question": "栈的典型特点是？",
     "options": ["A: 先进先出", "B: 先进后出", "C: 随机访问", "D: 双向访问"],
     "answer": "B", "difficulty": "easy", "topic": "栈"},
    {"id": "d_ds_2", "subject": "data_structures", "subject_name": "数据结构",
     "question": "二叉树的前序遍历顺序是？",
     "options": ["A: 左-根-右", "B: 根-左-右", "C: 左-右-根", "D: 根-右-左"],
     "answer": "B", "difficulty": "easy", "topic": "树"},
    {"id": "d_ds_3", "subject": "data_structures", "subject_name": "数据结构",
     "question": "快速排序的平均时间复杂度是？",
     "options": ["A: O(n)", "B: O(nlogn)", "C: O(n²)", "D: O(logn)"],
     "answer": "B", "difficulty": "medium", "topic": "排序"},
    {"id": "d_ds_4", "subject": "data_structures", "subject_name": "数据结构",
     "question": "哈希表解决冲突的常用方法不包括？",
     "options": ["A: 开放定址法", "B: 再哈希法", "C: 链地址法", "D: 二分查找法"],
     "answer": "D", "difficulty": "medium", "topic": "查找"},
    {"id": "d_ds_5", "subject": "data_structures", "subject_name": "数据结构",
     "question": "图的深度优先遍历使用的数据结构是？",
     "options": ["A: 队列", "B: 栈", "C: 数组", "D: 链表"],
     "answer": "B", "difficulty": "medium", "topic": "图"},

    # 计算机组成原理
    {"id": "d_co_1", "subject": "computer_organization", "subject_name": "计算机组成原理",
     "question": "冯·诺依曼结构的核心思想是？",
     "options": ["A: 分布式计算", "B: 存储程序", "C: 并行处理", "D: 虚拟化"],
     "answer": "B", "difficulty": "easy", "topic": "概述"},
    {"id": "d_co_2", "subject": "computer_organization", "subject_name": "计算机组成原理",
     "question": "补码表示的整数-1在8位二进制中是？",
     "options": ["A: 10000001", "B: 11111111", "C: 11111110", "D: 10000000"],
     "answer": "B", "difficulty": "medium", "topic": "数据表示"},
    {"id": "d_co_3", "subject": "computer_organization", "subject_name": "计算机组成原理",
     "question": "Cache的地址映射方式不包括？",
     "options": ["A: 直接映射", "B: 全相联映射", "C: 组相联映射", "D: 顺序映射"],
     "answer": "D", "difficulty": "easy", "topic": "存储系统"},
    {"id": "d_co_4", "subject": "computer_organization", "subject_name": "计算机组成原理",
     "question": "CPU中程序计数器(PC)的功能是？",
     "options": ["A: 存储指令", "B: 存储下一条指令地址",
                 "C: 存储运算结果", "D: 存储状态标志"],
     "answer": "B", "difficulty": "easy", "topic": "CPU"},
    {"id": "d_co_5", "subject": "computer_organization", "subject_name": "计算机组成原理",
     "question": "DMA方式的优点是？",
     "options": ["A: 不需要CPU干预", "B: 传输速度快，CPU可并行工作",
                 "C: 实现简单", "D: 成本低"],
     "answer": "B", "difficulty": "medium", "topic": "I/O"},

    # 操作系统
    {"id": "d_os_1", "subject": "operating_system", "subject_name": "操作系统",
     "question": "操作系统中，进程与程序的主要区别是？",
     "options": ["A: 进程是静态的，程序是动态的", "B: 进程是动态的，程序是静态的",
                 "C: 两者都是动态的", "D: 两者都是静态的"],
     "answer": "B", "difficulty": "easy", "topic": "进程管理"},
    {"id": "d_os_2", "subject": "operating_system", "subject_name": "操作系统",
     "question": "以下哪个不是进程调度算法？",
     "options": ["A: 先来先服务", "B: 短作业优先", "C: 银行家算法", "D: 时间片轮转"],
     "answer": "C", "difficulty": "medium", "topic": "进程调度"},
    {"id": "d_os_3", "subject": "operating_system", "subject_name": "操作系统",
     "question": "虚拟内存管理的基础是？",
     "options": ["A: 分页技术", "B: 分段技术", "C: 分页+请求调页", "D: 覆盖技术"],
     "answer": "C", "difficulty": "medium", "topic": "内存管理"},
    {"id": "d_os_4", "subject": "operating_system", "subject_name": "操作系统",
     "question": "LRU页面置换算法替换的是？",
     "options": ["A: 最近最少使用的页面", "B: 最近最久未使用的页面",
                 "C: 最先进入的页面", "D: 访问频率最低的页面"],
     "answer": "B", "difficulty": "easy", "topic": "页面置换"},
    {"id": "d_os_5", "subject": "operating_system", "subject_name": "操作系统",
     "question": "死锁产生的四个必要条件不包括？",
     "options": ["A: 互斥条件", "B: 请求与保持", "C: 循环等待", "D: 优先级反转"],
     "answer": "D", "difficulty": "medium", "topic": "死锁"},
]


# ── 请求/响应模型 ──

class DiagnosticStartResponse(BaseModel):
    """开始诊断返回的题目列表"""
    total_questions: int
    subjects: list[str]
    questions: list[dict]


class DiagnosticSubmitRequest(BaseModel):
    """提交诊断答案"""
    answers: dict[str, str]  # {question_id: selected_option}


class DiagnosticResult(BaseModel):
    """单科目诊断结果"""
    subject: str
    subject_name: str
    total: int
    correct: int
    accuracy: float
    weak_topics: list[str]
    strong_topics: list[str]
    recommendation: str


class DiagnosticSubmitResponse(BaseModel):
    """诊断提交返回结果"""
    results: list[DiagnosticResult]
    overall_accuracy: float
    overall_recommendation: str
    profile: dict


# ── 端点 ──

@router.get("/start")
async def start_diagnostic(user: dict = Depends(get_current_user)):
    """获取入学测评题目"""
    subjects = ["computer_network", "data_structures", "computer_organization", "operating_system"]
    subject_names = {
        "computer_network": "计算机网络",
        "data_structures": "数据结构",
        "computer_organization": "计算机组成原理",
        "operating_system": "操作系统",
    }
    # 返回不带答案的题目
    questions = []
    for q in DIAGNOSTIC_QUESTIONS:
        questions.append({
            "id": q["id"],
            "subject": q["subject"],
            "subject_name": q["subject_name"],
            "question": q["question"],
            "options": q["options"],
            "difficulty": q["difficulty"],
            "topic": q["topic"],
        })
    return DiagnosticStartResponse(
        total_questions=len(questions),
        subjects=[subject_names[s] for s in subjects],
        questions=questions,
    )


@router.post("/submit", response_model=DiagnosticSubmitResponse)
async def submit_diagnostic(req: DiagnosticSubmitRequest, user: dict = Depends(get_current_user)):
    """提交诊断答案并生成画像和推荐"""
    from db.user_store import save_profile

    # L1/L2/L3 三层学情记忆联动（低侵入：诊断结果写入 L2 语义记忆）
    try:
        user_id = user.get("user_id") or user.get("id") or ""
        from db import memory_store as _ms
        _ms.append_episode(user_id, "diagnostic", {
            "total_questions": len(DIAGNOSTIC_QUESTIONS),
            "answers_count": len(req.answers),
        })
    except Exception as _me:
        logger.debug(f"诊断记忆事件写入失败(忽略): {_me}")

    # 按科目统计
    subject_results = {}
    for q in DIAGNOSTIC_QUESTIONS:
        subj = q["subject"]
        if subj not in subject_results:
            subject_results[subj] = {
                "subject_name": q["subject_name"],
                "total": 0, "correct": 0,
                "topics": {},
            }
        subject_results[subj]["total"] += 1
        topic = q["topic"]
        if topic not in subject_results[subj]["topics"]:
            subject_results[subj]["topics"][topic] = {"total": 0, "correct": 0}

        subject_results[subj]["topics"][topic]["total"] += 1
        user_answer = req.answers.get(q["id"], "")
        if user_answer == q["answer"]:
            subject_results[subj]["correct"] += 1
            subject_results[subj]["topics"][topic]["correct"] += 1

    # 生成各科目诊断结果
    results = []
    weak_topics_all = []
    strong_topics_all = []
    total_correct = 0
    total_questions = len(DIAGNOSTIC_QUESTIONS)

    for subj, data in subject_results.items():
        accuracy = data["correct"] / data["total"] if data["total"] > 0 else 0
        weak_topics = []
        strong_topics = []
        for topic, tdata in data["topics"].items():
            t_acc = tdata["correct"] / tdata["total"] if tdata["total"] > 0 else 0
            if t_acc < 0.5:
                weak_topics.append(topic)
                weak_topics_all.append(f"{data['subject_name']}-{topic}")
            else:
                strong_topics.append(topic)
                strong_topics_all.append(f"{data['subject_name']}-{topic}")

        # 生成推荐建议
        if accuracy >= 0.8:
            recommendation = f"{data['subject_name']}基础扎实，可以进入强化阶段"
        elif accuracy >= 0.5:
            weak_str = "、".join(weak_topics) if weak_topics else "部分知识点"
            recommendation = f"{data['subject_name']}需要重点加强{weak_str}"
        else:
            recommendation = f"{data['subject_name']}需要从基础开始系统学习"

        results.append(DiagnosticResult(
            subject=subj, subject_name=data["subject_name"],
            total=data["total"], correct=data["correct"],
            accuracy=round(accuracy, 2), weak_topics=weak_topics,
            strong_topics=strong_topics, recommendation=recommendation,
        ))
        total_correct += data["correct"]

    overall_accuracy = total_correct / total_questions if total_questions > 0 else 0

    # 生成整体推荐
    if overall_accuracy >= 0.8:
        overall_recommendation = "整体基础扎实，建议进入强化阶段，重点攻克高频考点和跨科目综合题"
    elif overall_accuracy >= 0.5:
        overall_recommendation = f"部分科目存在薄弱点，建议优先补齐：{'、'.join(weak_topics_all[:5])}"
    else:
        overall_recommendation = "建议从基础概念开始系统学习，按「计网→数据结构→计组→OS」顺序逐步推进"

    # 生成并保存画像
    profile = {
        "knowledge_base": "advanced" if overall_accuracy >= 0.8 else "intermediate" if overall_accuracy >= 0.5 else "beginner",
        "weak_topics": weak_topics_all,
        "strong_topics": strong_topics_all,
        "overall_accuracy": overall_accuracy,
        "diagnostic_completed": True,
        "learning_style": "reading",
        "goal": "exam",
        "progress": 0,
        "study_time": "2-4h",
        "preferred_difficulty": "medium" if overall_accuracy >= 0.5 else "easy",
    }
    try:
        save_profile(user["user_id"], profile)
        logger.info(f"诊断画像已保存: user={user['user_id']}, accuracy={overall_accuracy:.2f}")
    except Exception as e:
        logger.warning(f"画像保存失败（非阻塞）: {e}")

    return DiagnosticSubmitResponse(
        results=results,
        overall_accuracy=round(overall_accuracy, 2),
        overall_recommendation=overall_recommendation,
        profile=profile,
    )