# ============================================================
# seed/ — 408 四科静态种子语料包（M-4 ③，自 seed_data.py 拆分）
#
# 为什么拆：原 seed_data.py 1,527 行把四科语料、知识图谱、学习路径 DAG 与派生
# 组装逻辑混装在一个文件里，改任何一科都要在巨型文件里翻找。
#
# 为什么是包而不是 scripts/：评审文档原建议「归入 scripts/（非运行时依赖）」经实测
# 不成立 —— api/{knowledge,learning_path,rag,subjects,teacher}、engines/frugal_rag_sft
# 与 app/lifespan 共 7 个**运行时**模块依赖它，且本文件尾部承载 408 四科 group 偏移
# 对齐的派生逻辑。塞进一次性脚本目录会迫使运行时依赖去 hack sys.path。
#
# ⚠️ 求值顺序敏感，勿重排：
#   1) net → ds → co → os 与拆分前逐字一致
#   2) 子模块内存在**同名重复定义**（CO_SEED_KNOWLEDGE_CHUNKS / OS_SEED_KNOWLEDGE_CHUNKS
#      各有两版、后者覆盖前者），顺序一变结果就变
#   3) 下方「── 合并 το 派生与组装 ──」段包含：
#      - 各科 EXTRA_SEED_QUESTIONS 的定义与 `.extend(...)` **执行语句**
#      - seed_data_expanded 的 import
#      - group 偏移对齐与自动 KG/chunk 生成（派生逻辑）
#      这三部分依赖前面的全部数据符号，**只能留在 __init__**（曾试图拆出 extras.py，
#      结果 NameError，被差分比对当场抓出）
#
# 对外兼容：seed_data.py 仍是入口，按 __all__ 重导出本包全部公共符号
# （20 处既有 `import seed_data` / `from seed_data import ...` 无需改动）。
# ============================================================

from seed.net import *
from seed.ds import *
from seed.co import *
from seed.os import *

# ── 合并 / 派生与组装（原 seed_data.py 1098-1527 行二进制原样搬运，勿改）──
# ============================================================
# 合并：将所有科目种子数据追加到主列表
# ============================================================
SEED_KNOWLEDGE_CHUNKS.extend(DS_SEED_KNOWLEDGE_CHUNKS)
SEED_KNOWLEDGE_CHUNKS.extend(CO_SEED_KNOWLEDGE_CHUNKS)
SEED_KNOWLEDGE_CHUNKS.extend(OS_SEED_KNOWLEDGE_CHUNKS)
SEED_QUESTIONS.extend(DS_SEED_QUESTIONS)
SEED_QUESTIONS.extend(CO_SEED_QUESTIONS)
SEED_QUESTIONS.extend(OS_SEED_QUESTIONS)

# ── 408 真题补充：均衡各科题量，覆盖高频考点 ──

CO_EXTRA_SEED_QUESTIONS = [
    # 计算机组成原理 - 补充
    {"id": "co_q21", "subject": "co_data", "chapter": "浮点数", "type": "choice", "difficulty": "medium",
     "text": "IEEE 754单精度浮点数格式中，阶码采用的编码方式是？",
     "options": ["原码", "反码", "移码", "补码"],
     "answer": 2, "source": "408统考 2019"},
    {"id": "co_q22", "subject": "co_data", "chapter": "校验码", "type": "choice", "difficulty": "easy",
     "text": "能检测出所有双比特错误并纠正单比特错误的编码是？",
     "options": ["奇偶校验", "海明码", "CRC循环冗余码", "曼彻斯特编码"],
     "answer": 1, "source": "408统考 2020"},
    {"id": "co_q23", "subject": "co_memory", "chapter": "Cache映射", "type": "compute", "difficulty": "hard",
     "text": "某计算机主存容量256MB，按字节编址，Cache容量32KB，块大小64B，采用直接映射方式，求主存地址中Tag字段占多少位？",
     "answer": "主存28位，块内6位，Cache行32KB/64B=512行→9位，Tag=28-6-9=13位",
     "source": "408统考 2021"},
    {"id": "co_q24", "subject": "co_memory", "chapter": "虚拟存储器", "type": "choice", "difficulty": "medium",
     "text": "下列关于虚拟存储器的叙述中，正确的是？",
     "options": ["虚拟存储只能基于连续分配技术", "虚拟存储只能基于非连续分配技术",
                "虚拟存储容量只受外存容量限制", "虚拟存储容量只受内存容量限制"],
     "answer": 1, "source": "408统考 2018"},
    {"id": "co_q25", "subject": "co_isa", "chapter": "指令格式", "type": "choice", "difficulty": "easy",
     "text": "RISC指令系统的特点不包括？",
     "options": ["指令长度固定", "寻址方式少", "通用寄存器数量多", "指令数量多、功能复杂"],
     "answer": 3, "source": "408统考 2017"},
    {"id": "co_q26", "subject": "co_isa", "chapter": "寻址方式", "type": "choice", "difficulty": "medium",
     "text": "相对寻址方式中，操作数的有效地址是？",
     "options": ["基址寄存器内容+形式地址", "程序计数器内容+形式地址",
                "变址寄存器内容+形式地址", "栈指针内容+形式地址"],
     "answer": 1, "source": "408统考 2019"},
    {"id": "co_q27", "subject": "co_cpu", "chapter": "控制器", "type": "fill", "difficulty": "medium",
     "text": "CPU中，用于存放下一条要执行指令地址的寄存器是______。",
     "answer": "程序计数器（PC）", "source": "408统考 2020"},
    {"id": "co_q28", "subject": "co_cpu", "chapter": "流水线冒险", "type": "choice", "difficulty": "hard",
     "text": "下列哪种流水线冒险不能通过数据转发（forwarding）解决？",
     "options": ["EX段后的RAW冒险", "MEM段后的RAW冒险",
                "load-use冒险", "WB段前的RAW冒险"],
     "answer": 2, "source": "408统考 2022"},
    {"id": "co_q29", "subject": "co_cpu", "chapter": "指令流水线", "type": "compute", "difficulty": "medium",
     "text": "五段流水线(IF,ID,EX,MEM,WB)执行10条指令，理想情况下（无冒险）需要多少个时钟周期？",
     "answer": "5+(10-1)=14个时钟周期",
     "source": "408统考 2016"},
    {"id": "co_q30", "subject": "co_bus", "chapter": "总线仲裁", "type": "choice", "difficulty": "easy",
     "text": "在计数器定时查询方式下，若每次计数从0开始，则设备的优先级？",
     "options": ["相等", "设备号小的优先级高", "设备号大的优先级高", "随机"],
     "answer": 1, "source": "408统考 2015"},
    {"id": "co_q31", "subject": "co_io", "chapter": "IO方式", "type": "choice", "difficulty": "medium",
     "text": "下列I/O方式中，完全由硬件实现、不需要CPU执行程序的是？",
     "options": ["程序查询方式", "中断方式", "DMA方式", "通道方式"],
     "answer": 2, "source": "408统考 2021"},
    {"id": "co_q32", "subject": "co_io", "chapter": "中断系统", "type": "fill", "difficulty": "hard",
     "text": "中断响应过程中，保护程序计数器(PC)的作用是______。",
     "answer": "使中断服务程序执行完后能正确返回断点继续执行原程序",
     "source": "408统考 2018"},
]

OS_EXTRA_SEED_QUESTIONS = [
    # 操作系统 - 补充
    {"id": "os_q22", "subject": "os_overview", "chapter": "系统调用", "type": "choice", "difficulty": "easy",
     "text": "用户程序发起系统调用时，CPU的状态转换是？",
     "options": ["从用户态到核心态", "从核心态到用户态", "保持用户态", "保持核心态"],
     "answer": 0, "source": "408统考 2020"},
    {"id": "os_q23", "subject": "os_process", "chapter": "进程调度", "type": "choice", "difficulty": "medium",
     "text": "下列调度算法中，可能导致饥饿现象的是？",
     "options": ["先来先服务(FCFS)", "时间片轮转(RR)", "短作业优先(SJF)", "高响应比优先"],
     "answer": 2, "source": "408统考 2019"},
    {"id": "os_q24", "subject": "os_process", "chapter": "进程同步", "type": "compute", "difficulty": "hard",
     "text": "设系统中有n个进程(n≥3)共享一个临界资源R，若使用信号量机制实现互斥访问，则信号量初值为多少？信号量的取值范围是多少？",
     "answer": "初值为1；取值范围是-(n-1)到1",
     "source": "408统考 2021"},
    {"id": "os_q25", "subject": "os_process", "chapter": "死锁", "type": "choice", "difficulty": "medium",
     "text": "某系统有3个并发进程，各需要同类资源4个，则系统不会发生死锁的最少资源数是？",
     "options": ["9", "10", "11", "12"],
     "answer": 1, "source": "408统考 2017"},
    {"id": "os_q26", "subject": "os_memory", "chapter": "页面置换", "type": "choice", "difficulty": "hard",
     "text": "在页面置换算法中，Belady异常（分配物理块数增多但缺页率反而升高）可能出现在？",
     "options": ["OPT最佳置换", "FIFO先进先出", "LRU最近最久未使用", "CLOCK时钟算法"],
     "answer": 1, "source": "408统考 2014"},
    {"id": "os_q27", "subject": "os_memory", "chapter": "虚拟内存", "type": "choice", "difficulty": "medium",
     "text": "请求分页系统中，页表项中的访问位用于？",
     "options": ["判断页面是否在内存", "判断页面是否被修改", "供页面置换算法参考", "实现页面保护"],
     "answer": 2, "source": "408统考 2018"},
    {"id": "os_q28", "subject": "os_memory", "chapter": "分页存储", "type": "compute", "difficulty": "medium",
     "text": "某分页系统页面大小4KB，页表项4B，采用一级页表，用户空间2GB，求页表所需最大空间。",
     "answer": "2GB/4KB=512K页，页表大小=512K×4B=2MB",
     "source": "408统考 2016"},
    {"id": "os_q29", "subject": "os_file", "chapter": "文件目录", "type": "choice", "difficulty": "easy",
     "text": "文件系统中，设立当前工作目录的主要目的是？",
     "options": ["节省外存空间", "节省内存空间", "加快文件检索速度", "便于文件共享"],
     "answer": 2, "source": "408统考 2015"},
    {"id": "os_q30", "subject": "os_file", "chapter": "磁盘调度", "type": "choice", "difficulty": "medium",
     "text": "磁盘调度算法SCAN（电梯算法）的特点是？",
     "options": ["按请求先后顺序访问", "优先访问距当前磁头最近的磁道",
                "沿一个方向移动直到无请求再反向", "先处理当前柱面所有请求再移动"],
     "answer": 2, "source": "408统考 2022"},
    {"id": "os_q31", "subject": "os_io", "chapter": "SPOOLing", "type": "choice", "difficulty": "medium",
     "text": "SPOOLing技术的主要作用是？",
     "options": ["提高CPU运算速度", "将独占设备改造为共享设备",
                "减轻内存负担", "实现设备与CPU并行"],
     "answer": 1, "source": "408统考 2019"},
]

# 数据结构补充
DS_EXTRA_SEED_QUESTIONS = [
    {"id": "ds_q31", "subject": "ds_graph", "chapter": "最小生成树", "type": "choice", "difficulty": "medium",
     "text": "下列算法中，用于求解最小生成树的是？",
     "options": ["Dijkstra算法", "Floyd算法", "Prim算法", "KMP算法"],
     "answer": 2, "source": "408统考 2020"},
    {"id": "ds_q32", "subject": "ds_graph", "chapter": "拓扑排序", "type": "choice", "difficulty": "easy",
     "text": "对有n个顶点e条边的有向图进行拓扑排序，时间复杂度为？",
     "options": ["O(n)", "O(e)", "O(n+e)", "O(n×e)"],
     "answer": 2, "source": "408统考 2019"},
    {"id": "ds_q33", "subject": "ds_search", "chapter": "BST", "type": "choice", "difficulty": "medium",
     "text": "在二叉排序树中，查找关键字等于给定值的结点的时间复杂度为？",
     "options": ["O(1)", "O(logn)", "O(n)", "平均O(logn)，最坏O(n)"],
     "answer": 3, "source": "408统考 2018"},
    {"id": "ds_q34", "subject": "ds_search", "chapter": "哈希表", "type": "compute", "difficulty": "medium",
     "text": "设哈希表长m=14，哈希函数H(key)=key mod 11，采用线性探测再散列处理冲突，关键字序列{19,14,23,1,68,20,84,27,55,11}，求查找成功的平均查找长度。",
     "answer": "散列地址:19→8,14→3,23→1,1→1冲突→2,68→2冲突→3冲突→4,20→9,84→7,27→5,55→0,11→0冲突→1→...→10; ASL=(1+1+1+2+3+1+1+1+1+6)/10=18/10=1.8",
     "source": "408统考 2010"},
    {"id": "ds_q35", "subject": "ds_sort", "chapter": "排序算法", "type": "choice", "difficulty": "easy",
     "text": "下列排序算法中，不稳定的是？",
     "options": ["冒泡排序", "插入排序", "快速排序", "归并排序"],
     "answer": 2, "source": "408统考 2021"},
    {"id": "ds_q36", "subject": "ds_sort", "chapter": "堆排序", "type": "choice", "difficulty": "medium",
     "text": "在含有n个关键字的大顶堆中，关键字最小的记录可能出现在？",
     "options": ["堆顶", "最后一个叶子结点", "某个叶子结点", "根的右孩子"],
     "answer": 2, "source": "408统考 2017"},
    {"id": "ds_q37", "subject": "ds_tree", "chapter": "平衡二叉树", "type": "choice", "difficulty": "hard",
     "text": "在平衡二叉树中插入一个结点后造成不平衡，设最低不平衡结点为A，A的左孩子的右子树比左子树高，则应选择哪种旋转调整？",
     "options": ["LL", "RR", "LR", "RL"],
     "answer": 2, "source": "408统考 2019"},
    {"id": "ds_q38", "subject": "ds_stack", "chapter": "栈的应用", "type": "fill", "difficulty": "medium",
     "text": "若进栈序列为1,2,3,4，则可能的出栈序列有______种。",
     "answer": "14（卡特兰数C(4)=14）", "source": "408统考 经典题"},
]

SEED_QUESTIONS.extend(CO_EXTRA_SEED_QUESTIONS)
SEED_QUESTIONS.extend(OS_EXTRA_SEED_QUESTIONS)
SEED_QUESTIONS.extend(DS_EXTRA_SEED_QUESTIONS)

# ── 扩展知识库数据（知识图谱扩容至500+节点，知识库扩容至500+ chunks）──
from seed_data_expanded import (
    NET_EXPANDED_CHUNKS, DS_EXPANDED_CHUNKS, CO_EXPANDED_CHUNKS, OS_EXPANDED_CHUNKS,
    NET_EXPANDED_KG_NODES, NET_EXPANDED_KG_EDGES,
    DS_EXPANDED_KG_NODES, DS_EXPANDED_KG_EDGES,
    CO_EXPANDED_KG_NODES, CO_EXPANDED_KG_EDGES,
    OS_EXPANDED_KG_NODES, OS_EXPANDED_KG_EDGES,
)

SEED_KNOWLEDGE_CHUNKS.extend(NET_EXPANDED_CHUNKS)
SEED_KNOWLEDGE_CHUNKS.extend(DS_EXPANDED_CHUNKS)
SEED_KNOWLEDGE_CHUNKS.extend(CO_EXPANDED_CHUNKS)
SEED_KNOWLEDGE_CHUNKS.extend(OS_EXPANDED_CHUNKS)

# ============================================================
# 合并科目定义、知识图谱、学习路径（408四科）
# ============================================================

# 合并 subject 定义
_ALL_SUBJECTS = {}
_ALL_SUBJECTS.update(SEED_SUBJECTS)           # 计网
_ALL_SUBJECTS.update(DS_SEED_SUBJECTS)         # 数据结构
_ALL_SUBJECTS.update(CO_SEED_SUBJECTS)         # 计组
_ALL_SUBJECTS.update(OS_SEED_SUBJECTS)         # 操作系统
SEED_SUBJECTS = _ALL_SUBJECTS

# 合并知识图谱（需要调整 DS/CO/OS 的 group 编号，避免与计网 groups 13-19 冲突）
def _adjust_groups(nodes, offset):
    """对知识图谱节点列表的 group 值加偏移量"""
    return [{**n, "group": n["group"] + offset} for n in nodes]

_NET_NODES = list(KNOWLEDGE_GRAPH["nodes"])                          # 计网: groups 13-19（基础 KNOWLEDGE_GRAPH 原样拷贝，未偏移）
_DS_NODES  = _adjust_groups(DS_KNOWLEDGE_GRAPH["nodes"], 7)         # DS:   groups 1-7 → 8-14
_CO_NODES  = _adjust_groups(CO_KNOWLEDGE_GRAPH["nodes"], 14)        # CO:   groups 1-7 → 15-21
_OS_NODES  = _adjust_groups(OS_KNOWLEDGE_GRAPH["nodes"], 21)        # OS:   groups 1-5 → 22-26

_ALL_GRAPH_NODES = _NET_NODES + _DS_NODES + _CO_NODES + _OS_NODES
_ALL_GRAPH_EDGES = list(KNOWLEDGE_GRAPH["edges"]) + list(DS_KNOWLEDGE_GRAPH["edges"]) + list(CO_KNOWLEDGE_GRAPH["edges"]) + list(OS_KNOWLEDGE_GRAPH["edges"])

# 添加扩展知识图谱节点和边
_ALL_GRAPH_NODES.extend(NET_EXPANDED_KG_NODES)
_ALL_GRAPH_NODES.extend(DS_EXPANDED_KG_NODES)
_ALL_GRAPH_NODES.extend(CO_EXPANDED_KG_NODES)
_ALL_GRAPH_NODES.extend(OS_EXPANDED_KG_NODES)
_ALL_GRAPH_EDGES.extend(NET_EXPANDED_KG_EDGES)
_ALL_GRAPH_EDGES.extend(DS_EXPANDED_KG_EDGES)
_ALL_GRAPH_EDGES.extend(CO_EXPANDED_KG_EDGES)
_ALL_GRAPH_EDGES.extend(OS_EXPANDED_KG_EDGES)

# 添加科目间跨学科连接
_ALL_GRAPH_EDGES.append({"source": "overview", "target": "ds_linear"})
_ALL_GRAPH_EDGES.append({"source": "co_overview", "target": "os_overview"})
_ALL_GRAPH_EDGES.append({"source": "os_memory", "target": "co_memory"})
_ALL_GRAPH_EDGES.append({"source": "os_io", "target": "co_io"})
KNOWLEDGE_GRAPH = {"nodes": _ALL_GRAPH_NODES, "edges": _ALL_GRAPH_EDGES}

# ── 程序化生成额外知识图谱节点（从学习路径DAG的topics展开）──
_AUTO_KG_NODES = []
_AUTO_KG_EDGES = []
_seen_node_ids = {n["id"] for n in KNOWLEDGE_GRAPH["nodes"]}

for _chapter_name, _chapter_info in LEARNING_PATH_DAG.items():
    _parent_id = _chapter_info["id"]
    _group = _chapter_info["chapter"]  # 用chapter编号作为group
    # 为每个chapter的topics创建节点
    for _topic_idx, _topic in enumerate(_chapter_info.get("topics", [])):
        _node_id = f"{_parent_id}_t{_topic_idx}"
        if _node_id not in _seen_node_ids:
            _AUTO_KG_NODES.append({"id": _node_id, "label": _topic[:12], "group": _group})
            _AUTO_KG_EDGES.append({"source": _parent_id, "target": _node_id})
            _seen_node_ids.add(_node_id)

# 合并自动生成的节点
KNOWLEDGE_GRAPH["nodes"].extend(_AUTO_KG_NODES)
KNOWLEDGE_GRAPH["edges"].extend(_AUTO_KG_EDGES)

# ── 程序化生成额外知识库chunks（从学习路径topics展开，每个topic生成3个维度）──
_AUTO_CHUNKS = []
_CHUNK_TEMPLATES = [
    ("概念定义", "本知识点属于{chapter}章节，{topic}的定义、基本概念和核心要素。需要理解其内涵和外延，区分易混淆概念。"),
    ("原理方法", "{chapter}中{topic}的工作原理和实现方法。掌握核心算法/机制，能进行定量分析和计算。考研常考计算题和原理分析题。"),
    ("应用实例", "{topic}的实际应用场景和典型例题。在408考研中，本知识点常以选择题和综合题形式出现，需要结合具体案例理解。"),
]
for _chapter_name, _chapter_info in LEARNING_PATH_DAG.items():
    _parent_id = _chapter_info["id"]
    _subj = _parent_id
    for _topic in _chapter_info.get("topics", []):
        for _tmpl_name, _tmpl_content in _CHUNK_TEMPLATES:
            _AUTO_CHUNKS.append({
                "content": f"{_chapter_name} - {_topic}（{_tmpl_name}）：" + _tmpl_content.format(chapter=_chapter_name, topic=_topic),
                "metadata": {
                    "subject": _subj,
                    "chapter": _chapter_name,
                    "type": "knowledge_point",
                    "sub_topic": _topic,
                    "dimension": _tmpl_name,
                    "auto_generated": True,
                }
            })

SEED_KNOWLEDGE_CHUNKS.extend(_AUTO_CHUNKS)

# ── 程序化生成额外知识图谱节点（从扩展chunks的sub_topic展开）──
_AUTO_KG_NODES2 = []
_AUTO_KG_EDGES2 = []
_seen_node_ids2 = {n["id"] for n in KNOWLEDGE_GRAPH["nodes"]}

_subj_group_map = {}
for _ch_name, _ch_info in LEARNING_PATH_DAG.items():
    _subj_group_map[_ch_info["id"]] = _ch_info["chapter"]

for _chunk in SEED_KNOWLEDGE_CHUNKS:
    _meta = _chunk.get("metadata", {})
    _sub_topic = _meta.get("sub_topic", "")
    _subj = _meta.get("subject", "")
    if _sub_topic and _subj:
        _node_id = f"{_subj}_{_sub_topic[:20]}".replace(" ", "_").replace("/", "_")
        if _node_id not in _seen_node_ids2 and _subj in _subj_group_map:
            _AUTO_KG_NODES2.append({"id": _node_id, "label": _sub_topic[:12], "group": _subj_group_map[_subj]})
            _AUTO_KG_EDGES2.append({"source": _subj, "target": _node_id})
            _seen_node_ids2.add(_node_id)

KNOWLEDGE_GRAPH["nodes"].extend(_AUTO_KG_NODES2)
KNOWLEDGE_GRAPH["edges"].extend(_AUTO_KG_EDGES2)

# ── 从知识图谱节点自动生成知识库chunks（确保每个KG节点都有对应知识内容）──
_KG_AUTO_CHUNKS = []
_existing_contents = {c["content"][:50] for c in SEED_KNOWLEDGE_CHUNKS}
_kg_subject_map = {}
for _ch_name, _ch_info in LEARNING_PATH_DAG.items():
    _kg_subject_map[_ch_info["id"]] = _ch_name

for _node in KNOWLEDGE_GRAPH["nodes"]:
    _node_id = _node["id"]
    _label = _node["label"]
    # 找到该节点属于哪个科目
    _subj = ""
    _chapter = ""
    for _pid, _pname in _kg_subject_map.items():
        if _node_id.startswith(_pid):
            _subj = _pid
            _chapter = _pname
            break
    if not _subj:
        # 通过group查找
        _subj = "overview"
        _chapter = _label

    _content = f"{_label}：本知识点涉及{_chapter}中的{_label}相关内容，包括基本概念、核心原理、计算方法和典型应用。在408考研中需要重点理解并能灵活运用。"
    if _content[:50] not in _existing_contents:
        _KG_AUTO_CHUNKS.append({
            "content": _content,
            "metadata": {
                "subject": _subj,
                "chapter": _chapter,
                "type": "knowledge_point",
                "sub_topic": _label,
                "auto_generated": True,
            }
        })
        _existing_contents.add(_content[:50])

SEED_KNOWLEDGE_CHUNKS.extend(_KG_AUTO_CHUNKS)

# ── 从题库生成额外KG节点（每道题对应一个知识点节点）──
_Q_KG_NODES = []
_Q_KG_EDGES = []
_seen_q_nodes = {n["id"] for n in KNOWLEDGE_GRAPH["nodes"]}

for _q in SEED_QUESTIONS:
    _subj = _q.get("subject", "overview")
    _chapter = _q.get("chapter", "")
    _q_id = _q.get("id", "")
    if _q_id:
        _node_id = f"q_{_q_id}"
        if _node_id not in _seen_q_nodes:
            _Q_KG_NODES.append({"id": _node_id, "label": _chapter[:10], "group": 1})
            # 连接到对应科目节点
            _Q_KG_EDGES.append({"source": _subj, "target": _node_id})
            _seen_q_nodes.add(_node_id)

KNOWLEDGE_GRAPH["nodes"].extend(_Q_KG_NODES)
KNOWLEDGE_GRAPH["edges"].extend(_Q_KG_EDGES)

# ── 从chunks的sub_topic生成更细粒度的KG节点 ──
_FINE_KG_NODES = []
_FINE_KG_EDGES = []
_seen_fine = {n["id"] for n in KNOWLEDGE_GRAPH["nodes"]}
_subj_chapter_group = {}
for _ch_name, _ch_info in LEARNING_PATH_DAG.items():
    _subj_chapter_group[_ch_info["id"]] = _ch_info["chapter"]

for _chunk in SEED_KNOWLEDGE_CHUNKS:
    _meta = _chunk.get("metadata", {})
    _sub = _meta.get("sub_topic", "")
    _subj = _meta.get("subject", "")
    _dim = _meta.get("dimension", "")
    if _sub and _subj and _dim:
        _fine_id = f"{_subj}_{_sub[:15]}_{_dim[:5]}".replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
        if _fine_id not in _seen_fine and _subj in _subj_chapter_group:
            _FINE_KG_NODES.append({"id": _fine_id, "label": _sub[:8], "group": _subj_chapter_group[_subj]})
            _FINE_KG_EDGES.append({"source": _subj, "target": _fine_id})
            _seen_fine.add(_fine_id)

KNOWLEDGE_GRAPH["nodes"].extend(_FINE_KG_NODES)
KNOWLEDGE_GRAPH["edges"].extend(_FINE_KG_EDGES)

# ── 跨学科概念节点（408四科交叉知识点）──
_CROSS_NODES = [
    {"id": "cross_storage", "label": "存储层次", "group": 1},
    {"id": "cross_interrupt", "label": "中断机制", "group": 1},
    {"id": "cross_io", "label": "IO控制", "group": 1},
    {"id": "cross_addr", "label": "地址映射", "group": 1},
    {"id": "cross_pipeline", "label": "流水线", "group": 1},
    {"id": "cross_cache", "label": "缓存思想", "group": 1},
    {"id": "cross_queue", "label": "队列应用", "group": 1},
    {"id": "cross_tree", "label": "树结构应用", "group": 1},
    {"id": "cross_graph", "label": "图算法应用", "group": 1},
    {"id": "cross_sort", "label": "排序应用", "group": 1},
    {"id": "cross_hash", "label": "哈希应用", "group": 1},
    {"id": "cross_bit", "label": "位运算", "group": 1},
    {"id": "cross_protocol", "label": "协议设计", "group": 1},
    {"id": "cross_security", "label": "安全机制", "group": 1},
    {"id": "cross_perf", "label": "性能分析", "group": 1},
    {"id": "cross_concurrency", "label": "并发控制", "group": 1},
    {"id": "cross_deadlock", "label": "死锁分析", "group": 1},
    {"id": "cross_encoding", "label": "编码方式", "group": 1},
    {"id": "cross_virtual", "label": "虚拟化", "group": 1},
    {"id": "cross_sync", "label": "同步机制", "group": 1},
]
KNOWLEDGE_GRAPH["nodes"].extend(_CROSS_NODES)
# 跨学科连接
for _cn in _CROSS_NODES:
    _cn_id = _cn["id"]
    if _cn_id == "cross_storage":
        KNOWLEDGE_GRAPH["edges"].append({"source": "co_memory", "target": _cn_id})
        KNOWLEDGE_GRAPH["edges"].append({"source": "os_memory", "target": _cn_id})
    elif _cn_id == "cross_interrupt":
        KNOWLEDGE_GRAPH["edges"].append({"source": "co_io", "target": _cn_id})
        KNOWLEDGE_GRAPH["edges"].append({"source": "os_process", "target": _cn_id})
    elif _cn_id == "cross_io":
        KNOWLEDGE_GRAPH["edges"].append({"source": "co_io", "target": _cn_id})
        KNOWLEDGE_GRAPH["edges"].append({"source": "os_io", "target": _cn_id})
    elif _cn_id == "cross_cache":
        KNOWLEDGE_GRAPH["edges"].append({"source": "co_cache", "target": _cn_id})
        KNOWLEDGE_GRAPH["edges"].append({"source": "os_virtual", "target": _cn_id})

# 合并学习路径DAG（含四科推荐学习顺序）
LEARNING_PATH_DAG = {
    "计算机网络概述": {"id": "overview", "chapter": 1, "prerequisites": [], "topics": ["计算机网络定义", "分组交换", "OSI和TCP/IP体系结构", "性能指标"]},
    "物理层": {"id": "physical", "chapter": 2, "prerequisites": ["计算机网络概述"], "topics": ["传输媒体", "信道复用技术", "数字传输系统"]},
    "数据链路层": {"id": "datalink", "chapter": 3, "prerequisites": ["物理层"], "topics": ["差错检测CRC", "CSMA/CD", "以太网", "VLAN"]},
    "网络层": {"id": "network", "chapter": 4, "prerequisites": ["数据链路层"], "topics": ["IP地址与子网划分", "ARP协议", "路由选择(RIP/OSPF/BGP)", "NAT", "IPv6"]},
    "运输层": {"id": "transport", "chapter": 5, "prerequisites": ["网络层"], "topics": ["UDP协议", "TCP报文段格式", "TCP可靠传输", "TCP拥塞控制", "TCP连接管理"]},
    "应用层": {"id": "application", "chapter": 6, "prerequisites": ["运输层"], "topics": ["DNS域名解析", "HTTP/HTTPS", "FTP", "电子邮件"]},
    "网络安全": {"id": "security", "chapter": 7, "prerequisites": ["运输层", "应用层"], "topics": ["SSL/TLS", "防火墙", "网络攻击防范", "数字签名"]},
    # 数据结构（并行学习路径）
    "线性表": {"id": "ds_linear", "chapter": 1, "prerequisites": [], "topics": ["顺序存储", "链式存储(单链表/双向/循环)", "线性表应用"]},
    "栈和队列": {"id": "ds_stack", "chapter": 2, "prerequisites": ["线性表"], "topics": ["栈(LIFO)", "队列(FIFO)", "循环队列", "栈和队列的应用"]},
    "串": {"id": "ds_string", "chapter": 3, "prerequisites": ["线性表"], "topics": ["串的基本概念", "朴素匹配", "KMP算法", "next数组"]},
    "树与二叉树": {"id": "ds_tree", "chapter": 4, "prerequisites": ["线性表"], "topics": ["树的概念", "二叉树性质", "遍历(先/中/后/层)", "BST", "AVL", "哈夫曼树"]},
    "图": {"id": "ds_graph", "chapter": 5, "prerequisites": ["树与二叉树"], "topics": ["图的定义与存储", "DFS/BFS", "最小生成树(Prim/Kruskal)", "最短路径(Dijkstra/Floyd)", "拓扑排序与关键路径"]},
    "查找": {"id": "ds_search", "chapter": 6, "prerequisites": ["树与二叉树"], "topics": ["顺序/折半查找", "BST与AVL", "B树/B+树", "哈希表"]},
    "排序": {"id": "ds_sort", "chapter": 7, "prerequisites": ["线性表"], "topics": ["插入排序(直接/折半/希尔)", "交换排序(冒泡/快排)", "选择排序(简单选择/堆)", "归并排序", "基数排序", "排序算法比较"]},
    # 计算机组成原理
    "计算机概述": {"id": "co_overview", "chapter": 1, "prerequisites": [], "topics": ["冯诺依曼结构", "性能指标", "计算机发展"]},
    "数据表示与运算": {"id": "co_data", "chapter": 2, "prerequisites": ["计算机概述"], "topics": ["定点数与浮点数", "IEEE 754", "ALU运算器", "补码加减与溢出"]},
    "存储系统": {"id": "co_memory", "chapter": 3, "prerequisites": ["数据表示与运算"], "topics": ["层次结构", "Cache映射与替换", "Cache写策略", "主存连接与扩展"]},
    "指令系统": {"id": "co_isa", "chapter": 4, "prerequisites": ["数据表示与运算"], "topics": ["指令格式", "寻址方式", "CISC vs RISC"]},
    "中央处理器": {"id": "co_cpu", "chapter": 5, "prerequisites": ["指令系统", "存储系统"], "topics": ["数据通路", "指令流水线(IF/ID/EX/MEM/WB)", "流水线冲突与解决", "控制器实现"]},
    "总线": {"id": "co_bus", "chapter": 6, "prerequisites": ["存储系统"], "topics": ["总线分类与标准", "总线仲裁", "总线定时"]},
    "IO系统": {"id": "co_io", "chapter": 7, "prerequisites": ["总线"], "topics": ["IO接口", "程序查询/中断/DMA", "中断系统"]},
    # 操作系统
    "操作系统概述": {"id": "os_overview", "chapter": 1, "prerequisites": [], "topics": ["OS定义与功能", "OS发展历程", "内核态与用户态"]},
    "进程管理": {"id": "os_process", "chapter": 2, "prerequisites": ["操作系统概述"], "topics": ["进程与线程", "信号量与PV操作", "死锁与银行家算法", "调度算法(FCFS/SJF/RR)"]},
    "内存管理": {"id": "os_memory", "chapter": 3, "prerequisites": ["进程管理"], "topics": ["连续/分页/分段分配", "虚拟内存与页面置换", "TLB与多级页表"]},
    "文件系统": {"id": "os_file", "chapter": 4, "prerequisites": ["内存管理"], "topics": ["文件结构与目录", "空闲空间管理", "磁盘调度算法(FCFS/SSTF/SCAN)"]},
    "IO管理": {"id": "os_io", "chapter": 5, "prerequisites": ["文件系统"], "topics": ["IO层次与SPOOLing", "缓冲区技术", "磁盘高速缓存"]},
}

# ── 对外表面 ──
# 显式列出（而非运行时推导）：让 `from seed import *` 精确导出 **33 个**公共符号，
# 与拆分前 seed_data 完全一致（由 scripts/verify_seed_data_split.py 差分校验）。
__all__ = [
    "CO_EXPANDED_CHUNKS",
    "CO_EXPANDED_KG_EDGES",
    "CO_EXPANDED_KG_NODES",
    "CO_EXTRA_SEED_QUESTIONS",
    "CO_KNOWLEDGE_GRAPH",
    "CO_SEED_KNOWLEDGE_CHUNKS",
    "CO_SEED_QUESTIONS",
    "CO_SEED_SUBJECTS",
    "DS_EXPANDED_CHUNKS",
    "DS_EXPANDED_KG_EDGES",
    "DS_EXPANDED_KG_NODES",
    "DS_EXTRA_SEED_QUESTIONS",
    "DS_KNOWLEDGE_GRAPH",
    "DS_LEARNING_PATH_DAG",
    "DS_SEED_KNOWLEDGE_CHUNKS",
    "DS_SEED_QUESTIONS",
    "DS_SEED_SUBJECTS",
    "KNOWLEDGE_GRAPH",
    "LEARNING_PATH_DAG",
    "NET_EXPANDED_CHUNKS",
    "NET_EXPANDED_KG_EDGES",
    "NET_EXPANDED_KG_NODES",
    "OS_EXPANDED_CHUNKS",
    "OS_EXPANDED_KG_EDGES",
    "OS_EXPANDED_KG_NODES",
    "OS_EXTRA_SEED_QUESTIONS",
    "OS_KNOWLEDGE_GRAPH",
    "OS_SEED_KNOWLEDGE_CHUNKS",
    "OS_SEED_QUESTIONS",
    "OS_SEED_SUBJECTS",
    "SEED_KNOWLEDGE_CHUNKS",
    "SEED_QUESTIONS",
    "SEED_SUBJECTS",
]
