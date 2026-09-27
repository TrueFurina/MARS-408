# coding: utf-8
# 操作系统（OS）段 —— 自 seed_data.py 第 959-1097 行二进制原样搬运（M-4 ③）。
# 含 OS_SEED_KNOWLEDGE_CHUNKS 的**最终版**（覆盖 seed/net.py 中的 v1）。
# 注：这是包内子模块 seed.os，与标准库 os 无冲突（Python 3 绝对导入语义）。
# ============================================================
# 操作系统种子数据
# 5章：概述/进程管理/内存管理/文件系统/IO管理
# ============================================================

OS_SEED_KNOWLEDGE_CHUNKS = [
    # ---- 第1章 操作系统概述 ----
    {"content": "操作系统定义：管理计算机硬件与软件资源的系统软件。功能：处理机管理、存储器管理、设备管理、文件管理、用户接口。特征：并发、共享、虚拟、异步。", "metadata": {"subject": "os_overview", "chapter": "操作系统概述", "type": "knowledge_point"}},
    {"content": "操作系统发展：手工→单道批处理→多道批处理→分时系统→实时系统→网络OS→分布式OS。多道批处理提高CPU和IO并行度。分时系统的关键：时间片轮转，交互性强。", "metadata": {"subject": "os_overview", "chapter": "OS发展", "type": "knowledge_point"}},
    {"content": "内核态vs用户态：内核态（管态/系统态）可执行特权指令（如IO指令、中断开关、修改PSW），用户态只能执行非特权指令。系统调用是用户程序进入内核态的唯一入口。", "metadata": {"subject": "os_overview", "chapter": "内核态与用户态", "type": "knowledge_point"}},
    # ---- 第2章 进程管理 ----
    {"content": "进程是程序的一次执行实例，是资源分配的基本单位。进程控制块PCB（Process Control Block）：进程标识、CPU现场、调度信息、资源信息。进程状态：创建/就绪/运行/阻塞/终止。", "metadata": {"subject": "os_process", "chapter": "进程概念", "type": "knowledge_point"}},
    {"content": "线程是CPU调度的基本单位。同一进程的线程共享：地址空间、打开文件、信号处理等；独有：线程ID、PC寄存器、栈。用户级线程（ULT）：OS不可见,调度在用户空间；内核级线程（KLT）：OS调度和支持。", "metadata": {"subject": "os_process", "chapter": "线程", "type": "knowledge_point"}},
    {"content": "进程同步：临界区是访问共享资源的代码段。互斥四个条件——空闲让进、忙则等待、有限等待、让权等待。Peterson算法（2进程软件互斥）、硬件方法（关中断/TestAndSet/Swap指令）。", "metadata": {"subject": "os_process", "chapter": "进程同步", "type": "knowledge_point"}},
    {"content": "信号量机制：P操作（wait：s--; 若s<0进程阻塞入等待队列）、V操作（signal：s++; 若s<=0从队列唤醒一个进程）。应用：生产者-消费者（empty/full/mutex三个信号量）、读者-写者（读互斥、写独占）。", "metadata": {"subject": "os_process", "chapter": "信号量", "type": "knowledge_point"}},
    {"content": "死锁：两个以上进程因竞争资源而无限等待。必要条件（4个必须同时满足）：互斥、请求和保持（占有并等待）、不可剥夺、循环等待。预防：破坏四个条件之一；避免：银行家算法(安全状态判断)；检测：资源分配图化简。", "metadata": {"subject": "os_process", "chapter": "死锁", "type": "knowledge_point"}},
    # ---- 第3章 内存管理 ----
    {"content": "连续分配：单一连续（仅单道）、固定分区（分区大小固定,内部碎片）、动态分区（按需分割,外部碎片）。动态分区分配算法：首次适应FF、最佳适应BF(碎片最多)、最差适应WF、邻近适应NF。", "metadata": {"subject": "os_memory", "chapter": "连续分配", "type": "knowledge_point"}},
    {"content": "分页存储：逻辑地址分为页号+页内偏移。页表存页号→物理块号映射。快表TLB：高速缓冲最近使用的页表项,命中则无需访存查页表。缺页中断：访问的页不在内存→调入→更新页表。", "metadata": {"subject": "os_memory", "chapter": "分页", "type": "knowledge_point"}},
    {"content": "多级页表：页目录+页表。32位地址：10位页目录(1024项)+10位页表(1024项)+12位页内偏移(4KB页)。分段存储：逻辑地址=段号+段内偏移,段表存段号→基址+限长。段页式：先分段再分页。", "metadata": {"subject": "os_memory", "chapter": "多级页表与分段", "type": "knowledge_point"}},
    {"content": "虚拟内存：程序部分装入即可运行,大于物理内存的程序也可运行。实现：请求分页或请求分段。页面置换算法：OPT（最佳,无法实现）、FIFO（Belady异常：帧多缺页也多）、LRU（最近最久未使用）、Clock（NRU,访问位+修改位）。", "metadata": {"subject": "os_memory", "chapter": "虚拟内存", "type": "knowledge_point"}},
    {"content": "页面置换算法比较：FIFO实现简单但有Belady异常；LRU效果接近OPT但需硬件支持（栈）；Clock（NRU）是LRU近似,用访问位A和修改位M,选择(A=0,M=0)优先→(0,1)→(1,0)→(1,1)。缺页率取决于工作集。", "metadata": {"subject": "os_memory", "chapter": "页面置换", "type": "knowledge_point"}},
    {"content": "页面置换算法主要有：OPT（最佳置换，选最远将来使用的页，理论最优但无法实现）、FIFO（先进先出，按调入顺序淘汰，可能出现Belady异常）、LRU（最近最久未使用，命中率接近OPT但需硬件栈支持）、CLOCK（时钟/最近未用NRU算法，用访问位A与修改位M近似LRU，是LRU的低成本实现，扫描找(A=0,M=0)的页淘汰）。", "metadata": {"subject": "os_memory", "chapter": "页面置换", "type": "knowledge_point"}},
    {"content": "请求调页（请求分页）是虚拟内存的核心机制：进程运行时只把部分页面装入内存，当访问的页不在内存时触发缺页中断，操作系统将所需页从外存调入内存、修改页表后重新执行指令。请求调页使程序能使用比物理内存更大的逻辑地址空间。", "metadata": {"subject": "os_memory", "chapter": "虚拟内存", "type": "knowledge_point"}},
    {"content": "虚拟内存的作用：①扩充内存容量——以磁盘（外存）作为内存扩充，使程序可用比物理内存更大的逻辑地址空间；②支持请求调页——按需把页面调入内存；③地址变换——逻辑地址经页表/段表由MMU转换为物理地址（地址变换），并用TLB快表加速。虚拟内存建立在离散分配和局部性原理之上。", "metadata": {"subject": "os_memory", "chapter": "虚拟内存", "type": "knowledge_point"}},
    {"content": "缓冲技术的作用：①缓和CPU与I/O设备之间的速度不匹配（速度不匹配）；②减少对CPU的中断频率（中断），放宽CPU对中断的响应时间要求；③提高CPU与I/O设备的并行工作能力。常见：单缓冲、双缓冲、循环缓冲、缓冲池。", "metadata": {"subject": "os_io", "chapter": "缓冲", "type": "knowledge_point"}},
    # ---- 第4章 文件系统 ----
    {"content": "文件逻辑结构：无结构（流式文件/字节序列）和有结构（记录式文件）。文件物理结构：连续分配（顺序快,外碎片）、链接分配（无外碎片,随机访问慢,隐式链接）、索引分配（每个文件一个索引块,FAT是变种）。", "metadata": {"subject": "os_file", "chapter": "文件结构", "type": "knowledge_point"}},
    {"content": "文件目录结构：单级目录（全系统唯一）、两级目录（主目录MFD+用户目录UFD）、树形目录（多级,路径名:绝对路径/相对路径）。FCB（文件控制块）：文件名、物理位置、大小、权限、时间戳。", "metadata": {"subject": "os_file", "chapter": "目录结构", "type": "knowledge_point"}},
    {"content": "文件存储空间管理：空闲表法（连续空闲区链表）、空闲链表法（空闲盘块链）、位示图（每位对应一块：1已分配/0空闲）、成组链接法（UNIX,结合空闲表和链表）。", "metadata": {"subject": "os_file", "chapter": "空间管理", "type": "knowledge_point"}},
    {"content": "磁盘调度算法：FCFS（先来先服务）、SSTF（最短寻道优先,可能饥饿）、SCAN（电梯算法,来回扫描）、C-SCAN（单向扫描,回程不服务）、LOOK/C-LOOK（到达最远请求即折返）。磁盘访问时间 = 寻道时间 + 旋转延迟 + 传输时间。", "metadata": {"subject": "os_file", "chapter": "磁盘调度", "type": "knowledge_point"}},
    # ---- 第5章 IO管理 ----
    {"content": "IO软件层次：用户层IO→设备无关软件层（提供统一接口,缓冲区管理,差错处理）→设备驱动程序（与具体设备交互）→中断处理程序→硬件。SPOOLing：虚拟设备技术,输入井/输出井。", "metadata": {"subject": "os_io", "chapter": "IO层次", "type": "knowledge_point"}},
    {"content": "缓冲区技术：单缓冲（处理时间=max(C,T)+M）、双缓冲（流水线,max(C,T)）、循环缓冲、缓冲池。目的：缓和CPU与IO设备速度不匹配。磁盘高速缓存：内存中缓存磁盘块,减少磁盘IO。", "metadata": {"subject": "os_io", "chapter": "缓冲区", "type": "knowledge_point"}},
    {"content": "进程调度算法：FCFS先来先服务（非抢占,长作业有利）、SJF短作业优先（最优平均等待时间,需预知运行时间,长作业饥饿）、RR时间片轮转（分时系统,响应快）、优先级调度（静态/动态）、多级反馈队列（多队列+时间片递增+抢占）。", "metadata": {"subject": "os_process", "chapter": "调度算法", "type": "knowledge_point"}},
    {"content": "进程同步经典问题：哲学家进餐（5位5筷,死锁解决：最多4位同时进餐/奇数先左筷偶数先右筷）、吸烟者问题（3进程需不同材料,供应者随机放2种材料）、理发师问题（n个座椅,无顾客理发师睡觉）。", "metadata": {"subject": "os_process", "chapter": "经典同步问题", "type": "knowledge_point"}},
]

OS_SEED_QUESTIONS = [
    # 概述
    {"id": "os_q1", "subject": "os_overview", "chapter": "内核态与用户态", "type": "choice", "difficulty": "medium",
     "text": "用户程序进入内核态的唯一入口是？",
     "options": ["函数调用", "系统调用", "中断", "异常"], "answer": 1, "source": "操作系统 第1章"},
    # 进程管理
    {"id": "os_q2", "subject": "os_process", "chapter": "线程", "type": "choice", "difficulty": "medium",
     "text": "下列哪项是线程独有的（不与其他线程共享）？",
     "options": ["地址空间", "打开文件", "栈和寄存器", "信号处理函数"], "answer": 2, "source": "操作系统 第2章"},
    {"id": "os_q3", "subject": "os_process", "chapter": "死锁", "type": "choice", "difficulty": "medium",
     "text": "死锁的四个必要条件不包括？",
     "options": ["互斥条件", "请求保持条件", "不可抢占条件", "饥饿条件"], "answer": 3, "source": "操作系统 第2章"},
    {"id": "os_q4", "subject": "os_process", "chapter": "信号量", "type": "choice", "difficulty": "hard",
     "text": "信号量S的初值为3，执行5次P操作和3次V操作后S的值为？",
     "options": ["1", "-2", "0", "5"], "answer": 0, "source": "操作系统 第2章"},
    {"id": "os_q5", "subject": "os_process", "chapter": "调度算法", "type": "choice", "difficulty": "medium",
     "text": "能使平均等待时间最短的调度算法是？",
     "options": ["FCFS", "SJF", "RR", "多级反馈队列"], "answer": 1, "source": "操作系统 第2章"},
    # 内存管理
    {"id": "os_q6", "subject": "os_memory", "chapter": "页面置换", "type": "choice", "difficulty": "hard",
     "text": "可能导致Belady异常的页面置换算法是？",
     "options": ["OPT", "LRU", "FIFO", "Clock"], "answer": 2, "source": "操作系统 第3章"},
    {"id": "os_q7", "subject": "os_memory", "chapter": "分页", "type": "choice", "difficulty": "medium",
     "text": "分页存储管理中，物理地址=？",
     "options": ["页号×页大小+页内偏移", "块号×页大小+页内偏移", "段号×页大小+页内偏移", "块号+页内偏移"], "answer": 1, "source": "操作系统 第3章"},
    {"id": "os_q8", "subject": "os_memory", "chapter": "虚拟内存", "type": "fill", "difficulty": "medium",
     "text": "虚拟内存的两个核心技术：请求分页和______。",
     "answer": "页面置换（或请求分段）", "source": "操作系统 第3章"},
    # 文件系统
    {"id": "os_q9", "subject": "os_file", "chapter": "磁盘调度", "type": "choice", "difficulty": "medium",
     "text": "SCAN磁盘调度算法又称为什么？",
     "options": ["最短寻道优先", "电梯算法", "循环扫描", "LOOK算法"], "answer": 1, "source": "操作系统 第4章"},
    # IO
    {"id": "os_q10", "subject": "os_io", "chapter": "缓冲区", "type": "choice", "difficulty": "easy",
     "text": "引入缓冲技术的主要目的是？",
     "options": ["减少数据量", "缓和CPU与IO速度不匹配", "减少内存占用", "简化程序设计"], "answer": 1, "source": "操作系统 第5章"},
    {"id": "os_q11", "subject": "os_process", "chapter": "死锁", "type": "choice", "difficulty": "medium",
     "text": "死锁产生的四个必要条件中，哪个条件通过资源一次性分配可以破坏？",
     "options": ["互斥", "请求与保持", "不可剥夺", "循环等待"], "answer": 1, "source": "操作系统 第2章"},
    {"id": "os_q12", "subject": "os_memory", "chapter": "页面置换", "type": "choice", "difficulty": "hard",
     "text": "在页面置换算法中，LRU算法的实现需要什么硬件支持？", "options": ["移位寄存器", "页表", "TLB", "Cache"], "answer": 0, "source": "操作系统 第3章"},
    {"id": "os_q13", "subject": "os_overview", "chapter": "操作系统概述", "type": "choice", "difficulty": "easy",
     "text": "操作系统的主要功能不包括？", "options": ["进程管理", "内存管理", "编译程序", "文件管理"], "answer": 2, "source": "操作系统 第1章"},
    {"id": "os_q14", "subject": "os_process", "chapter": "进程管理", "type": "fill", "difficulty": "medium",
     "text": "进程的三种基本状态是______、______和______。", "answer": "就绪、运行、阻塞", "source": "操作系统 第2章"},
    {"id": "os_q15", "subject": "os_file", "chapter": "文件系统", "type": "choice", "difficulty": "medium",
     "text": "FAT文件系统的空闲空间管理方式是？", "options": ["空闲表法", "空闲链表法", "位示图法", "成组链接法"], "answer": 1, "source": "操作系统 第4章"},
    {"id": "os_q16", "subject": "os_io", "chapter": "IO控制", "type": "choice", "difficulty": "medium",
     "text": "SPOOLing技术可以将独占设备变为？", "options": ["共享设备", "虚拟设备", "字符设备", "块设备"], "answer": 1, "source": "操作系统 第5章"},
    {"id": "os_q17", "subject": "os_memory", "chapter": "分段", "type": "choice", "difficulty": "medium",
     "text": "分段存储中，段表的基地址字段存的是？", "options": ["段号", "段长", "段在内存中的起始地址", "段的保护位"], "answer": 2, "source": "操作系统 第3章"},
    {"id": "os_q18", "subject": "os_process", "chapter": "PV操作", "type": "fill", "difficulty": "hard",
     "text": "信号量初始值为1，执行P操作后信号量值变为______，执行V操作后变为______。", "answer": "0、1", "source": "操作系统 第2章"},
    {"id": "os_q19", "subject": "os_memory", "chapter": "分页", "type": "compute", "difficulty": "medium",
     "text": "逻辑地址空间32页，每页2KB，物理内存256KB，计算逻辑地址0x3500对应的物理地址（设页表为：0→3,1→5,2→8,3→10）。", "answer": "10*2048+0x3500%2048=20480+1280=21760=0x5500", "source": "操作系统 第3章"},
    {"id": "os_q20", "subject": "os_process", "chapter": "线程", "type": "choice", "difficulty": "easy",
     "text": "同一进程中的多个线程共享的是？", "options": ["栈", "程序计数器", "寄存器", "全局变量"], "answer": 3, "source": "操作系统 第2章"},
    {"id": "os_q21", "subject": "os_memory", "chapter": "TLB", "type": "fill", "difficulty": "medium",
     "text": "TLB的全称是______。", "answer": "Translation Lookaside Buffer（快表）", "source": "操作系统 第3章"},
]

OS_SEED_SUBJECTS = {
    "os_overview": {"name": "操作系统概述", "chapters": ["OS定义与功能", "OS发展历程", "内核态与用户态"]},
    "os_process": {"name": "进程管理", "chapters": ["进程与线程", "进程同步与信号量", "死锁", "调度算法"]},
    "os_memory": {"name": "内存管理", "chapters": ["连续分配", "分页与分段", "虚拟内存", "页面置换算法"]},
    "os_file": {"name": "文件系统", "chapters": ["文件结构", "目录结构", "空闲空间管理", "磁盘调度"]},
    "os_io": {"name": "IO管理", "chapters": ["IO层次", "缓冲区", "SPOOLing"]},
}

OS_KNOWLEDGE_GRAPH = {
    "nodes": [
        {"id": "os_overview", "label": "操作系统概述", "group": 1},
        {"id": "os_process", "label": "进程管理", "group": 2},
        {"id": "os_thread", "label": "线程", "group": 2},
        {"id": "os_sync", "label": "同步与信号量", "group": 2},
        {"id": "os_deadlock", "label": "死锁", "group": 2},
        {"id": "os_schedule", "label": "调度算法", "group": 2},
        {"id": "os_memory", "label": "内存管理", "group": 3},
        {"id": "os_virtual", "label": "虚拟内存", "group": 3},
        {"id": "os_page", "label": "页面置换", "group": 3},
        {"id": "os_file", "label": "文件系统", "group": 4},
        {"id": "os_disk", "label": "磁盘调度", "group": 4},
        {"id": "os_io", "label": "IO管理", "group": 5},
    ],
    "edges": [
        {"source": "os_overview", "target": "os_process"},
        {"source": "os_process", "target": "os_thread"},
        {"source": "os_process", "target": "os_sync"},
        {"source": "os_sync", "target": "os_deadlock"},
        {"source": "os_process", "target": "os_schedule"},
        {"source": "os_overview", "target": "os_memory"},
        {"source": "os_memory", "target": "os_virtual"},
        {"source": "os_virtual", "target": "os_page"},
        {"source": "os_overview", "target": "os_file"},
        {"source": "os_file", "target": "os_disk"},
        {"source": "os_overview", "target": "os_io"},
        {"source": "os_process", "target": "os_memory"},
        {"source": "os_file", "target": "os_io"},
    ],
}

