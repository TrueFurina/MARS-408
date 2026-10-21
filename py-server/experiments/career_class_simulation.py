#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""career_class_simulation.py — 信息安全1班「计算机模拟演练」（**不是真实试用**）

背景（用户 2026-10-21 拍板原话）：「真实试点是不可能的，纯按照计算机模拟的来」。

数据源（只读，PII 不入库）：
    E:\\3chuang\\MangDeHenZhi\\06-学生信息\\脱敏试点班级-信息安全1班.csv
    —— 只取「序号 + 学号后4位」两列；**性别/政治面貌列不读取、不落库、不进任何报告**
    （政治面貌属敏感个人信息）。名单 47 条，含一处重复学号 5129（序号 29 与 47），
    按源数据原样导入并在报告中如实记录。

演练内容（本地环境，127.0.0.1:8002，LLM_PROVIDER=deepseek）：
    教师建班 → 导入 47 人名册 → 发任务码（5 轮）
    → 10 名模拟学生**自注册**（sim_ 前缀，display_name=花名册姓名，演示姓名绑定链路）
    → 凭码加入 → 6 人完整作答 5 轮 + 终评（真实 LLM，异步等报告）
    → 2 人开练未完成 → 2 人只加入不开练 → 其余 35 人未加入
    → 输出看板聚合真值 + 每场评估来源（assessment_source）清单

诚信约束（硬）：
    1. sim_ 前缀已登记进 experiments/pilot_evidence_report.py 的 TEST_ACCOUNT_PREFIXES
       —— 不登记的话这些账号会把 distinct_users_real / max_bound_class 撑成假阳性，
       制造「试用已开展」的假象；
    2. 本脚本产出的一切数字**只能表述为「模拟演练」**，不得当作试用成效引用；
    3. 跑完必须复跑 pilot_evidence_report.py，确认仍 exit 1（真实用户仍不足）。

用法：
    cd py-server && LLM_PROVIDER=deepseek .venv/Scripts/python.exe \\
        experiments/career_class_simulation.py [--base http://127.0.0.1:8002]
"""

import argparse
import csv
import json
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import urllib.request
import urllib.error

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# 脱敏花名册的候选位置（本机绝对路径优先；仓库相对路径兜底）
_ROSTER_CANDIDATES = [
    r"E:\3chuang\MangDeHenZhi\06-学生信息\脱敏试点班级-信息安全1班.csv",
    os.path.join(REPO_ROOT, "..", "..", "3chuang", "MangDeHenZhi", "06-学生信息",
                 "脱敏试点班级-信息安全1班.csv"),
]
ROSTER_CSV = next((p for p in _ROSTER_CANDIDATES if os.path.exists(p)),
                  _ROSTER_CANDIDATES[0])

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# 演练规模
N_JOIN = 10          # 加入（绑定名册）的模拟学生数
N_FINISH = 6         # 其中完整作答 + 终评的人数
N_UNFINISHED = 2     # 开练但未完成的人数
MAX_TURNS = 5

# 作答内容池（计算机学院信息安全方向场景，6 人轮换偏移取用，保证同轮不同文）
ANSWER_POOL = [
    "我的选题是多智能体强化学习驱动的共识机制优化。理由是现有 PBFT 在节点规模上升时通信开销呈平方增长，实际部署到 16 节点就明显掉吞吐。",
    "方法上采用分阶段共识：候选提名、加权投票、提交确认三阶段，用历史行为形成的信用权重替代全量广播，每轮只与高信用节点通信。",
    "主要风险是信用权重本身可能被恶意节点通过长期小额作恶来操纵。我准备用身份锚定加三阶段防护，把单点影响限制在局部。",
    "实验设计是与基线 PBFT 对比，在 4、8、16 节点三种规模下测吞吐和延迟，另外做 20% 恶意节点注入，观察吞吐量衰减幅度。",
    "预期贡献是把通信复杂度从平方级降到近似线性，并且在 16 节点规模下保持吞吐不下降，同时恶意节点场景下衰减控制在可接受范围。",
    "团队分工上我负责共识模块与实验部分，另外两名同学分别负责身份锚定和防护策略，每周同步一次进展并跑一次集成测试。",
    "时间计划是前两周完成候选提名阶段，中间两周做投票与提交确认，最后两周做恶意节点注入实验和论文撰写。",
    "如果重来一次，我会更早做小规模端到端联调，而不是等三个模块都完成后才集成，那样问题定位会快很多。",
]


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def api(base: str, method: str, path: str, token: str = "", body=None, timeout: int = 60):
    """最小 HTTP 客户端（stdlib，无第三方依赖）。返回 (status, parsed_json)。"""
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        # 双头：线上网关只透传自定义头；本地无网关但保持与生产一致的调用方式
        req.add_header("X-App-Token", token)
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else {}
        except Exception:
            return e.code, {"raw": raw[:200].decode("utf-8", "replace")}


def load_roster(path: str):
    """读脱敏花名册：只要 序号 + 学号后4位；性别/政治面貌**不读**。"""
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header[0].strip() == "序号" and "学号" in header[1], f"表头不符：{header}"
        for r in reader:
            if not r or not r[0].strip():
                continue
            rows.append({"idx": r[0].strip(), "sid4": r[1].strip()})
    return rows


def create_sim_teacher(password: str):
    """直接建教师账号（注册接口只开学生角色；本地演练用 store 直建）。"""
    sys.path.insert(0, REPO_ROOT)
    from db import user_store
    return user_store.create_user("sim_teacher", password, "模拟教师", role="teacher")


def run_student(base: str, username: str, password: str, display_name: str,
                join_code: str, mode: str, answers, task_id: str, scenario_id: str):
    """单个模拟学生的完整链路。mode: full / unfinished / join_only。"""
    out = {"user": username, "name": display_name, "mode": mode}
    st, body = api(base, "POST", "/api/auth/register", body={
        "username": username, "password": password, "display_name": display_name})
    if st == 200 and body.get("token"):
        out["registered"] = True
    elif st in (400, 409) and ("已存在" in str(body) or "exists" in str(body).lower()):
        out["registered"] = "already"
    else:
        out["registered"] = f"FAIL({st}:{str(body)[:80]})"
        return out
    st, body = api(base, "POST", "/api/auth/login",
                   body={"username": username, "password": password})
    # 登录限流 10 次/分钟/IP：10 名模拟学生 + 教师会超线，429 时退避重试
    for attempt in range(4):
        if st != 429:
            break
        wait = 20 * (attempt + 1)
        log(f"  {username} 登录被限流(429)，{wait}s 后重试")
        time.sleep(wait)
        st, body = api(base, "POST", "/api/auth/login",
                       body={"username": username, "password": password})
    if st != 200 or not body.get("token"):
        out["login"] = f"FAIL({st})"
        return out
    token = body["token"]

    st, joined = api(base, "POST", "/api/career/task/join",
                     token=token, body={"join_code": join_code})
    out["join"] = {"status": st, "roster_bound": joined.get("roster_bound"),
                   "bound_name": joined.get("bound_name"),
                   "matched_by": joined.get("bound_match")}
    if st != 200:
        return out
    if mode == "join_only":
        return out

    st, sess = api(base, "POST", "/api/career/session/start", token=token, body={
        "scenario_id": scenario_id, "max_turns": MAX_TURNS, "task_id": task_id})
    if st != 200:
        out["start"] = f"FAIL({st}:{str(sess)[:80]})"
        return out
    sid = sess["session_id"]
    out["session_id"] = sid

    turns = MAX_TURNS if mode == "full" else 2
    for i in range(turns):
        st, ans = api(base, "POST", f"/api/career/session/{sid}/answer", token=token,
                      body={"answer": answers[i % len(answers)]}, timeout=180)
        if st != 200:
            out[f"answer_{i+1}"] = f"FAIL({st}:{str(ans)[:80]})"
            return out
    if mode == "unfinished":
        out["left_unfinished"] = True
        return out

    st, end = api(base, "POST", f"/api/career/session/{sid}/end", token=token,
                  body={"force": False}, timeout=60)
    out["end"] = st
    # 终评异步：轮询报告。**就绪判定不能用 status 值**——get_report 就绪时返回的
    # status 是**会话态**（"finished"）而非 "ready"，也没有 "report" 键（首版因此
    # 6 场全部误判超时，其实评估早已落库）。正确判据：assessment 字段非空。
    # 字段位置（实测）：assessment.assessment_source ∈ {llm, rule_fallback}；
    # assessment.overall 为综合分。
    t0 = time.time()
    while time.time() - t0 < 240:
        time.sleep(5)
        st, rep = api(base, "GET", f"/api/career/session/{sid}/report", token=token)
        assess = rep.get("assessment") or {}
        if st == 200 and assess:
            out["report"] = {
                "status": "ready",
                "assessment_source": assess.get("assessment_source", ""),
                "overall": assess.get("overall"),
                "dimensions": sorted((assess.get("dimensions") or {}).keys()),
                "wait_s": round(time.time() - t0, 1),
            }
            return out
        if rep.get("status") == "failed":
            out["report"] = {"status": "failed",
                             "message": str(rep.get("message"))[:120]}
            return out
    out["report"] = {"status": "timeout", "wait_s": round(time.time() - t0, 1)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8002")
    ap.add_argument("--roster", default=ROSTER_CSV)
    args = ap.parse_args()
    base = args.base.rstrip("/")

    t_start = time.time()
    log("=== 信息安全1班 计算机模拟演练（非真实试用） ===")
    log(f"base={base}  roster={args.roster}")

    roster = load_roster(args.roster)
    dup = {}
    for r in roster:
        dup.setdefault(r["sid4"], []).append(r["idx"])
    dups = {k: v for k, v in dup.items() if len(v) > 1}
    log(f"花名册 {len(roster)} 条；重复学号：{dups or '无'}")

    # ── 1) 教师侧：建班 + 导名册 + 发任务 ──
    tch_pw = "SimTch#" + uuid.uuid4().hex[:8]
    tch = create_sim_teacher(tch_pw)
    log(f"教师账号 sim_teacher 就绪（{tch['id'][:12]}…）")
    st, body = api(base, "POST", "/api/auth/login",
                   body={"username": "sim_teacher", "password": tch_pw})
    assert st == 200, f"教师登录失败：{body}"
    tch_token = body["token"]

    cls_name = "信息安全1班-模拟演练"
    st, cls = api(base, "POST", "/api/career/classes", token=tch_token,
                  body={"class_name": cls_name})
    assert st == 200, f"建班失败：{cls}"
    class_id = cls["class_id"]
    log(f"建班：{cls_name}（{class_id}）")

    # 名册行：「学号后4位 学生NN」——姓名用合成名（真实姓名不入库）
    roster_text = "\n".join(f"{r['sid4']} 学生{int(r['idx']):02d}" for r in roster)
    st, imp = api(base, "POST", f"/api/career/classes/{class_id}/students",
                  token=tch_token, body={"roster": roster_text})
    assert st == 200, f"导入名册失败：{imp}"
    log(f"导入花名册：{imp.get('imported')} 条")

    st, scs = api(base, "GET", "/api/career/scenarios", token=tch_token)
    scenario = scs["scenarios"][0]
    st, task = api(base, "POST", "/api/career/tasks", token=tch_token, body={
        "class_id": class_id, "scenario_id": scenario["id"],
        "difficulty": "medium", "max_turns": MAX_TURNS})
    assert st == 200, f"发任务失败：{task}"
    join_code, task_id = task["join_code"], task["task_id"]
    log(f"发布任务：情景「{scenario['title']}」 任务码 {join_code}")

    # ── 2) 学生侧：10 人注册 + 加入；6 人完整 / 2 人未完成 / 2 人只加入 ──
    students = []
    for i in range(1, N_JOIN + 1):
        mode = ("full" if i <= N_FINISH else
                "unfinished" if i <= N_FINISH + N_UNFINISHED else "join_only")
        students.append({
            "username": f"sim_stu{i:02d}", "password": "SimStu#1021aa",
            "display_name": f"学生{i:02d}", "mode": mode,
            "answers": ANSWER_POOL[i % len(ANSWER_POOL):] + ANSWER_POOL[:i % len(ANSWER_POOL)],
        })

    results = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {pool.submit(run_student, base, s["username"], s["password"],
                            s["display_name"], join_code, s["mode"], s["answers"],
                            task_id, scenario["id"]): s for s in students}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            rep = r.get("report") or {}
            log(f"  {r['user']}（{r['name']}） mode={r['mode']}"
                f" 绑定={ (r.get('join') or {}).get('matched_by') or '-' }"
                f" 报告={rep.get('status', '-')}/{rep.get('assessment_source', '-')}"
                f" 综合={rep.get('overall', '-')}")

    # ── 3) 看板聚合真值 ──
    st, dash = api(base, "GET", f"/api/career/classes/{class_id}/dashboard",
                   token=tch_token)
    summary = (dash.get("summary") or {}) if st == 200 else {}

    out = {
        "meta": {
            "kind": "SIMULATION_DRILL",   # 硬标记：模拟演练，非真实试用
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "base": base,
            "llm_provider": os.environ.get("LLM_PROVIDER", "deepseek"),
            "class_name": cls_name, "class_id": class_id,
            "join_code": join_code, "task_id": task_id,
            "scenario": scenario["title"],
            "roster_size": len(roster), "roster_duplicates": dups,
            "note": "模拟学生账号均为 sim_ 前缀（已登记进证据闸门排除清单）；"
                    "所有数字只能表述为「模拟演练」，不得当作试用成效引用。",
        },
        "summary": summary,
        "students": results,
        "elapsed_s": round(time.time() - t_start, 1),
    }
    path = os.path.join(RESULTS_DIR, f"class_simulation_{datetime.now():%Y%m%d_%H%M}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    log(f"结果已写：{path}")

    log("── 看板聚合 ──")
    log(f"  已加入 {summary.get('joined_count')}/{summary.get('student_count')}"
        f" ｜ 已开练 {summary.get('started_count')}"
        f" ｜ 完成 {summary.get('finished_count')}"
        f" ｜ 可评估 {summary.get('assessed_count')}")
    srcs = [ (r.get("report") or {}).get("assessment_source") for r in results ]
    log(f"  评估来源分布：{ {s: srcs.count(s) for s in set(srcs) if s} }")
    log(f"总耗时 {out['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
