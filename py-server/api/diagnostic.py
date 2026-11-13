# ============================================================
# API — 入学测评诊断（/api/diagnostic/*）
# 报告§3.2 前端交互层：「入学测评模块」
# 功能：诊断式初始画像构建，覆盖四科知识点掌握度评估
# ============================================================

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
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

# ── 逐题解析 ──
# 题库里不放解析，是为了让 /start 返回的题目保持干净的"题干+选项"；
# 交卷后按 id 取，随 details 一起下发，学生才能在结果页核对"为什么错"。
EXPLANATIONS = {
    "d_cn_1": "TCP 建立连接要三次握手：客户端先发 SYN（同步序号），服务端回 SYN+ACK，客户端再回 ACK。第一个报文只能是 SYN，客户端此时还没有任何可确认的数据。",
    "d_cn_2": "A 类地址首字节最高位为 0，第一字节取值 1–126（0 与 127 保留），所以范围写作 0.0.0.0–127.255.255.255。B 类是 128–191，C 类是 192–223，D 类 224 起是组播。",
    "d_cn_3": "OSI 七层自上而下：应用层、表示层、会话层、传输层、网络层、数据链路层、物理层。TCP/IP 常说的「五层」是折中模型，不是 OSI 本身。",
    "d_cn_4": "以太网 CSMA/CD 冲突后用的是「截断二进制指数退避」：第 n 次冲突从 0 到 2^n−1 中随机取值作为退避时隙数，重传 10 次后范围封顶，16 次放弃。",
    "d_cn_5": "慢启动阶段拥塞窗口按 RTT 翻倍（每收到一个 ACK 加 1 个 MSS），是指数增长；到慢启动阈值后转拥塞避免，才变成线性增长。",
    "d_ds_1": "栈是后进先出（LIFO），插入删除都在栈顶；先进先出是队列的特征。",
    "d_ds_2": "前序：根 → 左 → 右；中序：左 → 根 → 右；后序：左 → 右 → 根。",
    "d_ds_3": "快排平均 O(n log n)，最坏（每次划分都极不均衡）退化到 O(n²)。归并排序才是稳定的 O(n log n) 且最坏也是 O(n log n)。",
    "d_ds_4": "哈希冲突的常规处理是开放定址、再哈希、链地址、建立公共溢出区。二分查找要求表有序并按位置折半，是查找算法，不用于解决冲突。",
    "d_ds_5": "DFS 用栈（递归实现时用的是系统调用栈）回溯；BFS 用队列按层推进。",
    "d_co_1": "冯·诺依曼结构的核心是「存储程序」：指令和数据以同等地位存放在同一存储器，按地址顺序取出执行。",
    "d_co_2": "8 位补码中 −1 是全 1，即 11111111；10000000 是 −128，10000001 是 −127。",
    "d_co_3": "Cache 与主存的地址映射只有三种：直接映射、全相联映射、组相联映射。「顺序映射」不是映射方式。",
    "d_co_4": "PC（程序计数器）存放的是下一条待取指令的地址，取指后自动递增；它不存指令内容，也不存运算结果或状态标志（那些在 IR、ACC、PSW 里）。",
    "d_co_5": "DMA 由专门的控制器直接在内存和外设之间搬运数据块，CPU 只需在开始和结束时介入，因此传输期间 CPU 可以并行做别的事。",
    "d_os_1": "程序是静态的指令集合，存放在磁盘上；进程是程序在某数据集上的一次动态执行过程，有创建、就绪、运行、阻塞、终止的生命周期。",
    "d_os_2": "FCFS、SJF、时间片轮转都是进程调度算法；银行家算法是死锁避免算法，用来判断分配资源后系统是否仍处于安全状态。",
    "d_os_3": "虚拟内存靠「分页（或分段）+ 请求调页」实现：只把当前要用的页调入内存，缺页时再调，从而让逻辑地址空间可以远大于物理内存。单说分页只是地址划分，不构成虚拟内存。",
    "d_os_4": "LRU 替换的是「最近最久未使用」的页面，依据是局部性原理——很久没被访问的页，短期内大概率也不会被访问。注意它和 LFU（访问频率最低）不是一回事。",
    "d_os_5": "死锁四个必要条件：互斥、请求与保持、不可剥夺、循环等待。优先级反转是调度中的另一个问题（低优先级任务持锁导致高优先级任务被阻塞），不属于死锁条件。",
}


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
    # 逐题明细：学生交卷后要能核对「我选的 / 正确答案 / 对错 / 解析」
    details: list[dict] = []
    session_id: str = ""
    taken_at: str = ""


# ── 端点 ──

@router.get("/start", response_model=DiagnosticStartResponse)
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
    from services.user_service import save_profile

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

    # 逐题明细：交卷后要能逐题核对（用户作答 / 正确答案 / 对错 / 解析）。
    # 正确答案在这里才下发——/start 阶段刻意不发，避免边做边看答案。
    details = []
    for q in DIAGNOSTIC_QUESTIONS:
        ua = req.answers.get(q["id"], "")
        details.append({
            "question_id": q["id"],
            "subject": q["subject"],
            "subject_name": q["subject_name"],
            "topic": q["topic"],
            "question": q["question"],
            "options": q["options"],
            "user_answer": ua,
            "correct_answer": q["answer"],
            "is_correct": ua == q["answer"],
            "explanation": EXPLANATIONS.get(q["id"], ""),
        })

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

    # 整场测评落库：只存汇总的话，"去历史里核对答案"这件事就无从谈起
    import uuid
    from db.profile_store import append_diagnostic_history

    session_id = uuid.uuid4().hex[:12]
    taken_at = ""
    try:
        payload = {
            "results": [r.model_dump() for r in results],
            "overall_recommendation": overall_recommendation,
            "details": details,
        }
        taken_at = append_diagnostic_history(
            user["user_id"], session_id, round(overall_accuracy, 2), payload
        )
    except Exception as e:
        logger.warning(f"测评历史写入失败（非阻塞）: {e}")
        from datetime import datetime
        taken_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return DiagnosticSubmitResponse(
        results=results,
        overall_accuracy=round(overall_accuracy, 2),
        overall_recommendation=overall_recommendation,
        profile=profile,
        session_id=session_id,
        taken_at=taken_at,
        details=details,
    )


@router.get("/history")
async def diagnostic_history(user: dict = Depends(get_current_user)):
    """历次入学测评记录（含逐题明细），供「答题历史」页回看与核对答案。"""
    from db.profile_store import get_diagnostic_history

    user_id = user.get("user_id") or user.get("id") or ""
    try:
        records = get_diagnostic_history(user_id)
    except Exception as e:
        logger.warning(f"读取测评历史失败: {e}")
        records = []
    return {"status": "ok", "records": records}