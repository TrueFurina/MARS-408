# ============================================================
# 智能答题引擎 — 步骤拆解 + 错因分析 + 薄弱点追踪
#
# 核心能力：
# 1. 步骤拆解：将复杂题目拆成可独立判断的子步骤
# 2. 错因分析：分类错误原因（概念混淆/计算错误/遗漏条件）
# 3. 薄弱点追踪：记录错因 → 优先出同类题 → 闭环追踪
# ============================================================

import json
import logging
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger("netlearn.quiz_engine")


# ── 数据结构 ──

@dataclass
class StepResult:
    """单步答题结果"""
    step_index: int
    step_name: str
    correct: bool
    user_answer: str = ""
    correct_answer: str = ""
    error_type: str = ""       # concept_confusion / calculation_error / missing_condition / correct
    hint: str = ""             # 针对性的提示
    confidence: float = 0.0    # 学生对这一步的把握度


@dataclass
class QuestionStep:
    """题目拆解步骤"""
    step_name: str
    description: str
    check_type: str  # choice / fill / formula
    options: list[str] = field(default_factory=list)
    answer: str = ""
    hint_on_error: str = ""
    error_type_if_wrong: str = "concept_confusion"


@dataclass
class StepQuestion:
    """步骤化题目"""
    id: str
    subject: str
    chapter: str
    difficulty: str
    question_text: str
    steps: list[QuestionStep]
    error_type_map: dict = field(default_factory=dict)  # 错因 → 知识点映射


@dataclass
class WeakPoint:
    """薄弱点记录"""
    subject: str
    chapter: str
    concept: str           # 具体知识点
    error_type: str        # 错因类型
    count: int = 0          # 出错次数
    last_wrong: str = ""    # 最后出错时间
    mastered: bool = False  # 是否已掌握


# ── 步骤化题目库 ──

STEP_QUESTIONS: list[StepQuestion] = [
    # ── 计算机网络：TCP拥塞控制 ──
    StepQuestion(
        id="step_tcp_1", subject="computer_network", chapter="tcp_congestion", difficulty="hard",
        question_text="TCP拥塞控制：发送窗口从12KB增长到18KB，ssthresh=16KB。请问此时处于什么阶段？窗口增长方式是什么？",
        steps=[
            QuestionStep(step_name="判断阶段", description="当前窗口12KB < ssthresh(16KB)，处于哪个阶段？",
                         check_type="choice", options=["慢启动（指数增长）", "拥塞避免（线性增长）", "快恢复", "超时重传"],
                         answer="慢启动（指数增长）", hint_on_error="慢启动阶段窗口 < ssthresh，窗口指数增长；拥塞避免阶段窗口 ≥ ssthresh，窗口线性增长。",
                         error_type_if_wrong="concept_confusion"),
            QuestionStep(step_name="计算增长", description="慢启动阶段每收到一个ACK，窗口如何变化？",
                         check_type="choice", options=["加1KB", "翻倍（×2）", "加1 MSS", "不变"],
                         answer="翻倍（×2）", hint_on_error="慢启动每收到一个ACK，窗口翻倍（指数增长）。拥塞避免才每RTT加1。",
                         error_type_if_wrong="concept_confusion"),
            QuestionStep(step_name="确认结果", description="窗口从12KB增长到18KB，增长了多少？",
                         check_type="choice", options=["6KB（指数增长，12→24但被ssthresh限制）", "6KB（线性增长，每次+1）", "12KB", "3KB"],
                         answer="6KB（指数增长，12→24但被ssthresh限制）",
                         hint_on_error="慢启动指数增长：12→24，但增长到ssthresh(16)后切换为拥塞避免线性增长，所以最终到18。",
                         error_type_if_wrong="calculation_error"),
        ],
        error_type_map={"concept_confusion": "TCP拥塞控制阶段判断", "calculation_error": "TCP窗口计算"},
    ),
    # ── 数据结构：二叉树遍历 ──
    StepQuestion(
        id="step_tree_1", subject="data_structures", chapter="tree", difficulty="medium",
        question_text="已知二叉树先序序列为 ABDECF，中序序列为 DBEAFC，求后序序列。",
        steps=[
            QuestionStep(step_name="确定根节点", description="先序遍历的第一个节点是什么？",
                         check_type="choice", options=["A", "B", "D", "C"],
                         answer="A", hint_on_error="先序遍历的第一个节点是根节点。",
                         error_type_if_wrong="concept_confusion"),
            QuestionStep(step_name="划分左右子树", description="在中序序列中找到A，A的左边有哪些节点？",
                         check_type="choice", options=["DBE", "BDE", "EDB", "FC"],
                         answer="DBE", hint_on_error="中序序列中，根节点左边是左子树，右边是右子树。A在第二个位置，左边是D、B、E。",
                         error_type_if_wrong="missing_condition"),
            QuestionStep(step_name="递归构建", description="左子树先序为BDE，中序为DBE，左子树的根是？",
                         check_type="choice", options=["B", "D", "E", "C"],
                         answer="B", hint_on_error="左子树的先序第一个节点是B，所以B是左子树的根。",
                         error_type_if_wrong="concept_confusion"),
            QuestionStep(step_name="求后序", description="根据以上分析，后序序列是？",
                         check_type="choice", options=["DEBFCA", "DBEFCA", "DEBCFA", "EDBFCA"],
                         answer="DEBFCA",
                         hint_on_error="后序遍历：左→右→根。左子树后序DEB，右子树后序FC，根A。合起来DEBFCA。",
                         error_type_if_wrong="calculation_error"),
        ],
        error_type_map={"concept_confusion": "二叉树遍历概念", "missing_condition": "中序划分", "calculation_error": "后序推导"},
    ),
    # ── 计算机组成原理：Cache映射 ──
    StepQuestion(
        id="step_cache_1", subject="computer_organization", chapter="cache", difficulty="hard",
        question_text="主存容量256MB，按字节编址，Cache容量64KB，块大小32B，采用直接映射方式。计算Cache行数，并给出主存地址1A2B3C4H对应的Cache行号。",
        steps=[
            QuestionStep(step_name="计算Cache行数", description="Cache容量64KB，块大小32B，Cache有多少行？",
                         check_type="choice", options=["2048", "1024", "4096", "512"],
                         answer="2048", hint_on_error="Cache行数 = Cache容量 / 块大小 = 64KB / 32B = 65536/32 = 2048。",
                         error_type_if_wrong="calculation_error"),
            QuestionStep(step_name="地址分解", description="直接映射下，主存地址分为哪三部分？",
                         check_type="choice", options=["标记+行号+块内地址", "行号+标记+块内地址", "块内地址+行号+标记", "标记+块内地址+行号"],
                         answer="标记+行号+块内地址", hint_on_error="直接映射地址格式：标记位 | Cache行号 | 块内地址。",
                         error_type_if_wrong="concept_confusion"),
            QuestionStep(step_name="计算地址位", description="块大小32B=2^5，Cache行数2048=2^11，主存256MB=2^28。标记位几位？",
                         check_type="choice", options=["12", "28-5-11=12", "28-11=17", "28-5=23"],
                         answer="12", hint_on_error="标记位位数 = 主存地址位数 - 行号位数 - 块内地址位数 = 28 - 11 - 5 = 12。",
                         error_type_if_wrong="calculation_error"),
            QuestionStep(step_name="计算行号", description="地址1A2B3C4H，块内地址5位，行号11位，行号是？",
                         check_type="choice", options=["0x1A2B3C4H >> 5 取低11位", "0x1A2B3C4H & 0xFFFF", "0x1A2B3C4H >> 5", "0x1A2B3C4H & 0x7FF"],
                         answer="0x1A2B3C4H >> 5 取低11位",
                         hint_on_error="行号 = 地址右移5位（去掉块内地址），再取低11位。",
                         error_type_if_wrong="calculation_error"),
        ],
        error_type_map={"concept_confusion": "Cache映射概念", "calculation_error": "Cache地址计算"},
    ),
    # ── 操作系统：页面置换 ──
    StepQuestion(
        id="step_page_1", subject="operating_system", chapter="page_replacement", difficulty="medium",
        question_text="某进程页面访问序列为：7,0,1,2,0,3,0,4,2,3,0,3,2,1,2，内存分配3个页框。使用LRU算法，写出每次缺页时的置换情况。",
        steps=[
            QuestionStep(step_name="初始化", description="LRU的含义是什么？",
                         check_type="choice", options=["最近最久未使用", "先进先出", "最优置换", "最不经常使用"],
                         answer="最近最久未使用", hint_on_error="LRU = Least Recently Used，淘汰最近最久未使用的页面。",
                         error_type_if_wrong="concept_confusion"),
            QuestionStep(step_name="前3步", description="前3次访问7,0,1，页框为空，是否缺页？",
                         check_type="choice", options=["都缺页，直接装入", "都不缺页", "第1次缺页", "第3次缺页"],
                         answer="都缺页，直接装入", hint_on_error="初始页框为空，前3次访问都缺页，直接装入无需置换。",
                         error_type_if_wrong="missing_condition"),
            QuestionStep(step_name="第4步", description="第4次访问2，页框已满，LRU淘汰谁？",
                         check_type="choice", options=["7（最早进入的）", "0", "1", "2（当前访问的不淘汰）"],
                         answer="7（最早进入的）", hint_on_error="LRU淘汰最近最久未使用的页面。此时7,0,1中7最久未使用。",
                         error_type_if_wrong="concept_confusion"),
            QuestionStep(step_name="计算缺页率", description="若总缺页次数为9，总访问15次，缺页率是？",
                         check_type="choice", options=["60%", "9/15=60%", "40%", "6/15=40%"],
                         answer="60%", hint_on_error="缺页率 = 缺页次数 / 总访问次数 = 9/15 = 60%。",
                         error_type_if_wrong="calculation_error"),
        ],
        error_type_map={"concept_confusion": "页面置换算法", "missing_condition": "LRU初始状态", "calculation_error": "缺页率计算"},
    ),
    # ── 计算机网络：子网划分 ──
    StepQuestion(
        id="step_subnet_1", subject="computer_network", chapter="ip", difficulty="medium",
        question_text="将 192.168.1.0/24 划分为4个等长子网，写出每个子网的网络地址、广播地址和可用主机范围。",
        steps=[
            QuestionStep(step_name="确定子网掩码", description="将/24划分4个子网，需要借几位？新子网掩码是多少？",
                         check_type="choice", options=["借2位，/26即255.255.255.192", "借1位，/25", "借3位，/27", "借4位，/28"],
                         answer="借2位，/26即255.255.255.192",
                         hint_on_error="4=2^2，需要借2位。原/24借2位变成/26，即255.255.255.192。",
                         error_type_if_wrong="calculation_error"),
            QuestionStep(step_name="计算子网地址", description="第一个子网的网络地址是？",
                         check_type="choice", options=["192.168.1.0", "192.168.1.64", "192.168.1.128", "192.168.1.192"],
                         answer="192.168.1.0",
                         hint_on_error="/26的网络地址每64为一个子网：0, 64, 128, 192。第一个是192.168.1.0。",
                         error_type_if_wrong="calculation_error"),
            QuestionStep(step_name="计算广播地址", description="第一个子网的广播地址是？",
                         check_type="choice", options=["192.168.1.63", "192.168.1.255", "192.168.1.64", "192.168.1.127"],
                         answer="192.168.1.63",
                         hint_on_error="广播地址是该子网的下一个子网地址减1，即64-1=63。所以是192.168.1.63。",
                         error_type_if_wrong="calculation_error"),
            QuestionStep(step_name="可用主机数", description="每个子网可用的主机地址有多少个？",
                         check_type="choice", options=["62", "64", "126", "254"],
                         answer="62",
                         hint_on_error="2^(32-26)-2 = 2^6-2 = 64-2 = 62。减2是因为网络地址和广播地址不可用。",
                         error_type_if_wrong="calculation_error"),
        ],
        error_type_map={"concept_confusion": "子网划分概念", "calculation_error": "子网计算"},
    ),
    # ── 数据结构：哈希表 ──
    StepQuestion(
        id="step_hash_1", subject="data_structures", chapter="hash", difficulty="medium",
        question_text="关键字序列 {19,14,23,1,68,20,84,27,55,11,10,79}，散列函数H(key)=key%13，用拉链法处理冲突。",
        steps=[
            QuestionStep(step_name="计算散列值", description="关键字19的散列地址是？",
                         check_type="choice", options=["6", "5", "4", "7"],
                         answer="6", hint_on_error="19 % 13 = 6。",
                         error_type_if_wrong="calculation_error"),
            QuestionStep(step_name="同义词判断", description="哪些关键字与19同义词（散列地址都是6）？",
                         check_type="choice", options=["84, 6", "68, 84", "20, 84", "55, 20"],
                         answer="84, 6", hint_on_error="84%13=6, 6%13=6（实际上6不在序列中）。检查每个key mod 13=6的。20%13=7，68%13=3，84%13=6，55%13=3。",
                         error_type_if_wrong="calculation_error"),
            QuestionStep(step_name="ASL计算", description="假设12个关键字均匀分布，拉链法查找成功的平均查找长度ASL是？",
                         check_type="choice", options=["(1×6+2×4+3×2)/12≈1.5", "(1+2×3+3×2)/12", "12/13≈0.92", "6/12=0.5"],
                         answer="(1×6+2×4+3×2)/12≈1.5",
                         hint_on_error="ASL = 每个关键字的比较次数之和 / 关键字数。拉链法中，每个链中第一个元素比较1次，第二个2次...",
                         error_type_if_wrong="calculation_error"),
        ],
        error_type_map={"calculation_error": "哈希计算", "concept_confusion": "哈希表概念"},
    ),
    # ── 计算机组成原理：补码运算 ──
    StepQuestion(
        id="step_complement_1", subject="computer_organization", chapter="data", difficulty="easy",
        question_text="设 x=-69，用8位补码表示x，并计算 x+25 的补码结果。",
        steps=[
            QuestionStep(step_name="求原码", description="69的二进制是？",
                         check_type="choice", options=["01000101", "01010101", "01001011", "01000011"],
                         answer="01000101", hint_on_error="69=64+4+1=01000101B。",
                         error_type_if_wrong="calculation_error"),
            QuestionStep(step_name="求补码", description="-69的8位补码是？",
                         check_type="choice", options=["10111011", "11000101", "10111010", "11000100"],
                         answer="10111011",
                         hint_on_error="正数69的原码01000101，补码=符号位1，数值位取反+1：10111010+1=10111011。",
                         error_type_if_wrong="concept_confusion"),
            QuestionStep(step_name="补码加法", description="25的8位补码是？-69+25的补码运算结果是？",
                         check_type="choice", options=["25补码=00011001，结果=11010100=-44", "25补码=00011001，结果=10111011", "25补码=00011001，结果=11010100=44", "25补码=10011001，结果=01000100"],
                         answer="25补码=00011001，结果=11010100=-44",
                         hint_on_error="25=00011001B。10111011+00011001=11010100，最高位1表示负数，转换为原码：10101100=-44。",
                         error_type_if_wrong="calculation_error"),
        ],
        error_type_map={"calculation_error": "补码运算", "concept_confusion": "补码概念"},
    ),
    # ── 操作系统：进程调度 ──
    StepQuestion(
        id="step_sched_1", subject="operating_system", chapter="process", difficulty="medium",
        question_text="进程到达时间和服务时间：P1(0,5), P2(1,3), P3(2,2), P4(3,4)。计算RR(q=2)的平均等待时间。",
        steps=[
            QuestionStep(step_name="时间片轮转", description="RR调度中，时间片q=2的含义是什么？",
                         check_type="choice", options=["每个进程每次最多运行2个时间单位", "每2个时间单位调度一次", "进程最多运行2次", "每2秒创建一个进程"],
                         answer="每个进程每次最多运行2个时间单位",
                         hint_on_error="RR调度中，时间片q=2表示每个进程每次被调度时最多运行2个时间单位。",
                         error_type_if_wrong="concept_confusion"),
            QuestionStep(step_name="0-2时刻", description="0-2时刻，哪个进程在运行？",
                         check_type="choice", options=["P1", "P2", "P3", "P4"],
                         answer="P1", hint_on_error="0时刻只有P1到达，所以P1运行。",
                         error_type_if_wrong="missing_condition"),
            QuestionStep(step_name="2-4时刻", description="2时刻P1时间片到，P2已到达。此时就绪队列中有谁？谁运行？",
                         check_type="choice", options=["P2运行，就绪队列有P3", "P2运行，就绪队列为空", "P1继续运行，就绪队列有P2", "P3运行，就绪队列有P2"],
                         answer="P2运行，就绪队列有P3",
                         hint_on_error="2时刻P1时间片到，P2已在就绪队列，P3刚到达。调度P2运行，P3入就绪队列。",
                         error_type_if_wrong="missing_condition"),
            QuestionStep(step_name="计算平均等待时间", description="所有进程完成后，P1的等待时间是多少？",
                         check_type="choice", options=["P1等待时间=(5-2)+...=3", "P1等待时间=0", "P1等待时间=5", "P1等待时间=2"],
                         answer="P1等待时间=(5-2)+...=3",
                         hint_on_error="P1运行了0-2和4-5两次，总服务时间5，完成时间5，等待时间=完成时间-到达时间-服务时间=5-0-5=0。不对，让我重新算：P1:0-2,4-5完成，等待时间=(2-0)+(5-4)=3。",
                         error_type_if_wrong="calculation_error"),
        ],
        error_type_map={"concept_confusion": "RR调度概念", "missing_condition": "调度过程分析", "calculation_error": "等待时间计算"},
    ),
    # ── 数据结构：排序对比 ──
    StepQuestion(
        id="step_sort_1", subject="data_structures", chapter="sorting", difficulty="medium",
        question_text="对序列 {49,38,65,97,76,13,27,49} 进行快速排序（以第一个元素为基准），写出第一趟划分后的结果。",
        steps=[
            QuestionStep(step_name="选定基准", description="快速排序以第一个元素为基准，基准值是？",
                         check_type="choice", options=["49", "38", "13", "27"],
                         answer="49", hint_on_error="以第一个元素为基准，即49。",
                         error_type_if_wrong="concept_confusion"),
            QuestionStep(step_name="划分过程", description="从右向左找第一个小于49的元素，是哪个？",
                         check_type="choice", options=["27", "38", "13", "76"],
                         answer="27", hint_on_error="从右向左扫描，最后一个元素49不小于49，倒数第二个27小于49，所以找到27。",
                         error_type_if_wrong="missing_condition"),
            QuestionStep(step_name="第一趟结果", description="第一趟划分结束后的序列是？",
                         check_type="choice", options=["{27,38,13} 49 {76,97,65,49}", "{13,27,38} 49 {65,76,97,49}", "{49,38,13,27} 49 {76,97,65}", "{38,27,13} 49 {49,97,76,65}"],
                         answer="{27,38,13} 49 {76,97,65,49}",
                         hint_on_error="第一趟：从右找到27（交换），从左找到65（交换），再从右找到13（交换），从左找到97（交换），再从右找到49（与基准交换）。结果：{27,38,13} 49 {76,97,65,49}。",
                         error_type_if_wrong="calculation_error"),
        ],
        error_type_map={"concept_confusion": "快速排序概念", "missing_condition": "划分过程", "calculation_error": "排序结果"},
    ),
]


# ── 错因分析引擎 ──

class ErrorAnalyzer:
    """错因分析引擎：分类错误原因，给出针对性反馈"""

    ERROR_CATEGORIES = {
        "concept_confusion": {
            "label": "概念混淆",
            "suggestion": "建议复习相关概念对比，理解两者的区别和适用场景。",
            "drill_type": "概念辨析题",
        },
        "calculation_error": {
            "label": "计算错误",
            "suggestion": "建议重新计算，注意公式和单位换算，分步骤推导。",
            "drill_type": "计算练习题",
        },
        "missing_condition": {
            "label": "遗漏条件",
            "suggestion": "建议仔细审题，列出所有已知条件后再作答。",
            "drill_type": "条件分析题",
        },
        "careless_mistake": {
            "label": "粗心错误",
            "suggestion": "建议放慢速度，检查答案是否合理后再提交。",
            "drill_type": "复查练习",
        },
    }

    @staticmethod
    def analyze(step_results: list[StepResult]) -> dict:
        """分析多步答题结果，返回综合错因分析"""
        wrong_steps = [s for s in step_results if not s.correct]
        if not wrong_steps:
            return {"passed": True, "error_types": [], "primary_cause": "", "suggestion": "全部正确！"}

        # 统计错因类型
        from collections import Counter
        error_counter = Counter(s.error_type for s in wrong_steps if s.error_type)
        primary_error = error_counter.most_common(1)[0][0] if error_counter else "unknown"

        # 生成建议
        suggestions = []
        for s in wrong_steps:
            cat = ErrorAnalyzer.ERROR_CATEGORIES.get(s.error_type, {})
            label = cat.get("label", s.error_type)
            drill = cat.get("drill_type", "练习")
            suggestions.append(f"• 第{s.step_index+1}步「{s.step_name}」: {label} → {s.hint}")

        return {
            "passed": False,
            "error_types": list(error_counter.keys()),
            "primary_cause": ErrorAnalyzer.ERROR_CATEGORIES.get(primary_error, {}).get("label", primary_error),
            "step_suggestions": suggestions,
            "drill_recommendation": ErrorAnalyzer.ERROR_CATEGORIES.get(primary_error, {}).get("drill_type", "综合练习"),
        }


# ── 薄弱点追踪器 ──

class WeakPointTracker:
    """薄弱点追踪：记录错因 → 优先出同类题 → 闭环追踪"""

    def __init__(self):
        self._weak_points: dict[str, WeakPoint] = {}

    def record_error(self, question: StepQuestion, step_results: list[StepResult], user_id: str):
        """记录答题错误到薄弱点"""
        key_prefix = f"{user_id}:{question.subject}:{question.chapter}"

        for step in step_results:
            if not step.correct and step.error_type:
                concept = question.error_type_map.get(step.error_type, f"{question.chapter}_{step.step_name}")
                wp_key = f"{key_prefix}:{concept}"

                if wp_key in self._weak_points:
                    self._weak_points[wp_key].count += 1
                else:
                    self._weak_points[wp_key] = WeakPoint(
                        subject=question.subject,
                        chapter=question.chapter,
                        concept=concept,
                        error_type=step.error_type,
                        count=1,
                    )

    def get_weak_topics(self, user_id: str, subject: str = "", top_n: int = 5) -> list[WeakPoint]:
        """获取用户薄弱知识点排名"""
        results = []
        for key, wp in self._weak_points.items():
            if key.startswith(f"{user_id}:{subject}") if subject else key.startswith(user_id):
                if not wp.mastered:
                    results.append(wp)

        results.sort(key=lambda x: x.count, reverse=True)
        return results[:top_n]

    def mark_mastered(self, user_id: str, subject: str, chapter: str, concept: str):
        """标记知识点已掌握"""
        for key, wp in self._weak_points.items():
            if key.startswith(f"{user_id}:{subject}:{chapter}") and wp.concept == concept:
                wp.mastered = True
                break

    def get_recommended_questions(self, user_id: str, subject: str = "", top_n: int = 3) -> list[str]:
        """根据薄弱点推荐题目ID"""
        weak = self.get_weak_topics(user_id, subject, top_n)
        if not weak:
            return []

        # 根据薄弱点的error_type匹配题目
        recommended = []
        for q in STEP_QUESTIONS:
            if subject and q.subject != subject:
                continue
            for wp in weak:
                # 检查题目的错因映射是否包含薄弱点
                for error_type, concept in q.error_type_map.items():
                    if wp.error_type == error_type or wp.concept in concept:
                        if q.id not in recommended:
                            recommended.append(q.id)
                            break

        return recommended[:top_n]


# 全局实例
error_analyzer = ErrorAnalyzer()
weak_point_tracker = WeakPointTracker()