import{a as H,b as n,g as t,t as l,F as O,h as T,f as h,p as J,n as Z,A as tt,r as i,c as et,j as o,i as st,o as ot,m as $,v as z,q as I,L as V,y as nt,e as at,s as ct}from"./vue-vendor-DQUnlWCz.js";import{c as Y,a as P,f as S}from"./index-Dj-4vXEs.js";const lt={class:"pdf-reader"},it={class:"pdf-sidebar"},rt={class:"pdf-sidebar-title"},dt={class:"pdf-chapter-list"},ut=["onClick"],pt={class:"pdf-chapter-num"},vt={class:"pdf-chapter-title"},ht={key:0,class:"pdf-chapter-header"},mt={class:"pdf-text"},_t={key:1,class:"pdf-empty"},xt=H({__name:"PdfReader",props:{textbookId:{},textbookName:{},chapters:{}},emits:["askAboutText"],setup(c,{emit:r}){const p=c,x=r,v=i(0),g=i(""),u=i(!1),_=i({x:0,y:0}),C=et(()=>p.chapters[v.value]||null);function A(m){const d=window.getSelection();if(!d||d.isCollapsed||!d.toString().trim()){u.value=!1;return}g.value=d.toString().trim(),_.value={x:m.clientX,y:m.clientY},u.value=!0}function w(){u.value=!1,g.value&&x("askAboutText",g.value)}function f(m){v.value=m,u.value=!1,window.getSelection()?.removeAllRanges()}return(m,d)=>(o(),n("div",lt,[t("div",it,[t("div",rt,l(c.textbookName),1),t("div",dt,[(o(!0),n(O,null,T(c.chapters,(b,k)=>(o(),n("button",{key:b.id,class:st(["pdf-chapter-item",{active:v.value===k}]),onClick:B=>f(k)},[t("span",pt,l(k+1),1),t("span",vt,l(b.title),1)],10,ut))),128))])]),t("div",{class:"pdf-content",onMouseup:A},[C.value?(o(),n("div",ht,[t("h2",null,l(C.value.title),1)])):h("",!0),t("div",mt,l(C.value?.content||"暂无内容"),1),C.value?h("",!0):(o(),n("div",_t,[...d[1]||(d[1]=[t("div",{class:"empty-icon"},null,-1),t("div",{class:"empty-text"},"选择章节开始阅读",-1)])]))],32),(o(),J(tt,{to:"body"},[u.value?(o(),n("div",{key:0,class:"selection-menu",style:Z({left:_.value.x+"px",top:_.value.y+"px"})},[t("button",{class:"selection-btn",onClick:w}," 问选中"),t("button",{class:"selection-btn",onClick:d[0]||(d[0]=b=>u.value=!1),"aria-label":"关闭选区操作菜单"})],4)):h("",!0)]))]))}}),gt=Y(xt,[["__scopeId","data-v-b70c4171"]]),D={id:"seed_cn",name:"计算机网络（第七版）",subject:"computer_network",created_at:"2026-07-20T00:00:00",status:"ok",chapter_count:7,total_chars:0,chapters:[{id:"cn_ch1",title:"第一章 概述",content:`计算机网络是互连的、自治的计算机集合。"互连"是指各计算机之间通过通信链路相互连接，"自治"是指各计算机没有主从关系。

互联网的组成：边缘部分（由主机组成，用户直接使用）和核心部分（由路由器组成，为边缘部分提供连通性）。

电路交换：通话前先建立连接，通话期间独占通信资源。报文交换：整个报文先存储再转发。分组交换：采用存储转发方式，将报文分割成较小的分组分别传输，是计算机网络的核心技术。

网络体系结构：OSI 七层模型（物理层、数据链路层、网络层、传输层、会话层、表示层、应用层），TCP/IP 四层模型（网络接口层、网际层、传输层、应用层）。五层协议体系结构综合了两者的优点。

性能指标：速率（bit/s）、带宽（Hz 或 bit/s）、吞吐量、时延（发送时延 + 传播时延 + 处理时延 + 排队时延）、利用率。

例题：在带宽为 1Mbps 的链路上，发送 1000Byte 的数据需要多少时间？（忽略传播时延）
解：发送时延 = 数据长度 / 带宽 = 1000×8 / 1×10^6 = 8ms。

例题：ping 命令使用的是什么协议？
解：ICMP 协议，用于测试网络连通性。`},{id:"cn_ch2",title:"第二章 物理层",content:`物理层考虑的是如何在连接各计算机的传输媒体上传输数据比特流，而不是指具体的传输媒体。

主要任务：确定与传输媒体接口有关的一些特性，包括机械特性、电气特性、功能特性和规程特性。

数据通信的基本模型：源系统（源点+发送器）→ 传输系统 → 目的系统（接收器+终点）。

通信方式：单向通信（单工）、双向交替通信（半双工）、双向同时通信（全双工）。

调制技术：基带调制（数字信号→数字信号，编码方式：NRZ、曼彻斯特、差分曼彻斯特）、带通调制（数字信号→模拟信号，方式：调幅ASK、调频FSK、调相PSK、正交调幅QAM）。

传输介质：双绞线（屏蔽STP/非屏蔽UTP）、同轴电缆、光纤（单模/多模）、无线（微波/红外/激光）。

信道复用技术：频分复用FDM、时分复用TDM（同步/统计）、波分复用WDM、码分复用CDM（CDMA码分多址）。`},{id:"cn_ch3",title:"第三章 数据链路层",content:`数据链路层使用的信道主要有两种：点对点信道和广播信道。

三个基本问题：封装成帧、透明传输、差错检测。封装成帧是在一段数据前后分别添加首部和尾部构成帧。透明传输是指不管什么数据都能原样传输。差错检测常用循环冗余检验（CRC）。

PPP 协议：点对点协议，是用户计算机与 ISP 通信时使用的数据链路层协议。PPP 应满足：简单、封装成帧、透明性、多种网络层协议、多种类型链路、差错检测、连接状态、最大传送单元、网络层地址协商、数据压缩协商。

CSMA/CD 协议：载波监听多点接入/碰撞检测，用于总线型以太网。"多点接入"说明是总线型网络，"载波监听"是发送前先检测信道，"碰撞检测"是边发送边检测。使用截断二进制指数退避算法。

以太网 MAC 帧：目的地址（6B）+ 源地址（6B）+ 类型（2B）+ 数据（46~1500B）+ FCS（4B）。

VLAN：虚拟局域网，由 IEEE 802.1Q 标准定义，通过在 MAC 帧中插入 4 字节的 VLAN 标签来划分虚拟网络，限制广播域。`},{id:"cn_ch4",title:"第四章 网络层",content:`网络层负责将分组从源主机发送到目的主机，提供主机间的逻辑通信。主要功能：路由选择、分组转发、拥塞控制、网际互连。

IP 数据报格式：版本（4bit）+ 首部长度（4bit）+ 区分服务（8bit）+ 总长度（16bit）+ 标识（16bit）+ 标志（3bit）+ 片偏移（13bit）+ 生存时间TTL（8bit）+ 协议（8bit）+ 首部校验和（16bit）+ 源IP地址（32bit）+ 目的IP地址（32bit）+ 选项+填充。

IP 地址分类：A类（1.0.0.0~127.255.255.255）、B类（128.0.0.0~191.255.255.255）、C类（192.0.0.0~223.255.255.255）、D类（组播）、E类（保留）。

子网划分：从主机号借用若干位作为子网号。子网掩码：IP 地址中网络号和子网号对应的位全为1，主机号全为0。

CIDR（无分类域间路由）：IP 地址 = 网络前缀 + 主机号，用斜线表示法如 192.168.0.0/24。路由聚合：将多个前缀合并为一个前缀。

ARP 协议：地址解析协议，将 IP 地址解析为 MAC 地址。

ICMP 协议：互联网控制报文协议，用于差错报告和网络诊断（ping、traceroute）。

路由协议：RIP（距离向量，跳数≤15）、OSPF（链路状态，Dijkstra 算法）、BGP（路径向量，边界网关协议）。

NAT：网络地址转换，将私有IP映射为公网IP。私有地址：10.0.0.0/8、172.16.0.0/12、192.168.0.0/16。

IPv6：128位地址空间，冒号十六进制表示，取消了校验和字段。`},{id:"cn_ch5",title:"第五章 运输层",content:`运输层提供进程间的逻辑通信（端到端），网络层提供主机间的逻辑通信（点到点）。

UDP：用户数据报协议，无连接、不可靠、面向报文、无拥塞控制、首部开销小（8B）。适合实时应用、DNS、SNMP 等。

TCP：传输控制协议，面向连接、可靠传输、面向字节流、全双工通信、首部开销大（20B）。

TCP 报文段首部：源端口（2B）+ 目的端口（2B）+ 序号（4B）+ 确认号（4B）+ 数据偏移（4bit）+ 保留（6bit）+ 标志位（6bit: URG/ACK/PSH/RST/SYN/FIN）+ 窗口（2B）+ 检验和（2B）+ 紧急指针（2B）+ 选项。

TCP 三次握手：客户端发送 SYN（SYN=1, seq=x）→ 服务器返回 SYN+ACK（SYN=1, ACK=1, seq=y, ack=x+1）→ 客户端发送 ACK（ACK=1, seq=x+1, ack=y+1）。

TCP 四次挥手：客户端发送 FIN → 服务器返回 ACK → 服务器发送 FIN → 客户端返回 ACK，等待 2MSL 后关闭。

可靠传输：序号、确认、重传。流量控制：利用滑动窗口机制让发送方速率匹配接收方。拥塞控制：慢开始、拥塞避免、快重传、快恢复。

例题：TCP 三次握手中，为什么客户端最后还要发送一次 ACK？
解：防止已失效的连接请求报文段突然传到服务器，导致服务器误以为客户端要建立连接而浪费资源。

例题：TCP 拥塞控制中，慢开始阶段窗口如何增长？
解：每收到一个 ACK，拥塞窗口 cwnd 增加 1 个 MSS，呈指数增长。当 cwnd 达到慢开始门限 ssthresh 时，进入拥塞避免阶段，改为线性增长（每 RTT 增加 1 个 MSS）。`},{id:"cn_ch6",title:"第六章 应用层",content:`应用层是体系结构中的最高层，直接为用户的应用进程提供服务。

DNS：域名系统，将域名解析为 IP 地址。层次结构：根域名服务器 → 顶级域名服务器 → 权威域名服务器。查询方式：递归查询、迭代查询。

HTTP：超文本传输协议，无状态、面向事务。持久连接（Keep-Alive）和非持久连接。HTTP/1.1 支持流水线。HTTP 报文：请求报文（GET/POST/PUT/DELETE）和响应报文（状态码：1xx 信息、2xx 成功、3xx 重定向、4xx 客户端错误、5xx 服务器错误）。

FTP：文件传输协议，使用两个 TCP 连接（控制连接 21 端口、数据连接 20 端口）。

SMTP：简单邮件传输协议，使用 TCP 25 端口。POP3（110 端口）和 IMAP（143 端口）用于接收邮件。

DHCP：动态主机配置协议，使用 UDP 67/68 端口，自动分配 IP 地址。

SNMP：简单网络管理协议，用于网络设备管理。`},{id:"cn_ch7",title:"第七章 网络安全",content:`网络安全威胁：截获（被动攻击）、中断、篡改、伪造（主动攻击）。

对称密钥加密：加密和解密使用相同密钥。DES（56位密钥）、AES（128/192/256位密钥）。

非对称密钥加密：加密和解密使用不同密钥（公钥和私钥）。RSA、ECC。

数字签名：对消息的哈希摘要用私钥加密，保证完整性和不可否认性。

SSL/TLS：安全套接层，在传输层之上提供加密通信。

防火墙：包过滤防火墙、应用级网关（代理服务器）。

入侵检测系统（IDS）和入侵防御系统（IPS）。`}]};D.total_chars=D.chapters.reduce((c,r)=>c+r.content.length,0);const E={id:"seed_ds",name:"数据结构（C语言版）",subject:"data_structures",created_at:"2026-07-20T00:00:00",status:"ok",chapter_count:7,total_chars:0,chapters:[{id:"ds_ch1",title:"第一章 绪论",content:`数据结构是计算机存储、组织数据的方式。数据结构包括逻辑结构、存储结构和数据运算。

逻辑结构：集合结构（元素间无关系）、线性结构（一对一）、树形结构（一对多）、图形结构（多对多）。

存储结构：顺序存储（连续）、链式存储（指针）、索引存储（索引表）、散列存储（哈希）。

算法：解决问题的方法和步骤。算法特性：有穷性、确定性、可行性、输入、输出。

算法复杂度：时间复杂度（执行时间与问题规模的关系）和空间复杂度（存储空间与问题规模的关系）。大O表示法：O(1) < O(log n) < O(n) < O(n log n) < O(n²) < O(2ⁿ)。`},{id:"ds_ch2",title:"第二章 线性表",content:`线性表是具有相同数据类型的 n（n≥0）个数据元素的有限序列。特点：元素个数有限、元素具有逻辑顺序、元素都是数据元素、元素的数据类型相同、元素具有抽象性。

顺序表：用一组地址连续的存储单元依次存储线性表中的元素，逻辑上相邻的元素物理上也相邻。优点：随机访问、存储密度高。缺点：插入删除需要移动大量元素、需要连续存储空间。

单链表：通过指针将一组零散的内存块串联。每个节点包含数据域和指针域。优点：插入删除方便、不需要预分配空间。缺点：不能随机访问、需要额外指针空间。

双向链表：每个节点有前驱和后继两个指针，可以双向遍历。

循环链表：尾节点指针指向头节点，形成环。

时间复杂度对比：顺序表按序查找 O(n)、按位查找 O(1)；链表按序查找 O(n)、按位查找 O(n)。顺序表插入删除 O(n)，链表插入删除 O(1)（已知节点位置）。

例题：设计一个算法，将带头节点的单链表就地逆置。
解：采用头插法，依次将原链表的每个节点插入到新链表的最前面。时间 O(n)，空间 O(1)。

例题：顺序表和链表各有什么优缺点？分别适用于什么场景？
解：顺序表支持随机访问，插入删除效率低，适用于频繁查找、较少插入删除的场景。链表插入删除效率高，不支持随机访问，适用于频繁插入删除的场景。`},{id:"ds_ch3",title:"第三章 栈和队列",content:`栈：限定仅在表尾进行插入和删除操作的线性表。后进先出（LIFO）。栈顶是允许操作的一端，栈底是另一端。

基本操作：Push（入栈）、Pop（出栈）、Top（取栈顶元素）、IsEmpty（判空）。

应用：括号匹配、表达式求值（中缀转后缀）、函数调用、八皇后问题。

队列：只允许在一端（队尾）插入、另一端（队头）删除的线性表。先进先出（FIFO）。

循环队列：解决假溢出问题，通过模运算实现队列的头尾相连。队空条件：front==rear；队满条件：(rear+1)%maxSize==front。

双端队列：允许两端都可以进行入队和出队操作的队列。

应用：层次遍历、缓冲区、作业调度。`},{id:"ds_ch4",title:"第四章 串",content:`串：由零个或多个字符组成的有限序列。空串：长度为0的串。子串：串中任意连续字符组成的子序列。

串的基本操作：赋值、比较、求长度、连接、求子串、定位（模式匹配）。

朴素模式匹配：从主串的第一个字符开始依次与模式串比较，时间 O(n×m)。

KMP 算法：利用模式串的部分匹配信息，避免主串指针回溯。next 数组：记录模式串中当前位置之前的最长公共前后缀长度。时间 O(n+m)。

改进的 KMP（nextval）：解决 next 数组在连续相同字符时的冗余比较。`},{id:"ds_ch5",title:"第五章 树与二叉树",content:`树是 n（n≥0）个节点的有限集合。n=0 为空树。非空树有且仅有一个根节点，其余节点可分为若干互不相交的有限集合，每个集合本身又是一棵树（子树）。

二叉树：每个节点最多有两棵子树（左子树和右子树），子树有左右之分。满二叉树：所有分支节点都有左右子树，且叶子都在最底层。完全二叉树：按层序编号，编号为 i 的节点与满二叉树中编号 i 的节点位置相同。

二叉树性质：第 i 层最多 2^(i-1) 个节点；深度为 k 的二叉树最多 2^k - 1 个节点；n0 = n2 + 1；n 个节点的完全二叉树深度为 ⌊log₂n⌋ + 1。

遍历：先序遍历（根-左-右）、中序遍历（左-根-右）、后序遍历（左-右-根）、层序遍历（BFS）。

二叉排序树（BST）：左子树所有节点值 < 根 < 右子树所有节点值。中序遍历得到有序序列。查找 O(log n)~O(n)。

平衡二叉树（AVL）：左右子树高度差不超过 1。查找 O(log n)。旋转：LL、RR、LR、RL 四种调整。

哈夫曼树：带权路径长度最小的二叉树。构造：每次选两个权值最小的树合并。哈夫曼编码：左 0 右 1，前缀编码。

例题：已知二叉树先序序列 ABDECF，中序序列 DBEAFC，求后序序列。
解：先序第一个 A 是根，中序中 A 左边 DBE 是左子树，右边 FC 是右子树。左子树先序 BDE，中序 DBE，根为 B。递归可得后序：DEBFCA。

例题：完全二叉树有 1001 个节点，叶子节点数是多少？
解：n0 = n2 + 1，n = n0 + n1 + n2 = 2n2 + n1 + 1。完全二叉树 n1 为 0 或 1，代入得 n2 = 500，n0 = 501。`},{id:"ds_ch6",title:"第六章 图",content:`图：由顶点集 V 和边集 E 组成，记为 G=(V,E)。有向图：边有方向。无向图：边无方向。

基本概念：完全图、连通图/强连通图、生成树、度/入度/出度、权、网、路径长度、回路。

存储结构：邻接矩阵（顺序存储，O(n²)空间）、邻接表（链式存储，O(n+e)空间）、十字链表、邻接多重表。

遍历：深度优先搜索（DFS，栈/递归）和广度优先搜索（BFS，队列）。

最小生成树：Prim 算法（选顶点，O(n²)，适合稠密图）和 Kruskal 算法（选边，O(e log e)，适合稀疏图）。

最短路径：Dijkstra 算法（单源，O(n²)）和 Floyd 算法（多源，O(n³)）。

拓扑排序：AOV 网（顶点表示活动），有向无环图才有拓扑序列。

关键路径：AOE 网（边表示活动），最早发生时间、最迟发生时间、时间余量（关键路径为0）。`},{id:"ds_ch7",title:"第七章 查找与排序",content:`查找：在数据集合中寻找满足某种条件的数据元素的过程。

顺序查找：从头到尾逐个比较。时间 O(n)。

折半查找（二分查找）：仅适用于有序顺序表。每次与中间元素比较，缩小一半范围。时间 O(log n)。

分块查找：将表分成若干块，块间有序、块内无序。先块间折半查找，再块内顺序查找。

B 树：多路平衡查找树。m 阶 B 树每个节点最多 m 棵子树、最少 ⌈m/2⌉ 棵子树。适合磁盘等外部存储。

哈希表：通过哈希函数将关键字映射到存储位置。冲突解决方法：开放定址法（线性探测、平方探测）、链地址法（拉链法）。装填因子 α = 记录数/表长，α 越大冲突概率越高。

排序：将无序序列变为有序序列。

插入排序：直接插入 O(n²)、折半插入 O(n²)、希尔排序 O(n^1.3)。

交换排序：冒泡排序 O(n²)、快速排序 O(n log n) 平均。

选择排序：简单选择 O(n²)、堆排序 O(n log n)。

归并排序：O(n log n)，稳定。

基数排序：O(d(n+r))，稳定，非比较排序。

稳定性：相同关键字排序后相对位置不变即为稳定。直接插入、冒泡、归并、基数是稳定的。`}]};E.total_chars=E.chapters.reduce((c,r)=>c+r.content.length,0);const R={id:"seed_co",name:"计算机组成原理",subject:"computer_organization",created_at:"2026-07-20T00:00:00",status:"ok",chapter_count:6,total_chars:0,chapters:[{id:"co_ch1",title:"第一章 概述",content:`计算机组成原理是研究计算机硬件系统各组成部分的结构、功能及相互关系的学科。

计算机发展历程：第一代电子管、第二代晶体管、第三代集成电路、第四代大规模集成电路、第五代超大规模集成电路。

冯·诺依曼结构：存储程序、指令和数据以二进制形式存储、指令由操作码和地址码组成、指令按顺序执行。五大部件：存储器、运算器、控制器、输入设备、输出设备。

计算机性能指标：CPU主频、CPI（每条指令周期数）、IPS（每秒指令数）、FLOPS（每秒浮点运算次数）、MIPS（每秒百万条指令）。

性能公式：CPU执行时间 = 指令数 × CPI × 时钟周期。`},{id:"co_ch2",title:"第二章 数据表示",content:`数制转换：十进制与其他进制互转。

真值与机器数：真值是带符号的二进制数，机器数是计算机中表示的二进制数（符号位0正1负）。

原码：符号位 + 绝对值。反码：正数同原码，负数符号位不变其余位取反。补码：正数同原码，负数为反码+1。移码：补码的符号位取反，用于浮点数阶码。

定点数：小数点位置固定。定点小数（纯小数）和定点整数。

浮点数：N = 2^E × M。IEEE 754标准：单精度（32位：1位符号+8位阶码+23位尾数）、双精度（64位：1位符号+11位阶码+52位尾数）。

运算：加法、减法、乘法（原码一位乘、补码Booth算法）、除法（原码恢复余数、补码加减交替）。

ALU：算术逻辑单元，核心部件，支持算术运算和逻辑运算。`},{id:"co_ch3",title:"第三章 存储系统",content:`存储器层次结构：寄存器 → Cache → 主存 → 辅存。从上到下速度递减、容量递增、每位价格递减。

SRAM：静态随机存取存储器，用触发器存储信息，速度快、不需要刷新、集成度低、功耗大。用于 Cache。

DRAM：动态随机存取存储器，用电容存储信息，需要定期刷新（一般为 2ms）、集成度高、功耗低。用于主存。刷新方式：集中刷新、分散刷新、异步刷新。

ROM：只读存储器。PROM（可编程）、EPROM（可擦除）、EEPROM（电可擦除）、Flash（闪存）。

存储器扩展：位扩展（增加字长）、字扩展（增加容量）、字位同时扩展。

Cache：高速缓冲存储器，解决 CPU 和主存速度不匹配问题。命中率 h = 命中次数/总访问次数。平均访问时间 t = h·tc + (1-h)·tm。

Cache 映射方式：
1. 直接映射：主存块只能映射到固定的 Cache 行。地址 = 标记 + 行号 + 块内地址。简单但冲突率高。
2. 全相联映射：主存块可映射到任意 Cache 行。冲突率低但比较器复杂。
3. 组相联映射：主存块映射到固定组的任意行。直接映射和全相联的折中。

替换算法：随机（RAND）、先进先出（FIFO）、最近最少使用（LRU）、最不经常使用（LFU）。

Cache 写策略：全写法（写直达）、写回法。写不命中处理：写分配法、非写分配法。`},{id:"co_ch4",title:"第四章 指令系统与CPU",content:`指令系统：计算机所能执行的全部指令的集合。指令格式 = 操作码 + 地址码。

寻址方式：确定操作数或指令地址的方法。
1. 立即寻址：操作数直接在指令中。
2. 直接寻址：地址码给出操作数的有效地址。
3. 间接寻址：地址码给出操作数地址的地址。
4. 寄存器寻址：操作数在寄存器中。
5. 寄存器间接寻址：寄存器中存操作数地址。
6. 基址寻址：基址寄存器 + 偏移量。
7. 变址寻址：变址寄存器 + 偏移量。
8. 相对寻址：PC + 偏移量。

CISC vs RISC：
CISC（复杂指令集）：指令丰富、长度可变、寻址方式多、寄存器少。x86 为代表。
RISC（精简指令集）：指令精简、长度固定、寻址方式少、寄存器多、流水线优化。ARM/MIPS 为代表。

CPU 数据通路：指令部件（取指、译码）、算术逻辑部件（ALU）、寄存器组、CPU 内部总线。

指令流水线：将指令执行分为多个阶段（如取指、译码、执行、访存、写回），各阶段并行工作。理想情况下吞吐率提升为流水段数倍。

流水线冲突（冒险）：
1. 结构冲突：硬件资源竞争。解决：资源重复。
2. 数据冲突：指令间存在数据依赖。解决：转发（旁路）、插入气泡（停顿）。
3. 控制冲突：分支指令改变 PC。解决：分支预测、延迟分支。

控制器：硬布线控制器（速度快、修改难）和微程序控制器（速度慢、修改易、可扩展）。`},{id:"co_ch5",title:"第五章 总线",content:`总线：一组能为多个部件分时共享的公共信息传送线路。

总线分类：片内总线（芯片内部）、系统总线（数据总线、地址总线、控制总线）、通信总线（外部设备）。

系统总线：数据总线（双向传输数据）、地址总线（单向传输地址）、控制总线（传输控制信号）。

总线仲裁：集中仲裁（链式查询、计数器查询、独立请求）和分布仲裁。

总线标准：ISA、PCI、AGP、PCIe、USB、SATA。

总线性能指标：宽度（位数）、频率（MHz）、带宽（MB/s）。带宽 = 宽度 × 频率 / 8。`},{id:"co_ch6",title:"第六章 输入输出系统",content:`I/O 接口：CPU 与外部设备之间的缓冲部件，实现数据缓冲、信号转换、设备选择、中断管理等功能。

I/O 编址方式：统一编址（内存映射I/O）和独立编址（专用I/O指令）。

I/O 控制方式：
1. 程序查询方式：CPU 轮询设备状态，效率低。
2. 中断方式：设备主动通知 CPU，效率高。
3. DMA 方式：直接内存访问，无需 CPU 干预。
4. 通道方式：专用 I/O 处理器。

中断：CPU 暂停当前程序，转去执行中断服务程序，执行完后再返回原程序。中断优先级：多个中断同时发生时，按优先级顺序处理。中断屏蔽：允许或禁止某些中断。

DMA：直接存储器访问。DMA 控制器接管总线控制权，在内存和外设间直接传输数据。工作方式：CPU 停止、周期挪用、交替访问。`}]};R.total_chars=R.chapters.reduce((c,r)=>c+r.content.length,0);const L={id:"seed_os",name:"计算机操作系统",subject:"operating_system",created_at:"2026-07-20T00:00:00",status:"ok",chapter_count:5,total_chars:0,chapters:[{id:"os_ch1",title:"第一章 操作系统概述",content:`操作系统是控制和管理计算机硬件和软件资源、合理组织计算机工作流程、方便用户使用的程序的集合。

操作系统的特征：并发（多任务同时执行）、共享（资源互斥共享/同时共享）、虚拟（将物理资源映射为逻辑资源）、异步（程序执行的不确定性）。

操作系统的功能：处理机管理（进程调度）、存储器管理（内存分配）、文件管理（文件系统）、设备管理（I/O控制）、用户接口（命令/程序）。

操作系统的发展：手工操作阶段（独占、人机速度矛盾）、批处理阶段（单道/多道）、分时系统（时间片轮转）、实时系统（及时响应）、网络/分布式系统。

操作系统类型：批处理（效率高、交互差）、分时（交互好、公平）、实时（及时响应、可靠性高）、嵌入式（专用、资源受限）、分布式（多机协作）。

中断与异常：中断（外部事件，异步）、异常（内部事件，同步）。中断处理流程：关中断→保存断点→中断服务程序→恢复断点→开中断。`},{id:"os_ch2",title:"第二章 进程管理",content:`进程：程序在数据集合上的一次执行过程，是系统进行资源分配和调度的基本单位。进程是动态的，程序是静态的。

进程状态：就绪、运行、阻塞。基本转换：就绪→运行（调度）、运行→就绪（时间片到）、运行→阻塞（等待资源）、阻塞→就绪（资源到位）。

进程控制块（PCB）：进程存在的唯一标志，包含进程标识、状态、寄存器、调度信息、资源清单等。组织方式：链接方式、索引方式。

进程与线程：线程是进程中的一个实体，是 CPU 调度和分派的基本单位。进程是资源分配的基本单位，线程是独立调度的基本单位。同一进程的线程共享资源。用户级线程（内核不可见）、内核级线程。

进程同步：协调多个进程的执行次序。临界区互斥的四大原则：空闲让进、忙则等待、有限等待、让权等待。

信号量机制：整型信号量、记录型信号量（P/V 操作）。P 操作（wait）：申请资源，S=S-1，若 S<0 则阻塞。V 操作（signal）：释放资源，S=S+1，若 S≤0 唤醒一个进程。

经典同步问题：生产者-消费者（empty 和 full 信号量）、读者-写者、哲学家进餐。

死锁：多个进程因竞争资源而造成僵局。产生条件：互斥、请求和保持、不剥夺、环路等待。处理策略：预防（破坏必要条件）、避免（银行家算法）、检测与解除、鸵鸟策略。

调度算法：FCFS（先来先服务）、SJF（短作业优先）、优先级调度、时间片轮转、多级反馈队列。`},{id:"os_ch3",title:"第三章 内存管理",content:`内存管理功能：内存分配与回收、地址变换、内存扩充、存储共享与保护。

连续分配方式：单一连续分配、固定分区分配（内部碎片）、动态分区分配（外部碎片）。动态分区分配算法：首次适应（FF）、最佳适应（BF）、最坏适应（WF）、邻近适应（NF）。

分页管理：将进程的逻辑地址空间分为若干页，物理空间分为若干块（页框/帧）。页表记录页号→块号映射。地址 = 页号 + 页内偏移。逻辑地址到物理地址转换：通过页表查到块号，块号×块大小+偏移。

TLB（快表）：页表的高速缓存（相联存储器），减少访存次数。有效访存时间 EAT = (h·TLB时间) + (1-h)·(TLB时间+访存时间)。

分段管理：按逻辑关系分段，每段有自己的段表项（段号→段起始地址+段长）。段页式：先分段再分页。

虚拟内存：基于局部性原理，将部分内容装入内存即可运行。请求分页：在分页基础上增加请求调页和页面置换功能。

页面置换算法：
1. OPT（最佳）：淘汰未来最长时间不被访问的页面。理论最优，不可实现。
2. FIFO（先进先出）：淘汰最先进入的页面。可能 Belady 异常。
3. LRU（最近最久未使用）：淘汰最长时间未被访问的页面。性能好但开销大。
4. CLOCK（时钟）：近似 LRU，利用访问位循环扫描。改进型 CLOCK 同时考虑访问位和修改位。

抖动（颠簸）：频繁缺页导致 CPU 利用率急剧下降。原因：分配页面数不足。工作集：某段时间内进程访问的页面集合。`},{id:"os_ch4",title:"第四章 文件系统",content:`文件：具有文件名的一组相关信息的集合。文件系统：操作系统中负责管理和存储文件的模块。

文件逻辑结构：有结构文件（记录式）、无结构文件（流式）。文件物理结构：连续分配、链接分配（隐式链接、显式链接 FAT）、索引分配。

目录结构：单级目录、两级目录、树形目录、无环图目录。文件控制块（FCB）：文件名 + 属性（类型、大小、位置、创建时间、权限等）。

磁盘调度算法：
1. FCFS：按请求顺序服务。
2. SSTF（最短寻道时间优先）：选择离当前磁头最近的请求。可能饥饿。
3. SCAN（电梯调度）：磁头在两端往返，沿途服务请求。
4. C-SCAN（循环扫描）：单向移动服务请求，到端后快速返回另一端。
5. LOOK / C-LOOK：SCAN/C-SCAN 的改进，磁头只移动到最远请求处。

磁盘访问时间 = 寻道时间 + 旋转延迟 + 传输时间。寻道时间是主要优化目标。

空闲空间管理：空闲表法、空闲链表法、位示图法、成组链接法。`},{id:"os_ch5",title:"第五章 输入输出管理",content:`I/O 设备分类：按传输速率（低速、中速、高速）、按信息交换单位（字符设备、块设备）、按共享属性（独占、共享、虚拟）。

I/O 控制方式：程序直接控制、中断驱动、DMA、通道控制。

缓冲技术：解决 CPU 与 I/O 设备速度不匹配问题。单缓冲、双缓冲、循环缓冲、缓冲池。

SPOOLing 技术：将独占设备改造为共享设备。输入井/输出井、输入/输出进程。

设备分配：静态分配（进程独占）、动态分配（进程使用完即释放）。设备分配数据结构：设备控制表（DCT）、控制器控制表（COCT）、通道控制表（CHCT）、系统设备表（SDT）。

设备独立性：用户程序使用逻辑设备名，系统将逻辑设备名映射为物理设备名。

虚拟设备：通过 SPOOLing 技术将独占设备虚拟为共享设备。`}]};L.total_chars=L.chapters.reduce((c,r)=>c+r.content.length,0);const G=[D,E,R,L],j=G.map(c=>({id:c.id,name:c.name,subject:c.subject,chapter_count:c.chapter_count,total_chars:c.total_chars,created_at:c.created_at}));function q(c){return G.find(r=>r.id===c)}function Ct(c){return c.startsWith("seed_")}const bt={class:"page-section",style:{"max-width":"100%",padding:"1rem"}},yt={class:"section-header",style:{"max-width":"75rem",margin:"0 auto 1rem"}},Pt={class:"section-actions"},ft={class:"search-input-wrap",style:{position:"relative",display:"flex","align-items":"center"}},kt={key:0,class:"memory-mini-strip",style:{display:"flex",gap:"8px","flex-wrap":"wrap","max-width":"75rem",margin:"0 auto 12px","font-size":"12px"}},St={key:1,class:"textbook-grid",style:{"max-width":"75rem",margin:"0 auto"}},Ot={class:"rag-stats-card",style:{"grid-column":"1/-1",display:"flex","align-items":"center",gap:"1rem",padding:"1rem",background:"var(--color-surface)",border:"1px solid var(--color-border)","border-radius":"12px","margin-bottom":"8px"}},Tt={style:{flex:"1"}},At={style:{"font-size":"0.875rem",color:"var(--color-text-2)"}},wt={style:{color:"var(--accent-primary)"}},It={style:{display:"flex",gap:"0.5rem","align-items":"center"}},Bt=["disabled"],Mt={key:0,style:{"grid-column":"1/-1","margin-bottom":"12px"}},Ft={style:{"font-size":"0.875rem","font-weight":"600","margin-bottom":"8px",color:"var(--color-text-2)"}},Dt={style:{"font-size":"0.75rem",color:"var(--accent-primary)","font-weight":"600","margin-bottom":"2px"}},Et={style:{"font-size":"0.8125rem",color:"var(--color-text-2)","line-height":"1.5"}},Rt={style:{"font-size":"0.6875rem",color:"var(--color-text-3)","margin-top":"4px"}},Lt=["aria-label","onClick","onKeydown"],Kt={class:"textbook-name"},Ut={class:"textbook-meta"},Nt={key:1,class:"empty-state",style:{"grid-column":"1/-1","text-align":"center",padding:"60px"}},$t={key:2,class:"search-panel",style:{"max-width":"75rem",margin:"0 auto 1rem"}},zt={class:"search-header"},Vt={class:"search-title"},jt={class:"search-source"},qt={class:"search-content"},Ht={key:0,class:"search-empty"},Yt={key:3,class:"ask-panel",style:{"max-width":"75rem",margin:"0 auto 1rem"}},Gt={class:"ask-selected"},Qt={key:0,class:"ask-loading"},Wt={key:1,class:"ask-answer",style:{"white-space":"pre-wrap"}},Xt={key:4,style:{"max-width":"75rem",margin:"0 auto"}},Jt={class:"back-row",style:{"margin-bottom":"8px"}},Zt={style:{"margin-left":"12px","font-size":"16px","font-weight":"600",color:"var(--color-text)"}},te=H({__name:"KnowledgeBaseView",setup(c){ct();const r=i(j),p=i(null),x=i(""),v=i([]),g=i(!1),u=i(""),_=i(!1),C=i(""),A=i(!1),w=i({total_docs:0}),f=i([]),m=i(""),d=i(!1);ot(async()=>{A.value=!0;try{const[a,e]=await Promise.all([P.get("/knowledge-base/textbooks"),P.get("/rag/status")]),s=a.textbooks||[];s.length>0&&(r.value=s),w.value={total_docs:e.total_docs||0}}catch(a){console.warn(S(a,"加载数据失败"))}finally{A.value=!1}k()});const b=i(null);async function k(){try{const a=await P.get("/memory/overview");a?.status==="ok"&&(b.value=a)}catch{}}async function B(){if(m.value.trim()){d.value=!0;try{const a=await P.post("/rag/search",{query:m.value,top_k:20});f.value=a.results||[]}catch(a){console.warn(S(a,"搜索知识库失败"))}finally{d.value=!1}}}async function M(a){if(Ct(a)){const e=q(a);p.value=e||null;return}try{const e=await P.get(`/knowledge-base/textbook/${a}`);p.value=e.textbook||null}catch(e){console.warn(S(e,"加载教材失败"))}}async function Q(){if(x.value.trim()){g.value=!0;try{const a=await P.post("/knowledge-base/search",{query:x.value});v.value=a.results||[],v.value.length===0&&K()}catch(a){console.warn(S(a,"搜索失败")),K()}}}function K(){const a=x.value.trim().toLowerCase(),e=[];for(const s of j){const y=q(s.id);if(y)for(const F of y.chapters){const U=F.content.toLowerCase().indexOf(a);if(U>=0){const N=Math.max(0,U-40),X=F.content.slice(N,N+200).replace(/\n/g," ");e.push({source:`${s.name} · ${F.title}`,content:"..."+X+"..."})}}}v.value=e.slice(0,10)}async function W(a){C.value=a,u.value="",_.value=!0;try{const e=await P.post("/knowledge-base/ask",{selected_text:a,question:"请解释这段内容的含义"});u.value=e.answer||""}catch(e){u.value=S(e,"提问失败，请稍后重试")}_.value=!1}return(a,e)=>(o(),n("div",bt,[t("div",yt,[e[4]||(e[4]=t("div",{class:"section-title-group"},[t("div",null,[t("div",{class:"section-title"}," 课程知识库"),t("div",{class:"section-desc"},"读原文 · 问选中 · 回答有出处")])],-1)),t("div",Pt,[t("div",ft,[$(t("input",{"onUpdate:modelValue":e[0]||(e[0]=s=>x.value=s),class:"search-input",placeholder:"搜索教材内容...",onKeyup:I(Q,["enter"]),style:{padding:"8px 14px",border:"1px solid var(--color-border)","border-radius":"8px",background:"var(--color-surface-2)",color:"var(--color-text)","font-size":"14px",width:"250px"}},null,544),[[z,x.value]])])])]),b.value?.weak_points?.length?(o(),n("div",kt,[e[5]||(e[5]=t("span",{style:{padding:"3px 10px","border-radius":"12px",background:"var(--accent-primary-10)",color:"var(--accent-primary)"}}," 记忆薄弱点:",-1)),(o(!0),n(O,null,T(b.value.weak_points.slice(0,6),s=>(o(),n("span",{key:s,style:{padding:"3px 10px","border-radius":"12px",background:"rgba(239,68,68,0.12)",color:"var(--accent-danger)"}},l(s),1))),128))])):h("",!0),p.value?h("",!0):(o(),n("div",St,[t("div",Ot,[e[9]||(e[9]=t("div",{style:{"font-size":"2rem"}},null,-1)),t("div",Tt,[e[8]||(e[8]=t("div",{style:{"font-size":"1rem","font-weight":"600",color:"var(--color-text)"}},"知识库文档",-1)),t("div",At,[e[6]||(e[6]=V("共 ",-1)),t("strong",wt,l(w.value.total_docs),1),e[7]||(e[7]=V(" 条知识文档，覆盖 408 四科核心知识点",-1))])]),t("div",It,[$(t("input",{"onUpdate:modelValue":e[1]||(e[1]=s=>m.value=s),placeholder:"搜索知识库...",onKeyup:I(B,["enter"]),style:{padding:"6px 10px","border-radius":"6px",border:"1px solid var(--color-border)",background:"var(--color-surface-2)",color:"var(--color-text)","font-size":"13px",width:"180px"}},null,544),[[z,m.value]]),t("button",{class:"btn btn-sm btn-soft",onClick:B,disabled:d.value},l(d.value?"搜索中...":"搜索"),9,Bt)])]),f.value.length>0?(o(),n("div",Mt,[t("div",Ft,"搜索结果 ("+l(f.value.length)+")",1),(o(!0),n(O,null,T(f.value,(s,y)=>(o(),n("div",{key:y,class:"rag-result-item",style:{padding:"8px 12px","margin-bottom":"6px",background:"var(--color-surface)",border:"1px solid var(--color-border)","border-radius":"8px"}},[t("div",Dt,l(s.metadata&&s.metadata.subject||"未知科目")+" · "+l(s.metadata&&s.metadata.topic||""),1),t("div",Et,l((s.content||"").slice(0,200))+l((s.content||"").length>200?"...":""),1),t("div",Rt,"相关度: "+l(typeof s.distance=="number"&&isFinite(s.distance)?((1-s.distance)*100).toFixed(0)+"%":"—"),1)]))),128))])):h("",!0),(o(!0),n(O,null,T(r.value,s=>(o(),n("div",{key:s.id,class:"textbook-card",role:"button",tabindex:"0","aria-label":"教材: "+(s.name||s.id),onClick:y=>M(s.id),onKeydown:[I(y=>M(s.id),["enter"]),I(at(y=>M(s.id),["prevent"]),["space"])]},[e[10]||(e[10]=t("div",{class:"textbook-icon"},null,-1)),t("div",Kt,l(s.name),1),t("div",Ut,l(s.chapter_count)+" 章 · "+l((s.total_chars/1e3).toFixed(0))+"K 字",1)],40,Lt))),128)),r.value.length===0?(o(),n("div",Nt,[...e[11]||(e[11]=[t("div",{class:"empty-icon"},null,-1),t("div",{class:"empty-title"},"暂无教材",-1),t("div",{class:"empty-desc"},"请先上传 PDF 教材文件",-1)])])):h("",!0)])),g.value?(o(),n("div",$t,[t("div",zt,[t("span",Vt," 搜索结果 ("+l(v.value.length)+")",1),t("button",{class:"btn btn-sm btn-ghost",onClick:e[2]||(e[2]=s=>{g.value=!1,v.value=[]})},"关闭")]),(o(!0),n(O,null,T(v.value,s=>(o(),n("div",{key:s.source,class:"search-item"},[t("div",jt,l(s.source),1),t("div",qt,l(s.content),1)]))),128)),v.value.length===0?(o(),n("div",Ht,"无匹配结果")):h("",!0)])):h("",!0),u.value||_.value?(o(),n("div",Yt,[e[12]||(e[12]=t("div",{class:"ask-header"}," 对选中文本提问",-1)),t("div",Gt,"「"+l(C.value.slice(0,100))+"...」",1),_.value?(o(),n("div",Qt,"思考中...")):(o(),n("div",Wt,l(u.value),1))])):h("",!0),p.value?(o(),n("div",Xt,[t("div",Jt,[t("button",{class:"btn btn-ghost btn-sm",onClick:e[3]||(e[3]=s=>p.value=null)},"← 返回教材列表"),t("span",Zt,l(p.value.name),1)]),nt(gt,{"textbook-id":p.value.id,"textbook-name":p.value.name,chapters:p.value.chapters||[],onAskAboutText:W},null,8,["textbook-id","textbook-name","chapters"])])):h("",!0)]))}}),oe=Y(te,[["__scopeId","data-v-c416591c"]]);export{oe as default};
