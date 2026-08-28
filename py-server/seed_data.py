# ============================================================
# 种子数据 — 从 main.py 提取，供 API 路由和初始化共用
# ============================================================

SEED_KNOWLEDGE_CHUNKS = [
    # ---- 第1章 计算机网络概述 ----
    {"content": "计算机网络是互连的、自治的计算机集合。由资源子网和通信子网组成，核心功能是数据通信和资源共享。", "metadata": {"subject": "overview", "chapter": "概述", "type": "knowledge_point"}},
    {"content": "OSI七层模型：物理层→数据链路层→网络层→运输层→会话层→表示层→应用层。TCP/IP四层模型：网络接口层→网际层→运输层→应用层。", "metadata": {"subject": "overview", "chapter": "体系结构", "type": "knowledge_point"}},
    {"content": "分组交换采用存储转发机制，数据被分割成数据包（分组），每个分组独立选择路由，动态分配传输带宽，利用率高。", "metadata": {"subject": "overview", "chapter": "分组交换", "type": "knowledge_point"}},
    # ---- 第2章 物理层 ----
    {"content": "物理层的主要任务：确定与传输媒体的接口特性（机械特性、电气特性、功能特性、过程特性），实现比特流的传输。", "metadata": {"subject": "physical", "chapter": "基本概念", "type": "knowledge_point"}},
    {"content": "信道复用技术：频分复用FDM、时分复用TDM、波分复用WDM、码分复用CDM。其中CDMA是码分多址的简称。", "metadata": {"subject": "physical", "chapter": "信道复用", "type": "knowledge_point"}},
    {"content": "常用的传输媒体包括双绞线（最大100m）、同轴电缆、光纤（单模/多模）、无线传输（无线电波/微波/红外）。", "metadata": {"subject": "physical", "chapter": "传输媒体", "type": "knowledge_point"}},
    # ---- 第3章 数据链路层 ----
    {"content": "数据链路层使用MAC地址（48位，前24位为OUI厂商代码）。封装成帧、透明传输、差错检测是链路层的三个基本问题。", "metadata": {"subject": "datalink", "chapter": "基本概念", "type": "knowledge_point"}},
    {"content": "CSMA/CD协议：先听后发、边听边发、冲突停发、随机重发。截断二进制指数退避算法：退避时间=2^k×基本退避时间，k=min(重传次数,10)。", "metadata": {"subject": "datalink", "chapter": "CSMA/CD", "type": "knowledge_point"}},
    {"content": "以太网交换机工作在数据链路层，根据MAC地址转发。VLAN通过802.1Q标记实现虚拟局域网隔离，最大4096个VLAN。", "metadata": {"subject": "datalink", "chapter": "交换机与VLAN", "type": "knowledge_point"}},
    # ---- 第4章 网络层 ----
    {"content": "IP地址是32位二进制数（IPv4），通常用点分十进制表示。A类(0-127)、B类(128-191)、C类(192-223)是主分类。", "metadata": {"subject": "network", "chapter": "IP地址", "type": "knowledge_point"}},
    {"content": "子网划分：将IP地址的主机号部分借位作为子网号。子网掩码中1对应网络号+子网号，0对应主机号。CIDR无分类域间路由使用/前缀长度表示。", "metadata": {"subject": "network", "chapter": "子网划分", "type": "knowledge_point"}},
    {"content": "ARP协议：IP地址→MAC地址的映射。主机广播ARP请求，目标主机单播ARP响应。ARP缓存有生存期（通常20分钟）。", "metadata": {"subject": "network", "chapter": "ARP", "type": "knowledge_point"}},
    {"content": "路由选择协议：RIP（距离向量，跳数≤15，30s更新）、OSPF（链路状态，Dijkstra算法，区域划分）、BGP（路径向量，策略路由）。", "metadata": {"subject": "network", "chapter": "路由协议", "type": "knowledge_point"}},
    # ---- 第5章 运输层 ----
    {"content": "TCP是面向连接的可靠传输协议，提供全双工通信。UDP是无连接的不可靠传输协议，开销小，适合实时应用。", "metadata": {"subject": "transport", "chapter": "概述", "type": "knowledge_point"}},
    {"content": "TCP三次握手：①客户端→SYN(seq=x)→服务器 ②服务器→SYN+ACK(seq=y,ack=x+1)→客户端 ③客户端→ACK(seq=x+1,ack=y+1)→服务器。", "metadata": {"subject": "transport", "chapter": "TCP", "type": "knowledge_point"}},
    {"content": "TCP拥塞控制四种算法：慢启动（指数增长）、拥塞避免（线性增长/加法增大）、快重传（收到3个冗余ACK立即重传）、快恢复（减半阈值后进入拥塞避免）。", "metadata": {"subject": "transport", "chapter": "拥塞控制", "type": "knowledge_point"}},
    # ---- 第6章 应用层 ----
    {"content": "DNS域名解析：递归查询和迭代查询两种方式。顶级域名包括.com/.org/.cn等，二级域名如baidu.com。", "metadata": {"subject": "application", "chapter": "DNS", "type": "knowledge_point"}},
    {"content": "HTTP是超文本传输协议（80端口），无状态、无连接。HTTPS=HTTP+SSL/TLS（443端口），提供加密传输和身份认证。", "metadata": {"subject": "application", "chapter": "HTTP/HTTPS", "type": "knowledge_point"}},
    {"content": "FTP（文件传输协议，20/21端口）采用客户端/服务器模式，基于TCP。控制连接(21)和数据连接(20)分开。", "metadata": {"subject": "application", "chapter": "FTP", "type": "knowledge_point"}},
    {"content": "HTTP请求方法：GET（获取资源）、POST（提交数据）、PUT（更新资源）、DELETE（删除资源）、HEAD（获取首部）。状态码：1xx信息、2xx成功(200 OK)、3xx重定向(301永久/302临时)、4xx客户端错误(404 Not Found)、5xx服务器错误(500)。", "metadata": {"subject": "application", "chapter": "HTTP", "type": "knowledge_point"}},
    {"content": "HTTP首部字段：通用首部(Cache-Control/Connection)、请求首部(Host/User-Agent/Accept)、响应首部(Server/WWW-Authenticate)、实体首部(Content-Type/Content-Length/Content-Encoding)。", "metadata": {"subject": "application", "chapter": "HTTP", "type": "knowledge_point"}},
    {"content": "HTTP/2特性：二进制分帧、多路复用(一个TCP连接并行多个请求)、头部压缩(HPACK)、服务器推送。HTTP/3基于QUIC(UDP)，解决TCP队头阻塞问题。", "metadata": {"subject": "application", "chapter": "HTTP", "type": "knowledge_point"}},
    {"content": "DNS解析全过程：浏览器缓存→系统缓存→hosts文件→本地DNS服务器(递归)→根域名服务器→顶级域名服务器→权威域名服务器(迭代)→返回IP。默认端口53，基于UDP。", "metadata": {"subject": "application", "chapter": "DNS", "type": "knowledge_point"}},
    {"content": "DNS记录类型：A(IPv4地址)、AAAA(IPv6地址)、CNAME(别名)、MX(邮件交换)、NS(域名服务器)、TXT(文本记录)、PTR(反向解析)。TTL控制缓存生存时间。", "metadata": {"subject": "application", "chapter": "DNS", "type": "knowledge_point"}},
    {"content": "电子邮件系统三大组件：用户代理(UA)、邮件服务器、SMTP。发送用SMTP(25端口)，接收用POP3(110)或IMAP(143)。MIME扩展支持多媒体附件。", "metadata": {"subject": "application", "chapter": "电子邮件", "type": "knowledge_point"}},
    {"content": "DHCP动态主机配置协议(67/68端口，基于UDP)自动分配IP地址：DISCOVER→OFFER→REQUEST→ACK四步。租约期到了需续租(RENEW/REBIND)。", "metadata": {"subject": "application", "chapter": "DHCP", "type": "knowledge_point"}},
    {"content": "WWW万维网由URL(统一资源定位符)、HTTP(传输协议)、HTML(超文本标记语言)三部分组成。URL格式：协议://主机:端口/路径?查询#片段。", "metadata": {"subject": "application", "chapter": "WWW", "type": "knowledge_point"}},
    {"content": "P2P应用：BitTorrent(文件共享)、Skype(VoIP)。与C/S模式对比：P2P每个节点既是客户端又是服务器，扩展性好，但管理困难。CDN内容分发网络缓存就近服务。", "metadata": {"subject": "application", "chapter": "P2P/CDN", "type": "knowledge_point"}},
    # ---- 第7章 网络安全 ----
    {"content": "SSL/TLS协议在传输层之上提供安全服务：握手协议（身份认证+密钥协商）、记录协议（数据加密+完整性校验）。", "metadata": {"subject": "security", "chapter": "SSL/TLS", "type": "knowledge_point"}},
    {"content": "防火墙是位于网络边界的安全设备，通过规则集控制进出网络的流量。常见类型：包过滤防火墙、状态检测防火墙、应用代理防火墙。", "metadata": {"subject": "security", "chapter": "防火墙", "type": "knowledge_point"}},
    {"content": "常见的网络攻击类型：DDoS（分布式拒绝服务攻击）、SQL注入、XSS跨站脚本、中间人攻击MITM、ARP欺骗、DNS劫持。", "metadata": {"subject": "security", "chapter": "网络攻击", "type": "knowledge_point"}},
    {"content": "密码学两大类：对称加密(加密解密同一密钥，DES/AES/3DES，速度快适合大批量)、非对称加密(公钥加密私钥解密，RSA/ECC，安全但慢)。混合加密：用非对称交换对称密钥，再用对称加密数据。", "metadata": {"subject": "security", "chapter": "密码学", "type": "knowledge_point"}},
    {"content": "AES对称加密：分组长度128位，密钥长度128/192/256位，轮数10/12/14。取代DES(56位密钥已被暴力破解)。AES的SubBytes/ShiftRows/MixColumns/AddRoundKey四步轮变换。", "metadata": {"subject": "security", "chapter": "密码学", "type": "knowledge_point"}},
    {"content": "RSA非对称加密：基于大整数分解难题。密钥生成：选两素数p,q→n=pq,φ(n)=(p-1)(q-1)→选e→算d。公钥(n,e)，私钥(n,d)。加密c=m^e mod n，解密m=c^d mod n。", "metadata": {"subject": "security", "chapter": "密码学", "type": "knowledge_point"}},
    {"content": "报文摘要(哈希)：MD5(128位，已不安全)、SHA-1(160位，已弃用)、SHA-256(256位，推荐)。特性：固定长度输出、单向不可逆、抗碰撞。用于完整性校验和数字签名。", "metadata": {"subject": "security", "chapter": "报文摘要", "type": "knowledge_point"}},
    {"content": "数字签名：发送方用私钥对消息摘要加密，接收方用公钥验证。提供身份认证、完整性、不可否认性。签名=加密(哈希(消息),发送方私钥)。", "metadata": {"subject": "security", "chapter": "数字签名", "type": "knowledge_point"}},
    {"content": "数字证书：CA(证书颁发机构)用其私钥对(公钥+持有者身份+有效期)签名。证书链：根CA→中间CA→终端证书。浏览器信任根CA预置公钥，逐级验证签名。X.509标准。", "metadata": {"subject": "security", "chapter": "数字证书", "type": "knowledge_point"}},
    {"content": "TLS 1.3握手(1-RTT)：ClientHello(含支持的密码套件+key_share)→ServerHello(选定套件+key_share)→双方算出共享密钥→加密传输。相比TLS 1.2简化握手，废弃RSA密钥交换，强制前向安全。", "metadata": {"subject": "security", "chapter": "SSL/TLS", "type": "knowledge_point"}},
    {"content": "HTTPS证书验证流程：服务器返回证书链→浏览器验证证书签名(用CA公钥)→检查有效期/域名匹配/吊销列表(CRL/OCSP)→通过后用证书公钥加密预主密钥交换。", "metadata": {"subject": "security", "chapter": "SSL/TLS", "type": "knowledge_point"}},
    {"content": "DDoS攻击分类：流量型(SYN Flood/UDP Flood/ICMP Flood，耗尽带宽)、协议型(慢速攻击，耗尽连接)、应用层型(HTTP Flood/CC，伪装正常请求)。防御：流量清洗、CDN分散、限流。", "metadata": {"subject": "security", "chapter": "DDoS", "type": "knowledge_point"}},
    {"content": "SYN Flood攻击：攻击者发送大量伪造源IP的SYN包，服务器为每个分配资源并回复SYN+ACK等待ACK，半连接队列填满导致正常用户无法连接。防御：SYN Cookie(不分配资源直至ACK到达)、增大队列、防火墙过滤。", "metadata": {"subject": "security", "chapter": "DDoS", "type": "knowledge_point"}},
    {"content": "SQL注入：攻击者在输入中嵌入SQL片段，篡改查询逻辑。防御：参数化查询(预编译语句)、输入过滤、最小权限原则、WAF。分类：布尔盲注、时间盲注、联合查询、堆叠查询。", "metadata": {"subject": "security", "chapter": "Web攻击", "type": "knowledge_point"}},
    {"content": "XSS跨站脚本：攻击者注入恶意脚本到网页，受害者浏览器执行。分类：存储型(存数据库)、反射型(URL参数)、DOM型。窃取Cookie/会话劫持。防御：输出编码、CSP策略、HttpOnly Cookie。", "metadata": {"subject": "security", "chapter": "Web攻击", "type": "knowledge_point"}},
    {"content": "ARP欺骗：攻击者伪造ARP响应，将自己MAC与网关IP绑定，流量被中间人截获。防御：静态ARP绑定、DAI(动态ARP检测)、端口隔离。DNS劫持类似，伪造DNS响应。", "metadata": {"subject": "security", "chapter": "网络攻击", "type": "knowledge_point"}},
    {"content": "中间人攻击MITM：攻击者拦截并可能篡改双方通信。HTTPS通过证书体系防御，但用户忽略证书警告仍可被攻破。WiFi环境下伪造AP是常见MITM手段。", "metadata": {"subject": "security", "chapter": "网络攻击", "type": "knowledge_point"}},
    {"content": "IDS入侵检测系统：旁路部署，监测并报警。IPS入侵防御系统：串联部署，可阻断。检测方式：特征库匹配(已知攻击)、异常检测(偏离基线)。Snort/Suricata是开源IDS。", "metadata": {"subject": "security", "chapter": "IDS/IPS", "type": "knowledge_point"}},
    {"content": "VPN虚拟专用网：在公共网络上建立加密隧道。IPSec工作在网络层(AH认证/ESP加密/IKE密钥协商)，SSL VPN工作在应用层(浏览器即可)。保证机密性、完整性、身份认证。", "metadata": {"subject": "security", "chapter": "VPN", "type": "knowledge_point"}},
    {"content": "网络安全五要素：机密性(加密)、完整性(哈希/MAC)、可用性(抗DDoS)、可控性(访问控制)、不可否认性(数字签名)。CIA三要素为核心。", "metadata": {"subject": "security", "chapter": "安全基础", "type": "knowledge_point"}},
]

SEED_QUESTIONS = [
    # 计算机网络概述
    {"id": "q1", "subject": "overview", "chapter": "概述", "type": "choice", "difficulty": "easy",
     "text": "计算机网络最基本的功能是？",
     "options": ["数据通信和资源共享", "分布式处理", "负载均衡", "数据加密"], "answer": 0, "source": "计算机网络教程 第1章"},
    {"id": "q2", "subject": "overview", "chapter": "体系结构", "type": "choice", "difficulty": "medium",
     "text": "OSI参考模型从下到上的第三层是？",
     "options": ["数据链路层", "传输层", "网络层", "会话层"], "answer": 2, "source": "计算机网络教程 第1章"},
    # 数据链路层
    {"id": "q3", "subject": "datalink", "chapter": "CSMA/CD", "type": "choice", "difficulty": "medium",
     "text": "在CSMA/CD中，站点检测到冲突后，退避时间取决于？",
     "options": ["随机数", "重传次数", "帧长度", "传输速率"], "answer": 1, "source": "计算机网络教程 第3章"},
    {"id": "q4", "subject": "datalink", "chapter": "差错检测", "type": "fill", "difficulty": "hard",
     "text": "CRC校验中，若生成多项式为G(x)=x³+x+1，则其对应的二进制除数是______",
     "answer": "1011", "source": "计算机网络教程 第3章"},
    # 网络层
    {"id": "q5", "subject": "network", "chapter": "IP地址", "type": "choice", "difficulty": "medium",
     "text": "IP地址 192.168.1.0/24 可以分配多少个可用主机地址？",
     "options": ["254", "255", "256", "252"], "answer": 0, "source": "计算机网络教程 第4章"},
    {"id": "q6", "subject": "network", "chapter": "子网划分", "type": "compute", "difficulty": "hard",
     "text": "将 192.168.1.0/24 划分为4个等长子网，写出每个子网的网络地址、广播地址和可用主机范围。",
     "answer": "子网1: 192.168.1.0/26, 广播 192.168.1.63, 可用 1-62", "source": "计算机网络教程 第4章"},
    # 运输层
    {"id": "q7", "subject": "transport", "chapter": "TCP", "type": "choice", "difficulty": "easy",
     "text": "TCP三次握手中，客户端发送的第一个报文段的标志位是？",
     "options": ["ACK", "SYN", "SYN+ACK", "FIN"], "answer": 1, "source": "计算机网络教程 第5章"},
    {"id": "q8", "subject": "transport", "chapter": "拥塞控制", "type": "choice", "difficulty": "medium",
     "text": "TCP拥塞控制中，慢启动阶段的窗口增长方式是？",
     "options": ["线性增长", "指数增长", "对数增长", "固定值"], "answer": 1, "source": "计算机网络教程 第5章"},
    # 应用层
    {"id": "q9", "subject": "application", "chapter": "HTTP", "type": "choice", "difficulty": "easy",
     "text": "HTTP默认使用哪个端口？",
     "options": ["80", "443", "8080", "21"], "answer": 0, "source": "计算机网络教程 第6章"},
    {"id": "q10", "subject": "application", "chapter": "DNS", "type": "choice", "difficulty": "medium",
     "text": "DNS域名解析中，迭代查询的特点是？",
     "options": ["服务器直接返回结果", "服务器告知下一站地址由客户端自行查询", "服务器代替客户端继续查询", "使用广播查询"], "answer": 1, "source": "计算机网络教程 第6章"},
    # 网络安全
    {"id": "q11", "subject": "security", "chapter": "TLS", "type": "choice", "difficulty": "medium",
     "text": "HTTPS使用的安全协议栈是在HTTP下增加了哪一层？",
     "options": ["IPsec", "SSL/TLS", "SSH", "PGP"], "answer": 1, "source": "计算机网络教程 第7章"},
    {"id": "q12", "subject": "security", "chapter": "防火墙", "type": "choice", "difficulty": "easy",
     "text": "包过滤防火墙主要依据什么进行过滤？",
     "options": ["MAC地址", "IP地址和端口号", "应用层协议", "用户名"], "answer": 1, "source": "计算机网络教程 第7章"},
    {"id": "q13", "subject": "network", "chapter": "IP地址", "type": "compute", "difficulty": "hard",
     "text": "将 192.168.1.0/24 划分为4个等长子网，写出每个子网的网络地址和广播地址。",
     "answer": "192.168.1.0/26 ~ 192.168.1.192/26", "source": "计算机网络教程 第4章"},
    {"id": "q14", "subject": "transport", "chapter": "拥塞控制", "type": "fill", "difficulty": "medium",
     "text": "TCP拥塞控制中，拥塞避免阶段的窗口增长方式是______增长，而慢启动阶段是______增长。",
     "answer": "线性、指数", "source": "计算机网络教程 第5章"},
    # ── 应用层补充题 ──
    {"id": "q15", "subject": "application", "chapter": "HTTP", "type": "choice", "difficulty": "medium",
     "text": "HTTP状态码 301 表示？",
     "options": ["请求成功", "永久重定向", "临时重定向", "资源未找到"], "answer": 1, "source": "计算机网络教程 第6章"},
    {"id": "q16", "subject": "application", "chapter": "HTTP", "type": "choice", "difficulty": "medium",
     "text": "HTTP/2 相比 HTTP/1.1 的主要改进不包括？",
     "options": ["二进制分帧", "多路复用", "头部压缩", "基于UDP传输"], "answer": 3, "source": "计算机网络教程 第6章"},
    {"id": "q17", "subject": "application", "chapter": "DNS", "type": "choice", "difficulty": "medium",
     "text": "DNS中 MX 记录的作用是？",
     "options": ["IPv4地址", "IPv6地址", "邮件交换服务器", "别名指向"], "answer": 2, "source": "计算机网络教程 第6章"},
    {"id": "q18", "subject": "application", "chapter": "DNS", "type": "fill", "difficulty": "medium",
     "text": "DNS默认使用的端口是______，基于______协议传输。",
     "answer": "53、UDP", "source": "计算机网络教程 第6章"},
    {"id": "q19", "subject": "application", "chapter": "电子邮件", "type": "choice", "difficulty": "medium",
     "text": "用户从邮件服务器读取邮件常用的协议是？",
     "options": ["SMTP", "FTP", "POP3", "HTTP"], "answer": 2, "source": "计算机网络教程 第6章"},
    {"id": "q20", "subject": "application", "chapter": "DHCP", "type": "choice", "difficulty": "medium",
     "text": "DHCP分配IP地址的四步交互顺序是？",
     "options": ["DISCOVER→OFFER→REQUEST→ACK", "REQUEST→OFFER→DISCOVER→ACK", "DISCOVER→REQUEST→OFFER→ACK", "OFFER→DISCOVER→REQUEST→ACK"], "answer": 0, "source": "计算机网络教程 第6章"},
    {"id": "q21", "subject": "application", "chapter": "HTTP", "type": "choice", "difficulty": "easy",
     "text": "下列哪个HTTP方法用于向服务器提交数据？",
     "options": ["GET", "POST", "HEAD", "OPTIONS"], "answer": 1, "source": "计算机网络教程 第6章"},
    # ── 网络安全补充题 ──
    {"id": "q22", "subject": "security", "chapter": "密码学", "type": "choice", "difficulty": "medium",
     "text": "下列属于非对称加密算法的是？",
     "options": ["DES", "AES", "RSA", "3DES"], "answer": 2, "source": "计算机网络教程 第7章"},
    {"id": "q23", "subject": "security", "chapter": "密码学", "type": "choice", "difficulty": "medium",
     "text": "AES加密算法的分组长度是？",
     "options": ["64位", "128位", "256位", "512位"], "answer": 1, "source": "计算机网络教程 第7章"},
    {"id": "q24", "subject": "security", "chapter": "报文摘要", "type": "choice", "difficulty": "medium",
     "text": "下列哈希算法中目前推荐使用的是？",
     "options": ["MD5", "SHA-1", "SHA-256", "CRC32"], "answer": 2, "source": "计算机网络教程 第7章"},
    {"id": "q25", "subject": "security", "chapter": "数字签名", "type": "choice", "difficulty": "medium",
     "text": "数字签名发送方使用的是？",
     "options": ["自己的公钥", "自己的私钥", "接收方的公钥", "接收方的私钥"], "answer": 1, "source": "计算机网络教程 第7章"},
    {"id": "q26", "subject": "security", "chapter": "数字证书", "type": "choice", "difficulty": "hard",
     "text": "数字证书的签发者是？",
     "options": ["服务器自身", "用户自己", "CA证书颁发机构", "浏览器厂商"], "answer": 2, "source": "计算机网络教程 第7章"},
    {"id": "q27", "subject": "security", "chapter": "DDoS", "type": "choice", "difficulty": "medium",
     "text": "SYN Flood攻击利用的漏洞是？",
     "options": ["TCP握手时服务器分配半连接资源", "UDP无连接特性", "ICMP广播", "DNS递归查询"], "answer": 0, "source": "计算机网络教程 第7章"},
    {"id": "q28", "subject": "security", "chapter": "DDoS", "type": "choice", "difficulty": "medium",
     "text": "下列哪种技术能有效防御SYN Flood攻击？",
     "options": ["增大缓存", "SYN Cookie", "关闭防火墙", "使用UDP"], "answer": 1, "source": "计算机网络教程 第7章"},
    {"id": "q29", "subject": "security", "chapter": "Web攻击", "type": "choice", "difficulty": "medium",
     "text": "SQL注入攻击最有效的防御手段是？",
     "options": ["输入过滤", "参数化查询", "隐藏数据库", "加密网页"], "answer": 1, "source": "计算机网络教程 第7章"},
    {"id": "q30", "subject": "security", "chapter": "Web攻击", "type": "choice", "difficulty": "medium",
     "text": "XSS攻击中攻击者注入的代码在哪里执行？",
     "options": ["服务器端", "数据库", "受害者浏览器", "CDN节点"], "answer": 2, "source": "计算机网络教程 第7章"},
    {"id": "q31", "subject": "security", "chapter": "网络攻击", "type": "choice", "difficulty": "medium",
     "text": "ARP欺骗攻击的核心是伪造？",
     "options": ["IP地址", "MAC地址与IP的映射", "DNS响应", "TCP序列号"], "answer": 1, "source": "计算机网络教程 第7章"},
    {"id": "q32", "subject": "security", "chapter": "IDS/IPS", "type": "choice", "difficulty": "hard",
     "text": "IDS与IPS的关键区别是？",
     "options": ["检测方式不同", "IDS旁路报警，IPS串联可阻断", "IDS用硬件，IPS用软件", "无区别"], "answer": 1, "source": "计算机网络教程 第7章"},
    {"id": "q33", "subject": "security", "chapter": "VPN", "type": "choice", "difficulty": "medium",
     "text": "IPSec VPN工作在OSI的哪一层？",
     "options": ["数据链路层", "网络层", "运输层", "应用层"], "answer": 1, "source": "计算机网络教程 第7章"},
    {"id": "q34", "subject": "security", "chapter": "安全基础", "type": "fill", "difficulty": "medium",
     "text": "网络安全CIA三要素指机密性、______和可用性。",
     "answer": "完整性", "source": "计算机网络教程 第7章"},
    {"id": "q35", "subject": "security", "chapter": "SSL/TLS", "type": "choice", "difficulty": "hard",
     "text": "TLS 1.3 相比 TLS 1.2 的改进是？",
     "options": ["增加RSA密钥交换", "简化握手为1-RTT", "使用UDP传输", "取消证书验证"], "answer": 1, "source": "计算机网络教程 第7章"},
    # ── 扩展题（四科） ──
    {"id": "q36", "subject": "overview", "chapter": "性能指标", "type": "fill", "difficulty": "easy",
     "text": "计算机网络中，比特率的单位是______。", "answer": "bps", "source": "计算机网络教程 第1章"},
    {"id": "q37", "subject": "physical", "chapter": "信道复用", "type": "choice", "difficulty": "medium",
     "text": "下列哪种复用技术是光纤通信特有的？", "options": ["FDM", "TDM", "WDM", "CDM"], "answer": 2, "source": "计算机网络教程 第2章"},
    {"id": "q38", "subject": "datalink", "chapter": "以太网", "type": "choice", "difficulty": "medium",
     "text": "以太网MAC地址的长度是？", "options": ["32位", "48位", "64位", "128位"], "answer": 1, "source": "计算机网络教程 第3章"},
    {"id": "q39", "subject": "network", "chapter": "IP地址", "type": "choice", "difficulty": "medium",
     "text": "IPv6地址的长度是？", "options": ["32位", "64位", "128位", "256位"], "answer": 2, "source": "计算机网络教程 第4章"},
    {"id": "q40", "subject": "network", "chapter": "路由协议", "type": "choice", "difficulty": "medium",
     "text": "OSPF的Hello报文用于？", "options": ["发现和维持邻居关系", "传输路由表", "交换链路状态", "建立AS间连接"], "answer": 0, "source": "计算机网络教程 第4章"},
    {"id": "q41", "subject": "transport", "chapter": "TCP", "type": "fill", "difficulty": "medium",
     "text": "TCP段的首部最小长度是______字节。", "answer": "20", "source": "计算机网络教程 第5章"},
    {"id": "q42", "subject": "application", "chapter": "HTTP", "type": "choice", "difficulty": "easy",
     "text": "HTTP状态码404表示？", "options": ["服务器错误", "资源未找到", "请求超时", "禁止访问"], "answer": 1, "source": "计算机网络教程 第6章"},
    {"id": "q43", "subject": "security", "chapter": "防火墙", "type": "fill", "difficulty": "easy",
     "text": "防火墙的三种类型是包过滤、______和代理防火墙。", "answer": "状态检测", "source": "计算机网络教程 第7章"},
    {"id": "q44", "subject": "ds_tree", "chapter": "二叉树", "type": "choice", "difficulty": "easy",
     "text": "完全二叉树中，编号为i的节点若存在左孩子，其左孩子编号为？", "options": ["2i", "2i+1", "i/2", "i+1"], "answer": 0, "source": "数据结构 第5章"},
    {"id": "q45", "subject": "ds_stack", "chapter": "栈", "type": "fill", "difficulty": "easy",
     "text": "栈的特点是______。", "answer": "后进先出(LIFO)", "source": "数据结构 第3章"},
    {"id": "q46", "subject": "ds_sort", "chapter": "插入排序", "type": "choice", "difficulty": "easy",
     "text": "直接插入排序在最好情况下的时间复杂度是？", "options": ["O(n)", "O(n^2)", "O(nlogn)", "O(logn)"], "answer": 0, "source": "数据结构 第8章"},
    {"id": "q47", "subject": "ds_graph", "chapter": "遍历", "type": "choice", "difficulty": "medium",
     "text": "图的深度优先遍历(DFS)使用的数据结构是？", "options": ["队列", "栈", "数组", "链表"], "answer": 1, "source": "数据结构 第6章"},
    {"id": "q48", "subject": "co_data", "chapter": "定点数", "type": "fill", "difficulty": "medium",
     "text": "8位补码11111111表示的十进制值是______。", "answer": "-1", "source": "计算机组成原理 第2章"},
    {"id": "q49", "subject": "co_memory", "chapter": "Cache", "type": "choice", "difficulty": "medium",
     "text": "提高Cache命中率的方法不包括？", "options": ["增大Cache容量", "提高映射灵活性", "降低主存容量", "采用替换算法"], "answer": 2, "source": "计算机组成原理 第3章"},
    {"id": "q50", "subject": "co_io", "chapter": "DMA", "type": "fill", "difficulty": "medium",
     "text": "DMA方式的数据传送单位是______。", "answer": "数据块", "source": "计算机组成原理 第7章"},
    {"id": "q51", "subject": "os_process", "chapter": "调度算法", "type": "choice", "difficulty": "easy",
     "text": "下列调度算法中，时间片的大小直接影响系统性能的是？", "options": ["FCFS", "RR(时间片轮转)", "SJF", "优先级调度"], "answer": 1, "source": "操作系统 第2章"},
    {"id": "q52", "subject": "os_memory", "chapter": "分页", "type": "fill", "difficulty": "easy",
     "text": "在分页存储管理中，CPU产生的地址称为______地址。", "answer": "逻辑（或虚拟）", "source": "操作系统 第3章"},
    {"id": "q53", "subject": "os_file", "chapter": "磁盘调度", "type": "choice", "difficulty": "medium",
     "text": "磁盘调度中，N-Step SCAN相比SCAN的优势是？", "options": ["减少寻道时间", "防止饥饿", "提高吞吐量", "降低能耗"], "answer": 1, "source": "操作系统 第4章"},
    {"id": "q54", "subject": "ds_search", "chapter": "B树", "type": "choice", "difficulty": "hard",
     "text": "3阶B树的一个节点最多可以有多少个关键字？", "options": ["1", "2", "3", "4"], "answer": 1, "source": "数据结构 第7章"},
    {"id": "q55", "subject": "ds_sort", "chapter": "基数排序", "type": "choice", "difficulty": "medium",
     "text": "基数排序的稳定性是？", "options": ["稳定", "不稳定", "取决于基数", "取决于排序趟数"], "answer": 0, "source": "数据结构 第8章"},
    {"id": "q56", "subject": "co_cpu", "chapter": "流水线", "type": "choice", "difficulty": "hard",
     "text": "五段流水线中，EX阶段的功能是？", "options": ["取指令", "译码", "执行计算", "写回"], "answer": 2, "source": "计算机组成原理 第5章"},
    {"id": "q57", "subject": "co_memory", "chapter": "DRAM", "type": "fill", "difficulty": "medium",
     "text": "典型的DRAM刷新周期是______ms。", "answer": "64", "source": "计算机组成原理 第3章"},
    {"id": "q58", "subject": "os_overview", "chapter": "内核态", "type": "choice", "difficulty": "easy",
     "text": "用户态切换到内核态的方式是？", "options": ["系统调用", "函数调用", "程序跳转", "信号处理"], "answer": 0, "source": "操作系统 第1章"},
    {"id": "q59", "subject": "os_process", "chapter": "死锁", "type": "choice", "difficulty": "medium",
     "text": "系统有5个进程和4个同类资源，每个进程最多需要3个资源，则系统是否会死锁？", "options": ["一定死锁", "可能死锁", "一定不死锁", "无法判断"], "answer": 1, "source": "操作系统 第2章"},
    {"id": "q60", "subject": "ds_linear", "chapter": "顺序表", "type": "choice", "difficulty": "easy",
     "text": "顺序存储结构的最大缺点是？", "options": ["存储密度低", "插入删除操作效率低", "查找效率低", "只能顺序存取"], "answer": 1, "source": "数据结构 第2章"},
    {"id": "q61", "subject": "physical", "chapter": "传输媒体", "type": "fill", "difficulty": "easy",
     "text": "UTP的中文含义是______。", "answer": "非屏蔽双绞线", "source": "计算机网络教程 第2章"},
    # ── 扩展题②（四科全覆盖）──
    {"id": "q62", "subject": "overview", "chapter": "分组交换", "type": "choice", "difficulty": "medium",
     "text": "分组交换中每个分组除数据外还需包含？", "options": ["源IP", "目的地址+序号", "源MAC", "端口号"], "answer": 1, "source": "计网 第1章"},
    {"id": "q63", "subject": "network", "chapter": "NAT", "type": "choice", "difficulty": "medium",
     "text": "NAT的主要作用？", "options": ["提高网速", "解决IPv4短缺", "数据加密", "负载均衡"], "answer": 1, "source": "计网 第4章"},
    {"id": "q64", "subject": "ds_tree", "chapter": "二叉树", "type": "choice", "difficulty": "medium",
     "text": "完全二叉树1000节点，叶子节点数？", "options": ["500", "490", "501", "511"], "answer": 0, "source": "数据结构 第5章"},
    {"id": "q65", "subject": "ds_stack", "chapter": "栈", "type": "choice", "difficulty": "medium",
     "text": "后缀表达式3 4 + 5 *的值？", "options": ["35", "27", "45", "15"], "answer": 0, "source": "数据结构 第3章"},
    {"id": "q66", "subject": "co_cpu", "chapter": "数据通路", "type": "choice", "difficulty": "hard",
     "text": "单周期CPU效率低主因？", "options": ["时钟周期按最长指令", "无流水线", "指令集缺陷", "控制复杂"], "answer": 0, "source": "计组 第5章"},
    {"id": "q67", "subject": "os_process", "chapter": "信号量", "type": "choice", "difficulty": "hard",
     "text": "PV实现同步时信号量初值？", "options": ["0", "1", "n(资源数)", "-1"], "answer": 0, "source": "操作系统 第2章"},
    {"id": "q68", "subject": "ds_sort", "chapter": "快排", "type": "choice", "difficulty": "medium",
     "text": "快排每趟将哪个元素放最终位？", "options": ["最小值", "最大值", "枢轴元素", "中间值"], "answer": 2, "source": "数据结构 第8章"},
    {"id": "q69", "subject": "co_memory", "chapter": "Cache", "type": "choice", "difficulty": "medium",
     "text": "Cache映射方式中灵活性最高的是？", "options": ["直接映射", "全相联映射", "组相联映射", "混合映射"], "answer": 1, "source": "计组 第3章"},
    {"id": "q70", "subject": "os_process", "chapter": "PV操作", "type": "choice", "difficulty": "medium",
     "text": "生产者-消费者互斥P/V信号量初值？", "options": ["0", "1", "n", "-1"], "answer": 1, "source": "操作系统 第2章"},
    {"id": "q71", "subject": "ds_search", "chapter": "B+树", "type": "choice", "difficulty": "hard",
     "text": "B+树相比B树最大优势？", "options": ["查询更快", "范围查找高效", "插入更快", "删除更快"], "answer": 1, "source": "数据结构 第7章"},
    {"id": "q72", "subject": "co_data", "chapter": "IEEE754", "type": "choice", "difficulty": "hard",
     "text": "IEEE754单精度浮点偏置值？", "options": ["127", "128", "1023", "255"], "answer": 0, "source": "计组 第2章"},
    {"id": "q73", "subject": "security", "chapter": "数字签名", "type": "choice", "difficulty": "medium",
     "text": "数字签名使用的加密体制？", "options": ["对称", "非对称", "哈希", "混合"], "answer": 1, "source": "计网 第7章"},
    {"id": "q74", "subject": "os_memory", "chapter": "分页", "type": "choice", "difficulty": "easy",
     "text": "逻辑地址→物理地址转换由谁完成？", "options": ["CPU硬件(MMU)", "OS", "编译器", "链接器"], "answer": 0, "source": "操作系统 第3章"},
    {"id": "q75", "subject": "ds_graph", "chapter": "拓扑排序", "type": "choice", "difficulty": "medium",
     "text": "有向无环图拓扑排序可得到？", "options": ["唯一序列", "可能多个序列", "逆序", "零序列"], "answer": 1, "source": "数据结构 第6章"},
    {"id": "q76", "subject": "co_bus", "chapter": "总线", "type": "choice", "difficulty": "medium",
     "text": "支持多主设备的总线仲裁方式？", "options": ["链式查询", "计数器查询", "独立请求", "同步定时"], "answer": 2, "source": "计组 第6章"},
    {"id": "q77", "subject": "co_memory", "chapter": "主存", "type": "compute", "difficulty": "medium",
     "text": "CPU地址24根按字节寻址最大容量MB？", "answer": "16", "source": "计组 第3章"},
    {"id": "q78", "subject": "os_memory", "chapter": "页面置换", "type": "choice", "difficulty": "medium",
     "text": "FIFO置换算法可能产生什么异常？", "options": ["死锁", "Belady异常", "颠簸", "缺页异常"], "answer": 1, "source": "操作系统 第3章"},
    {"id": "q79", "subject": "datalink", "chapter": "VLAN", "type": "choice", "difficulty": "medium",
     "text": "802.1Q标签长度是？", "options": ["2B", "4B", "8B", "1B"], "answer": 1, "source": "计网 第3章"},
    {"id": "q80", "subject": "ds_search", "chapter": "哈希", "type": "compute", "difficulty": "medium",
     "text": "长度为12的有序表折半查找ASL(成功)？", "answer": "37/12≈3.08", "source": "数据结构 第7章"},
    {"id": "q81", "subject": "transport", "chapter": "TCP", "type": "fill", "difficulty": "medium",
     "text": "TCP首部最小长度______字节。", "answer": "20", "source": "计网 第5章"},
    {"id": "q82", "subject": "application", "chapter": "HTTP", "type": "choice", "difficulty": "easy",
     "text": "HTTP持久连接相对于非持久连接的优势？", "options": ["减少TCP握手", "更快响应", "并发请求", "更安全"], "answer": 0, "source": "计网 第6章"},
    {"id": "q83", "subject": "co_isa", "chapter": "RISC", "type": "choice", "difficulty": "medium",
     "text": "RISC特点不包括？", "options": ["指令数少", "寻址方式少", "微程序控制", "寄存器多"], "answer": 2, "source": "计组 第4章"},
    {"id": "q84", "subject": "ds_sort", "chapter": "基数排序", "type": "choice", "difficulty": "medium",
     "text": "基数排序的稳定性是？", "options": ["稳定", "不稳定", "取决于基数", "看趟数"], "answer": 0, "source": "数据结构 第8章"},
    {"id": "q85", "subject": "os_io", "chapter": "SPOOLing", "type": "choice", "difficulty": "medium",
     "text": "SPOOLing将独占设备变为？", "options": ["共享设备", "虚拟设备", "块设备", "字符设备"], "answer": 1, "source": "操作系统 第5章"},
    {"id": "q86", "subject": "network", "chapter": "路由协议", "type": "choice", "difficulty": "medium",
     "text": "OSPF基于什么算法？", "options": ["距离向量", "链路状态(Dijkstra)", "路径向量", "贪心"], "answer": 1, "source": "计网 第4章"},
    {"id": "q87", "subject": "ds_tree", "chapter": "哈夫曼", "type": "compute", "difficulty": "hard",
     "text": "七个叶子节点的哈夫曼树总节点数？", "answer": "13", "source": "数据结构 第5章"},
{"id": "q87", "subject": "ds_tree", "chapter": "哈夫曼", "type": "compute", "difficulty": "hard",
 "text": "七个叶子节点的哈夫曼树总节点数？", "answer": "13", "source": "数据结构 第5章"},
# ── 扩展题③（四科全覆盖，33题）──
{"id": "q88", "subject": "network", "chapter": "IP地址", "type": "choice", "difficulty": "easy",
 "text": "IPv6地址多少位？", "options": ["32", "64", "128", "256"], "answer": 2, "source": "计网 第4章"},
{"id": "q89", "subject": "ds_linear", "chapter": "链表", "type": "choice", "difficulty": "easy",
 "text": "单链表删除p的后继：", "options": ["p->next=p", "p->next=p->next->next", "p=p->next", "free(p)"], "answer": 1, "source": "数据结构 第2章"},
{"id": "q90", "subject": "ds_tree", "chapter": "AVL", "type": "choice", "difficulty": "hard",
 "text": "AVL插入引起LR旋转？", "options": ["左旋再右旋", "右旋再左旋", "单左旋", "单右旋"], "answer": 0, "source": "数据结构 第5章"},
{"id": "q91", "subject": "ds_graph", "chapter": "MST", "type": "choice", "difficulty": "medium",
 "text": "Kruskal适合什么图？", "options": ["稠密图", "稀疏图", "有向图", "带负权图"], "answer": 1, "source": "数据结构 第6章"},
{"id": "q92", "subject": "ds_sort", "chapter": "归并", "type": "fill", "difficulty": "medium",
 "text": "二路归并空间复杂度______。", "answer": "O(n)", "source": "数据结构 第8章"},
{"id": "q93", "subject": "co_overview", "chapter": "冯诺依曼", "type": "choice", "difficulty": "easy",
 "text": "冯诺依曼核心思想？", "options": ["存储程序", "并行", "分布式", "微程序"], "answer": 0, "source": "计组 第1章"},
{"id": "q94", "subject": "co_cpu", "chapter": "控制器", "type": "choice", "difficulty": "medium",
 "text": "微程序控制器核心？", "options": ["ALU", "控制存储器CM", "PC", "IR"], "answer": 1, "source": "计组 第5章"},
{"id": "q95", "subject": "co_memory", "chapter": "TLB", "type": "choice", "difficulty": "medium",
 "text": "TLB位于？", "options": ["硬盘", "CPU内MMU", "主存", "Cache"], "answer": 1, "source": "计组 第3章"},
{"id": "q96", "subject": "os_overview", "chapter": "OS特征", "type": "choice", "difficulty": "easy",
 "text": "OS最基本特征？", "options": ["并发与共享", "虚拟", "异步", "并行"], "answer": 0, "source": "操作系统 第1章"},
{"id": "q97", "subject": "os_process", "chapter": "调度", "type": "choice", "difficulty": "medium",
 "text": "中级调度功能？", "options": ["进程创建", "内存对换", "CPU分配", "资源回收"], "answer": 1, "source": "操作系统 第2章"},
{"id": "q98", "subject": "os_file", "chapter": "目录", "type": "choice", "difficulty": "easy",
 "text": "多级目录优点？", "options": ["减少命名冲突", "检索更快", "管理方便", "以上都是"], "answer": 3, "source": "操作系统 第4章"},
{"id": "q99", "subject": "os_process", "chapter": "PV", "type": "compute", "difficulty": "hard",
 "text": "S初值3，5次P、3次V后S=？", "answer": "1", "source": "操作系统 第2章"},
{"id": "q100", "subject": "transport", "chapter": "拥塞控制", "type": "choice", "difficulty": "medium",
 "text": "TCP拥塞避免窗口增长方式？", "options": ["线性", "指数", "对数", "固定"], "answer": 0, "source": "计网 第5章"},
{"id": "q101", "subject": "co_isa", "chapter": "指令", "type": "choice", "difficulty": "medium",
 "text": "RISC特点不包括？", "options": ["少指令", "少寻址", "微程序控制", "多寄存器"], "answer": 2, "source": "计组 第4章"},
{"id": "q102", "subject": "os_memory", "chapter": "页置换", "type": "choice", "difficulty": "medium",
 "text": "FIFO置换可能产生？", "options": ["死锁", "Belady异常", "颠簸", "缺页"], "answer": 1, "source": "操作系统 第3章"},
{"id": "q103", "subject": "ds_graph", "chapter": "MST", "type": "choice", "difficulty": "medium",
 "text": "Prim适合什么图？", "options": ["稠密图", "稀疏图", "有向图", "带负权图"], "answer": 0, "source": "数据结构 第6章"},
{"id": "q104", "subject": "co_memory", "chapter": "主存", "type": "compute", "difficulty": "medium",
 "text": "地址线24根，按字(32位)编址最大容量MB？", "answer": "64", "source": "计组 第3章"},
{"id": "q105", "subject": "os_io", "chapter": "DMA", "type": "choice", "difficulty": "medium",
 "text": "DMA传送以什么为单位？", "options": ["字", "字节", "数据块", "位"], "answer": 2, "source": "操作系统 第5章"},
{"id": "q106", "subject": "application", "chapter": "SMTP", "type": "fill", "difficulty": "easy",
 "text": "SMTP默认端口______。", "answer": "25", "source": "计网 第6章"},
{"id": "q107", "subject": "ds_tree", "chapter": "二叉树", "type": "compute", "difficulty": "hard",
 "text": "n个节点的完全二叉树深度？", "answer": "⌊log2n⌋+1", "source": "数据结构 第5章"},
{"id": "q108", "subject": "co_overview", "chapter": "性能", "type": "choice", "difficulty": "medium",
 "text": "CPI表示什么？", "options": ["每秒指令数", "每指令时钟周期", "每秒时钟", "程序总周期"], "answer": 1, "source": "计组 第1章"},
{"id": "q109", "subject": "os_process", "chapter": "线程", "type": "choice", "difficulty": "easy",
 "text": "用户级线程切换谁负责？", "options": ["OS内核", "用户态程序", "硬件", "MMU"], "answer": 1, "source": "操作系统 第2章"},
{"id": "q110", "subject": "ds_sort", "chapter": "堆排序", "type": "fill", "difficulty": "medium",
 "text": "建初始堆的时间复杂度______。", "answer": "O(n)", "source": "数据结构 第8章"},
{"id": "q111", "subject": "physical", "chapter": "奈氏准则", "type": "choice", "difficulty": "medium",
 "text": "奈氏准则给出什么上限？", "options": ["传输速率", "码元速率", "信噪比", "误码率"], "answer": 1, "source": "计网 第2章"},
{"id": "q112", "subject": "ds_queue", "chapter": "队列", "type": "choice", "difficulty": "easy",
 "text": "队列的应用不包括？", "options": ["层次遍历", "CPU调度", "函数调用", "缓冲区"], "answer": 2, "source": "数据结构 第3章"},
{"id": "q113", "subject": "co_data", "chapter": "补码", "type": "compute", "difficulty": "medium",
 "text": "8位补码10111011对应的十进制？", "answer": "-69", "source": "计组 第2章"},
{"id": "q114", "subject": "os_memory", "chapter": "分页", "type": "fill", "difficulty": "easy",
 "text": "分页系统中逻辑地址到物理地址转换由______完成。", "answer": "MMU(硬件)", "source": "操作系统 第3章"},
{"id": "q115", "subject": "datalink", "chapter": "CRC", "type": "fill", "difficulty": "medium",
 "text": "CRC中接收端余数为0说明______。", "answer": "无差错", "source": "计网 第3章"},
{"id": "q116", "subject": "security", "chapter": "数字签名", "type": "choice", "difficulty": "medium",
 "text": "数字签名提供哪种安全服务？", "options": ["机密性", "完整性+不可否认", "可用性", "认证"], "answer": 1, "source": "计网 第7章"},
{"id": "q117", "subject": "ds_string", "chapter": "KMP", "type": "fill", "difficulty": "hard",
 "text": "'ababa'的next数组(1开始)______。", "answer": "01123", "source": "数据结构 第4章"},
{"id": "q118", "subject": "co_io", "chapter": "中断", "type": "choice", "difficulty": "medium",
 "text": "中断响应优先级由什么决定？", "options": ["中断向量", "中断屏蔽字", "中断请求", "中断号"], "answer": 1, "source": "计组 第7章"},
{"id": "q119", "subject": "os_file", "chapter": "磁盘", "type": "choice", "difficulty": "medium",
 "text": "磁盘调度中电梯算法指的是？", "options": ["FCFS", "SSTF", "SCAN", "C-SCAN"], "answer": 2, "source": "操作系统 第4章"},
{"id": "q120", "subject": "network", "chapter": "子网划分", "type": "compute", "difficulty": "hard",
 "text": "192.168.1.0/26子网掩码？", "answer": "255.255.255.192", "source": "计网 第4章"},
{"id": "q121", "subject": "overview", "chapter": "分组交换", "type": "choice", "difficulty": "easy",
 "text": "分组交换比电路交换的优势？", "options": ["延迟低", "线路利用率高", "成本低", "带宽高"], "answer": 1, "source": "计网 第1章"},
{"id": "q122", "subject": "ds_tree", "chapter": "BST", "type": "fill", "difficulty": "medium",
 "text": "BST中序序列的性质是______。", "answer": "递增有序", "source": "数据结构 第5章"},
{"id": "q123", "subject": "co_data", "chapter": "ALU", "type": "choice", "difficulty": "medium",
 "text": "ALU核心组成是？", "options": ["累加器和暂存器", "加法器和控制逻辑", "寄存器和译码器", "计数器和比较器"], "answer": 1, "source": "计组 第2章"},
{"id": "q124", "subject": "os_process", "chapter": "进程", "type": "choice", "difficulty": "easy",
 "text": "进程控制块PCB的作用？", "options": ["代码存储", "描述进程状态和资源", "数据缓存", "指令执行"], "answer": 1, "source": "操作系统 第2章"},
{"id": "q125", "subject": "application", "chapter": "HTTP", "type": "choice", "difficulty": "medium",
 "text": "HTTP/2新增特性不包括？", "options": ["多路复用", "头部压缩", "服务端推送", "明文传输"], "answer": 3, "source": "计网 第6章"},
{"id": "q126", "subject": "ds_sort", "chapter": "外部排序", "type": "choice", "difficulty": "hard",
 "text": "外部排序主要时间开销在？", "options": ["CPU计算", "内存比较", "IO读写", "网络传输"], "answer": 2, "source": "数据结构 第8章"},
{"id": "q127", "subject": "co_memory", "chapter": "主存扩展", "type": "compute", "difficulty": "hard",
 "text": "用4片16K×8位芯片构成64K×8位存储器需多少位地址线？", "answer": "16", "source": "计组 第3章"},
{"id": "q128", "subject": "os_memory", "chapter": "虚拟内存", "type": "choice", "difficulty": "medium",
 "text": "缺页中断属于哪种中断？", "options": ["外中断", "内中断(异常)", "可屏蔽中断", "NMI"], "answer": 1, "source": "操作系统 第3章"},
]


SEED_SUBJECTS = {
    "overview": {"name": "计算机网络概述", "chapters": ["互联网与信息时代", "分组交换", "网络体系结构", "性能指标"]},
    "physical": {"name": "物理层", "chapters": ["传输媒体", "信道复用", "数字传输系统", "接入技术"]},
    "datalink": {"name": "数据链路层", "chapters": ["差错检测", "停止等待协议", "CSMA/CD", "以太网", "VLAN"]},
    "network": {"name": "网络层", "chapters": ["IP地址与编址", "ARP", "路由选择", "RIP/OSPF/BGP", "NAT", "IPv6"]},
    "transport": {"name": "运输层", "chapters": ["UDP", "TCP报文段", "可靠传输", "流量控制", "拥塞控制", "连接管理"]},
    "application": {"name": "应用层", "chapters": ["DNS", "WWW", "电子邮件", "FTP", "DHCP"]},
    "security": {"name": "网络安全", "chapters": ["机密性与密码学", "报文摘要", "数字签名", "SSL/TLS", "防火墙"]},
}

# ============================================================
# 计算机组成原理种子数据（408 统考）
# 9章：系统概述、数据表示、存储系统、指令系统、CPU、总线、I/O系统
# ============================================================

CO_SEED_KNOWLEDGE_CHUNKS = [
    # ---- 第1章 计算机系统概述 ----
    {"content": "计算机系统由硬件和软件两部分组成。硬件是物理实体，软件是程序和数据。计算机体系结构是程序员可见的属性（指令集、数据类型、寻址方式），计算机组成是实现体系结构的具体部件。", "metadata": {"subject": "co_overview", "chapter": "系统概述", "type": "knowledge_point"}},
    {"content": " Flynn分类法：SISD（单指令流单数据流）、SIMD（单指令流多数据流）、MISD（多指令流单数据流）、MIMD（多指令流多数据流）。现代多核CPU属于MIMD。", "metadata": {"subject": "co_overview", "chapter": "体系结构", "type": "knowledge_point"}},
    {"content": " 计算机性能指标：主频（时钟周期）、CPI（每指令周期数）、CPU时间=指令数×CPI×时钟周期时间、MIPS=指令数/(CPU时间×10^6)、MFLOPS=浮点操作数/(CPU时间×10^6)。", "metadata": {"subject": "co_overview", "chapter": "性能评价", "type": "knowledge_point"}},
    # ---- 第2章 数据的表示和运算 ----
    {"content": " 定点数表示：原码、反码、补码、移码。补码求法：正数同原码，负数除符号位外按位取反末位加1。移码常用于阶码，补码常用于数值计算。", "metadata": {"subject": "co_data", "chapter": "定点数", "type": "knowledge_point"}},
    {"content": " IEEE 754浮点数：单精度(32位)符号位1位，阶码8位(偏移127)，尾数23位；双精度(64位)符号位1位，阶码11位(偏移1023)，尾数52位。规格化数尾数最高位为1(隐含)。", "metadata": {"subject": "co_data", "chapter": "浮点数", "type": "knowledge_point"}},
    {"content": " 浮点数加减法步骤：对阶（小阶向大阶看齐）、尾数加减、规格化、舍入、溢出判断。溢出判断：阶码全1为无穷大/NaN，阶码全0为非规格化数。", "metadata": {"subject": "co_data", "chapter": "浮点运算", "type": "knowledge_point"}},
    # ---- 第3章 存储系统 ----
    {"content": " 存储层次结构：寄存器→Cache→主存→外存。速度递减，容量递增，成本递减。局部性原理：时间局部性（近期访问的指令/数据可能再次访问）、空间局部性（相邻存储单元可能被访问）。", "metadata": {"subject": "co_memory", "chapter": "存储层次", "type": "knowledge_point"}},
    {"content": " SRAM（静态RAM）：双稳态触发器存储，速度快，集成度低，功耗高，用作Cache。DRAM（动态RAM）：电容存储，速度慢，集成度高，功耗低，需刷新，用作主存。", "metadata": {"subject": "co_memory", "chapter": "半导体存储", "type": "knowledge_point"}},
    {"content": " Cache地址映射：直接映射（主存块i→Cache块i mod 2^c）、全相联映射（主存块可放Cache任意位置）、组相联映射（主存块i→Cache组i mod 组数，组内全相联）。", "metadata": {"subject": "co_memory", "chapter": "Cache映射", "type": "knowledge_point"}},
    {"content": " 虚拟内存实现：页式（固定大小页）、段式（可变长度段）、段页式。页表机制：每个进程有页表，页表项包含页框号、有效位、访问位、修改位。TLB（快表）加速地址变换。", "metadata": {"subject": "co_memory", "chapter": "虚拟内存", "type": "knowledge_point"}},
    # ---- 第4章 指令系统 ----
    {"content": " 指令格式：操作码+地址码。操作码长度固定则编码简单但指令数少；操作码长度可变（扩展操作码）则指令数多。地址码长度：零地址、一地址、二地址、三地址。", "metadata": {"subject": "co_isa", "chapter": "指令格式", "type": "knowledge_point"}},
    {"content": " 寻址方式：立即寻址（快，但地址空间受限）、直接寻址（简单，但需访问内存）、间接寻址（灵活，但速度慢）、寄存器寻址（快）、寄存器间接寻址、基址寻址、变址寻址、相对寻址、堆栈寻址。", "metadata": {"subject": "co_isa", "chapter": "寻址方式", "type": "knowledge_point"}},
    {"content": " CISC（复杂指令集）：指令丰富，长度可变，寻址方式多，如x86。RISC（精简指令集）：指令少且长度固定，寻址方式少，硬连线控制，如ARM、MIPS。", "metadata": {"subject": "co_isa", "chapter": "CISC/RISC", "type": "knowledge_point"}},
    # ---- 第5章 中央处理器 ----
    {"content": " CPU功能：取指令、分析指令、执行指令。数据通路：ALU、寄存器、数据总线。硬连线控制器：速度快，设计复杂。微程序控制器：灵活性高，速度慢。", "metadata": {"subject": "co_cpu", "chapter": "CPU功能", "type": "knowledge_point"}},
    {"content": " 指令流水线：将指令执行分为取指、译码、执行、访存、写回五段。理想情况下CPI=1。相关：数据相关（RAW）、控制相关（分支指令）、结构相关（资源冲突）。", "metadata": {"subject": "co_cpu", "chapter": "流水线", "type": "knowledge_point"}},
    {"content": " 流水线性能：加速比=流水线深度/(1+冒险 stalls)；吞吐率=1/最长段周期。解决冒险：数据前递（转发）、指令调度（延迟槽）、分支预测（静态/动态）。", "metadata": {"subject": "co_cpu", "chapter": "流水线性能", "type": "knowledge_point"}},
    # ---- 第6章 总线 ----
    {"content": " 总线分类：数据总线（DB，双向，位数=字长）、地址总线（AB，单向，位数=寻址空间）、控制总线（CB，传输控制信号）。总线仲裁：集中式（链式、计数器定时、独立请求）、分布式（逻辑环、冲突检测）。", "metadata": {"subject": "co_bus", "chapter": "总线分类", "type": "knowledge_point"}},
    {"content": " 总线操作：总线传输周期：申请分配、寻址、传数、结束。同步通信（统一时钟）、异步通信（应答式）。总线带宽=数据线宽度×总线频率。", "metadata": {"subject": "co_bus", "chapter": "总线操作", "type": "knowledge_point"}},
    # ---- 第7章 I/O系统 ----
    {"content": " I/O方式：程序查询（CPU忙等，效率低）、程序中断（CPU可并行，需保存现场）、DMA（外设直接访存，适合大批量传输）、通道方式（复杂I/O管理）。", "metadata": {"subject": "co_io", "chapter": "I/O方式", "type": "knowledge_point"}},
    {"content": " 中断处理过程：关中断→保存断点和现场→识别中断源→中断服务→开中断→返回。中断屏蔽字：设置优先级，高优先级中断可打断低优先级。中断向量表：存放各中断服务程序入口地址。", "metadata": {"subject": "co_io", "chapter": "中断", "type": "knowledge_point"}},
]

# ============================================================
# 操作系统种子数据（408 统考）
# 9章：概述、进程、调度、同步、死锁、内存、文件系统、I/O
# ============================================================

OS_SEED_KNOWLEDGE_CHUNKS = [
    # ---- 第1章 操作系统概述 ----
    {"content": " 操作系统功能：进程管理、内存管理、文件管理、设备管理、作业管理。OS是用户与计算机硬件之间的接口，提供运行环境。", "metadata": {"subject": "os_overview", "chapter": "OS概述", "type": "knowledge_point"}},
    {"content": " 系统调用：应用程序请求OS服务的唯一接口。常见系统调用：进程控制(create/exit/wait)、文件操作(open/read/write/close)、设备操作、信息维护、通信。", "metadata": {"subject": "os_overview", "chapter": "系统调用", "type": "knowledge_point"}},
    # ---- 第2章 进程管理 ----
    {"content": " 进程是程序的一次执行，是系统进行资源分配和调度的一个独立单位。进程状态：运行、就绪、阻塞。进程控制块(PCB)：进程存在的唯一标识，包含进程状态、程序计数器、CPU寄存器、调度信息等。", "metadata": {"subject": "os_process", "chapter": "进程与线程", "type": "knowledge_point"}},
    {"content": " 线程是进程内的一个执行单元，是CPU调度的基本单位。线程优点：减少并发执行时空切换开销、提高系统效率、通信方便。线程状态：运行、就绪、阻塞。", "metadata": {"subject": "os_process", "chapter": "进程与线程", "type": "knowledge_point"}},
    {"content": " 进程控制：进程创建（fork）、进程终止（exit）、进程阻塞（wait）、进程唤醒（wakeup）。原语操作：不可中断的过程。", "metadata": {"subject": "os_process", "chapter": "进程控制", "type": "knowledge_point"}},
    # ---- 第3章 处理机调度 ----
    {"content": " 调度层次：作业调度（高级调度，进入外存→内存）、内存调度（中级调度，挂起→就绪）、进程调度（低级调度，就绪→运行）。调度方式：抢占式（可剥夺）、非抢占式（不可剥夺）。", "metadata": {"subject": "os_sched", "chapter": "调度层次", "type": "knowledge_point"}},
    {"content": " 调度算法：FCFS（先来先服务，非抢占，平均等待时间长）、SJF（最短作业优先，最优平均等待时间，但可能饥饿）、优先级调度（静态/动态，可能导致饥饿）、RR（时间片轮转，抢占式，响应时间好）、多级队列（分优先级队列）、多级反馈队列（进程可升级/降级）。", "metadata": {"subject": "os_sched", "chapter": "调度算法", "type": "knowledge_point"}},
    # ---- 第4章 同步与互斥 ----
    {"content": " 临界资源：一次只允许一个进程访问的资源。临界区：进程中访问临界资源的程序段。同步：进程间直接制约关系；互斥：进程间间接制约关系（竞争临界资源）。", "metadata": {"subject": "os_sync", "chapter": "同步互斥", "type": "knowledge_point"}},
    {"content": " 信号量机制：整型信号量S>0表示可用资源数，S<=0表示等待进程数。P操作（wait）：S=S-1，若S<0则阻塞；V操作（signal）：S=S+1，若S<=0则唤醒。", "metadata": {"subject": "os_sync", "chapter": "信号量", "type": "knowledge_point"}},
    {"content": " 经典同步问题：生产者-消费者（互斥+同步）、读者-写者（读写互斥、写写互斥、读读共享）、哲学家进餐（防止死锁）、 Sleeping Barber（理发师问题）。", "metadata": {"subject": "os_sync", "chapter": "经典问题", "type": "knowledge_point"}},
    # ---- 第5章 死锁 ----
    {"content": " 死锁四个必要条件：互斥条件、请求和保持条件、不剥夺条件、环路等待条件。只要破坏一个条件即可防止死锁。", "metadata": {"subject": "os_deadlock", "chapter": "死锁条件", "type": "knowledge_point"}},
    {"content": " 死锁预防：破坏互斥（Spooling技术）、破坏请求和保持（一次性请求所有资源）、破坏不剥夺（资源可剥夺）、破坏环路等待（资源有序分配）。死锁避免：银行家算法（安全性算法、资源请求算法）。", "metadata": {"subject": "os_deadlock", "chapter": "死锁处理", "type": "knowledge_point"}},
    {"content": " 死锁检测与解除：资源分配图简化法检测死锁。解除方法：资源剥夺法、撤销进程法（终止进程并剥夺资源）。", "metadata": {"subject": "os_deadlock", "chapter": "死锁检测", "type": "knowledge_point"}},
    # ---- 第6章 内存管理 ----
    {"content": " 内存分配方式：连续分配（单一连续、固定分区、可变分区）、非连续分配（分页、分段、段页式）。连续分配特点：内存利用率低，存在外部碎片。", "metadata": {"subject": "os_mem", "chapter": "内存分配", "type": "knowledge_point"}},
    {"content": " 分页存储管理：将物理内存分成固定大小的帧，逻辑空间分成同样大小的页。页表实现地址映射：逻辑地址→页号+页内偏移→查页表得帧号→物理地址。快表（TLB）加速页表访问。", "metadata": {"subject": "os_mem", "chapter": "分页管理", "type": "knowledge_point"}},
    {"content": " 分段存储管理：按程序逻辑段划分（代码段、数据段、堆栈段），每段长度可变。段表：段号、段长、段基址。优点：便于共享和保护，便于动态链接。", "metadata": {"subject": "os_mem", "chapter": "分段管理", "type": "knowledge_point"}},
    # ---- 第7章 虚拟内存 ----
    {"content": " 虚拟内存：基于局部性原理，只装入部分页面到内存。请求分页：缺页中断→查找空闲帧→读入页面→修改页表→重新执行。页面置换算法：OPT（最优，不可实现）、FIFO（可能Belady异常）、LRU（最近最少使用）、Clock（近似LRU）。", "metadata": {"subject": "os_vmem", "chapter": "虚拟内存", "type": "knowledge_point"}},
    {"content": " 页面分配策略：固定分配（每个进程固定页框数）、可变分配（进程运行期间可调整）。置换策略：全局置换（从所有进程选）、局部置换（从本进程选）。工作集模型：进程在一段时间内访问的页面集合。", "metadata": {"subject": "os_vmem", "chapter": "页面置换", "type": "knowledge_point"}},
    # ---- 第8章 文件系统 ----
    {"content": " 文件逻辑结构：流式文件（无结构，字节序列）、记录式文件（有结构，定长/变长记录）。文件物理结构：连续分配、链接分配（隐式/显式）、索引分配（单级/多级/混合）。", "metadata": {"subject": "os_file", "chapter": "文件结构", "type": "knowledge_point"}},
    {"content": " 目录结构：单级目录（简单但命名冲突）、两级目录（树形，用户独立）、树形目录（多级，路径唯一）、图形目录（可共享，复杂）。文件共享：硬链接（同一索引节点，共享文件）、符号链接（新文件指向原文件路径）。", "metadata": {"subject": "os_file", "chapter": "目录与共享", "type": "knowledge_point"}},
    {"content": " 磁盘调度算法：FCFS（先来先服务，公平但效率低）、SSTF（最短寻道时间优先，效率高但可能饥饿）、SCAN（电梯算法，来回扫描）、C-SCAN（循环扫描，均匀响应）、LOOK（只在有请求处停下）。", "metadata": {"subject": "os_file", "chapter": "磁盘调度", "type": "knowledge_point"}},
    # ---- 第9章 I/O管理 ----
    {"content": " I/O控制方式：程序查询（CPU忙等）、中断驱动（CPU与I/O并行）、DMA（外设直接访存，适合高速外设）、通道控制（复杂I/O管理）。设备分类：块设备（磁盘）、字符设备（键盘/显示器）、网络设备。", "metadata": {"subject": "os_io", "chapter": "I/O方式", "type": "knowledge_point"}},
    {"content": " 缓冲区管理：单缓冲（效率低）、双缓冲（解决生产者-消费者问题）、循环缓冲（多缓冲，适合高速外设）。SPOOLing技术：用磁盘模拟设备，实现虚拟设备，将独占设备改造为共享设备。", "metadata": {"subject": "os_io", "chapter": "缓冲技术", "type": "knowledge_point"}},
]


KNOWLEDGE_GRAPH = {
    "nodes": [
        # 数据结构（group 1-4）
        {"id": "ds_linear", "label": "线性表", "group": 1},
        {"id": "ds_stack", "label": "栈和队列", "group": 1},
        {"id": "ds_string", "label": "串", "group": 2},
        {"id": "ds_tree", "label": "树和二叉树", "group": 2},
        {"id": "ds_graph", "label": "图", "group": 3},
        {"id": "ds_search", "label": "查找", "group": 3},
        {"id": "ds_sort", "label": "排序", "group": 4},
        # 计算机组成原理（group 5-7）
        {"id": "co_overview", "label": "计算机系统概述", "group": 5},
        {"id": "co_data", "label": "数据表示和运算", "group": 5},
        {"id": "co_memory", "label": "存储系统", "group": 6},
        {"id": "co_cpu", "label": "中央处理器", "group": 6},
        {"id": "co_bus", "label": "总线", "group": 7},
        {"id": "co_io", "label": "I/O系统", "group": 7},
        # 操作系统（group 8-10）
        {"id": "os_overview", "label": "操作系统概述", "group": 8},
        {"id": "os_process", "label": "进程管理", "group": 8},
        {"id": "os_sched", "label": "处理机调度", "group": 9},
        {"id": "os_sync", "label": "同步与互斥", "group": 9},
        {"id": "os_deadlock", "label": "死锁", "group": 10},
        {"id": "os_mem", "label": "内存管理", "group": 10},
        {"id": "os_vmem", "label": "虚拟内存", "group": 11},
        {"id": "os_file", "label": "文件系统", "group": 11},
        {"id": "os_io", "label": "I/O管理", "group": 12},
        # 计算机网络（group 13-19）
        {"id": "overview", "label": "计算机网络概述", "group": 13},
        {"id": "architecture", "label": "体系结构", "group": 13},
        {"id": "switching", "label": "分组交换", "group": 13},
        {"id": "physical", "label": "物理层", "group": 14},
        {"id": "media", "label": "传输媒体", "group": 14},
        {"id": "multiplex", "label": "信道复用", "group": 14},
        {"id": "datalink", "label": "数据链路层", "group": 15},
        {"id": "csma", "label": "CSMA/CD", "group": 15},
        {"id": "ethernet", "label": "以太网", "group": 15},
        {"id": "vlan", "label": "VLAN", "group": 15},
        {"id": "network", "label": "网络层", "group": 16},
        {"id": "ip", "label": "IP协议", "group": 16},
        {"id": "arp", "label": "ARP", "group": 16},
        {"id": "routing", "label": "路由选择", "group": 16},
        {"id": "transport", "label": "运输层", "group": 17},
        {"id": "tcp", "label": "TCP协议", "group": 17},
        {"id": "udp", "label": "UDP协议", "group": 17},
        {"id": "app", "label": "应用层", "group": 18},
        {"id": "dns", "label": "DNS", "group": 18},
        {"id": "http", "label": "HTTP", "group": 18},
        {"id": "security", "label": "网络安全", "group": 19},
        {"id": "tls", "label": "SSL/TLS", "group": 19},
        {"id": "firewall", "label": "防火墙", "group": 19},
    ],
    "edges": [
        # 数据结构内部关系
        {"source": "ds_linear", "target": "ds_stack"},
        {"source": "ds_linear", "target": "ds_string"},
        {"source": "ds_linear", "target": "ds_tree"},
        {"source": "ds_tree", "target": "ds_graph"},
        {"source": "ds_linear", "target": "ds_search"},
        {"source": "ds_linear", "target": "ds_sort"},
        # 计算机组成原理内部关系
        {"source": "co_overview", "target": "co_data"},
        {"source": "co_overview", "target": "co_memory"},
        {"source": "co_data", "target": "co_memory"},
        {"source": "co_memory", "target": "co_cpu"},
        {"source": "co_cpu", "target": "co_bus"},
        {"source": "co_bus", "target": "co_io"},
        # 操作系统内部关系
        {"source": "os_overview", "target": "os_process"},
        {"source": "os_process", "target": "os_sched"},
        {"source": "os_process", "target": "os_sync"},
        {"source": "os_sync", "target": "os_deadlock"},
        {"source": "os_overview", "target": "os_mem"},
        {"source": "os_mem", "target": "os_vmem"},
        {"source": "os_overview", "target": "os_file"},
        {"source": "os_overview", "target": "os_io"},
        # 计算机网络内部关系
        {"source": "overview", "target": "architecture"},
        {"source": "overview", "target": "switching"},
        {"source": "overview", "target": "physical"},
        {"source": "physical", "target": "media"},
        {"source": "physical", "target": "multiplex"},
        {"source": "physical", "target": "datalink"},
        {"source": "datalink", "target": "csma"},
        {"source": "datalink", "target": "ethernet"},
        {"source": "datalink", "target": "vlan"},
        {"source": "datalink", "target": "network"},
        {"source": "network", "target": "ip"},
        {"source": "network", "target": "arp"},
        {"source": "network", "target": "routing"},
        {"source": "network", "target": "transport"},
        {"source": "transport", "target": "tcp"},
        {"source": "transport", "target": "udp"},
        {"source": "transport", "target": "app"},
        {"source": "app", "target": "dns"},
        {"source": "app", "target": "http"},
        {"source": "app", "target": "security"},
        {"source": "security", "target": "tls"},
        {"source": "security", "target": "firewall"},
        # 跨课程依赖关系（408学习路径）
        {"source": "ds_linear", "target": "co_overview"},
        {"source": "co_memory", "target": "os_mem"},
        {"source": "os_process", "target": "network"},
    ],
}

LEARNING_PATH_DAG = {
    # === 408 统考四门课 ===
    # 数据结构（第1-8章）
    "数据结构": {
        "id": "ds", "chapter": 1, "prerequisites": [],
        "topics": ["线性表", "栈和队列", "串", "数组和广义表", "树和二叉树", "图", "查找", "排序"],
    },
    # 计算机组成原理（第1-9章）
    "计算机组成原理": {
        "id": "co", "chapter": 2, "prerequisites": ["数据结构"],
        "topics": ["计算机系统概述", "数据的表示和运算", "存储系统", "指令系统", "中央处理器", "总线", "I/O系统"],
    },
    # 操作系统（第1-9章）
    "操作系统": {
        "id": "os", "chapter": 3, "prerequisites": ["计算机组成原理"],
        "topics": ["操作系统概述", "进程管理", "处理机调度", "同步与互斥", "死锁", "内存管理", "虚拟内存", "文件系统", "I/O管理"],
    },
    # 计算机网络（第1-7章）
    "计算机网络": {
        "id": "cn", "chapter": 4, "prerequisites": ["操作系统"],
        "topics": ["计算机网络体系结构", "物理层", "数据链路层", "网络层", "运输层", "应用层", "网络安全"],
    },
}

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
    # ---- 第3章 串 ----
    {"content": "串是字符组成的有限序列。空串：长度为0。空格串：由空格字符组成，长度≥1。子串：串中任意连续字符序列。主串：包含子串的串。子串位置：子串第一个字符在主串中的序号。", "metadata": {"subject": "ds_string", "chapter": "串", "type": "knowledge_point"}},
    {"content": "KMP算法核心：利用已匹配信息避免主串指针回退。next数组：next[j]=模式串T[1..j-1]中最长相同前后缀长度+1。匹配失败时主串i不变，模式串j=next[j]。时间复杂度O(n+m)。", "metadata": {"subject": "ds_string", "chapter": "KMP", "type": "knowledge_point"}},
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
    {"content": "散列表(哈希表)：根据关键字直接计算存储地址。常用哈希函数：直接定址(H(key)=a*key+b)、除留余数(H(key)=key%p, p<=表长且为质数)、数字分析。冲突处理：开放定址(线性探测/二次探测/双重哈希)、拉链法。", "metadata": {"subject": "ds_search", "chapter": "哈希", "type": "knowledge_point"}},
    {"content": "哈希冲突：线性探测容易堆积(聚集)。二次探测：H_i=(H(key)+d_i)%m, d_i=1^2,-1^2,2^2,-2^2,...。双重哈希：d_i=i*H2(key)。拉链法：同义词链表，不堆积，删除方便，适合动态表。", "metadata": {"subject": "ds_search", "chapter": "哈希冲突", "type": "knowledge_point"}},
    # ---- 第7章 排序 ----
    {"content": "插入排序：直接插入(无序序列逐个插入有序序列,O(n^2)稳定)、折半插入(查找用二分但仍需移动,O(n^2)稳定)、希尔排序(按增量分组直接插入,增量递减至1,不稳定,O(n^1.3)~O(n^2))。", "metadata": {"subject": "ds_sort", "chapter": "插入排序", "type": "knowledge_point"}},
    {"content": "交换排序：冒泡排序(相邻比较交换,一趟确定一个最终位置,O(n^2)稳定)、快速排序(选枢轴划分左右递归,平均O(nlogn)最坏O(n^2)不稳定,空间O(logn)最坏O(n))。快排是最常用排序。", "metadata": {"subject": "ds_sort", "chapter": "交换排序", "type": "knowledge_point"}},
    {"content": "选择排序：简单选择(每趟选最小交换,O(n^2)不稳定)、堆排序(建大根堆,堆顶与末尾交换再调整,O(nlogn)不稳定)。堆：完全二叉树，大根堆根>=子树所有节点。建堆O(n)，调整O(logn)。", "metadata": {"subject": "ds_sort", "chapter": "选择排序", "type": "knowledge_point"}},
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
    {"content": "死锁：两个以上进程因竞争资源而无限等待。必要条件（4个必须同时满足）：互斥、请求保持、不可剥夺、循环等待。预防：破坏四个条件之一；避免：银行家算法(安全状态判断)；检测：资源分配图化简。", "metadata": {"subject": "os_process", "chapter": "死锁", "type": "knowledge_point"}},
    # ---- 第3章 内存管理 ----
    {"content": "连续分配：单一连续（仅单道）、固定分区（分区大小固定,内部碎片）、动态分区（按需分割,外部碎片）。动态分区分配算法：首次适应FF、最佳适应BF(碎片最多)、最差适应WF、邻近适应NF。", "metadata": {"subject": "os_memory", "chapter": "连续分配", "type": "knowledge_point"}},
    {"content": "分页存储：逻辑地址分为页号+页内偏移。页表存页号→物理块号映射。快表TLB：高速缓冲最近使用的页表项,命中则无需访存查页表。缺页中断：访问的页不在内存→调入→更新页表。", "metadata": {"subject": "os_memory", "chapter": "分页", "type": "knowledge_point"}},
    {"content": "多级页表：页目录+页表。32位地址：10位页目录(1024项)+10位页表(1024项)+12位页内偏移(4KB页)。分段存储：逻辑地址=段号+段内偏移,段表存段号→基址+限长。段页式：先分段再分页。", "metadata": {"subject": "os_memory", "chapter": "多级页表与分段", "type": "knowledge_point"}},
    {"content": "虚拟内存：程序部分装入即可运行,大于物理内存的程序也可运行。实现：请求分页或请求分段。页面置换算法：OPT（最佳,无法实现）、FIFO（Belady异常：帧多缺页也多）、LRU（最近最久未使用）、Clock（NRU,访问位+修改位）。", "metadata": {"subject": "os_memory", "chapter": "虚拟内存", "type": "knowledge_point"}},
    {"content": "页面置换算法比较：FIFO实现简单但有Belady异常；LRU效果接近OPT但需硬件支持（栈）；Clock（NRU）是LRU近似,用访问位A和修改位M,选择(A=0,M=0)优先→(0,1)→(1,0)→(1,1)。缺页率取决于工作集。", "metadata": {"subject": "os_memory", "chapter": "页面置换", "type": "knowledge_point"}},
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
