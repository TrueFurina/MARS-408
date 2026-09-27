# coding: utf-8
# 计算机组成原理（CO）段 —— 自 seed_data.py 第 815-958 行二进制原样搬运（M-4 ③）。
# 含 CO_SEED_KNOWLEDGE_CHUNKS 的**最终版**（覆盖 seed/net.py 中的 v1）。
# ============================================================
# 计算机组成原理种子数据
# 7章：概述/数据表示/存储系统/指令系统/CPU/总线/IO
# ============================================================

CO_SEED_KNOWLEDGE_CHUNKS = [
    # ---- 第1章 计算机系统概述 ----
    {"content": "计算机系统由硬件和软件组成。硬件：运算器、控制器、存储器、输入设备、输出设备（冯·诺依曼结构五大部件）。软件：系统软件（OS/编译器等）和应用软件。", "metadata": {"subject": "co_overview", "chapter": "计算机系统概述", "type": "knowledge_point"}},
    {"content": "冯·诺依曼计算机特点：存储程序（指令和数据同等存储）、按地址访问顺序执行。程序计数器PC指向下一条指令地址。五大部件通过总线连接。", "metadata": {"subject": "co_overview", "chapter": "冯诺依曼结构", "type": "knowledge_point"}},
    {"content": "计算机性能指标：主频（时钟频率）、CPI（每条指令平均时钟周期数）、MIPS（百万指令每秒）、MFLOPS（百万浮点运算每秒）。CPU执行时间 = 指令数 × CPI × 时钟周期。", "metadata": {"subject": "co_overview", "chapter": "性能指标", "type": "knowledge_point"}},
    # ---- 第2章 数据的表示和运算 ----
    {"content": "定点数表示：原码（符号位+绝对值）、反码（正数同原码、负数除符号外取反）、补码（正数同原码、负数反码+1）。补码优势：0唯一表示、减法变加法。移码：补码符号位取反。", "metadata": {"subject": "co_data", "chapter": "定点数", "type": "knowledge_point"}},
    {"content": "IEEE 754浮点数：单精度(32位：1符号+8阶码+23尾数)、双精度(64位：1+11+52)。阶码用移码(偏置值127/1023)、尾数用原码(隐含1)。规格化数：尾数在[1,2)。", "metadata": {"subject": "co_data", "chapter": "浮点数", "type": "knowledge_point"}},
    {"content": "ALU算术逻辑单元：半加器(不考虑进位)、全加器(考虑低位进位)。串行进位加法器延迟大(n位需n倍门延迟)，先行进位CLA采用进位生成/传递信号并行计算。", "metadata": {"subject": "co_data", "chapter": "运算器", "type": "knowledge_point"}},
    {"content": "补码加减运算：溢出判断三种方法——(1)双符号位法(00正/11负/01上溢/10下溢)、(2)单符号位法(Cn⊕C(n-1)=1溢出)、(3)双高位判别法。", "metadata": {"subject": "co_data", "chapter": "补码运算", "type": "knowledge_point"}},
    # ---- 第3章 存储系统 ----
    {"content": "存储器层次结构：寄存器→Cache→主存→辅存，速度递减、容量递增、价格递减。时间局部性（刚访问的近期再访问）和空间局部性（访问某地址则附近也访问）是Cache和虚拟存储器的理论基础。", "metadata": {"subject": "co_memory", "chapter": "层次结构", "type": "knowledge_point"}},
    {"content": "Cache映射方式：直接映射（每块只有1个位置,冲突高）、全相联映射（任意位置,硬件代价大）、组相联映射（折中,每组k块→k路组相联）。替换算法：LRU（未使用最久）、FIFO、随机、LFU。", "metadata": {"subject": "co_memory", "chapter": "Cache", "type": "knowledge_point"}},
    {"content": "Cache写策略：写命中→写直达（同时写Cache和主存）+写回（仅写Cache,替换时写回）；写不命中→写分配（调入Cache再写）+非写分配（直接写主存）。Cache访存平均时间 = 命中率×Cache时间 + (1-命中率)×主存时间。", "metadata": {"subject": "co_memory", "chapter": "Cache写策略", "type": "knowledge_point"}},
    {"content": "主存与CPU的连接：地址线决定寻址范围(n根→2^n地址)、数据线决定字长。存储器扩展包含位扩展（增加字长）和字扩展（增加容量）。片选信号CS由高位地址线译码产生。", "metadata": {"subject": "co_memory", "chapter": "主存连接", "type": "knowledge_point"}},
    {"content": "DRAM（动态RAM）：用电容存储,需刷新(2ms周期)，地址线分时复用(行/列地址)。SRAM（静态RAM）：用触发器,速度快 无需刷新,价格高,用于Cache。ROM/EPROM/EEPROM/Flash属于非易失存储器。", "metadata": {"subject": "co_memory", "chapter": "RAM/ROM", "type": "knowledge_point"}},
    # ---- 第4章 指令系统 ----
    {"content": "指令格式：操作码OP（指出做什么）+ 地址码A（指出操作数在哪）。按地址数分：三地址(A←B op C)、二地址(A←A op B)、一地址(隐含ACC累加器)、零地址(堆栈)。指令字长：定长/变长。", "metadata": {"subject": "co_isa", "chapter": "指令格式", "type": "knowledge_point"}},
    {"content": "寻址方式：立即寻址（操作数=地址码）、直接寻址（EA=A）、间接寻址（EA=(A)）、寄存器寻址（EA=Ri）、寄存器间接（EA=(Ri)）、变址寻址（EA=(IX)+A）、基址寻址（EA=(BR)+A）、相对寻址（EA=(PC)+A）。", "metadata": {"subject": "co_isa", "chapter": "寻址方式", "type": "knowledge_point"}},
    {"content": "CISC（复杂指令集）vs RISC（精简指令集）：CISC指令多变长、寻址方式多、微程序控制；RISC指令少定长、寻址方式少、硬布线控制、load/store架构、流水线友好。x86是CISC的代表，ARM/MIPS是RISC。", "metadata": {"subject": "co_isa", "chapter": "CISC vs RISC", "type": "knowledge_point"}},
    # ---- 第5章 中央处理器 ----
    {"content": "CPU基本组成：运算器ALU+寄存器组（PC/IR/MAR/MDR/ACC/PSW）+控制器CU。指令周期：取指→间址→执行→中断，含多个CPU周期（机器周期），每机器周期含多个时钟周期。", "metadata": {"subject": "co_cpu", "chapter": "CPU结构", "type": "knowledge_point"}},
    {"content": "数据通路：单总线结构（一次只能传一个数据,需多周期）、双总线（输入输出分离）、三总线（同时传两个源操作数和结果）。微操作序列：控制信号在时钟节拍下触发各部件动作。", "metadata": {"subject": "co_cpu", "chapter": "数据通路", "type": "knowledge_point"}},
    {"content": "指令流水线：五段经典流水：取指IF→译码ID→执行EX→访存MEM→写回WB。流水线性能：吞吐率=n/T_k 实际加速比<n（冲突开销）。三类冲突：结构冲突（硬件资源）、数据冲突（RAW/WAR/WAW）、控制冲突（分支）。", "metadata": {"subject": "co_cpu", "chapter": "流水线", "type": "knowledge_point"}},
    {"content": "数据冲突解决：转发/旁路技术（ALU输出直接反馈到输入）、插入气泡（stall一个周期NOP）、编译器调度（重排指令顺序）。控制冲突：分支预测（静态：预测不跳转；动态：基于历史）。延迟分支：在分支槽填有用指令。", "metadata": {"subject": "co_cpu", "chapter": "流水线冲突", "type": "knowledge_point"}},
    {"content": "控制器实现：硬布线（组合逻辑电路,速度快,不易修改）和微程序（控制存储器存微指令,顺序执行,灵活但慢）。微指令包含微操作控制字段+顺序控制字段（下址）。微指令格式：水平型（编码短/并行度高）和垂直型（编码长/类似机器指令）。", "metadata": {"subject": "co_cpu", "chapter": "控制器", "type": "knowledge_point"}},
    # ---- 第6章 总线 ----
    {"content": "总线分类：片内总线（CPU内部）、系统总线（数据总线/地址总线/控制总线）、通信总线（外部设备间）。总线标准：PCI（并行,33/66MHz）、PCIe X1/4/8/16（串行差分,高带宽）、USB（通用串行）。", "metadata": {"subject": "co_bus", "chapter": "总线概述", "type": "knowledge_point"}},
    {"content": "总线仲裁：集中式仲裁——链式查询(3根线,优先级固定距离近优先)、计数器定时查询(去除BG线,各设备均有BR,设备号可动态改变)、独立请求(每设备一对BR/BG线,控制器排队,灵活但线多)。分布式仲裁不需要中央仲裁器。", "metadata": {"subject": "co_bus", "chapter": "总线仲裁", "type": "knowledge_point"}},
    {"content": "总线定时：同步通信（统一时钟,速度快但设备速度必须匹配）、异步通信（握手应答,灵活但复杂）、半同步（统一时钟+等待信号,折中）、分离式通信（主设备发送后释放总线从设备准备再申请,提高利用率）。", "metadata": {"subject": "co_bus", "chapter": "总线定时", "type": "knowledge_point"}},
    # ---- 第7章 输入输出系统 ----
    {"content": "IO接口功能：设备选择（通过地址码）、数据缓冲、信号转换（串/并、电平转换）、中断管理。IO端口编址：独立编址（独立IO指令,如x86的IN/OUT）和统一编址（与主存统一地址空间,如ARM的MMIO）。", "metadata": {"subject": "co_io", "chapter": "IO接口", "type": "knowledge_point"}},
    {"content": "IO控制方式：程序查询(CPU轮询,效率低)、程序中断(外设主动通知CPU,CPU暂停当前程序转入中断服务程序)、DMA(直接存储器访问,不需要CPU干预,块传输前CPU仅初始化)。", "metadata": {"subject": "co_io", "chapter": "IO控制方式", "type": "knowledge_point"}},
    {"content": "DMA：由DMA控制器完成主存与IO设备间的数据块传输。三种传送方式：CPU停止法（传输期间CPU不访存）、周期挪用（DMA窃取总线周期）、交替访问（分时复用）。DMA初始化阶段CPU参与，数据传输阶段CPU不参与。", "metadata": {"subject": "co_io", "chapter": "DMA", "type": "knowledge_point"}},
    {"content": "中断系统：中断请求→中断响应（CPU在指令执行最后查询中断请求信号）→中断服务→中断返回。中断向量（存储中断服务程序入口地址的表）。多重中断：高优先级可打断低优先级（需开中断）。中断屏蔽字：屏蔽低优先级中断。", "metadata": {"subject": "co_io", "chapter": "中断", "type": "knowledge_point"}},
]

CO_SEED_QUESTIONS = [
    # 概述
    {"id": "co_q1", "subject": "co_overview", "chapter": "性能指标", "type": "choice", "difficulty": "medium",
     "text": "CPU执行时间等于？",
     "options": ["指令数×CPI×主频", "指令数×CPI×时钟周期", "指令数/CPI×时钟周期", "CPI×时钟周期/指令数"], "answer": 1, "source": "计算机组成原理 第1章"},
    {"id": "co_q2", "subject": "co_overview", "chapter": "冯诺依曼结构", "type": "fill", "difficulty": "easy",
     "text": "冯·诺依曼计算机的核心思想是______。",
     "answer": "存储程序", "source": "计算机组成原理 第1章"},
    # 数据的表示
    {"id": "co_q3", "subject": "co_data", "chapter": "定点数", "type": "choice", "difficulty": "medium",
     "text": "补码相比于原码的优点是？",
     "options": ["0表示唯一", "便于人类阅读", "不需要符号位", "存储空间小"], "answer": 0, "source": "计算机组成原理 第2章"},
    {"id": "co_q4", "subject": "co_data", "chapter": "浮点数", "type": "choice", "difficulty": "hard",
     "text": "IEEE 754单精度浮点数的阶码偏置值（bias）是？",
     "options": ["127", "128", "1023", "255"], "answer": 0, "source": "计算机组成原理 第2章"},
    # 存储系统
    {"id": "co_q5", "subject": "co_memory", "chapter": "Cache", "type": "choice", "difficulty": "medium",
     "text": "Cache的映射方式中，冲突概率最低的是？",
     "options": ["直接映射", "全相联映射", "2路组相联", "4路组相联"], "answer": 1, "source": "计算机组成原理 第3章"},
    {"id": "co_q6", "subject": "co_memory", "chapter": "Cache写策略", "type": "choice", "difficulty": "medium",
     "text": "写回法（Write Back）的特点是？",
     "options": ["每次都同时写Cache和主存", "仅写Cache,替换时写回主存", "直接写主存不写Cache", "绕过Cache写主存"], "answer": 1, "source": "计算机组成原理 第3章"},
    # 指令系统
    {"id": "co_q7", "subject": "co_isa", "chapter": "寻址方式", "type": "choice", "difficulty": "medium",
     "text": "变址寻址中，有效地址EA等于？",
     "options": ["(IX)", "(IX)+A", "(A)+IX", "IX+A"], "answer": 1, "source": "计算机组成原理 第4章"},
    # CPU
    {"id": "co_q8", "subject": "co_cpu", "chapter": "流水线", "type": "choice", "difficulty": "hard",
     "text": "指令流水线中，RAW（Read After Write）属于哪种冲突？",
     "options": ["结构冲突", "数据冲突", "控制冲突", "资源冲突"], "answer": 1, "source": "计算机组成原理 第5章"},
    {"id": "co_q9", "subject": "co_cpu", "chapter": "流水线", "type": "fill", "difficulty": "hard",
     "text": "五段经典指令流水线的五个阶段依次是：IF→ID→→______→______→WB。",
     "answer": "ID→EX→MEM→WB", "source": "计算机组成原理 第5章"},
    # IO
    {"id": "co_q10", "subject": "co_io", "chapter": "IO控制方式", "type": "choice", "difficulty": "medium",
     "text": "DMA方式传送数据时，每传送一个数据占用几个存储周期？",
     "options": ["1个", "2个", "0个（不占用）", "取决于数据大小"], "answer": 0, "source": "计算机组成原理 第7章"},
    {"id": "co_q11", "subject": "co_io", "chapter": "中断", "type": "choice", "difficulty": "medium",
     "text": "CPU响应中断的条件不包括？",
     "options": ["中断源有请求", "CPU允许中断(开中断)", "一条指令执行结束", "当前指令是特权指令"], "answer": 3, "source": "计算机组成原理 第7章"},
    {"id": "co_q12", "subject": "co_memory", "chapter": "Cache", "type": "choice", "difficulty": "medium",
     "text": "Cache写操作中使用写直达法时，写操作的时间是？", "options": ["只写Cache", "同时写Cache和主存", "只写主存", "写Cache后异步写主存"], "answer": 1, "source": "计算机组成原理 第3章"},
    {"id": "co_q13", "subject": "co_data", "chapter": "浮点数", "type": "choice", "difficulty": "hard",
     "text": "IEEE 754单精度浮点数的阶码采用什么编码？", "options": ["原码", "补码", "移码(偏置127)", "反码"], "answer": 2, "source": "计算机组成原理 第2章"},
    {"id": "co_q14", "subject": "co_cpu", "chapter": "流水线", "type": "choice", "difficulty": "hard",
     "text": "流水线数据冲突的解决方式不包括？", "options": ["插入空操作(气泡)", "数据转发(旁路)", "调整指令顺序", "增加流水线级数"], "answer": 3, "source": "计算机组成原理 第5章"},
    {"id": "co_q15", "subject": "co_memory", "chapter": "DRAM", "type": "choice", "difficulty": "medium",
     "text": "DRAM需要刷新的原因是？", "options": ["电荷泄漏", "地址线复用", "功耗管理", "多路复用"], "answer": 0, "source": "计算机组成原理 第3章"},
    {"id": "co_q16", "subject": "co_isa", "chapter": "指令系统", "type": "choice", "difficulty": "medium",
     "text": "RISC相比CISC的特点不包括？", "options": ["指令数量少", "寻址方式少", "微程序控制", "寄存器多"], "answer": 2, "source": "计算机组成原理 第4章"},
    {"id": "co_q17", "subject": "co_bus", "chapter": "总线", "type": "fill", "difficulty": "medium",
     "text": "总线仲裁中，集中式仲裁方式有______、______和______三种。", "answer": "链式查询、计数器定时查询、独立请求", "source": "计算机组成原理 第6章"},
    {"id": "co_q18", "subject": "co_data", "chapter": "定点数", "type": "compute", "difficulty": "medium",
     "text": "设x=-69，用8位补码表示x，并求x的二进制补码表示。", "answer": "10111011", "source": "计算机组成原理 第2章"},
    {"id": "co_q19", "subject": "co_memory", "chapter": "Cache", "type": "compute", "difficulty": "hard",
     "text": "主存容量256MB，按字(32位)编址，Cache容量64KB，块大小16字，计算Cache行数。", "answer": "1024", "source": "计算机组成原理 第3章"},
    {"id": "co_q20", "subject": "co_cpu", "chapter": "CPU", "type": "fill", "difficulty": "medium",
     "text": "CPU中程序计数器PC的作用是______。", "answer": "存放下一条指令的地址", "source": "计算机组成原理 第5章"},
]

CO_SEED_SUBJECTS = {
    "co_overview": {"name": "计算机系统概述", "chapters": ["冯诺依曼结构", "性能指标", "计算机发展"]},
    "co_data": {"name": "数据的表示和运算", "chapters": ["定点数", "浮点数", "ALU", "补码运算"]},
    "co_memory": {"name": "存储系统", "chapters": ["层次结构", "Cache映射与替换", "Cache写策略", "主存扩展", "DRAM/SRAM"]},
    "co_isa": {"name": "指令系统", "chapters": ["指令格式", "寻址方式", "CISC vs RISC"]},
    "co_cpu": {"name": "中央处理器", "chapters": ["CPU结构与数据通路", "指令流水线", "流水线冲突", "控制器实现"]},
    "co_bus": {"name": "总线", "chapters": ["总线分类与标准", "总线仲裁", "总线定时"]},
    "co_io": {"name": "输入输出系统", "chapters": ["IO接口", "IO控制方式", "DMA", "中断系统"]},
}

CO_KNOWLEDGE_GRAPH = {
    "nodes": [
        {"id": "co_overview", "label": "计算机概述", "group": 1},
        {"id": "co_data", "label": "数据表示与运算", "group": 2},
        {"id": "co_memory", "label": "存储系统", "group": 3},
        {"id": "co_cache", "label": "Cache", "group": 3},
        {"id": "co_isa", "label": "指令系统", "group": 4},
        {"id": "co_cpu", "label": "CPU", "group": 5},
        {"id": "co_pipeline", "label": "流水线", "group": 5},
        {"id": "co_bus", "label": "总线", "group": 6},
        {"id": "co_io", "label": "IO系统", "group": 7},
        {"id": "co_dma", "label": "DMA", "group": 7},
        {"id": "co_interrupt", "label": "中断", "group": 7},
    ],
    "edges": [
        {"source": "co_overview", "target": "co_data"},
        {"source": "co_overview", "target": "co_memory"},
        {"source": "co_data", "target": "co_isa"},
        {"source": "co_data", "target": "co_cpu"},
        {"source": "co_memory", "target": "co_cache"},
        {"source": "co_cache", "target": "co_cpu"},
        {"source": "co_isa", "target": "co_cpu"},
        {"source": "co_cpu", "target": "co_pipeline"},
        {"source": "co_memory", "target": "co_bus"},
        {"source": "co_cpu", "target": "co_bus"},
        {"source": "co_bus", "target": "co_io"},
        {"source": "co_io", "target": "co_dma"},
        {"source": "co_io", "target": "co_interrupt"},
        {"source": "co_pipeline", "target": "co_io"},
    ],
}

