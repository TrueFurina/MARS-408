# coding: utf-8
# 数据结构（DS）段 —— 自 seed_data.py 第 591-814 行二进制原样搬运（M-4 ③）。
# ============================================================
# 数据结构种子数据（大创首期承诺：数据结构+计网）
# 8章：线性表、栈队列、串、树、图、查找、排序、综合
# ============================================================

DS_SEED_KNOWLEDGE_CHUNKS = [
    # ---- 第1章 线性表 ----
    {"content": "线性表是n个数据元素的有限序列。顺序存储（数组）优点：随机访问O(1)；缺点：插入删除需移动元素O(n)。链式存储（链表）优点：插入删除O(1)；缺点：查找O(n)。", "metadata": {"subject": "ds_linear", "chapter": "线性表", "type": "knowledge_point"}},
    {"content": "单链表：每个节点含data和next指针。头节点方便操作（空表处理统一）。插入：s->next=p->next, p->next=s。删除：p->next=p->next->next。注意操作顺序。", "metadata": {"subject": "ds_linear", "chapter": "链表", "type": "knowledge_point"}},
    {"content": "双向链表：节点含prior、data、next三个域。插入：s->next=p->next, p->next->prior=s, s->prior=p, p->next=s（4步，顺序关键）。删除：p->next->prior=p->prior, p->prior->next=p->next。", "metadata": {"subject": "ds_linear", "chapter": "双向链表", "type": "knowledge_point"}},
    {"content": "循环链表：尾节点next指向头节点。判空条件：头节点next==头节点自身。双向循环链表判空：头节点next==prior==自身。", "metadata": {"subject": "ds_linear", "chapter": "循环链表", "type": "knowledge_point"}},
    # ---- 第2章 栈和队列 ----
    {"content": "栈是后进先出(LIFO)线性表。顺序栈：top指针指向栈顶元素下一位置(top=-1为空)。入栈：S[top++]=x；出栈：x=S[--top]。共享栈：两个栈共用数组，栈1从左端增长，栈2从右端增长，栈满条件top1+1==top2。", "metadata": {"subject": "ds_stack", "chapter": "栈", "type": "knowledge_point"}},
    {"content": "队列是先进先出(FIFO)线性表。循环队列：front指向队头，rear指向队尾下一位置。队空：front==rear。队满：(rear+1)%MaxSize==front（牺牲一个空间）。元素个数：(rear-front+MaxSize)%MaxSize。", "metadata": {"subject": "ds_queue", "chapter": "队列", "type": "knowledge_point"}},
    {"content": "链队列：front指向头节点，rear指向尾节点。入队：rear->next=s, rear=s。出队：p=front->next, front->next=p->next, 若原队仅一个元素则rear=front。", "metadata": {"subject": "ds_queue", "chapter": "链队列", "type": "knowledge_point"}},
    {"content": "栈的应用：括号匹配(遇左括号入栈遇右括号出栈比对)、表达式求值(双栈：操作数栈+运算符栈)、递归(系统调用栈)、DFS深度优先遍历。队列应用：BFS广度优先遍历、打印缓冲、CPU任务调度。", "metadata": {"subject": "ds_stack", "chapter": "栈应用", "type": "knowledge_point"}},
    {"content": "双端队列(deque)：两端都可入出。受限双端队列：一端可入出+另一端只入(输出受限)或一端可入出+另一端只出(输入受限)。", "metadata": {"subject": "ds_queue", "chapter": "双端队列", "type": "knowledge_point"}},
    {"content": "栈和队列的主要区别：栈是后进先出(LIFO)的线性表，只允许在栈顶一端插入删除；队列是先进先出(FIFO)的线性表，在队尾入队、队头出队。二者最核心区别是操作受限位置不同——栈「后进先出」、队列「先进先出」。", "metadata": {"subject": "ds_stack", "chapter": "栈和队列", "type": "knowledge_point"}},
    # ---- 第3章 串 ----
    {"content": "串是字符组成的有限序列。空串：长度为0。空格串：由空格字符组成，长度≥1。子串：串中任意连续字符序列。主串：包含子串的串。子串位置：子串第一个字符在主串中的序号。", "metadata": {"subject": "ds_string", "chapter": "串", "type": "knowledge_point"}},
    {"content": "KMP算法核心：利用已匹配信息避免主串指针回退。next数组（部分匹配表，即最长公共前后缀表）：next[j]=模式串T[1..j-1]中最长相同前后缀长度+1。匹配失败时主串i不变，模式串j=next[j]。时间复杂度O(n+m)。", "metadata": {"subject": "ds_string", "chapter": "KMP", "type": "knowledge_point"}},
    {"content": "next数组计算：next[1]=0, next[2]=1。一般：若T[k]==T[j]则next[j+1]=next[j]+1=k+1；否则k=next[k]继续比较直到k=0。nextval优化：若T[next[j]]==T[j]则nextval[j]=nextval[next[j]]。", "metadata": {"subject": "ds_string", "chapter": "KMP优化", "type": "knowledge_point"}},
    # ---- 第4章 树 ----
    {"content": "树是n个节点的有限集。n=0时为空树。根节点唯一，子树互不相交。节点的度：拥有的子树数。树的度：各节点度的最大值。叶子节点：度为0。深度：从根到该节点路径长度+1。", "metadata": {"subject": "ds_tree", "chapter": "树", "type": "knowledge_point"}},
    {"content": "二叉树：每个节点最多2个子树(左子树和右子树有顺序)。满二叉树：每层都有最大节点数。完全二叉树：编号1~n的节点与满二叉树编号1~n一致。性质：第i层最多2^(i-1)个节点；深度k最多2^k-1个节点；n0=n2+1。", "metadata": {"subject": "ds_tree", "chapter": "二叉树", "type": "knowledge_point"}},
    {"content": "二叉树遍历：先序(根左右)、中序(左根右)、后序(左右根)。由先序+中序或后序+中序可唯一确定二叉树，但先序+后序不能。线索二叉树：利用n+1个空指针域存储前驱/后继线索。", "metadata": {"subject": "ds_tree", "chapter": "遍历", "type": "knowledge_point"}},
    {"content": "BST二叉排序树：左子树<根<右子树。查找平均O(logn)，最坏O(n)退化为链表。插入：沿查找路径到空位置插入。删除：叶子直接删；仅一子树用子树替代；有两子树用右子树最左节点(中序后继)替代。", "metadata": {"subject": "ds_tree", "chapter": "BST", "type": "knowledge_point"}},
    {"content": "AVL平衡二叉树：左右子树高度差|平衡因子|<=1。调整4种：LL(右旋)、RR(左旋)、LR(先左旋右子树再右旋)、RL(先右旋左子树再左旋)。查找O(logn)，插入删除需调整但也是O(logn)。", "metadata": {"subject": "ds_tree", "chapter": "AVL", "type": "knowledge_point"}},
    {"content": "哈夫曼树：WPL最小的二叉树。构造：每次选权值最小的两棵树合并。n个叶子节点→n-1次合并→共2n-1个节点。无度为1的节点。哈夫曼编码：左0右1，前缀编码(任一字符编码不是另一编码前缀)。", "metadata": {"subject": "ds_tree", "chapter": "哈夫曼", "type": "knowledge_point"}},
    # ---- 第5章 图 ----
    {"content": "图G=(V,E)。有向图：弧<v,w>，v弧尾w弧头。无向图：边(v,w)。完全图：有向n(n-1)条弧，无向n(n-1)/2条边。连通图：任意两顶点间有路径。强连通图：有向图任意两顶点互相可达。", "metadata": {"subject": "ds_graph", "chapter": "图", "type": "knowledge_point"}},
    {"content": "图的存储：邻接矩阵(适合稠密图,空间O(n^2),查边O(1))、邻接表(适合稀疏图,空间O(n+e),查边O(度))、十字链表(有向图)、邻接多重表(无向图)。", "metadata": {"subject": "ds_graph", "chapter": "存储", "type": "knowledge_point"}},
    {"content": "DFS深度优先遍历：类似树先序遍历，用栈/递归。BFS广度优先遍历：类似树层序遍历，用队列。时间复杂度：邻接矩阵O(n^2)，邻接表O(n+e)。", "metadata": {"subject": "ds_graph", "chapter": "遍历", "type": "knowledge_point"}},
    {"content": "最小生成树MST：Prim算法(从一点出发逐步加最近点,O(n^2))、Kruskal算法(按边权排序逐步加不构成环的边,O(eloge))。MST唯一条件：所有边权不相等。", "metadata": {"subject": "ds_graph", "chapter": "MST", "type": "knowledge_point"}},
    {"content": "最短路径：Dijkstra算法(单源,贪心,不适用负权边,O(n^2))、Floyd算法(所有顶点间,动态规划,O(n^3))。拓扑排序：AOV网，入度0的顶点入队逐步输出。关键路径：AOE网，最长路径决定工期。", "metadata": {"subject": "ds_graph", "chapter": "路径", "type": "knowledge_point"}},
    # ---- 第6章 查找 ----
    {"content": "顺序查找：O(n)。折半查找(二分)：有序表，O(logn)。判定树是平衡二叉树，n个元素树高h=floor(log2(n))+1。ASL成功=(1*1+2*2+...+h*2^(h-1))/n。", "metadata": {"subject": "ds_search", "chapter": "线性查找", "type": "knowledge_point"}},
    {"content": "B树(m阶)：每个节点最多m个子树m-1个关键字；非根节点至少m/2个子树(m/2-1向上取整)个关键字；根至少2个子树(非叶时)；所有叶在同一层。B+树：叶节点包含全部关键字+指向记录的指针，非叶节点仅索引。", "metadata": {"subject": "ds_search", "chapter": "B树", "type": "knowledge_point"}},
    {"content": "散列表(哈希表)：根据关键字直接计算存储地址。常用哈希函数：直接定址(H(key)=a*key+b)、除留余数(H(key)=key%p, p<=表长且为质数)、数字分析。冲突处理：开放定址(线性探测/二次探测/双重哈希)、拉链法(又称链地址法)。", "metadata": {"subject": "ds_search", "chapter": "哈希", "type": "knowledge_point"}},
    {"content": "哈希冲突：线性探测容易堆积(聚集)。二次探测：H_i=(H(key)+d_i)%m, d_i=1^2,-1^2,2^2,-2^2,...。双重哈希：d_i=i*H2(key)。拉链法：同义词链表，不堆积，删除方便，适合动态表。", "metadata": {"subject": "ds_search", "chapter": "哈希冲突", "type": "knowledge_point"}},
    # ---- 第7章 排序 ----
    {"content": "插入排序：直接插入(无序序列逐个插入有序序列,O(n^2)稳定)、折半插入(查找用二分但仍需移动,O(n^2)稳定)、希尔排序(按增量分组直接插入,增量递减至1,不稳定,O(n^1.3)~O(n^2))。", "metadata": {"subject": "ds_sort", "chapter": "插入排序", "type": "knowledge_point"}},
    {"content": "交换排序：冒泡排序(相邻比较交换,一趟确定一个最终位置,O(n^2)稳定)、快速排序(基于分治法,选基准pivot将序列分区partition为左≤基准右≥基准两部分再递归,平均O(nlogn)最坏O(n^2)不稳定,空间O(logn)最坏O(n))。快排是最常用排序。", "metadata": {"subject": "ds_sort", "chapter": "交换排序", "type": "knowledge_point"}},
    {"content": "选择排序：简单选择(每趟选最小交换,O(n^2)不稳定)、堆排序(建大根堆,堆顶与末尾交换再调整,O(nlogn)不稳定)。堆：完全二叉树，大顶堆(大根堆)根>=子树所有节点，小顶堆(小根堆)根<=子树所有节点。优先队列常用堆实现：大顶堆取最大/小顶堆取最小，插入删除O(logn)。建堆O(n)，调整O(logn)。", "metadata": {"subject": "ds_sort", "chapter": "选择排序", "type": "knowledge_point"}},
    {"content": "归并排序：分治合并,稳定,O(nlogn),空间O(n)。基数排序：按关键字各位分别排序(LSD/MSD),稳定,O(d(n+r)),空间O(r)。外部排序：多路归并+置换选择+最佳归并树。", "metadata": {"subject": "ds_sort", "chapter": "归并基数", "type": "knowledge_point"}},
    {"content": "排序算法比较：稳定：直接插入/冒泡/归并/基数。不稳定：希尔/快排/简单选择/堆排序。O(nlogn)：快排(平均)/堆排/归并。O(n^2)：直接插入/冒泡/简单选择。快排平均最快但最坏退化。归并稳定但空间大。堆排空间小但不稳定。", "metadata": {"subject": "ds_sort", "chapter": "比较", "type": "knowledge_point"}},
]

DS_SEED_QUESTIONS = [
    # 线性表
    {"id": "ds_q1", "subject": "ds_linear", "chapter": "链表", "type": "choice", "difficulty": "easy",
     "text": "在单链表中，插入一个节点s到节点p之后的操作是？",
     "options": ["s->next=p; p->next=s", "s->next=p->next; p->next=s", "p->next=s; s->next=p->next", "p=s->next; s=p->next"], "answer": 1, "source": "数据结构 第2章"},
    {"id": "ds_q2", "subject": "ds_linear", "chapter": "链表", "type": "choice", "difficulty": "medium",
     "text": "带头节点的单链表L为空的判定条件是？",
     "options": ["L==NULL", "L->next==NULL", "L->next==L", "L->data==0"], "answer": 1, "source": "数据结构 第2章"},
    # 栈和队列
    {"id": "ds_q3", "subject": "ds_stack", "chapter": "栈", "type": "choice", "difficulty": "easy",
     "text": "栈的操作特性是？",
     "options": ["先进先出", "后进先出", "随机存取", "顺序存取"], "answer": 1, "source": "数据结构 第3章"},
    {"id": "ds_q4", "subject": "ds_queue", "chapter": "队列", "type": "choice", "difficulty": "medium",
     "text": "循环队列中，队满的条件是（设front指向队头，rear指向队尾下一位置，MaxSize为队列容量）？",
     "options": ["front==rear", "(rear+1)%MaxSize==front", "rear==MaxSize-1", "front==(rear+1)%MaxSize"], "answer": 1, "source": "数据结构 第3章"},
    {"id": "ds_q5", "subject": "ds_queue", "chapter": "队列", "type": "fill", "difficulty": "medium",
     "text": "循环队列中元素个数的计算公式是（设front指向队头，rear指向队尾下一位置）______",
     "answer": "(rear-front+MaxSize)%MaxSize", "source": "数据结构 第3章"},
    # 串
    {"id": "ds_q6", "subject": "ds_string", "chapter": "KMP", "type": "choice", "difficulty": "hard",
     "text": "KMP算法相比朴素匹配算法的主要改进是？",
     "options": ["模式串指针不回退", "主串指针不回退", "两者都不回退", "使用哈希加速"], "answer": 1, "source": "数据结构 第4章"},
    # 树
    {"id": "ds_q7", "subject": "ds_tree", "chapter": "二叉树", "type": "choice", "difficulty": "easy",
     "text": "二叉树中，叶子节点数n0与度为2的节点数n2的关系是？",
     "options": ["n0=n2", "n0=n2+1", "n0=n2-1", "n0=2*n2"], "answer": 1, "source": "数据结构 第5章"},
    {"id": "ds_q8", "subject": "ds_tree", "chapter": "遍历", "type": "choice", "difficulty": "medium",
     "text": "可以唯一确定一棵二叉树的遍历序列组合是？",
     "options": ["先序+后序", "先序+中序", "后序+层序", "中序+层序不一定"], "answer": 1, "source": "数据结构 第5章"},
    {"id": "ds_q9", "subject": "ds_tree", "chapter": "BST", "type": "choice", "difficulty": "medium",
     "text": "BST中删除一个有两棵子树的节点，通常用哪个节点替代？",
     "options": ["左子树最大节点", "右子树最小节点", "左子树的根", "右子树的根"], "answer": 1, "source": "数据结构 第5章"},
    {"id": "ds_q10", "subject": "ds_tree", "chapter": "AVL", "type": "choice", "difficulty": "hard",
     "text": "AVL树在插入节点后需要LL调整，LL调整的操作是？",
     "options": ["左旋", "右旋", "先左旋再右旋", "先右旋再左旋"], "answer": 1, "source": "数据结构 第5章"},
    {"id": "ds_q11", "subject": "ds_tree", "chapter": "哈夫曼", "type": "fill", "difficulty": "medium",
     "text": "哈夫曼树中n个叶子节点共有______个节点。",
     "answer": "2n-1", "source": "数据结构 第5章"},
    # 图
    {"id": "ds_q12", "subject": "ds_graph", "chapter": "MST", "type": "choice", "difficulty": "medium",
     "text": "Prim算法的时间复杂度是（用邻接矩阵存储）？",
     "options": ["O(n^2)", "O(eloge)", "O(n^3)", "O(nlogn)"], "answer": 0, "source": "数据结构 第6章"},
    {"id": "ds_q13", "subject": "ds_graph", "chapter": "路径", "type": "choice", "difficulty": "medium",
     "text": "Dijkstra算法不适用于哪种情况？",
     "options": ["无向图", "有向图", "含负权边的图", "稀疏图"], "answer": 2, "source": "数据结构 第6章"},
    # 查找
    {"id": "ds_q14", "subject": "ds_search", "chapter": "哈希", "type": "choice", "difficulty": "medium",
     "text": "散列表中处理冲突的方法，哪种不容易产生堆积现象？",
     "options": ["线性探测", "二次探测", "双重哈希", "拉链法"], "answer": 3, "source": "数据结构 第7章"},
    # 排序
    {"id": "ds_q15", "subject": "ds_sort", "chapter": "交换排序", "type": "choice", "difficulty": "medium",
     "text": "快速排序在最坏情况下的时间复杂度是？",
     "options": ["O(nlogn)", "O(n^2)", "O(n)", "O(logn)"], "answer": 1, "source": "数据结构 第8章"},
    {"id": "ds_q16", "subject": "ds_sort", "chapter": "比较", "type": "choice", "difficulty": "easy",
     "text": "下列排序算法中不稳定的是？",
     "options": ["冒泡排序", "直接插入排序", "归并排序", "快速排序"], "answer": 3, "source": "数据结构 第8章"},
    {"id": "ds_q17", "subject": "ds_sort", "chapter": "选择排序", "type": "fill", "difficulty": "medium",
     "text": "堆排序的时间复杂度是______，空间复杂度是______。",
     "answer": "O(nlogn)、O(1)", "source": "数据结构 第8章"},
    # ── 数据结构扩展题 ──
    {"id": "ds_q18", "subject": "ds_tree", "chapter": "BST", "type": "choice", "difficulty": "medium",
     "text": "二叉排序树进行中序遍历得到的结果是？", "options": ["递减序列", "递增序列", "按层序递增", "无序"], "answer": 1, "source": "数据结构 第5章"},
    {"id": "ds_q19", "subject": "ds_queue", "chapter": "栈", "type": "choice", "difficulty": "medium",
     "text": "若入栈序列为1,2,3,4，出栈序列中不可能的是？", "options": ["1,2,3,4", "4,3,2,1", "3,2,4,1", "4,2,3,1"], "answer": 3, "source": "数据结构 第3章"},
    {"id": "ds_q20", "subject": "ds_sort", "chapter": "插入排序", "type": "choice", "difficulty": "easy",
     "text": "对基本有序的数组，哪种排序最快？", "options": ["冒泡", "直接插入", "快速", "堆"], "answer": 1, "source": "数据结构 第8章"},
    {"id": "ds_q21", "subject": "ds_graph", "chapter": "MST", "type": "fill", "difficulty": "medium",
     "text": "带权连通图中，所有生成树中权值最小的称为______。", "answer": "最小生成树", "source": "数据结构 第6章"},
    {"id": "ds_q22", "subject": "ds_sort", "chapter": "比较", "type": "fill", "difficulty": "medium",
     "text": "在n个元素中进行快速排序，最坏情况下的比较次数是______。", "answer": "n(n-1)/2", "source": "数据结构 第8章"},
    {"id": "ds_q23", "subject": "ds_linear", "chapter": "链表", "type": "choice", "difficulty": "hard",
     "text": "判断一个单链表是否有环的最佳方法是？", "options": ["标记法", "快慢指针", "计数法", "哈希表"], "answer": 1, "source": "数据结构 第2章"},
    {"id": "ds_q24", "subject": "ds_linear", "chapter": "顺序表", "type": "fill", "difficulty": "easy",
     "text": "线性表的顺序存储结构中，插入元素的时间复杂度是______。", "answer": "O(n)", "source": "数据结构 第2章"},
    {"id": "ds_q25", "subject": "ds_string", "chapter": "KMP", "type": "fill", "difficulty": "hard",
     "text": "KMP算法中，模式串'abaabc'的next数组（从1开始）是______。", "answer": "011223", "source": "数据结构 第4章"},
    {"id": "ds_q26", "subject": "ds_tree", "chapter": "二叉树", "type": "choice", "difficulty": "easy",
     "text": "深度为h的二叉树最多有多少个节点？", "options": ["2^h-1", "2^(h+1)-1", "2^(h-1)", "2^h"], "answer": 0, "source": "数据结构 第5章"},
    {"id": "ds_q27", "subject": "ds_search", "chapter": "折半查找", "type": "choice", "difficulty": "medium",
     "text": "折半查找要求查找表必须是？", "options": ["顺序存储且有序", "链式存储且有序", "顺序存储即可", "任意存储"], "answer": 0, "source": "数据结构 第7章"},
    {"id": "ds_q28", "subject": "ds_sort", "chapter": "归并排序", "type": "fill", "difficulty": "medium",
     "text": "二路归并排序的时间复杂度是______。", "answer": "O(nlogn)", "source": "数据结构 第8章"},
    {"id": "ds_q29", "subject": "ds_tree", "chapter": "二叉树", "type": "compute", "difficulty": "medium",
     "text": "已知二叉树先序序列为ABDECF，中序序列为DBEAFC，求后序序列。", "answer": "DEBFCA", "source": "数据结构 第5章"},
    {"id": "ds_q30", "subject": "ds_search", "chapter": "哈希", "type": "choice", "difficulty": "hard",
     "text": "哈希表的平均查找长度与哪些因素有关？", "options": ["装填因子", "关键字个数", "表长", "记录类型"], "answer": 0, "source": "数据结构 第7章"},
]

DS_SEED_SUBJECTS = {
    "ds_linear": {"name": "线性表", "chapters": ["顺序存储", "链式存储", "双向链表", "循环链表"]},
    "ds_stack": {"name": "栈", "chapters": ["顺序栈", "链栈", "栈的应用"]},
    "ds_queue": {"name": "队列", "chapters": ["循环队列", "链队列", "双端队列", "队列的应用"]},
    "ds_string": {"name": "串", "chapters": ["串的基本操作", "KMP算法", "next数组"]},
    "ds_tree": {"name": "树与二叉树", "chapters": ["树的定义", "二叉树性质", "遍历", "BST", "AVL", "哈夫曼树"]},
    "ds_graph": {"name": "图", "chapters": ["图的定义与存储", "遍历", "MST", "最短路径", "拓扑排序"]},
    "ds_search": {"name": "查找", "chapters": ["线性查找", "BST与AVL", "B树", "哈希表"]},
    "ds_sort": {"name": "排序", "chapters": ["插入排序", "交换排序", "选择排序", "归并排序", "基数排序", "外部排序"]},
}

DS_KNOWLEDGE_GRAPH = {
    "nodes": [
        {"id": "ds_linear", "label": "线性表", "group": 1},
        {"id": "ds_seq_list", "label": "顺序表", "group": 1},
        {"id": "ds_link_list", "label": "链表", "group": 1},
        {"id": "ds_stack", "label": "栈", "group": 2},
        {"id": "ds_queue", "label": "队列", "group": 2},
        {"id": "ds_string", "label": "串", "group": 3},
        {"id": "ds_kmp", "label": "KMP", "group": 3},
        {"id": "ds_tree", "label": "树", "group": 4},
        {"id": "ds_bst", "label": "BST", "group": 4},
        {"id": "ds_avl", "label": "AVL", "group": 4},
        {"id": "ds_huffman", "label": "哈夫曼", "group": 4},
        {"id": "ds_graph", "label": "图", "group": 5},
        {"id": "ds_mst", "label": "最小生成树", "group": 5},
        {"id": "ds_dijkstra", "label": "最短路径", "group": 5},
        {"id": "ds_search", "label": "查找", "group": 6},
        {"id": "ds_hash", "label": "哈希表", "group": 6},
        {"id": "ds_btree", "label": "B树", "group": 6},
        {"id": "ds_sort", "label": "排序", "group": 7},
        {"id": "ds_quick_sort", "label": "快排", "group": 7},
        {"id": "ds_heap_sort", "label": "堆排", "group": 7},
    ],
    "edges": [
        {"source": "ds_linear", "target": "ds_seq_list"},
        {"source": "ds_linear", "target": "ds_link_list"},
        {"source": "ds_linear", "target": "ds_stack"},
        {"source": "ds_linear", "target": "ds_queue"},
        {"source": "ds_stack", "target": "ds_string"},
        {"source": "ds_string", "target": "ds_kmp"},
        {"source": "ds_linear", "target": "ds_tree"},
        {"source": "ds_tree", "target": "ds_bst"},
        {"source": "ds_bst", "target": "ds_avl"},
        {"source": "ds_tree", "target": "ds_huffman"},
        {"source": "ds_linear", "target": "ds_graph"},
        {"source": "ds_graph", "target": "ds_mst"},
        {"source": "ds_graph", "target": "ds_dijkstra"},
        {"source": "ds_bst", "target": "ds_search"},
        {"source": "ds_search", "target": "ds_hash"},
        {"source": "ds_search", "target": "ds_btree"},
        {"source": "ds_linear", "target": "ds_sort"},
        {"source": "ds_sort", "target": "ds_quick_sort"},
        {"source": "ds_sort", "target": "ds_heap_sort"},
    ],
}

DS_LEARNING_PATH_DAG = {
    "线性表": {
        "id": "ds_linear", "chapter": 1, "prerequisites": [],
        "topics": ["顺序存储", "链式存储(单链表/双向/循环)", "线性表应用"],
    },
    "栈和队列": {
        "id": "ds_stack", "chapter": 2, "prerequisites": ["线性表"],
        "topics": ["栈(LIFO)", "队列(FIFO)", "循环队列", "栈和队列的应用"],
    },
    "串": {
        "id": "ds_string", "chapter": 3, "prerequisites": ["线性表"],
        "topics": ["串的基本概念", "朴素匹配", "KMP算法", "next数组"],
    },
    "树与二叉树": {
        "id": "ds_tree", "chapter": 4, "prerequisites": ["线性表"],
        "topics": ["树的概念", "二叉树性质", "遍历(先/中/后/层)", "BST", "AVL", "哈夫曼树"],
    },
    "图": {
        "id": "ds_graph", "chapter": 5, "prerequisites": ["树与二叉树"],
        "topics": ["图的定义与存储", "DFS/BFS", "最小生成树(Prim/Kruskal)", "最短路径(Dijkstra/Floyd)", "拓扑排序与关键路径"],
    },
    "查找": {
        "id": "ds_search", "chapter": 6, "prerequisites": ["树与二叉树"],
        "topics": ["顺序/折半查找", "BST与AVL", "B树/B+树", "哈希表"],
    },
    "排序": {
        "id": "ds_sort", "chapter": 7, "prerequisites": ["线性表"],
        "topics": ["插入排序(直接/折半/希尔)", "交换排序(冒泡/快排)", "选择排序(简单选择/堆)", "归并排序", "基数排序", "排序算法比较"],
    },
}

