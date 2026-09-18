# -*- coding: utf-8 -*-
"""408四科教材批量导入脚本 — 读取PDF → 分块 → 写入VectorDB(Milvus/InMemory)"""
import os, sys, re, json, hashlib, logging, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("textbook_import")

# ── 教材路径配置 ──
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "documents", "教材")

TEXTBOOKS = [
    # (目录名, 科目ID, 科目名, 章节映射key)
    ("数据结构", "data_structures", "数据结构"),
    ("计算机组成原理", "computer_organization", "计算机组成原理"),
    ("操作系统", "operating_system", "操作系统"),
    ("计算机网络", "computer_network", "计算机网络"),
]

# ── 章节分类关键词（支持多教材合并） ──
SUBJECT_CHAPTERS = {
    "computer_network": [
        (["概述","体系结构","OSI","TCP/IP","分层","协议","分组交换","性能指标","时延","带宽","吞吐量"], "overview", "第1章 概述"),
        (["物理层","传输媒体","双绞线","光纤","信道","复用","FDM","TDM","WDM","CDM","编码","调制","奈氏","香农"], "physical", "第2章 物理层"),
        (["数据链路","链路层","MAC","帧","封装","差错","CRC","CSMA/CD","以太网","VLAN","802","交换机","PPP","HDLC"], "datalink", "第3章 数据链路层"),
        (["网络层","IP地址","子网","CIDR","ARP","路由","RIP","OSPF","BGP","NAT","IPv6","分片","ICMP","路由器"], "network", "第4章 网络层"),
        (["运输层","传输层","UDP","TCP","报文段","可靠传输","流量控制","拥塞控制","慢启动","三次握手","四次挥手","端口"], "transport", "第5章 运输层"),
        (["应用层","DNS","域名","HTTP","HTTPS","FTP","SMTP","POP3","IMAP","WWW","URL","DHCP","CDN"], "application", "第6章 应用层"),
        (["网络安全","加密","密钥","公钥","私钥","RSA","DES","AES","数字签名","证书","CA","SSL","TLS","防火墙","DDoS"], "security", "第7章 网络安全"),
    ],
    "data_structures": [
        (["线性表","顺序表","链表","单链表","双链表","循环链表"], "ds_linear", "第2章 线性表"),
        (["栈","队列","栈和队列","递归"], "ds_stack", "第3章 栈和队列"),
        (["串","字符串","模式匹配","KMP"], "ds_string", "第4章 串"),
        (["树","二叉树","遍历","BST","AVL","红黑树","哈夫曼","堆"], "ds_tree", "第5章 树与二叉树"),
        (["图","遍历","DFS","BFS","最小生成树","Prim","Kruskal","最短路径","Dijkstra","拓扑"], "ds_graph", "第6章 图"),
        (["查找","搜索","二分","BST","散列","哈希"], "ds_search", "第7章 查找"),
        (["排序","插入","交换","冒泡","快速","选择","堆排序","归并","基数"], "ds_sort", "第8章 排序"),
    ],
    "computer_organization": [
        (["概述","冯诺依曼","计算机系统","性能","Amdahl"], "co_overview", "第1章 计算机系统概述"),
        (["数据表示","原码","反码","补码","移码","浮点","IEEE754","运算","ALU"], "co_data", "第2章 数据表示与运算"),
        (["存储","存储器","Cache","主存","ROM","RAM","虚拟存储器","页式","段式"], "co_memory", "第3章 存储系统"),
        (["指令","ISA","寻址","CISC","RISC","MIPS"], "co_isa", "第4章 指令系统"),
        (["CPU","处理器","数据通路","流水线","冒险","控制器","微程序"], "co_cpu", "第5章 中央处理器"),
        (["总线","系统总线","通信","仲裁"], "co_bus", "第6章 总线"),
        (["输入输出","I/O","中断","DMA","接口"], "co_io", "第7章 输入输出系统"),
    ],
    "operating_system": [
        (["概述","OS","操作系统","发展","分类","系统调用"], "os_overview", "第1章 操作系统概述"),
        (["进程","线程","调度","同步","互斥","死锁","信号量","PV","管程"], "os_process", "第2章 进程管理"),
        (["内存","分页","分段","虚拟内存","页面置换","LRU","FIFO","TLB"], "os_memory", "第3章 内存管理"),
        (["文件","文件系统","目录","磁盘","FCB"], "os_file", "第4章 文件管理"),
        (["I/O","输入输出","SPOOLing","缓冲","磁盘调度"], "os_io", "第5章 输入输出管理"),
    ],
}

def extract_pdf_text(pdf_path: str) -> str:
    """使用 pymupdf 提取 PDF 文本"""
    try:
        import fitz
    except ImportError:
        logger.error("需要 pymupdf: pip install pymupdf")
        return ""
    try:
        doc = fitz.open(pdf_path)
        text_parts = [page.get_text() for page in doc if page.get_text().strip()]
        doc.close()
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"PDF 解析失败 {pdf_path}: {e}")
        return ""

def semantic_chunk(text: str, max_chars: int = 800) -> list[str]:
    """语义分块"""
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if len(paragraphs) <= 1:
        return paragraphs if paragraphs else [text]
    chunks = []
    current = paragraphs[0]
    for para in paragraphs[1:]:
        should_split = True
        if len(current) < 120:
            should_split = False
        if len(current) + len(para) > max_chars:
            should_split = True
        if para.startswith(("如", "例如", "包括", ":", "：", "-", " ")):
            should_split = False
        if should_split:
            chunks.append(current.strip())
            current = para
        else:
            current += "\n" + para
    if current.strip():
        chunks.append(current.strip())
    return chunks if chunks else [text]

def detect_chapter(text: str, subject_map: list) -> tuple:
    """关键词检测章节"""
    for keywords, chapter_id, chapter_name in subject_map:
        for kw in keywords:
            if kw in text[:500]:
                return chapter_id, chapter_name
    return subject_map[0][1], subject_map[0][2]  # 默认第一章节

def find_pdfs(dir_name: str, subject_id: str) -> list[str]:
    """查找指定科目的 PDF 教材文件"""
    # 先试中文目录名，再试英文
    for name in [dir_name, subject_id]:
        subject_dir = os.path.join(DOCS_DIR, name)
        if os.path.exists(subject_dir):
            pdfs = []
            for root, _, files in os.walk(subject_dir):
                for f in files:
                    if f.lower().endswith('.pdf') and '真题' not in f and '试题' not in f and '大纲' not in f:
                        pdfs.append(os.path.join(root, f))
            return pdfs
    logger.warning(f"目录不存在: {os.path.join(DOCS_DIR, dir_name)}")
    return []

def import_subject(dir_name: str, subject_id: str, subject_name: str, max_chars: int = 800) -> int:
    """导入单个科目的所有 PDF，追加写入 vectordb_data netlearn_kb.json"""
    from db.embedder import embed_batch
    import json, hashlib

    subject_map = SUBJECT_CHAPTERS.get(subject_id, [])
    if not subject_map:
        logger.warning(f"{subject_name}: 无章节映射")
        return 0
    pdfs = find_pdfs(dir_name, subject_id)
    if not pdfs:
        logger.warning(f"{subject_name}: 未找到教材 PDF")
        return 0

    # 读取已有 ID 用于去重（只读，不影响持久化）
    from db.milvus_client import vector_db
    persist_file = os.path.join(os.path.dirname(__file__), "vectordb_data", "netlearn_kb.json")
    seen_ids = set()
    if os.path.exists(persist_file):
        try:
            with open(persist_file, "r", encoding="utf-8") as f:
                seen_ids = set(json.load(f).get("ids", []))
            logger.info(f"  已有持久化数据: {len(seen_ids)} 条")
        except Exception:
            pass

    total_chunks = 0

    for pdf_path in pdfs:
        logger.info(f"处理: {os.path.basename(pdf_path)} ({os.path.getsize(pdf_path)/1024/1024:.0f}MB)")
        text = extract_pdf_text(pdf_path)
        if not text:
            continue
        logger.info(f"  提取文本: {len(text)} 字符")

        raw_chunks = semantic_chunk(text, max_chars)
        valid_chunks = []
        for i, chunk in enumerate(raw_chunks):
            if len(chunk) < 30:
                continue
            chapter_id, chapter_name = detect_chapter(chunk, subject_map)
            cid = f"textbook_{subject_id}_{hashlib.md5(chunk.encode()).hexdigest()[:12]}"
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            valid_chunks.append({
                "id": cid,
                "text": chunk,
                "metadata": {
                    "subject": subject_id,
                    "chapter": chapter_id,
                    "chapter_name": chapter_name,
                    "type": "knowledge_point",
                    "source": os.path.basename(pdf_path),
                }
            })
        if not valid_chunks:
            logger.info(f"  无新块")
            continue

        logger.info(f"  新分块: {len(valid_chunks)} 个（计算 E5 嵌入中...）")
        texts = [c["text"] for c in valid_chunks]
        try:
            embeddings = embed_batch(texts)
        except Exception as e:
            logger.error(f"  E5 嵌入失败: {e}")
            continue

        # 通过 VectorDB 层写入（filelock + 批量延迟落盘，避免整文件覆盖）
        for c, emb in zip(valid_chunks, embeddings):
            c["embedding"] = emb
        vector_db.insert("netlearn_kb", valid_chunks, save=False)

        total_chunks += len(valid_chunks)
        logger.info(f"  累计: {total_chunks} 新块")

    if total_chunks > 0:
        vector_db.flush("netlearn_kb")
        final_count = vector_db.count("netlearn_kb")
        logger.info(f"  已通过 VectorDB 持久化，知识库总量: {final_count} 条")
    else:
        logger.info(f"  无新数据需要保存")

    return total_chunks

def main():
    logger.info("=" * 50)
    logger.info("408 四科教材批量导入")
    logger.info("=" * 50)

    total_all = 0
    for dir_name, subject_id, subject_name in TEXTBOOKS:
        subject_map = SUBJECT_CHAPTERS.get(subject_id, [])
        if not subject_map:
            logger.warning(f"跳过 {subject_name}: 无章节映射")
            continue
        logger.info(f"\n--- {subject_name} ---")
        count = import_subject(dir_name, subject_id, subject_name)
        total_all += count
        logger.info(f"  → 累计 {count} 块")

    from db.milvus_client import vector_db
    final = vector_db.count("netlearn_kb")
    logger.info(f"\n{'='*50}")
    logger.info(f"导入完成! 总计新增: {total_all} 块")
    logger.info(f"知识库总量: {final} 条文档")

if __name__ == "__main__":
    import sys, subprocess
    from pathlib import Path
    print("[DEPRECATED] import_textbook.py 不再直写向量库；已改为通过后端导入队列导入。")
    print("  等效命令： python tools/import_client.py --type textbook")
    client = Path(__file__).parent / "tools" / "import_client.py"
    sys.exit(subprocess.call([sys.executable, str(client), "--type", "textbook"]))
