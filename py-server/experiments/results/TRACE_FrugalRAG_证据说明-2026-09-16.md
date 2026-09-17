# FrugalRAG 真实检索 Trace 证据（2026-09-16）

- 时间：2026-09-16T15:47:35
- 端点：POST http://127.0.0.1:8002/api/rag/search
- 登录状态：200（demo/demo123456，token=已获取）
- 检索状态：200
- 查询：TCP三次握手过程（course=computer_network, top_k=5）
- 返回条目数：5

## 返回片段（前 5 条，含真实 score）
1. score=0.9164596199989319 | TCP三次握手：①客户端→SYN(seq=x)→服务器 ②服务器→SYN+ACK(seq=y,ack=x+1)→客户端 ③客户端→ACK(seq=x+1,ack
2. score=0.6529241299052588 | TCP连接释放四步挥手：1.A→FIN→B 2.B→ACK→A（B进入CLOSE_WAIT，A进入FIN_WAIT）3.B→FIN→A 4.A→ACK→B（A进
3. score=0.6735284092890995 | TLS 1.3握手(1-RTT)：ClientHello(含支持的密码套件+key_share)→ServerHello(选定套件+key_share)→双方算
4. score=0.9372814941235532 | [choice] TCP三次握手中，客户端发送的第一个报文段的标志位是？ 答案: 1 来源: 计算机网络教程 第5章
5. score=0.6432267328018516 | TCP可靠传输四大机制：(1)序号与确认——发送方为每个字节编号，接收方用累计确认(ACK)告知期望接收的下一字节序号；(2)重传——超时重传+快速重传(收到3

> 原始 JSON 见同目录 trace_frugalrag_search_2026-09-16.json（含完整响应，未裁剪）。