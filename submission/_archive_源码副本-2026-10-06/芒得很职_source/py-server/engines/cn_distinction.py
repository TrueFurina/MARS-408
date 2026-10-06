# ============================================================
# 计网易混淆概念辨析专项（cn_distinction）
# ------------------------------------------------------------
# 内置基于《计算机网络》（谢希仁）教材的易混淆概念对数据集，
# 每对含：混淆点、关键辨析、以及一道区分自测题（带标准答案与关键词）。
# 提供 get_pairs / get_pair / get_random_quiz，供 API 调用。
#
# 诚信：内容均为教材公开知识点，不编造；自测题采用确定性关键词判分，
#      不假装 AI 打分，避免不可复现。
# ============================================================

import random
from typing import Optional

CN_DISTINCTION_PAIRS = [
    {
        "id": "cn_switch",
        "title": "电路交换 vs 报文交换 vs 分组交换",
        "category": "数据交换方式",
        "confusion": "三者都用于『网络中传输数据』，但建立连接、转发单位、信道利用率差别巨大。",
        "key_points": [
            "电路交换：建立连接→通信→释放；独占整条信道；时延小但建立慢、线路利用率低；适合实时语音。",
            "报文交换：整个报文存储转发；无连接建立；但单报文大，时延高、缓存压力大。",
            "分组交换：报文切分为分组存储转发；无需建立连接（数据报）或建虚电路；灵活、利用率高，但有分组头开销与失序重组。",
        ],
        "quiz": {
            "question": "为什么计算机网络（尤其是因特网）普遍采用分组交换而非电路交换？",
            "expected_keywords": ["利用率", "灵活", "突发", "差错", "存储转发"],
            "answer": "分组交换无需建立连接、按需占用链路，多个用户可统计复用信道，线路利用率高；适合计算机通信『突发』的特性；且分组独立转发、便于差错控制与路由，鲁棒性好。电路交换在通信前独占整条信道，线路利用率低，不适合突发数据。",
        },
    },
    {
        "id": "cn_vc_datagram",
        "title": "虚电路 VC vs 数据报",
        "category": "网络层服务模型",
        "confusion": "都是网络层转发方式，区别在『是否预先建立连接』与『状态维护』。",
        "key_points": [
            "虚电路：面向连接；通信前建立虚电路并分配虚电路号；分组沿同一路径、有序到达；路由器需维护连接状态。",
            "数据报：无连接；每个分组携带完整目的地址、独立路由；可乱序到达；路由器不维护连接状态。",
            "典型：X.25/ATM/帧中继用虚电路；IP 用数据报。",
        ],
        "quiz": {
            "question": "虚电路网络与数据报网络在『路由器需要维护的状态』上有何本质不同？",
            "expected_keywords": ["虚电路", "状态", "连接", "数据报", "无连接"],
            "answer": "虚电路网络中路由器需维护每条虚电路的连接状态（转发表项随连接建立/拆除变化）；数据报网络的无连接路由器不维护任何端到端连接状态，仅依据目的地址逐包转发。",
        },
    },
    {
        "id": "cn_arq",
        "title": "停止-等待 vs GBN(后退N帧) vs SR(选择重传)",
        "category": "可靠传输（数据链路层）",
        "confusion": "都是滑动窗口+超时重传，区别在窗口大小、确认方式与重传范围。",
        "key_points": [
            "停止-等待：发送窗口=1；每发一帧等 ACK；超时重传该帧；信道利用率≈1/(1+2a)，a=传播/发送时延，a 大时极低。",
            "GBN：发送窗口>1、接收窗口=1；累积确认；超时重传『基帧及其后所有帧』；出错后大量重传。",
            "SR：发送窗口与接收窗口均>1；逐帧确认；只重传出错帧；接收方需缓存乱序帧。",
        ],
        "quiz": {
            "question": "信道误码率较高时，为什么 GBN 的效率会明显下降，而 SR 更优？",
            "expected_keywords": ["GBN", "重传", "所有", "SR", "只重传", "出错"],
            "answer": "GBN 采用累积确认，一旦某帧出错，发送方超时后会重传『该帧及其后所有已发未确认帧』，误码率高时大量正确帧被无辜重传，浪费带宽；SR 仅重传真正出错的帧，其余已正确接收的帧不重传，因此高误码率下效率更优。",
        },
    },
    {
        "id": "cn_tcp_udp",
        "title": "TCP vs UDP",
        "category": "运输层协议",
        "confusion": "都位于运输层，但一个可靠一个不可靠，常考『何时用哪个』。",
        "key_points": [
            "TCP：面向连接、可靠交付、字节流、有流量控制与拥塞控制、点对点、首部 20 字节起。",
            "UDP：无连接、尽最大努力交付（不可靠）、数据报、无拥塞控制、支持一对一/一对多/多对多、首部 8 字节。",
            "典型：HTTP/FTP/SMTP 用 TCP；DNS/视频直播/语音用 UDP。",
        ],
        "quiz": {
            "question": "为什么 DNS 主查询通常使用 UDP 而非 TCP？什么情况下 DNS 又会用 TCP？",
            "expected_keywords": ["UDP", "快", "小", "开销", "TCP", "大", "可靠"],
            "answer": "DNS 查询报文通常很小，对时延敏感，UDP 无连接、无握手开销，响应更快；当响应数据超过 512 字节（如区域传送、EDNS 超限）或需要可靠传输时，DNS 改用 TCP。",
        },
    },
    {
        "id": "cn_protocol_service",
        "title": "协议 vs 服务 vs 接口（SAP）",
        "category": "计算机网络体系结构",
        "confusion": "三层概念常被混为一谈，核心在『水平还是垂直』。",
        "key_points": [
            "协议：同一层『水平』实体之间的通信规则（语法/语义/时序）。",
            "服务：下层向相邻『上层』『垂直』提供的功能，通过 SAP 访问。",
            "接口（服务访问点 SAP）：相邻层交换原语的边界；上层看不见下层协议细节（透明）。",
        ],
        "quiz": {
            "question": "为什么说『协议是水平的，服务是垂直的』？下层协议对上层是否可见？",
            "expected_keywords": ["水平", "同一层", "垂直", "下层", "上层", "透明"],
            "answer": "协议是同一层对等实体间的水平约定；服务是下层为上层提供的垂直功能。下层协议的具体实现细节对上层是『透明』的，上层只通过 SAP 使用服务，不必知道下层用了什么协议。",
        },
    },
    {
        "id": "cn_csmacd_ca",
        "title": "CSMA/CD vs CSMA/CA",
        "category": "局域网（MAC 子层）",
        "confusion": "都基于『载波侦听』，但一个有冲突检测、一个避免冲突。",
        "key_points": [
            "CSMA/CD（冲突检测）：用于有线以太网（半双工）；边发送边检测，冲突则立即停止并退避；依赖『能同时收发』检测冲突。",
            "CSMA/CA（冲突避免）：用于无线 802.11；因无线无法边发边可靠收（隐藏站/暴露站），故用 RTS/CTS 预约、ACK 确认、随机退避『尽量避免』而非检测冲突。",
        ],
        "quiz": {
            "question": "为什么无线局域网用 CSMA/CA 而不是 CSMA/CD？",
            "expected_keywords": ["无线", "检测", "隐藏站", "RTS", "CTS", "避免"],
            "answer": "无线信道难以在发送的同时可靠检测到冲突（隐藏站问题、收发功率差大），CSMA/CD 的『冲突检测』在无线环境基本失效；因此 802.11 改用 CSMA/CA，通过 RTS/CTS 预约信道、ACK 确认与随机退避来避免冲突发生。",
        },
    },
    {
        "id": "cn_ip_cidr",
        "title": "分类地址 vs 子网划分 vs CIDR",
        "category": "网络层编址",
        "confusion": "都和 IP 地址结构有关，演进主线是『提高地址利用率』。",
        "key_points": [
            "分类地址：A/B/C 固定网络位 8/16/24；边界死板、大量浪费（如 B 类过大）。",
            "子网划分：在分类地址网络位后再『借位』，用子网掩码细分，主机位减少，但仍在分类框架内。",
            "CIDR：取消分类，用 /n 斜线记法表示前缀长度，支持地址块聚合（路由聚合）与按需分配，大幅减少路由表与浪费。",
        ],
        "quiz": {
            "question": "CIDR 相比传统分类地址，主要在哪两方面提升了 IP 地址的使用效率？",
            "expected_keywords": ["前缀", "任意长度", "聚合", "路由", "浪费"],
            "answer": "CIDR 用 /n 表示任意长度的前缀，可按需分配任意大小地址块，消除分类地址的固定边界浪费；同时支持路由聚合（超网），将多个连续前缀合并为一条路由，显著缩小骨干路由表规模。",
        },
    },
    {
        "id": "cn_devices",
        "title": "集线器 vs 交换机 vs 路由器",
        "category": "网络设备",
        "confusion": "都用于连接设备，但工作层次与隔离能力不同。",
        "key_points": [
            "集线器：物理层；所有端口在同一冲突域、同一广播域；共享带宽、广播转发。",
            "交换机：数据链路层；基于 MAC 转发；每个端口独立冲突域；默认不隔离广播域（VLAN 才隔离）。",
            "路由器：网络层；基于 IP 转发；隔离广播域；连接不同网络、运行路由协议。",
        ],
        "quiz": {
            "question": "交换机能否隔离广播域？要隔离广播域需要什么设备/技术？",
            "expected_keywords": ["不能", "广播域", "路由器", "VLAN"],
            "answer": "普通交换机默认不能隔离广播域，广播帧会转发到所有端口。要隔离广播域需用路由器（每个接口是独立广播域），或在交换机上划分 VLAN 来逻辑隔离广播域。",
        },
    },
    {
        "id": "cn_addresses",
        "title": "MAC 地址 vs IP 地址 vs 端口号",
        "category": "三层地址/标识",
        "confusion": "三者在『哪个层次、标识什么』上常被混淆。",
        "key_points": [
            "MAC 地址：数据链路层；标识局域网内网络接口（网卡）；固化/本地管理；用于同一网段内寻址。",
            "IP 地址：网络层；标识主机到主机的逻辑地址；可随网络改变；用于跨网络路由。",
            "端口号：运输层；标识主机内具体进程（应用）；TCP/UDP 各 65535 个。",
        ],
        "quiz": {
            "question": "IP 数据报在跨越多个网络转发时，其源/目的 IP 地址是否改变？源/目的 MAC 地址是否改变？",
            "expected_keywords": ["IP", "不变", "MAC", "改变", "下一跳"],
            "answer": "源/目的 IP 地址在整个端到端传输中保持不变；而 MAC 地址每经过一个路由器逐跳改写——源 MAC 变为出接口的 MAC、目的 MAC 变为下一跳的 MAC（ARP 解析得到）。",
        },
    },
    {
        "id": "cn_congestion_flow",
        "title": "拥塞控制 vs 流量控制",
        "category": "运输层/网络层调控",
        "confusion": "都限制发送速率，但作用范围与对象不同。",
        "key_points": [
            "拥塞控制：全局视角，防止『过多数据注入网络』导致网络（路由器/链路）过载；涉及发送方与整个网络。",
            "流量控制：点对点，接收方根据自己缓冲区限制发送方速率（滑动窗口），防止『接收方来不及处理』。",
            "TCP 中流量控制用接收窗口 rwnd，拥塞控制用拥塞窗口 cwnd，最终发送窗口=min(rwnd,cwnd)。",
        ],
        "quiz": {
            "question": "TCP 的发送窗口大小最终由哪两个窗口共同决定？它们分别防什么？",
            "expected_keywords": ["rwnd", "cwnd", "接收方", "网络", "拥塞", "流量"],
            "answer": "发送窗口 = min(接收窗口 rwnd, 拥塞窗口 cwnd)。rwnd 来自接收方的流量控制，防接收方缓冲区溢出；cwnd 来自拥塞控制，防整个网络过载。",
        },
    },
    {
        "id": "cn_dns_query",
        "title": "递归查询 vs 迭代查询（DNS）",
        "category": "应用层（域名系统）",
        "confusion": "都为了解析域名，但『谁来逐层追问』不同。",
        "key_points": [
            "递归查询：主机向本地 DNS 请求，本地 DNS 代替主机向根、TLD、权威服务器逐级追问，最终把结果返回主机；本地 DNS 负担重。",
            "迭代查询：本地 DNS 问根，根只回『去问 TLD 的地址』，本地 DNS 自己再去问 TLD，依次迭代；每次请求都由本地 DNS 主动发出。",
            "实际：主机→本地 DNS 多为递归；本地 DNS→上层服务器多为迭代。",
        ],
        "quiz": {
            "question": "在 DNS 解析中，本地域名服务器向根/TLD/权威服务器查询时通常采用递归还是迭代？为什么？",
            "expected_keywords": ["迭代", "本地DNS", "自己", "负担", "根"],
            "answer": "本地 DNS 向上层服务器通常采用迭代查询：根/TLD 只返回下一步该问谁，由本地 DNS 自己继续发请求。这样把逐级追问的负担留在本地 DNS，避免根与 TLD 服务器为每个终端递归追踪，减轻顶级服务器负载。",
        },
    },
    {
        "id": "cn_http_https",
        "title": "HTTP vs HTTPS",
        "category": "应用层（Web）",
        "confusion": "都用于 Web 传输，差别在安全性。",
        "key_points": [
            "HTTP：明文传输，TCP 端口 80；无加密、无完整性校验、无身份认证，易被窃听/篡改。",
            "HTTPS：HTTP over TLS/SSL，TCP 端口 443；提供加密、完整性保护与服务端（及可选客户端）身份认证。",
            "HTTPS 在 HTTP 之前先完成 TLS 握手（协商密钥、验证证书），再加密传输应用数据。",
        ],
        "quiz": {
            "question": "HTTPS 在建立连接时比 HTTP 多了哪一步关键过程？它解决了 HTTP 的哪些风险？",
            "expected_keywords": ["TLS", "握手", "加密", "窃听", "篡改", "认证"],
            "answer": "HTTPS 在传输应用数据前先完成 TLS 握手，协商出会话密钥并验证服务端证书。它解决了 HTTP 明文传输带来的窃听、中间人篡改与身份伪造风险，提供机密性、完整性和身份认证。",
        },
    },
]


def get_pairs() -> list:
    """返回全部辨析对（摘要级：不含 quiz）。"""
    return [
        {
            "id": p["id"],
            "title": p["title"],
            "category": p["category"],
            "confusion": p["confusion"],
            "key_points": p["key_points"],
        }
        for p in CN_DISTINCTION_PAIRS
    ]


def get_pair(pid: str) -> Optional[dict]:
    for p in CN_DISTINCTION_PAIRS:
        if p["id"] == pid:
            return p
    return None


def get_random_quiz(rng: Optional[random.Random] = None) -> dict:
    """随机抽取一道区分自测题，返回题面 + 标准答案关键词 + 答案。"""
    r = rng or random
    p = r.choice(CN_DISTINCTION_PAIRS)
    q = p["quiz"]
    return {
        "pair_id": p["id"],
        "pair_title": p["title"],
        "question": q["question"],
        "expected_keywords": q["expected_keywords"],
        "answer": q["answer"],
    }


def grade_quiz(quiz: dict, user_answer: str) -> dict:
    """对自测作答做确定性关键词判分（不依赖 LLM，可复现）。"""
    ua = (user_answer or "").lower()
    kws = [str(k).lower() for k in quiz.get("expected_keywords", [])]
    hit = [k for k in kws if k in ua]
    total = max(len(kws), 1)
    score = len(hit) / total
    passed = score >= 0.5
    return {
        "score": round(score, 2),
        "passed": passed,
        "hit_keywords": hit,
        "missed_keywords": [k for k in kws if k not in hit],
        "answer": quiz.get("answer", ""),
    }
