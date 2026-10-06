# ============================================================
# 演示种子数据 — 预装学生画像+答题历史+Agent评分
# 使用户登录后即刻看到完整的个性化闭环效果。
# 在主入口 main.py lifespan 中自动调用（首次启动）。
# ============================================================

import logging
from db.user_store import create_user, save_profile, append_quiz_history, save_conversations
from db.pg_client import pg_client

logger = logging.getLogger("netlearn.seed_demo")

# 演示学生账号
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo123456"
DEMO_DISPLAY = "张同学(408考研)"

# 8维度完整画像（赛题要求≥6）
DEMO_PROFILE = {
    "knowledge_base": "intermediate",
    "learning_style": "visual",
    "goal": "exam",
    "weak_points": "子网划分,拥塞控制,页面置换算法",
    "progress": 3,
    "interest_area": "networking",
    "study_time": "2-4h",
    "preferred_difficulty": "medium",
    "course": "computer_network",
    "recent_accuracy": 0.65,
}

# 答題历史（模拟计网各章练习记录）
DEMO_QUIZ_HISTORY = [
    # 概述 - 掌握较好
    {"subject": "overview", "correct": True, "difficulty": "easy"},
    {"subject": "overview", "correct": True, "difficulty": "medium"},
    {"subject": "overview", "correct": True, "difficulty": "easy"},
    # 物理层 - 大部分正确
    {"subject": "physical", "correct": True, "difficulty": "easy"},
    {"subject": "physical", "correct": False, "difficulty": "medium"},
    {"subject": "physical", "correct": True, "difficulty": "medium"},
    # 数据链路层 - 中等
    {"subject": "datalink", "correct": True, "difficulty": "easy"},
    {"subject": "datalink", "correct": False, "difficulty": "medium"},
    {"subject": "datalink", "correct": True, "difficulty": "medium"},
    {"subject": "datalink", "correct": False, "difficulty": "hard"},
    # 网络层 - 薄弱（子网划分）
    {"subject": "network", "correct": True, "difficulty": "easy"},
    {"subject": "network", "correct": False, "difficulty": "medium"},
    {"subject": "network", "correct": False, "difficulty": "medium"},
    {"subject": "network", "correct": False, "difficulty": "hard"},
    {"subject": "network", "correct": True, "difficulty": "easy"},
    # 运输层 - 部分薄弱（拥塞控制）
    {"subject": "transport", "correct": True, "difficulty": "easy"},
    {"subject": "transport", "correct": False, "difficulty": "hard"},
    {"subject": "transport", "correct": True, "difficulty": "medium"},
    {"subject": "transport", "correct": False, "difficulty": "hard"},
    # 数据结构扩展题
    {"subject": "ds_linear", "correct": True, "difficulty": "easy"},
    {"subject": "ds_tree", "correct": True, "difficulty": "medium"},
    {"subject": "ds_sort", "correct": False, "difficulty": "hard"},
    {"subject": "ds_graph", "correct": True, "difficulty": "medium"},
    # 计组扩展题
    {"subject": "co_overview", "correct": True, "difficulty": "easy"},
    {"subject": "co_data", "correct": False, "difficulty": "hard"},
    {"subject": "co_memory", "correct": True, "difficulty": "medium"},
    {"subject": "co_cpu", "correct": False, "difficulty": "hard"},
    # OS扩展题
    {"subject": "os_overview", "correct": True, "difficulty": "easy"},
    {"subject": "os_process", "correct": True, "difficulty": "medium"},
    {"subject": "os_process", "correct": False, "difficulty": "hard"},
    {"subject": "os_memory", "correct": False, "difficulty": "medium"},
]

# Agent 历史评分（使 GOMARL 动态权重有实际数据可算）
DEMO_AGENT_SCORES = [
    ("teacher", 8.5), ("teacher", 8.0), ("teacher", 9.0),
    ("quizmaster", 7.5), ("quizmaster", 7.0), ("quizmaster", 8.0),
    ("media_designer", 6.5), ("media_designer", 7.0), ("media_designer", 7.5),
    ("extension", 8.0), ("extension", 7.5), ("extension", 8.5),
    ("ppt_designer", 7.0), ("ppt_designer", 6.5), ("ppt_designer", 7.5),
    ("code_practice", 6.0), ("code_practice", 6.5), ("code_practice", 7.0),
]

# 学习路径推荐资源（真实链接到 Agent 生成端点）
DEMO_RESOURCE_LINKS = {
    "计算机网络概述": {
        "doc": "可用 /api/agents/generate-resource?topic=计算机网络体系结构 生成讲解文档",
        "quiz": "可用 /api/rag/generate?subject=overview 生成练习题",
        "extension": "RFC 1180 TCP/IP 入门指南",
    },
    "网络层": {
        "doc": "可用 /api/agents/generate-resource?topic=IP地址与子网划分 生成讲解",
        "quiz": "可用 /api/rag/generate?subject=network 生成子网划分练习题",
        "extension": "《TCP/IP详解》卷一 第3章 IP协议",
    },
    "运输层": {
        "doc": "可用 /api/agents/generate-resource?topic=TCP拥塞控制 生成讲解",
        "quiz": "可用 /api/rag/generate?subject=transport 生成练习题",
        "extension": "《计算机网络》第5章 运输层",
    },
    "数据结构": {
        "doc": "可用 /api/agents/generate-resource?topic=二叉树遍历 生成讲解",
        "quiz": "可用 /api/rag/generate?subject=ds_tree 生成练习题",
        "extension": "《算法导论》第10章 二叉树",
    },
    "计算机组成原理": {
        "doc": "可用 /api/agents/generate-resource?topic=CPU流水线 生成讲解",
        "quiz": "可用 /api/rag/generate?subject=co_cpu 生成练习题",
        "extension": "《计算机组成与设计》第4章 流水线",
    },
    "操作系统": {
        "doc": "可用 /api/agents/generate-resource?topic=页面置换算法 生成讲解",
        "quiz": "可用 /api/rag/generate?subject=os_memory 生成练习题",
        "extension": "《现代操作系统》第3章 内存管理",
    },
}


def seed_demo_data():
    """创建演示用户和种子数据（幂等：已存在则跳过）"""
    try:
        user = create_user(DEMO_USERNAME, DEMO_PASSWORD, DEMO_DISPLAY, role="student")
        user_id = user["id"]
        logger.info(f"演示用户已创建: {DEMO_USERNAME} (id={user_id})")
    except ValueError:
        # 用户已存在，查回 user_id
        from db.user_store import authenticate
        u = authenticate(DEMO_USERNAME, DEMO_PASSWORD)
        if not u:
            logger.warning("演示用户存在但无法认证")
            return
        user_id = u["id"]
        logger.info(f"演示用户已存在: {DEMO_USERNAME}")

    # 写入画像
    save_profile(user_id, DEMO_PROFILE)
    logger.info(f"演示用户画像已写入: {len(DEMO_PROFILE)} 个维度")

    # 写入答题历史
    append_quiz_history(user_id, DEMO_QUIZ_HISTORY)
    logger.info(f"演示用户答题历史已写入: {len(DEMO_QUIZ_HISTORY)} 条")

    # 写入 Agent 评分（需先连接 pg_client）
    try:
        pg_client.connect()
        for agent_name, score in DEMO_AGENT_SCORES:
            pg_client.log_agent_score(agent_name, score, "seed_demo", "demo_seed_data")
        logger.info(f"Agent 评分已写入: {len(DEMO_AGENT_SCORES)} 条")
    except Exception as e:
        logger.warning(f"Agent 评分写入失败（非阻塞）: {e}")

    # 写入演示对话历史（供 Dashboard 最近学习展示）
    demo_conversations = [
        {
            "id": "demo_conv_1",
            "title": "TCP三次握手与可靠传输",
            "messages": [
                {"role": "user", "content": "请讲解TCP三次握手的过程"},
                {"role": "assistant", "content": "TCP三次握手是建立可靠连接的关键过程：\n\n1. 客户端发送SYN报文(seq=x)\n2. 服务器回复SYN+ACK报文(seq=y,ack=x+1)\n3. 客户端发送ACK报文(seq=x+1,ack=y+1)\n\n握手完成后连接建立，双方进入ESTABLISHED状态。\n\n💡 提示：你可以点击消息旁的🔊按钮听语音讲解。"},
            ],
        },
        {
            "id": "demo_conv_2",
            "title": "子网划分练习",
            "messages": [
                {"role": "user", "content": "帮我讲解子网划分的基本步骤"},
                {"role": "assistant", "content": "子网划分四步法：\n1. 确定需要的子网数\n2. 计算需借用的主机位数\n3. 计算新子网掩码\n4. 列出各子网的网络地址、广播地址和可用主机范围\n\n例如：对于192.168.1.0/24，需要4个子网：\n- 借2位，新掩码255.255.255.192\n- 子网0: 192.168.1.0/26\n- 子网1: 192.168.1.64/26\n- 子网2: 192.168.1.128/26\n- 子网3: 192.168.1.192/26"},
            ],
        },
        {
            "id": "demo_conv_3",
            "title": "TCP拥塞控制算法",
            "messages": [
                {"role": "user", "content": "TCP拥塞控制有哪些算法？"},
                {"role": "assistant", "content": "TCP拥塞控制主要有四种算法：\n\n1. **慢启动**：从cwnd=1开始，每收到ACK翻倍，指数增长\n2. **拥塞避免**：达到慢启动阈值后，线性增长\n3. **快重传**：收到3个冗余ACK立即重传，不等待超时\n4. **快恢复**：快重传后，将cwnd减半并进入拥塞避免"},
            ],
        },
        {
            "id": "demo_conv_4",
            "title": "操作系统页面置换",
            "messages": [
                {"role": "user", "content": "讲解页面置换算法"},
                {"role": "assistant", "content": "常见页面置换算法：\n\n1. **FIFO**：先进先出，实现简单但可能有Belady异常\n2. **LRU**：最近最久未使用，性能好但实现成本高\n3. **Clock**：近似LRU，使用引用位，折中方案\n4. **OPT**：最优置换，理论不可实现，作为性能基准"},
            ],
        },
    ]
    save_conversations(user_id, demo_conversations)
    logger.info(f"演示对话已写入: {len(demo_conversations)} 条")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    seed_demo_data()
    print("演示种子数据写入完成。登录账号: demo / demo123456")
