# ============================================================
# eval_teaching_mode_prompt.py — teaching_mode → 生成 prompt 接线基线对比
#
# 目的：policy_action.teaching_mode 接入 teacher prompt 后，
#       **产物是否真的按要求的讲解顺序组织**（接线改产物 ⇒ 必须有基线对比）。
#
# 对比臂（同一 topic × 同一 profile × 同一 knowledge_context，只差讲解顺序指令）：
#   baseline    不注入（= 接线前行为）
#   sequential  概念→原理→应用
#   example_first  例子先行（规则版在薄弱点≥2 时真实产出的取值）
#   analogy     类比搭桥（仅 MAPPO 神经路径可能产出）
#
# 指标：**确定性结构探针**，不是 LLM 自评（自评不可复现且易被表面措辞骗）：
#   - order_compliance：是否满足该 mode 的顺序特征（例：example_first 要求
#     首个例子标记出现在首个定义标记之前）
#   - analog_marker_hit：类比标记命中（analogy 臂专用）
#   - degradation_guard：是否保住 TEACHER_START 标记 / 非空 / 未明显截断
#     （顺序改好了但把内容写坏了 = 更差，必须一起看）
#
# 诚实性约定：
#   - 每个 trial 增量 append + fsync（崩了不丢已跑数据，也不靠内存里的总数下结论）
#   - 每格同记 successes / trials / errors —— errors>0 时成功率是下界，
#     "全挂"与"顺序没生效"必须可区分（项目硬纪律）
#   - 判定门禁显式列出 errors；errors 占比过高直接判 INCONCLUSIVE 而非 PASS/FAIL
#
# 运行：.venv\Scripts\python.exe experiments\eval_teaching_mode_prompt.py
#       [--topics N] [--repeats N] [--modes a,b,c] [--provider deepseek] [--dry-run]
# 产物：experiments/results/teaching_mode_prompt_eval_YYYYMMDD_HHMMSS.jsonl + .summary.json
# ============================================================

import argparse
import asyncio
import datetime
import json
import os
import statistics
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from agents.generator_cluster import (  # noqa: E402
    TEACHING_MODE_INSTRUCTIONS,
    _build_agent_prompt,
)
from db.llm_provider import LLMProvider  # noqa: E402
from prompts import TEACHER_PROMPT  # noqa: E402

# ── 探针词表（中文讲解文档的显式结构标记）──
EXAMPLE_MARKERS = ["例", "比如", "举例", "典型题", "设想", "想象", "来看一个", "试想", "一道题", "这道"]
# 定义类标记：实测deepseek-chat 的讲解文档**极少使用"定义/是指"字面**，
# 因此该词表只作辅助；主判据是下面的结构标记（首段形态 + 引导句式）。
DEFINITION_MARKERS = ["定义", "是指", "称为", "所谓", "本质", "是一种", "指的是"]
ANALOGY_MARKERS = ["类比", "好比", "相当于", "就像", "类似于", "打个比方", "等同于"]
# 结构性标记：讲解文档开头出现这类形态，说明"先给具体场景/例子"而非"先下定义"。
# ⚠️ 词表来自**真实产物实测归并**（2026-10-14 首轮 36 次调用）：模型实际用的引导形态
# 有「从一个具体例子说起」「从一道典型题说起」「先看一道典型题」「引入题」等，
# 初版词表漏掉这些 → 明明照做了却被判不合规（合规率被系统性低估）。
OPENING_STRUCTURE = [
    "我们先", "先看", "先来", "先说一个", "举个", "设想", "想象一下", "想象一个",
    "试想", "从一个问题", "从一个", "有一种情况", "你会发现", "有没有想过",
    "从一道", "从某", "从一则", "从某个", "引入题", "引入一个", "导入",
]
# 概念陈述句（"先下定义"的形态）。
# ⚠️ **刻意不含 "定义"**：实测产物里"定义"多出现在代码语境（如"定义全局变量 int cnt"），
# 会把"先出题再讲解"误判成"先下定义"。首轮实测中3 例误判全部源于此。
CONCEPT_LEAD = [
    "是一种", "指的是", "的核心", "由", "包括", "负责", "全称", "简称",
    "是",  # 概念陈述几乎必有"X 是…"，故允许单字；它在 120 字窗口内出现即算概念先
]
# 首段窗口收紧到120 字：更贴近"开头形态"，避免正文中间的举例被误判为开头形态
HEAD_WINDOW = 120

# 教师讲解文档的硬要求（来自 TEACHER_PROMPT），用于 degradation_guard
MIN_BODY_CHARS = 150
TEACHER_START = "---TEACHER_START---"

# 固定 topic 矩阵：408 真实考点，跨层次（基础/进阶），不依赖检索（隔离检索噪声）
TOPIC_MATRIX = [
    {
        "topic": "TCP 拥塞控制的慢开始与拥塞避免",
        "chapter": "计算机网络 / 传输层",
        "knowledge_context": (
            "【知识库】TCP 拥塞控制中，cwnd（拥塞窗口）是发送方维持的、在途报文段数上限。"
            "慢开始阶段 cwnd 从 1 个 MSS 开始按指数增长（每经过一个 RTT 翻倍），"
            "到达 ssthresh 后进入拥塞避免阶段，改为每个 RTT 加 1 个 MSS 的线性增长。"
            "检测到丢包（超时或三次重复 ACK）时 ssthresh 减半。"
        ),
    },
    {
        "topic": "进程与线程的区别及地址空间隔离",
        "chapter": "操作系统 / 进程管理",
        "knowledge_context": (
            "【知识库】进程是程序的一次执行实例，拥有独立的虚拟地址空间；"
            "线程是进程内的执行流，共享所属进程的地址空间与全局变量，"
            "但各自拥有独立的程序计数器、寄存器和栈。线程切换开销远小于进程切换，"
            "但共享内存要求同步机制（互斥锁/信号量）避免竞态条件。"
        ),
    },
    {
        "topic": "B+ 树索引与范围查询",
        "chapter": "数据结构 / 查找与索引",
        "knowledge_context": (
            "【知识库】B+ 树是数据库常用多级索引：非叶结点只存索引键，"
            "叶结点串成有序链表且存放全部记录。B+ 树高度低（3~4 层即可存千万级记录），"
            "扇出大，因此磁盘 IO 次数少。范围查询只需定位第一个键后沿叶链顺序扫描，"
            "这是 B+ 树相对 B 树、红黑树的核心优势。"
        ),
    },
    {
        "topic": "虚拟内存的页表与地址转换",
        "chapter": "操作系统 / 内存管理",
        "knowledge_context": (
            "【知识库】虚拟内存通过页表把虚拟地址的页号映射为物理块号。"
            "MMU 借助 TLB（快表）缓存近期页表项以避免每次访存都访问内存。"
            "缺页时由操作系统调入所需物理页，页面置换算法（如 LRU、Clock）决定淘汰谁。"
        ),
    },
]

# 学生画像矩阵。🔴 **profile 的薄弱点必须与所配 topic 领域一致**——
# 首轮实测教训：weak2 画像写"拥塞窗口/慢开始"(TCP)却被配到「进程与线程」话题，
# 模型开篇就纠正"话题与薄弱点错位"（3/6 条），于是没有先出题；
# 那不是"顺序指令失效"，是**输入自相矛盾**。故按 topic 领域配薄弱点。
PROFILE_MATRIX = [
    {
        "id": "weak",
        "profile": {
            "learning_style": "reading",
            "knowledge_base": "beginner",
            # 占位：由 profile_for() 按 topic 领域填充，见下
            "weak_points": "",
        },
        "diagnosis": {"recommended_focus": []},
    },
    {
        "id": "strong",
        "profile": {
            "learning_style": "reading",
            "knowledge_base": "advanced",
            "weak_points": "",
        },
        "diagnosis": {"recommended_focus": []},
    },
]

# 每个 topic 声明自己的薄弱点组合：≥2 个 ⇒ 规则版判定 example_first（接线真实触发）
TOPIC_WEAK_POINTS = {
    "TCP 拥塞控制的慢开始与拥塞避免": "拥塞窗口,慢开始与拥塞避免",
    "进程与线程的区别及地址空间隔离": "线程共享内存,进程地址空间隔离",
    "B+ 树索引与范围查询": "B+树扇出与树高,叶结点链表",
    "虚拟内存的页表与地址转换": "页表与地址转换,TLB 快表",
}


def profile_for(topic: dict, prof: dict) -> dict:
    """按 topic 领域填充薄弱点，并给 weak 画像生成 ≥2 个薄弱点。

    strong 画像保持 0 薄弱点（⇒ teaching_mode=sequential），作对照。
    """
    p = {**prof["profile"]}
    if prof["id"] == "weak":
        wps = TOPIC_WEAK_POINTS.get(topic["topic"], "要点甲,要点乙")
        p["weak_points"] = wps
        first = wps.split(",")[0]
        p["diagnosis"] = {"recommended_focus": [first]}
    else:
        p["diagnosis"] = {"recommended_focus": []}
    return p

MODES = ["baseline", "sequential", "example_first", "analogy"]


def _first_hit_pos(text: str, markers: list) -> int:
    """返回任一标记首次出现的位置；无命中返回 -1。取最早的那个标记。"""
    best = -1
    for m in markers:
        p = text.find(m)
        if p >= 0 and (best < 0 or p < best):
            best = p
    return best


def probe(body: str, mode: str) -> dict:
    """对生成产物做确定性结构探针。

    ⚠️ 判据设计教训（2026-10-14 首轮实测）：初版要求"例子标记与定义标记都命中"
    才判合规，而 deepseek-chat 的讲解文档几乎不使用"定义/是指"字面
    ⇒ 定义标记恒-1 ⇒ example_first 臂永远"不可观测"，看起来像"顺序没生效"，
    实为探针照不到。第二版改为**首段结构形态**判据（看开头 N 字是否已是举例/类比
    引导），不依赖任何单个词表命中；定义标记降级为辅助信息。

    仍刻意不认"把指令原句抄进开头"——原句复述不会让首段变成引导句式。
    """
    body = body or ""
    ex = _first_hit_pos(body, EXAMPLE_MARKERS)
    dfn = _first_hit_pos(body, DEFINITION_MARKERS)
    ana = _first_hit_pos(body, ANALOGY_MARKERS)

    # 首段窗口：正文前120 字（去掉 TEACHER_START 标记后）
    body_only = body.split(TEACHER_START, 1)[1] if TEACHER_START in body else body
    head = body_only.strip()[:HEAD_WINDOW]
    opening = _first_hit_pos(head, OPENING_STRUCTURE)
    concept = _first_hit_pos(head, CONCEPT_LEAD)

    # 判定统一为「引导句是否先于概念陈述句」。
    # 只看 opening>=0 会假绿（定义先行但正文稍后又有"我们先"，见探针自证）；
    # 故必须比较相对位置：引导在前 ⇒ 例题先行；概念在前 ⇒ 顺序讲解。
    # 两个都没命中 ⇒ 不可观测（既不像例子先行也不像概念先行），记为None。
    if mode == "example_first":
        # 引导先于概念 → 合规；概念明确先于引导 → 明确不合规；
        # 只命中概念 / 只命中引导 / 都不命中 → 判据力不足，记 None（不计入分母）
        compliant = True if opening >= 0 and (concept < 0 or opening < concept) else (
            False if concept >= 0 and (opening < 0 or concept < opening) else None)
    elif mode == "analogy":
        compliant = True if ana >= 0 or (opening >= 0 and (concept < 0 or opening < concept)) else (
            False if concept >= 0 and (opening < 0 or concept < opening) else None)
    elif mode == "sequential":
        # 顺序讲解：概念陈述先于场景引入（concept < opening）→ 合规；
        # 引导句明确在概念句之前 → 明确不合规（不能因"两者都命中"就记成中性：
        # 那会让"确实先举例了"被算进分母之外，等于把反例藏起来）。
        compliant = True if concept >= 0 and (opening < 0 or concept < opening) else (
            False if opening >= 0 and (concept < 0 or opening < concept) else None)
    else:  # baseline：只测护栏
        compliant = None

    observable = compliant is not None

    # ── 主指标 head_opens_with_scenario：模式无关，所有臂同尺量 ──
    # 🔴 教训（2026-10-14 首轮）：只用上面那个"各臂按自己的定义判合规"的合规率
    # 是**循环论证**——baseline 的 compliant 被设为 None（可比性0），于是每臂都在
    # 各自标准下自证，汇总看起来"所有臂都合规"，测不出指令效果。
    # 主指标只问一个与 mode 无关的问题：**正文开头是不是已经在讲具体场景/例子**。
    # baseline 与各臂同尺量，差值才是指令的效果。
    head_opens_with_scenario = opening >= 0

    has_start = TEACHER_START in body
    degraded = (not has_start) or len(body_only.strip()) < MIN_BODY_CHARS

    return {
        "mode": mode,
        "order_compliant": compliant,
        "order_observable": observable,
        "example_pos": ex,
        "definition_pos": dfn,
        "analogy_pos": ana,
        "opening_structure_pos": opening,
        "concept_pos": concept,
        "head_opens_with_scenario": head_opens_with_scenario,
        "has_teacher_start": has_start,
        "body_chars": len(body_only.strip()),
        "degraded": degraded,
        # 正文落盘：探针必须可被人工核对，否则"合规率"是不可证伪的数字
        "body_excerpt": body_only.strip()[:600],
    }


async def run_trial(llm, topic, prof, mode, provider_note) -> dict:
    """跑一次生成并探针。异常不外泄成 traceback，返回结构化 error 计数。"""
    prof_map = profile_for(topic, prof)
    plan = {
        "topic": topic["topic"],
        "chapter": topic["chapter"],
        "difficulty": "medium",
        "teacher_task": "生成该知识点的讲解文档",
    }
    instruction = "" if mode == "baseline" else TEACHING_MODE_INSTRUCTIONS[mode]
    user_prompt = _build_agent_prompt(
        "teacher", plan, prof_map, topic["knowledge_context"],
        prof_map["diagnosis"], "", instruction,
    )
    rec = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "topic": topic["topic"], "profile": prof["id"], "mode": mode,
        "weak_points": prof_map.get("weak_points", ""),
        "provider_note": provider_note, "prompt_extra_chars": len(instruction),
    }
    try:
        text = await llm.text_completion(
            TEACHER_PROMPT, user_prompt, temperature=0.7, max_tokens=2000, timeout=90,
        )
    except Exception as e:  # noqa: BLE001 —— 基础设施故障必须留痕，不得伪装成结论
        rec.update({"ok": False, "error": f"{type(e).__name__}: {e}"[:300]})
        return rec
    if not text or not text.strip():
        rec.update({"ok": False, "error": "empty_response"})
        return rec
    rec.update({"ok": True})
    rec.update(probe(text, mode))
    return rec


def _wilson(k: int, n: int, z: float = 1.96):
    """Wilson 95% 区间。小样本必需——点估计会把3/6 与 6/6 都显示成"看起来不错"。"""
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return (round(max(0.0, center - half), 3), round(min(1.0, center + half), 3))


def summarize_primary(records: list) -> dict:
    """主指标：**所有臂同尺量**的「开头即场景引入率」+ Wilson 区间 + 对 baseline 的差。

    这是唯一能回答"指令有没有起作用"的统计量。各臂按自身定义的自证合规率
    只作参考（`cells[].compliance_rate`），不进主指标。
    """
    by_mode: dict = {}
    for r in records:
        if not r.get("ok"):
            continue
        m = r["mode"]
        c = by_mode.setdefault(m, {"trials": 0, "head_scenario": 0, "errors": 0})
        c["trials"] += 1
        if r.get("head_opens_with_scenario"):
            c["head_scenario"] += 1
    for r in records:
        if not r.get("ok"):
            by_mode.setdefault(r["mode"], {"trials": 0, "head_scenario": 0, "errors": 0})
            by_mode[r["mode"]]["errors"] += 1

    out = {}
    for m, c in by_mode.items():
        ci = _wilson(c["head_scenario"], c["trials"])
        out[m] = {
            "trials": c["trials"],
            "errors": c["errors"],
            "head_scenario_hits": c["head_scenario"],
            "rate": round(c["head_scenario"] / c["trials"], 4) if c["trials"] else None,
            "wilson95": ci,
        }
    base = out.get("baseline", {}).get("rate")
    if base is not None:
        for m, c in out.items():
            c["delta_vs_baseline"] = None if c["rate"] is None else round(c["rate"] - base, 4)
    return out


def summarize(records: list) -> dict:
    """按 (profile, mode) 汇总。同记 trials / ok / errors / compliant。"""
    cells: dict = {}
    for r in records:
        k = f"{r['profile']}|{r['mode']}"
        c = cells.setdefault(k, {
            "profile": r["profile"], "mode": r["mode"],
            "trials": 0, "ok": 0, "errors": 0,
            "compliant": 0, "observable": 0, "degraded": 0,
            "body_chars": [], "error_kinds": {},
        })
        c["trials"] += 1
        if not r.get("ok"):
            c["errors"] += 1
            kd = r.get("error", "unknown").split(":")[0]
            c["error_kinds"][kd] = c["error_kinds"].get(kd, 0) + 1
            continue
        c["ok"] += 1
        if r.get("order_compliant") is True:
            c["compliant"] += 1
        if r.get("order_observable"):
            c["observable"] += 1
        if r.get("degraded"):
            c["degraded"] += 1
        c["body_chars"].append(r.get("body_chars", 0))

    for c in cells.values():
        # 只在可观测样本上算顺序合规率——否则「模型压根没写例子」会被算成"没合规"
        denom = c["observable"] if c["mode"] != "baseline" else c["ok"]
        c["compliance_denominator"] = denom
        c["compliance_rate"] = round(c["compliant"] / denom, 4) if denom else None
        c["degradation_rate"] = round(c["degraded"] / c["ok"], 4) if c["ok"] else None
        c["mean_body_chars"] = round(statistics.mean(c["body_chars"]), 1) if c["body_chars"] else None
        c["verdict"] = _verdict(c)
    return {"cells": list(cells.values())}


def _verdict(c: dict) -> str:
    """显式判定。errors 占比过高一律 INCONCLUSIVE——基础设施故障不得伪装成结论。"""
    if c["errors"] and c["errors"] / max(c["trials"], 1) > 0.2:
        return "INCONCLUSIVE(错误过多)"
    if not c["ok"]:
        return "INCONCLUSIVE(零有效样本)"
    if c["degraded"] / max(c["ok"], 1) > 0.3:
        return "FAIL(内容退化)"
    if c["mode"] == "baseline":
        return "REFERENCE"
    if c["compliance_denominator"] == 0:
        return "INCONCLUSIVE(无结构可观测)"
    return "OK" if c["compliance_rate"] >= 0.6 else "WEAK(合规率<0.6)"


async def main_async(args) -> int:
    topics = TOPIC_MATRIX[: args.topics]
    profs = PROFILE_MATRIX[: args.profiles]
    modes = [m for m in args.modes.split(",") if m]

    outdir = os.path.join(_ROOT, "experiments", "results")
    os.makedirs(outdir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    jl = os.path.join(outdir, f"teaching_mode_prompt_eval_{stamp}.jsonl")
    sp = os.path.join(outdir, f"teaching_mode_prompt_eval_{stamp}.summary.json")

    llm = LLMProvider(args.provider)
    try:
        pinfo = llm.get_provider_info()
    except Exception:  # noqa: BLE001
        pinfo = {}
    provider_note = json.dumps(
        {k: v for k, v in (pinfo or {}).items() if "key" not in k.lower() and "secret" not in k.lower()},
        ensure_ascii=False,
    )[:400]
    print(f"[provider] {provider_note}")
    print(f"[plan] topics={len(topics)} profiles={len(profs)} modes={modes} "
          f"repeats={args.repeats} => 预计 {len(topics)*len(profs)*len(modes)*args.repeats} 次调用")
    print(f"[budget-guard] 单次 max_tokens=2000，失败不重试（错误计入 errors 不隐藏）")

    if args.dry_run:
        from engines.teaching_rules import teaching_rules
        print("\n=== DRY-RUN：不调 LLM，只打印 prompt 差异与规则版决策 ===")
        for t in topics:
            for prof in profs:
                pm = profile_for(t, prof)
                pa = teaching_rules.decide_policy_action(profile=pm)
                print(f"  topic={t['topic'][:12]:12s} profile={prof['id']:6s} "
                      f"weak_points={pm['weak_points'][:24] or '(无)':24s} "
                      f"→ 规则版 teaching_mode={pa['teaching_mode']}")
        plan = {"topic": topics[0]["topic"], "chapter": topics[0]["chapter"],
                "difficulty": "medium", "teacher_task": "t"}
        pm0 = profile_for(topics[0], profs[0])
        base = _build_agent_prompt("teacher", plan, pm0,
                                   topics[0]["knowledge_context"], pm0["diagnosis"], "", "")
        for m in modes:
            if m == "baseline":
                continue
            n = _build_agent_prompt("teacher", plan, pm0,
                                    topics[0]["knowledge_context"], pm0["diagnosis"], "",
                                    TEACHING_MODE_INSTRUCTIONS[m])
            print(f"  {m:14s} prompt +{len(n)-len(base)} chars")
        print(f"\n[dry-run] 不写工件。真实运行去掉 --dry-run。")
        return 0

    records = []
    total = len(topics) * len(profs) * len(modes) * args.repeats
    done = 0
    with open(jl, "w", encoding="utf-8") as f:
        for topic in topics:
            for prof in profs:
                for mode in modes:
                    for rep in range(args.repeats):
                        rec = await run_trial(llm, topic, prof, mode, provider_note)
                        rec["rep"] = rep
                        records.append(rec)
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        f.flush()
                        os.fsync(f.fileno())  # 增量落盘：崩了不丢已跑证据
                        done += 1
                        st = "ok" if rec.get("ok") else f"ERR({rec.get('error','')[:40]})"
                        print(f"  [{done}/{total}] {prof['id']:7s} {mode:14s} rep{rep} "
                              f"chars={rec.get('body_chars','-')} {st}")

    summary = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "provider_note": provider_note,
        "params": {"topics": len(topics), "profiles": len(profs), "modes": modes,
                   "repeats": args.repeats, "temperature": 0.7, "max_tokens": 2000},
        "probes": {
            "example_markers": EXAMPLE_MARKERS,
            "definition_markers": DEFINITION_MARKERS,
            "analogy_markers": ANALOGY_MARKERS,
            "opening_structure": OPENING_STRUCTURE,
            "concept_lead": CONCEPT_LEAD,
            "note": (
                "主指标 head_opens_with_scenario 是模式无关结构量，所有臂同尺量；"
                "各臂按自身定义的自证合规率只作参考（否则是循环论证）。"
            ),
        },
        "primary_metric": summarize_primary(records),
        **summarize(records),
    }
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n=== 主指标：开头即场景引入率（所有臂同尺量，含 baseline 对照）===")
    for m in ["baseline", "sequential", "example_first", "analogy"]:
        c = summary["primary_metric"].get(m)
        if not c:
            continue
        ci = c["wilson95"]
        d = c.get("delta_vs_baseline")
        d_s = "—" if d is None else f"{d:+.0%}"
        rate_s = "—" if c["rate"] is None else f"{c['rate']:.0%}"
        print(f"  {m:14s} {c['head_scenario_hits']:2d}/{c['trials']:<2d} "
              f"= {rate_s:>4s}  Wilson[{ci[0]:.2f}, {ci[1]:.2f}]  "
              f"errors={c['errors']}  Δbaseline={d_s}")

    print(f"\n=== 参考：各臂自证合规率（不进主指标）===")
    for c in sorted(summary["cells"], key=lambda x: (x["profile"], x["mode"])):
        rate = c["compliance_rate"]
        rate_s = f"{rate:.0%}" if rate is not None else "—"
        print(f"  {c['profile']:7s} {c['mode']:14s} trials={c['trials']} ok={c['ok']} "
              f"errors={c['errors']} 可观测={c['observable']} 合规率={rate_s} "
              f"退化={c['degradation_rate']} 均长={c['mean_body_chars']} → {c['verdict']}")
    print(f"\n工件：\n  {jl}\n  {sp}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="teaching_mode→prompt 接线基线对比（真实 LLM）")
    ap.add_argument("--topics", type=int, default=2, help="取 topic 矩阵前 N 个（默认 2）")
    ap.add_argument("--profiles", type=int, default=2, help="取 profile 矩阵前 N 个")
    ap.add_argument("--repeats", type=int, default=3, help="每格重复次数（temperature=0.7 必须 >1）")
    ap.add_argument("--modes", default="baseline,sequential,example_first,analogy")
    ap.add_argument("--provider", default="deepseek")
    ap.add_argument("--dry-run", action="store_true", help="只验 prompt 差异与规则版决策，不调 LLM")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())