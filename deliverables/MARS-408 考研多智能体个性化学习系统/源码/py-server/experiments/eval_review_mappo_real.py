#!/usr/bin/env python
# ============================================================
# eval_review_mappo_real — 阶段 4：用**真实评审 trace** 复评评审权重策略
#
# 为什么必须有这个脚本
# -------------------
# 阶段 3 的全部结论都建立在**合成环境**上：`ReviewEnv` 的档位增益阶梯
# （matched 5.0 / balanced 3.0 / mismatch 1.0）是环境作者写死的判据，RL 的"赢"
# 只等价于"更常命中该判据"（环境内自造），**不是教学增益**。
# `CalibratedReviewEnv` 把奖励换成生产同款 `weighted_consistency_score`，但上下文
# (s_h, s_c, s_k) 仍是 `random.uniform` **采样**出来的，只是分布镜像线上。
# ⇒ 唯一能把"环境内自造最优"换成"真实增益"的路径，是在**真实评审 trace** 上复评。
#
# 本脚本做这件事：读真实 trace → 用真实特征管线与真实质量函数逐条复算
# → 报"若采用该策略，质量分相对现状（uniform）的真实偏移"。
#
# 诚信设计（硬约束）
# -----------------
#  1. **无输入即失败**：不给 trace 就明确报错退出，绝不生成任何数字。
#  2. **合成自测不可冒充真实**：`--make-selftest-fixture` 生成的样本会带
#     `_synthetic_fixture: true`，脚本检测到后把 `verdict_valid` 置 False 并在
#     notes 里强制标注 —— 用于验证管线通不通，不用于产出结论。
#  3. **可追溯**：落盘结果记录 trace 文件路径 + SHA256 + 条数，任何数字都能回溯到源。
#
# trace schema（JSON 数组，或 JSONL 每行一条）
# -------------------------------------------
#   {
#     "id": 任意可序列化的样本标识,
#     "evidence":  {"consistency_score": 0-100, "coverage": int, "expected_coverage": int},
#     "critic":    {"confidence": 0-1, "valid_count": int, "invalid_count": int},
#     "consensus": {"status": "pass"|"conflict"|"none", "confidence_score": 0-1,
#                   "overall_score": 0-100|null, "disagreement": 0-1},
#     "state":     {"gate_retry_count": int, "token_budget": int, "tokens_used": float,
#                   "last_consistency": 0-100, "disagreement": 0-1},
#     "mode_encoding": 0-1,   # 可选，默认 0.5
#     "round_ratio":   0-1,   # 可选，默认 0.5
#     "skip_streak":   int,   # 可选，默认 0（该会话此步之前已连发 skip 次数）
#     "reviews_done":  int    # 可选，默认 0（该会话此步之前已完成真实评审次数）
#   }
#   必填：evidence / consensus / state。缺字段会逐条报出，不会静默补默认值。
#
# 用法（在 py-server/ 下）
# ------------------------
#   # 真实复评
#   .venv/Scripts/python.exe experiments/eval_review_mappo_real.py \
#       --trace /path/to/review_trace.jsonl --seeds 7,42,2026 \
#       --ppo-episodes 3000 --ppo-batch 48 --env calibrated
#   # 只测管线（生成带标记的合成 fixture，结论强制 invalid）
#   .venv/Scripts/python.exe experiments/eval_review_mappo_real.py \
#       --make-selftest-fixture /tmp/_selftest_trace.jsonl --trace /tmp/_selftest_trace.jsonl
# ============================================================

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.review_policy import SKIP_STREAK_LIMIT  # noqa: E402
from engines.review_shadow_probe import build_shadow_policy, observe, summarize  # noqa: E402


# ────────────────────────────────────────────────────────────
# trace 读取与校验
# ────────────────────────────────────────────────────────────

REQUIRED = ("evidence", "consensus", "state")


def _validate_sample(i: int, s: dict) -> list[str]:
    """返回问题列表（空 = 合法）。不修改样本，不补默认值。"""
    problems = []
    if not isinstance(s, dict):
        return [f"#{i}: 不是对象"]
    for k in REQUIRED:
        if k not in s:
            problems.append(f"#{i}: 缺必填字段 `{k}`")
        elif not isinstance(s[k], dict):
            problems.append(f"#{i}: 字段 `{k}` 不是对象")
    return problems


def load_trace(path: Path) -> tuple[list[dict], dict]:
    """读 trace 文件（.json 数组 / .jsonl 每行一条），返回 (样本, 元信息)。"""
    if not path.exists():
        raise SystemExit(
            f"[real-eval] 输入 trace 不存在：{path}\n"
            "  阶段4 需要**真实评审 trace**。生产侧尚未实现轨迹落盘 ⇒ 该文件需由\n"
            "  业务侧导出（schema 见本脚本 docstring）。本脚本在无真实输入时不会\n"
            "  生成任何数字（避免合成数据冒充真实结论）。")

    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")

    samples: list[dict] = []
    if path.suffix.lower() == ".jsonl":
        for ln, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"[real-eval] {path.name}:{ln} JSON 解析失败: {e}")
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise SystemExit(f"[real-eval] {path.name} JSON 解析失败: {e}")
        samples = data if isinstance(data, list) else data.get("samples", [])
        if not isinstance(samples, list):
            raise SystemExit(f"[real-eval] {path.name}: 顶层既非数组也无 samples 数组")

    if not samples:
        raise SystemExit(f"[real-eval] {path.name}: 0 条样本 —— 拒绝产出空结论")

    problems = []
    for i, s in enumerate(samples):
        problems.extend(_validate_sample(i, s))
    if problems:
        head = problems[:10]
        raise SystemExit(
            f"[real-eval] trace schema 校验失败（{len(problems)} 处），前若干处：\n  "
            + "\n  ".join(head)
            + "\n  schema 见本脚本 docstring；不合法就不跑，避免用残缺输入产出看似有效的数字。")

    synthetic = any(bool(s.get("_synthetic_fixture")) for s in samples)
    meta = {
        "trace_path": str(path.resolve()),
        "trace_sha256": digest,
        "n_samples": len(samples),
        "is_synthetic_fixture": synthetic,
    }
    return samples, meta


def make_selftest_fixture(out: Path, n: int = 240, seed: int = 20260914) -> None:
    """生成**带标记**的合成 trace，仅用于验证本脚本管线可跑通。

    每个样本都带 `_synthetic_fixture: true`，脚本会据此把 `verdict_valid` 置 False。
    这样"管线能跑"与"结论可信"被强制分开。
    """
    sys.path.insert(0, str(_ROOT / "experiments"))
    from run_shadow_probe import generate_samples  # noqa: E402

    rng = random.Random(seed)
    samples = generate_samples(n, rng)
    for s in samples:
        s["_synthetic_fixture"] = True
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"[real-eval] 已生成自测 fixture（{n} 条，带 _synthetic_fixture 标记）-> {out}")


# ────────────────────────────────────────────────────────────
# 主流程
# ────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="阶段4：真实评审 trace 上复评评审权重策略（无真实输入即失败）")
    ap.add_argument("--trace", type=str, default=None,
                    help="真实评审 trace 文件（.json 数组或 .jsonl）")
    ap.add_argument("--make-selftest-fixture", type=str, default=None,
                    help="仅生成带标记的合成 fixture 用于管线自测（结论会强制 invalid）")
    ap.add_argument("--seeds", type=str, default="7,42,2026")
    ap.add_argument("--warmup-steps", type=int, default=600)
    ap.add_argument("--ppo-episodes", type=int, default=3000)
    ap.add_argument("--ppo-batch", type=int, default=48)
    ap.add_argument("--horizon", type=int, default=32)
    ap.add_argument("--env", choices=["calibrated", "legacy"], default="calibrated")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    if args.make_selftest_fixture:
        make_selftest_fixture(Path(args.make_selftest_fixture))

    if not args.trace:
        raise SystemExit(
            "[real-eval] 必须提供 --trace（或先用 --make-selftest-fixture 造自测输入）。\n"
            "  阶段4 的整个意义就是摆脱合成环境；无真实输入时本脚本不产出任何数字。")

    trace_path = Path(args.trace)
    samples, trace_meta = load_trace(trace_path)
    seed_list = [int(x) for x in args.seeds.split(",") if x.strip()]
    print(f"[real-eval] trace={trace_path.name} n={trace_meta['n_samples']} "
          f"sha256={trace_meta['trace_sha256'][:12]}… "
          f"synthetic={trace_meta['is_synthetic_fixture']}")

    # 训练环境
    env_factory = None
    if args.env == "calibrated":
        from engines.review_env_calibrated import CalibratedReviewEnv  # noqa: E402
        env_factory = lambda s, h: CalibratedReviewEnv(seed=s, horizon=h)  # noqa: E731
    print(f"[real-eval] 训练影子策略 seeds={seed_list} env={args.env} "
          f"(warmup={args.warmup_steps}, ppo={args.ppo_episodes}, batch={args.ppo_batch})")

    policies, train_stats = [], []
    for sd in seed_list:
        p = build_shadow_policy(sd, warmup_steps=args.warmup_steps,
                                ppo_episodes=args.ppo_episodes, horizon=args.horizon,
                                env_factory=env_factory, batch_episodes=args.ppo_batch)
        st = getattr(p, "_last_train_stats", {}) or {}
        train_stats.append({"seed": sd,
                            "torch_available": getattr(p, "torch_available", False),
                            "trained": getattr(p, "_trained", False),
                            "n_updates": st.get("n_updates"),
                            "improved_deterministic": st.get("improved_deterministic")})
        print(f"    seed={sd}: trained={getattr(p, '_trained', False)} "
              f"n_updates={st.get('n_updates')}")
        policies.append(p)

    records = []
    for s in samples:
        records.append(observe(
            evidence=s["evidence"], consensus=s["consensus"], state=s["state"],
            critic=s.get("critic"), shadow_policies=policies,
            skip_streak=int(s.get("skip_streak", 0) or 0),
            reviews_done=int(s.get("reviews_done", 0) or 0),
            mode_encoding=float(s.get("mode_encoding", 0.5)),
            round_ratio=float(s.get("round_ratio", 0.5))))
    summ = summarize(records)

    # 真实 trace 才给 valid 判决；合成 fixture 一律 invalid（防线，见模块 docstring）
    verdict_valid = not trace_meta["is_synthetic_fixture"]
    result = {
        "experiment": "review_mappo_real_trace_eval",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "stage": "阶段4 - 真实 trace 复评",
        "trace": trace_meta,
        "config": {"seeds": seed_list, "warmup_steps": args.warmup_steps,
                   "ppo_episodes": args.ppo_episodes, "ppo_batch_episodes": args.ppo_batch,
                   "horizon": args.horizon, "train_env": args.env,
                   "skip_streak_limit": SKIP_STREAK_LIMIT},
        "train_stats": train_stats,
        "summary": summ,
        "verdict_valid": verdict_valid,
        "notes": [],
    }
    if not verdict_valid:
        result["notes"].append(
            "⚠️ 本结果来自 **合成 fixture**（trace 内含 _synthetic_fixture 标记），"
            "仅用于验证管线可跑通；**不得作为真实增益结论引用**。")
    n_upd = [t.get("n_updates") for t in train_stats]
    if any((u or 0) < 20 for u in n_upd):
        result["notes"].append(
            f"⚠️ 存在训练不足的单元（n_updates={n_upd}，阈值 20）→ 该单元结论不可用。")
    out = args.out or str(_ROOT / "experiments" / "results"
                          / f"review_mappo_real_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    title = ("真实 trace 复评" if verdict_valid
             else "【管线自测 · 非真实结论】合成 fixture 复评")
    print(f"\n--- {title}（各臂真实平均有效分）---")
    for k, v in (summ.get("arm_means") or {}).items():
        print(f"  {k:<15} {v}")
    for k in ("delta_vs_uniform", "delta_vs_rule", "delta_vs_heuristic"):
        d = summ.get(k)
        if isinstance(d, dict):
            print(f"  {k:<20} mean={d.get('mean')} std={d.get('std')} "
                  f"pct_improve={d.get('pct_improve')}")
    for nt in result["notes"]:
        print("  " + nt)
    if not verdict_valid:
        print("\n  ⚠️ verdict_valid=False（合成 fixture，仅供管线自测，不得作为结论引用）")
    print(f"\n落盘: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
