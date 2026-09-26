#!/usr/bin/env python3
# ============================================================
# Jev 旁路对照试点脚手架（pilot_jev_judgment.py）
#
# 目的：把四个「判断型」节点（triage / critic / evidence_check / assessor）
#      的判断语义映射到 Jev（TypeSafe AI System One）三原语
#      （Choice / Noul / Score），做一次「零改主线」的旁路对照实验。
#
# 依据：deliverables/engineering-assurance/Jev-tech-selection-2026-09-23.md
#       §5（逐节点适配）与 §8（建议路线 P1）。
#
# 硬约束（安全第一，务必遵守）：
#   1) 严格旁路：本脚本不 import 任何 py-server 既有业务源码，不连库、不起服务，
#      不写入除自身 artifacts 目录以外的任何路径。导入本模块零副作用。
#   2) 默认不执行：只有在「同时」存在 TYPESAFE_API_KEY 且 JEV_PILOT_ENABLE=1
#      （或显式 --execute）时才会真正发起网络请求。
#   3) 无凭据 fail-loud：只要 TYPESAFE_API_KEY 缺失，一律打印明确错误（含如何
#      获取凭据的提示）并 exit 2，绝不发出任何网络请求，绝不静默跳过。
#
# 用法：
#   cd py-server
#   # 只打印将发送的请求摘要（不联网）。注意：无 key 时会 fail-loud（exit 2）。
#   TYPESAFE_API_KEY=<key> python experiments/pilot_jev_judgment.py
#   # 显式 dry-run（同样需要 key 存在，但不联网）
#   TYPESAFE_API_KEY=<key> python experiments/pilot_jev_judgment.py --dry-run
#   # 真正调用（需 key + 显式开关）
#   TYPESAFE_API_KEY=<key> JEV_PILOT_ENABLE=1 python experiments/pilot_jev_judgment.py --execute
#   # 小样本试跑
#   TYPESAFE_API_KEY=<key> python experiments/pilot_jev_judgment.py --limit 2
#
# 本机自检（Windows / WorkBuddy shell）：
#   env -u PYTHONPATH -u PYTHONSTARTUP -u NODE_OPTIONS -u ELECTRON_RUN_AS_NODE \
#       <项目 venv 的 python> experiments/pilot_jev_judgment.py
#   说明：本机 py-server/.venv 可能是跨盘 junction（指向冷存储）或被重建过，
#        路径不写死；若解释器缺失，用 `cd py-server && uv sync --frozen` 确定性重建，
#        或直接用受管解释器 C:\Users\Lenovo\.workbuddy\binaries\python\versions\3.13.12\python.exe。
# ============================================================

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# 本文件所在目录（artifacts 的父目录）：py-server/experiments/
_HERE = Path(__file__).resolve().parent

# ── 端点与凭据（来自 Jev 公开发布信息 2026-09-15，未在本项目独立复现）──
TYPESAFE_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
API_KEY_ENV = "TYPESAFE_API_KEY"
ENABLE_ENV = "JEV_PILOT_ENABLE"

# 说明：以下请求/响应 schema 依据公开发布资料整理；本机无 key，端到端未验证。
# 若官方文档给出不同字段名，请在此处按需调整，并同步更新 _parse_answer()。
API_SCHEMA_VERIFIED = False  # TODO(实现待补)：取得 API key 后对照官方文档核验 schema

# ── 三原语（Jev）：Choice / Noul / Score ──
PRIMITIVE_CHOICE = "choice"
PRIMITIVE_NOUL = "noul"
PRIMITIVE_SCORE = "score"

# ── 口径说明（2026-09-24 订正，QA D2）──
# 现行基准 benchmark_2026-09-18.json 里存在【两套不同题集】，不可混称：
#   · 实验1（检索臂）：28 条查询 → 对应本试验的题池 experiments/queries.json（实测 28 条唯一 id）
#   · 实验2（共识臂）：30 题 × 3 次 → 另一套题集，本试点不使用
# 因此本试点默认题量 = 28（对齐题池真实条数，无放回采样，distinct=100%），
# 而非沿用 30；若显式 --questions 超过题池，默认 fail-loud，需 --allow-repeat 才放行。
DEFAULT_SEED = 20260719
DEFAULT_QUESTIONS = 28
DEFAULT_TRIALS = 3

# ── 置信三级分流阈值（route: auto / review / human）──
# 注意：以下为占位默认值，【未标定，需实验确定】。不得据此宣称已优化/已校准。
DEFAULT_HIGH = 0.80
DEFAULT_LOW = 0.60

# ── 判断型节点 → 三原语映射 ──
# output_fields 均取自 py-server 既有实现（不杜撰字段名）：
#   - triage：agents/triage.py:triage_node 写 state["triage_level"/"triage_reason"]
#   - critic：agents/critic.py:critic_node 写 state["critic_issues"/"critic_report"]
#             与 state["consensus"]["status"/"confidence_score"]
#   - evidence_check：agents/evidence_check.py:evidence_check_node 写 state["evidence_report"]
#             （含 status / consistency_score / confidence_score / unresolved / grounding_flagged）
#   - assessor：agents/assessor.py:assessor_node 写 state["consensus"]["pre_assessment"]
#             （含 pre_score，量程 0-10，见 prompts.py:ASSESSOR_PROMPT）
NODE_SPECS: dict[str, dict[str, Any]] = {
    "triage": {
        "primitive": PRIMITIVE_CHOICE,
        "signal": "分级路由（选择档位）",
        "options": ["low", "high"],                 # 取值来自 triage.py:LEVEL_LOW/LEVEL_HIGH
        "question": "该用户请求应路由到哪一级处理档位？",
        "output_fields": ["triage_level", "triage_reason"],
        "decision_field": "triage_level",
    },
    "critic": {
        "primitive": PRIMITIVE_NOUL,
        "signal": "内容是否通过审阅（是 / 否）",
        "proposition": "待审内容是否通过审阅（无需要修正的有效问题）？",
        "output_fields": [
            "critic_issues",
            "critic_report",
            "consensus.status",
            "consensus.confidence_score",
        ],
        "decision_field": "consensus.status",
    },
    "evidence_check": {
        "primitive": PRIMITIVE_NOUL,
        "signal": "证据是否支撑结论（是 / 否）",
        "proposition": "现有证据是否支撑结论（不存在未解决冲突 / 非疑似幻觉）？",
        "output_fields": [
            "evidence_report.status",
            "evidence_report.consistency_score",
            "evidence_report.confidence_score",
            "evidence_report.unresolved",
            "evidence_report.grounding_flagged",
        ],
        "decision_field": "evidence_report.status",
    },
    "assessor": {
        "primitive": PRIMITIVE_SCORE,
        "signal": "按量程打分（综合质量）",
        "scale": [0.0, 10.0],                       # 量程 0-10，见 prompts.py:ASSESSOR_PROMPT
        "question": "对生成资源的综合质量评分（0-10）",
        "output_fields": ["consensus.pre_assessment.pre_score"],
        "decision_field": "consensus.pre_assessment.pre_score",
    },
}

NODE_ORDER = ["triage", "critic", "evidence_check", "assessor"]


# ============================================================
# 纯函数辅助
# ============================================================

def _sha256(text: str) -> str:
    """返回文本的 SHA-256 十六进制摘要（用于 state 可追溯审计）。"""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _now_utc_iso() -> str:
    """返回当前 UTC 时间的 ISO-8601 字符串（秒级，含 Z 后缀）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _route_by_confidence(confidence: Optional[float], high: float, low: float) -> str:
    """按置信度做三级分流：auto / review / human。

    阈值 high/low 均为占位默认值，【未标定，需实验确定】。
    confidence 缺失（None）时保守转人工（human）。
    """
    if confidence is None:
        return "human"
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        return "human"
    if c >= high:
        return "auto"
    if c >= low:
        return "review"
    return "human"


def _load_queries(queries_path: Path) -> list[dict[str, Any]]:
    """只读加载既有题集（experiments/queries.json）。"""
    with queries_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    queries = data.get("queries") or []
    if not isinstance(queries, list):
        raise ValueError("queries.json 格式异常：queries 字段应为列表")
    return queries


def _sample_queries(queries: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """用固定 seed 从题集确定性采样 n 条。

    - n <= len(queries)：无放回采样（组合固定，distinct 恒等于 n）。
    - n >  len(queries)：有放回采样（允许重复）。此路径【默认被 run_pilot 闸门 4 拦截】，
      只有显式 --allow-repeat 才会进入；调用方必须在报告中写明 distinct 与重复次数。
    """
    rng = random.Random(seed)
    if n <= 0:
        return []
    if n <= len(queries):
        return rng.sample(queries, n)
    return [rng.choice(queries) for _ in range(n)]


def _build_state(node: str, query: dict[str, Any]) -> dict[str, Any]:
    """为指定节点构建输入 state（字段名严格对齐 py-server/agents/state.py）。

    只读来源：experiments/queries.json（题集）中的 query / course / expected_subjects。
    生成的 7 类资源（teacher_doc / quiz / ...）在本机离线环境不存在，故留空，
    并在 _pilot_state_note 中显式标注；待接入真实 benchmark 产物后再填充。

    TODO(实现待补)：critic / evidence_check / assessor 的真实输入 state 需来自
    一次真实生成链路（teacher_doc、quiz、retrieved_chunks 等）；当前脚手架仅以
    题集文本构造占位 state，端到端语义对齐尚未验证。
    """
    text = str(query.get("text", ""))
    course = str(query.get("course", ""))
    subjects = query.get("expected_subjects") or []
    note = "scaffold: generated resources unavailable offline; populated from queries.json only"

    base: dict[str, Any] = {
        "user_request": text,
        "topic": text,
        "topic_label": text,
        "course": course,
        "difficulty": "",
        "_session_id": str(query.get("id", "")),
    }

    if node == "triage":
        # triage_node 实际读取：user_request / topic / course / difficulty / student_profile
        base["student_profile"] = {}
        base["expected_subjects"] = subjects
        base["_pilot_state_note"] = note
        return base

    if node == "critic":
        # critic_node 实际读取：topic_label/topic, teacher_doc, quiz, code_practice,
        # ppt_outline, memory_context, consensus
        base.update({
            "teacher_doc": "",
            "quiz": "",
            "code_practice": "",
            "ppt_outline": "",
            "memory_context": "",
            "consensus": {},
            "expected_subjects": subjects,
            "_pilot_state_note": note,
        })
        return base

    if node == "evidence_check":
        # evidence_check_node 实际读取：teacher_doc / quiz / code_practice / ppt_outline /
        # extension / mindmap / video_script / media_plan / retrieved_chunks / course
        base.update({
            "teacher_doc": "",
            "quiz": "",
            "code_practice": "",
            "ppt_outline": "",
            "extension": "",
            "mindmap": None,
            "video_script": "",
            "media_plan": "",
            "retrieved_chunks": [],
            "expected_subjects": subjects,
            "_pilot_state_note": note,
        })
        return base

    if node == "assessor":
        # assessor_node 实际读取：student_profile, diagnosis, consensus,
        # memory_context 及 7 类资源摘要
        base.update({
            "student_profile": {},
            "diagnosis": {},
            "consensus": {},
            "memory_context": "",
            "teacher_doc": "",
            "quiz": "",
            "extension": "",
            "code_practice": "",
            "ppt_outline": "",
            "video_script": "",
            "mindmap": None,
            "expected_subjects": subjects,
            "_pilot_state_note": note,
        })
        return base

    raise ValueError(f"未知节点：{node}")


def _state_to_text(state: dict[str, Any]) -> str:
    """把 state 序列化为稳定的审计文本（确定性键序，UTF-8 中文不转义）。"""
    return json.dumps(state, ensure_ascii=False, sort_keys=True)


def _build_payload(node: str, state_text: str) -> dict[str, Any]:
    """按三原语构建单节点请求 payload。

    schema 依据 Jev 公开发布信息整理（同一请求内可并行多个问题）。
    本机无 key，端到端未验证；如与实际接口不符，请调整本函数并更新解析逻辑。
    """
    spec = NODE_SPECS[node]
    primitive = spec["primitive"]

    question: dict[str, Any] = {"id": node, "type": primitive}
    if primitive == PRIMITIVE_CHOICE:
        question["prompt"] = spec["question"]
        question["options"] = list(spec["options"])
    elif primitive == PRIMITIVE_NOUL:
        question["prompt"] = spec["proposition"]
    elif primitive == PRIMITIVE_SCORE:
        question["prompt"] = spec["question"]
        question["scale"] = list(spec["scale"])
    else:  # pragma: no cover - 防御性分支
        raise ValueError(f"未知原语：{primitive}")

    return {
        "model": "systemone",
        "state": state_text,
        "questions": [question],
    }


def _parse_answer(node: str, resp: Any, high: float, low: float) -> dict[str, Any]:
    """从原始响应中尽力解析「概率 / 分值 + confidence」，并计算 route。

    无 key 无法核验真实响应结构，故采用防御式解析：任何字段缺失都不抛异常，
    对应值记 None（并在 route 上保守转 human）。model_version 缺失记 null。
    """
    primitive = NODE_SPECS[node]["primitive"]
    value: Any = None
    probability: Optional[float] = None
    score: Optional[float] = None
    confidence: Optional[float] = None

    answer: Any = None
    if isinstance(resp, dict):
        answers = resp.get("answers") or resp.get("results") or []
        if isinstance(answers, list) and answers:
            answer = answers[0]
        elif "value" in resp or "probability" in resp or "score" in resp:
            answer = resp

    if isinstance(answer, dict):
        value = answer.get("value", answer.get("choice", answer.get("label")))
        if answer.get("probability") is not None:
            try:
                probability = float(answer["probability"])
            except (TypeError, ValueError):
                probability = None
        if answer.get("score") is not None:
            try:
                score = float(answer["score"])
            except (TypeError, ValueError):
                score = None
        if answer.get("confidence") is not None:
            try:
                confidence = float(answer["confidence"])
            except (TypeError, ValueError):
                confidence = None
        # 概率分布形态：取最大值作为 confidence，并记录分布
        dist = answer.get("probabilities") or answer.get("distribution")
        if isinstance(dist, dict) and dist:
            try:
                prob_vals = [float(v) for v in dist.values()]
                if prob_vals and confidence is None:
                    confidence = max(prob_vals)
                if probability is None and value is not None and value in dist:
                    probability = float(dist[value])
            except (TypeError, ValueError):
                pass

    # 派生 confidence（当响应未直接给出时）
    if confidence is None:
        if primitive == PRIMITIVE_NOUL and probability is not None:
            confidence = max(probability, 1.0 - probability)
        elif primitive == PRIMITIVE_CHOICE and probability is not None:
            confidence = probability
        elif primitive == PRIMITIVE_SCORE and score is not None:
            lo, hi = NODE_SPECS[node]["scale"]
            if hi > lo:
                norm = (score - lo) / (hi - lo)
                confidence = max(norm, 1.0 - norm)

    return {
        "primitive": primitive,
        "value": value,
        "probability": probability,
        "score": score,
        "confidence": confidence,
        "route": _route_by_confidence(confidence, high, low),
    }


def _extract_model_version(resp_headers: dict[str, str], resp_body: Any) -> Optional[str]:
    """尽力从响应头 / 响应体提取模型版本标识；没有则返回 None（不编造）。"""
    for key in ("x-model-version", "x-jev-version", "model-version", "x-model"):
        if key in resp_headers and resp_headers[key]:
            return str(resp_headers[key])
    if isinstance(resp_body, dict):
        for key in ("model_version", "model", "version"):
            val = resp_body.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return None


# ============================================================
# 网络调用（仅 execute 模式下被调用）
# ============================================================

def _post_json(endpoint: str, api_key: str, payload: dict[str, Any], timeout: float = 30.0) -> tuple[Any, dict[str, str]]:
    """向 Jev 端点 POST JSON，返回 (响应体, 响应头)。

    优先复用项目已有依赖 httpx；若不可用则回退标准库 urllib.request。
    本函数只在 execute 分支被调用。

    代理处理（显式，不靠运气）：
    - httpx：trust_env=False，忽略 HTTP(S)_PROXY / NO_PROXY 等环境变量；
    - urllib：显式构造 ProxyHandler({}) 的 opener，绕开 Windows 注册表系统代理
      （实测：Clash 遗留的 127.0.0.1:7890 死端口会让 urllib 读注册表代理后假死）。
    如需走代理，调用方请显式传参（当前未提供，保持零依赖可复现）。
    """
    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    try:
        import httpx  # 项目依赖 pyproject.toml: httpx>=0.28.1
    except ImportError:
        httpx = None  # type: ignore[assignment]

    if httpx is not None:
        # trust_env=False：不读系统代理环境变量，避免死代理端口导致 UNEXPECTED_EOF 假死
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(endpoint, content=body_bytes, headers=headers)
            resp.raise_for_status()
            try:
                body = resp.json()
            except ValueError:
                body = {"_raw_text": resp.text}
            return body, dict(resp.headers)

    # 回退：标准库（显式禁用系统代理，绕开注册表代理污染）
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(endpoint, data=body_bytes, headers=headers, method="POST")
    with opener.open(req, timeout=timeout) as raw:
        raw_text = raw.read().decode("utf-8")
        resp_headers = {k.lower(): v for k, v in raw.headers.items()}
    try:
        body = json.loads(raw_text)
    except ValueError:
        body = {"_raw_text": raw_text}
    return body, resp_headers


# ============================================================
# 产物落盘（仅限 artifacts 目录）
# ============================================================

def _make_artifact_dir(base_dir: Path) -> Path:
    """创建并返回本次 run 的 artifacts 目录（仅追加）。"""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = base_dir / f"jev_pilot_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _append_record(records_path: Path, record: dict[str, Any]) -> None:
    """以 JSONL 追加一条判断记录。"""
    with records_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _write_run_meta(meta_path: Path, meta: dict[str, Any]) -> None:
    """写入本次 run 的 run_meta.json。"""
    with meta_path.open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2, sort_keys=True)


# ============================================================
# 主流程
# ============================================================

def _resolve_mode(args: argparse.Namespace, env_enabled: bool) -> str:
    """解析最终执行模式：'execute' 或 'dry'。

    CLI 语义与环境变量一致：
      - --execute 显式要求真实调用
      - --dry-run 显式要求 dry-run
      - 两者都未给：由 JEV_PILOT_ENABLE 决定（=1 → execute，否则 dry）
    注意：无论何种模式，只要 TYPESAFE_API_KEY 缺失都会在检测阶段 exit 2。
    """
    if args.execute:
        return "execute"
    if args.dry_run:
        return "dry"
    return "execute" if env_enabled else "dry"


def _fail_no_key() -> int:
    """无凭据 fail-loud：打印明确错误并返回退出码 2（不发起任何请求）。"""
    sys.stderr.write(
        "[jev-pilot] 错误：未设置环境变量 TYPESAFE_API_KEY，无法进行 Jev 试点。\n"
        "[jev-pilot] 如何获取凭据：请向 TypeSafe AI 申请 Jev / System One 早期访问，\n"
        "[jev-pilot]   获批后在环境变量中设置 TYPESAFE_API_KEY（例如：\n"
        "[jev-pilot]   export TYPESAFE_API_KEY=...）。\n"
        "[jev-pilot] 为避免误调用与静默跳过，本脚本在缺少凭据时一律失败退出（exit 2）。\n"
        "[jev-pilot] 本次未发出任何网络请求。\n"
    )
    return 2


def _print_dry_run_summary(records_preview: list[dict[str, Any]], n_questions: int, n_trials: int) -> None:
    """dry-run：打印将发送的 payload 结构摘要与请求条数，不发请求。"""
    total = n_questions * n_trials * len(NODE_ORDER)
    sys.stdout.write("[jev-pilot] DRY-RUN：不会发出任何网络请求。\n")
    sys.stdout.write(
        f"[jev-pilot] 计划请求条数：{total}"
        f"（{n_questions} 题 × {n_trials} trials × {len(NODE_ORDER)} 节点）\n"
    )
    sys.stdout.write("[jev-pilot] 端点：" + TYPESAFE_ENDPOINT + "\n")
    sys.stdout.write("[jev-pilot] payload 结构摘要：\n")
    for item in records_preview[:4]:
        payload = item["request_payload"]
        q = payload["questions"][0]
        sys.stdout.write(
            f"  - 节点={item['node']} 原语={item['primitive']} "
            f"questions[0].type={q['type']} "
            f"state_sha256={item['state_sha256'][:12]}... "
            f"state_len={len(payload['state'])}\n"
        )
    sys.stdout.write("[jev-pilot] 备注：state 原文与完整 payload 仅在 execute 模式落盘。\n")


def run_pilot(args: argparse.Namespace) -> int:
    """执行试点主流程，返回退出码。"""
    queries_path = _HERE / "queries.json"
    artifacts_base = _HERE / "artifacts"

    # ── 安全闸门 1：凭据（fail-loud，绝不联网）──
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if not api_key:
        return _fail_no_key()

    # ── 安全闸门 2：执行模式 ──
    env_enabled = os.environ.get(ENABLE_ENV, "") == "1"
    mode = _resolve_mode(args, env_enabled)
    dry_run = mode != "execute"

    # ── 安全闸门 3：置信阈值合法性（QA：原实现会静默接受倒置阈值）──
    high = float(getattr(args, "high", DEFAULT_HIGH))
    low = float(getattr(args, "low", DEFAULT_LOW))
    if not (0.0 <= low < high <= 1.0):
        sys.stderr.write(
            "[jev-pilot] 错误：置信分流阈值非法（要求 0 <= low < high <= 1）。\n"
            f"[jev-pilot]   当前 high={high} / low={low}；阈值倒置或越界会让三级分流语义失效，\n"
            "[jev-pilot]   为避免静默产生错误实验结论，一律失败退出（exit 2）。\n"
            "[jev-pilot] 本次未发出任何网络请求。\n"
        )
        return 2

    # ── 采样与 payload 构建（只读题集）──
    queries = _load_queries(queries_path)
    n_questions = args.limit if args.limit is not None else args.questions
    n_questions = max(0, int(n_questions))

    # ── 安全闸门 4：题量 vs 题池（QA D2：30 > 28 会退化为有放回采样，distinct 仅 19）──
    if n_questions > len(queries) and not getattr(args, "allow_repeat", False):
        sys.stderr.write(
            f"[jev-pilot] 错误：题量 {n_questions} 超过题池实际条数 {len(queries)}"
            "（experiments/queries.json）。\n"
            "[jev-pilot]   有放回采样会产生重复题（seed 20260719 实测 distinct=19 / 重复 11），\n"
            "[jev-pilot]   污染统计口径；如确需要，请显式追加 --allow-repeat 并在报告中说明。\n"
            "[jev-pilot] 为避免静默产出不可比数据，一律失败退出（exit 2）。\n"
            "[jev-pilot] 本次未发出任何网络请求。\n"
        )
        return 2

    sampled = _sample_queries(queries, n_questions, args.seed)

    preview: list[dict[str, Any]] = []
    for q in sampled:
        for node in NODE_ORDER:
            state = _build_state(node, q)
            state_text = _state_to_text(state)
            payload = _build_payload(node, state_text)
            preview.append({
                "node": node,
                "primitive": NODE_SPECS[node]["primitive"],
                "state_text": state_text,
                "state_sha256": _sha256(state_text),
                "request_payload": payload,
            })

    if dry_run:
        _print_dry_run_summary(preview, n_questions, args.trials)
        return 0

    # ── execute 分支：真正调用并落盘──
    run_dir = _make_artifact_dir(artifacts_base)
    records_path = run_dir / "records.jsonl"
    meta_path = run_dir / "run_meta.json"

    route_counts = {"auto": 0, "review": 0, "human": 0}
    did_call = False
    total_calls = 0
    total_errors = 0

    try:
        for q in sampled:
            for node in NODE_ORDER:
                for trial in range(int(args.trials)):
                    state = _build_state(node, q)
                    state_text = _state_to_text(state)
                    payload = _build_payload(node, state_text)
                    record: dict[str, Any] = {
                        "timestamp": _now_utc_iso(),
                        "node": node,
                        "primitive": NODE_SPECS[node]["primitive"],
                        "question_id": str(q.get("id", "")),
                        "trial": trial,
                        "state_sha256": _sha256(state_text),
                        "state_text": state_text,
                        "request_payload": payload,
                        "raw_response": None,
                        "model_version": None,
                        "parsed": None,
                        "error": None,
                    }
                    try:
                        body, headers = _post_json(TYPESAFE_ENDPOINT, api_key, payload)
                        did_call = True
                        total_calls += 1
                        parsed = _parse_answer(node, body, args.high, args.low)
                        record["raw_response"] = body
                        record["model_version"] = _extract_model_version(headers, body)
                        record["parsed"] = parsed
                        route_counts[parsed["route"]] = route_counts.get(parsed["route"], 0) + 1
                    except Exception as exc:  # noqa: BLE001 - 记录失败但不中断整轮
                        total_errors += 1
                        record["error"] = f"{type(exc).__name__}: {exc}"
                    _append_record(records_path, record)
    finally:
        meta = {
            "command_line": sys.argv,
            "endpoint": TYPESAFE_ENDPOINT,
            "api_schema_verified": API_SCHEMA_VERIFIED,
            "seed": args.seed,
            "n_questions": n_questions,
            "n_trials": int(args.trials),
            "n_nodes": len(NODE_ORDER),
            "dry_run": dry_run,
            "did_call": did_call,
            "total_calls": total_calls,
            "total_errors": total_errors,
            "thresholds": {"high": args.high, "low": args.low, "calibrated": False},
            "route_counts": route_counts,
            "python_version": platform.python_version(),
            "utc_timestamp": _now_utc_iso(),
        }
        _write_run_meta(meta_path, meta)

    sys.stdout.write(f"[jev-pilot] 完成。artifacts：{run_dir}\n")
    sys.stdout.write(f"[jev-pilot] 真实调用 {total_calls} 次，错误 {total_errors} 次，route 分布={route_counts}\n")
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        description="Jev 旁路对照试点脚手架（严格旁路 / 默认不执行 / 无凭据 fail-loud）",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run", action="store_true",
        help="只打印将发送的 payload 摘要，不发起任何网络请求。",
    )
    mode_group.add_argument(
        "--execute", action="store_true",
        help="显式要求真实调用（仍需 TYPESAFE_API_KEY；缺失则 exit 2）。",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"采样随机种子（默认 {DEFAULT_SEED}，对齐现行基准口径）。")
    parser.add_argument("--questions", type=int, default=DEFAULT_QUESTIONS,
                        help=f"题目数量（默认 {DEFAULT_QUESTIONS}，= queries.json 题池真实条数；"
                             "超过题池默认 fail-loud，须配合 --allow-repeat）。")
    parser.add_argument("--allow-repeat", action="store_true",
                        help="题量 > 题池时允许有放回采样（会产生重复题，distinct < n，需自行在报告中说明）。")
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS,
                        help=f"每题 trials 次数（默认 {DEFAULT_TRIALS}，对齐现行基准口径）。")
    parser.add_argument("--limit", type=int, default=None,
                        help="小样本试跑：覆盖 --questions，只取前 N 题。")
    parser.add_argument("--high", type=float, default=DEFAULT_HIGH,
                        help=f"置信分流高阈值（默认 {DEFAULT_HIGH}；未标定，需实验确定）。")
    parser.add_argument("--low", type=float, default=DEFAULT_LOW,
                        help=f"置信分流低阈值（默认 {DEFAULT_LOW}；未标定，需实验确定）。")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """入口：解析参数并执行。"""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return run_pilot(args)


if __name__ == "__main__":
    sys.exit(main())
