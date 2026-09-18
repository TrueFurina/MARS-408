"""草稿 gold 候选题验证：对每题跑真实 retrieve，检查
(1) expected_subject 是否进入 top-10；(2) answer_facts 覆盖率。
只保留双通过的候选，避免把"KB 没有的事实"误当检索失败。
"""
import asyncio, sys, json, re
sys.path.insert(0, ".")
from db.milvus_client import vector_db
from engines.frugal_rag import frugal_rag

SUBJECT_ALIAS = {'tcp':'transport','udp':'transport','ip':'network','routing':'network',
                 'arp':'network','dns':'application','http':'application','ssl':'security'}

CANDIDATES = [
    # computer_network
    {"id":"cn_x1","course":"computer_network","expected_subject":"tcp","question":"TCP 为什么是可靠传输？","answer_facts":["确认","重传","序号"]},
    {"id":"cn_x2","course":"computer_network","expected_subject":"tcp","question":"TCP 三次握手建立连接的过程？","answer_facts":["三次握手","SYN","确认"]},
    {"id":"cn_x3","course":"computer_network","expected_subject":"network","question":"IP 协议的主要特点是什么？","answer_facts":["无连接","不可靠","网络层"]},
    {"id":"cn_x4","course":"computer_network","expected_subject":"application","question":"DNS 域名系统的作用是什么？","answer_facts":["域名","IP","解析"]},
    {"id":"cn_x5","course":"computer_network","expected_subject":"datalink","question":"数据链路层常用的差错控制方法？","answer_facts":["CRC","检错","纠错"]},
    # data_structures
    {"id":"ds_x1","course":"data_structures","expected_subject":"ds_string","question":"KMP 字符串匹配算法的核心思想？","answer_facts":["next数组","前缀","失配"]},
    {"id":"ds_x2","course":"data_structures","expected_subject":"ds_tree","question":"AVL 平衡二叉树如何保持平衡？","answer_facts":["平衡因子","旋转","高度差"]},
    {"id":"ds_x3","course":"data_structures","expected_subject":"ds_search","question":"哈希冲突有哪些解决方法？","answer_facts":["链地址法","开放定址","冲突"]},
    {"id":"ds_x4","course":"data_structures","expected_subject":"ds_graph","question":"图的遍历有哪两种方式？","answer_facts":["DFS","BFS","深度优先"]},
    {"id":"ds_x5","course":"data_structures","expected_subject":"ds_sort","question":"快速排序的基本思想？","answer_facts":["分治","基准","划分"]},
    # computer_organization
    {"id":"co_x1","course":"computer_organization","expected_subject":"co_cpu","question":"CPU 主要由哪几部分组成？","answer_facts":["运算器","控制器","寄存器"]},
    {"id":"co_x2","course":"computer_organization","expected_subject":"co_memory","question":"Cache 高速缓存的作用是什么？","answer_facts":["高速","命中","缓冲"]},
    {"id":"co_x3","course":"computer_organization","expected_subject":"co_cpu","question":"什么是指令周期？包含哪些阶段？","answer_facts":["取指","执行","中断"]},
    {"id":"co_x4","course":"computer_organization","expected_subject":"co_bus","question":"总线按功能可分为哪几类？","answer_facts":["数据","地址","控制"]},
    # operating_system
    {"id":"os_x1","course":"operating_system","expected_subject":"os_process","question":"产生死锁的四个必要条件？","answer_facts":["互斥","占有等待","循环等待"]},
    {"id":"os_x2","course":"operating_system","expected_subject":"os_process","question":"进程和线程的主要区别？","answer_facts":["资源","调度","地址空间"]},
    {"id":"os_x3","course":"operating_system","expected_subject":"os_memory","question":"银行家算法用来做什么？","answer_facts":["死锁","避免","安全"]},
    {"id":"os_x4","course":"operating_system","expected_subject":"os_file","question":"文件的物理结构有哪些？","answer_facts":["连续","链接","索引"]},
]

async def main():
    vector_db.connect()
    keep = []
    for q in CANDIDATES:
        exp = SUBJECT_ALIAS.get(q["expected_subject"], q["expected_subject"])
        res = await frugal_rag.retrieve(q["question"], course=q["course"], top_k=10, use_kg_enhance=False)
        rank = None
        for i, r in enumerate(res):
            if r.get("metadata", {}).get("subject") == exp:
                rank = i + 1; break
        joined = " ".join(r.get("text", "") for r in res)
        _n = lambda s: re.sub(r"\s+", "", s)
        jn = _n(joined)
        miss = [f for f in q["answer_facts"] if _n(f) not in jn]
        fr = 1 - len(miss)/len(q["answer_facts"]) if q["answer_facts"] else 0
        ok = rank is not None and rank <= 10 and fr >= 0.75
        print(f"[{'OK ' if ok else 'XX '}] {q['id']:6s} rank={rank} fr={fr:.0%} miss={miss}")
        if ok:
            keep.append(q)
    print(f"\n保留 {len(keep)}/{len(CANDIDATES)} 题")
    return keep

if __name__ == "__main__":
    k = asyncio.run(main())
    with open("/tmp/gold_keep.json", "w", encoding="utf-8") as f:
        json.dump(k, f, ensure_ascii=False, indent=2)
