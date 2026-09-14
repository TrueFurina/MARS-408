# ============================================================
# eval_review_mappo — 三元评审权重 3-seed 对比实验（角色 C · 实验数据）
#
# 依据：docs/CTO-芒得很职三元评审权重MAPPO化攻坚令-2026-09-14.md 阶段 3
#   - baseline A = 均匀权重（绝对基线，= 现状灰度关闭行为）
#   - baseline B = 固定规则（_rule_action_idx，现有规则因子）
#   - baseline C = 监督学习（warmup_with_rules：离线回归到规则决策标签，无 RL）
#   - 方案 D = RL（warmup 预热 + PPO 微调）
#   - 3-seed × 4 方案 × 指标：评审质量增益 / 成本(token) / 精准率 / skip 频次
#   - 纪律指标：skip 连发 ≥2 发生率必须为 0
#
# 独立可复算纪律：本脚本不复用 evaluate_policy 的单一 mean_return，
#   而是自行重跑环境并复算全部指标（与 review_reward 口径同源），便于交叉校验。
#
# 诚信约束：torch 不可用时如实标注 degraded，不伪造训练/评估结果；
#   所有数字落盘 experiments/results/review_mappo_eval_YYYYMMDD.json，不落盘不对外引用。
# ============================================================

import argparse
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engines.review_policy import (  # noqa: E402
    ACTION_TOKENS,
    REVIEW_ACTIONS,
    REVIEW_MIN_REVIEW,
    REWARD_W,
    REV_GAIN_BALANCED,
    REV_GAIN_MATCHED,
    REV_GAIN_MISMATCH,
    REV_GAIN_SKIP,
    SKIP_STREAK_LIMIT,
    STATE_DIM,
    ReviewEnv,
    ReviewWeightPolicy,
    _rule_action_idx,
    discipline_gate,
    review_precision,
    review_reward,
)

# ── 复现性锁 ───────────────────────────────────────────────
# PPO 在 CPU 多线程下 torch.manual_seed 不保证跨进程逐位复现，
# 会导致"同 seed 两次跑动作分布不同"→ 报告与 JSON 漂移（已踩坑）。
# 锁定单线程 + 确定性算法，使 3-seed 实验可逐位复算。
import torch as _torch  # noqa: E402

_torch.set_num_threads(1)
try:
    _torch.use_deterministic_algorithms(True)
except Exception:  # pragma: no cover
    pass

SEEDS = [7, 42, 2026]
SCHEMES = ["uniform", "rule", "supervised", "rl"]
DEFAULT_EPISODES = 30
DEFAULT_HORIZON = 6
# PPO 批大小：必须**显式**传给 train_ppo。历史事故：train_ppo 改为 batch 化
# （默认 48）后，本脚本只传 episodes 不传 batch ⇒ 默认 60 episodes 只剩 2 次梯度更新，
# 训练被静默饿死，结论"RL 不如 uniform"是欠训练伪影而非方法缺陷。
DEFAULT_PPO_BATCH = 48
# 可用的最低梯度更新次数。低于此值视为"训练不足"，该单元结论标注为不可用。
# 依据：角色 B 的预算扫描 —— 更新 5/25/63 次时 shadow 分别为 68.445/68.964/69.896，
# 5 次明显低于规则基线（欠训练伪影），25 次起进入可用区间。
MIN_VIABLE_UPDATES = 20


# ────────────────────────────────────────────────────────────
# 环境口径指纹（量纲哨兵）
# ────────────────────────────────────────────────────────────

def env_fingerprint() -> dict:
    """环境口径**实测**指纹：量纲/常量一旦漂移，两版 JSON 一比即显形。

    为什么必须实测而非硬编码常量：本项目已发生"consistency 量纲 0-100 → 0-1 而无人
    察觉"——评测脚本里复刻的阈值 60/75 遂使精准率恒为 0，而全部单测仍绿。若指纹写死
    常量，量纲变更时指纹本身不会变，等于没有哨兵。故此处全部经**实际运行环境**测得。
    """
    e = ReviewEnv(seed=20260914, horizon=2, noisy=False)
    cs = []
    for _ in range(4000):
        e.reset()
        cs.append(e.consistency)
    c_min, c_max = min(cs), max(cs)

    # 单步机械增益（noisy=False ⇒ 无噪声，且该增量与动作无关）
    e.reset()
    c0 = e.consistency
    e.step(3)
    step_gain = round(e.consistency - c0, 6)

    # 原生 precision 的隐式阈值：二分求"action=4 时 consistency 低于何值判 False"。
    # 不变式：`review_precision(lo,4)` 必须为 False、`review_precision(hi,4)` 为 True。
    # ⚠️ 这里曾把更新方向写反（True 时抬 lo），使结果收敛到区间上界而非真阈值 ——
    #    故下面显式断言不变式，写错就直接失败，不给静默错数。
    lo, hi = c_min, c_max
    assert not review_precision(lo, 4) and review_precision(hi, 4), (
        f"precision 阈值二分的不变式不成立（lo={lo}, hi={hi}）—— "
        "说明 review_precision 语义已变，请同步本指纹函数")
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if review_precision(mid, 4):
            hi = mid          # mid 已判 True ⇒ 阈值 ≤ mid
        else:
            lo = mid          # mid 判 False ⇒ 阈值 > mid
    prec_threshold = round((lo + hi) / 2.0, 4)

    return {
        "consistency_observed_range": [round(c_min, 4), round(c_max, 4)],
        "consistency_step_gain": step_gain,
        "precision_threshold_action4": prec_threshold,
        "rev_gain": {"matched": REV_GAIN_MATCHED, "balanced": REV_GAIN_BALANCED,
                     "mismatch": REV_GAIN_MISMATCH, "skip": REV_GAIN_SKIP},
        "reward_w": dict(REWARD_W),
        "action_tokens": {str(k): v for k, v in ACTION_TOKENS.items()},
        "skip_streak_limit": SKIP_STREAK_LIMIT,
        "review_min_review": REVIEW_MIN_REVIEW,
        "state_dim": STATE_DIM,
        "actions": list(REVIEW_ACTIONS),
    }


def reward_term_audit(n_samples: int = 240, data_seed: int = 20260914) -> dict:
    """奖励四分量在**动作维度**上的判别力审计（只测量 + 告警，**不改任何奖励权重**）。

    做法：在每个采样上下文里，对 5 个动作分别用**生产同款** `review_reward`
    （`return_components=True`）复算四个分量，统计各分量在动作间的极差：
      - 极差 ≡ 0 ⇒ 该分量在本环境中不区分类动作，即"名义有权重、实际不参与决策"；
      - 同时给出两种口径：「全 5 动作」与「有效动作集 {0,1,2,3}」——skip 被纪律门禁掉
        后，只在 skip vs 非 skip 之间变化的 precision 分量可能在有效动作集上恒为常数。

    ⚠️ 本函数**不得**用于"为了让 RL 赢而调奖励"。若审计发现某分项零判别力，正确动作是
    ①显式记录该事实、②交 CTO 决定是否重设环境语义（设计变更），而不是就地改权重。
    """
    rng = random.Random(data_seed)
    keys = ("gate", "precision", "cost", "discipline")
    spans_all: dict = {k: [] for k in keys}
    spans_valid: dict = {k: [] for k in keys}
    n_zero_all = {k: 0 for k in keys}
    n_zero_valid = {k: 0 for k in keys}

    for _ in range(n_samples):
        env = ReviewEnv(seed=rng.randint(1, 10 ** 9), horizon=6, noisy=True)
        env.reset()
        comps = {}
        for a in range(len(REVIEW_ACTIONS)):
            comps[a] = review_reward(
                gate_before=0.0, gate_after=env.gain_of(a),
                precision=review_precision(env.consistency, a),
                tokens=ACTION_TOKENS.get(a, 0.0), skip_streak=0,
                return_components=True)
        for k in keys:
            all_v = [comps[a][k] for a in range(5)]
            val_v = [comps[a][k] for a in (0, 1, 2, 3)]
            spans_all[k].append(max(all_v) - min(all_v))
            spans_valid[k].append(max(val_v) - min(val_v))
            if max(all_v) - min(all_v) <= 1e-12:
                n_zero_all[k] += 1
            if max(val_v) - min(val_v) <= 1e-12:
                n_zero_valid[k] += 1

    def _summ(spans, zeros):
        return {k: {"mean_span": round(sum(spans[k]) / max(1, len(spans[k])), 6),
                    "zero_span_rate": round(zeros[k] / max(1, n_samples), 4)}
                for k in keys}

    out = {
        "n_samples": n_samples, "data_seed": data_seed,
        "over_all_5_actions": _summ(spans_all, n_zero_all),
        "over_valid_4_actions": _summ(spans_valid, n_zero_valid),
    }
    zero_valid = [k for k in keys
                  if out["over_valid_4_actions"][k]["zero_span_rate"] >= 0.999]
    out["zero_discrimination_terms_on_valid_actions"] = zero_valid
    out["note"] = (
        "zero_span_rate≈1 的分项 ⇒ 该分项在有效动作集上恒为常数，其权重不参与 argmax 决策"
        "（事实记录，非调参指令）。" if zero_valid
        else "四个分项在有效动作集上均有判别力。")
    # discipline 分项在受护栏轨迹上恒不激活 —— 这是**设计使然**，值得写清楚，
    # 否则会被误读为"惩罚项失效"。它只在 skip_streak ≥ SKIP_STREAK_LIMIT 时非零，
    # 而 discipline_gate 的职责正是让那条界线永远不被跨过（连发 ≥2 发生率为 0）。
    _disc_at_limit = review_reward(
        gate_before=0.0, gate_after=0.0, precision=True, tokens=0.0,
        skip_streak=SKIP_STREAK_LIMIT, return_components=True)["discipline"]
    out["discipline_term_activation"] = {
        "at_skip_streak_0": 0.0,
        "at_skip_streak_limit": round(_disc_at_limit, 4),
        "note": ("该项仅在 skip_streak ≥ SKIP_STREAK_LIMIT 时非零；而 discipline_gate "
                 "保证受约束轨迹上 skip_streak ≤ SKIP_STREAK_LIMIT−1 ⇒ 护栏生效时该项"
                 "恒为 0（权重存在但属'违规才激活'型惩罚，非失效）。"),
    }
    return out


# ────────────────────────────────────────────────────────────
# 单 episode 指标采集（独立复算，不依赖 evaluate_policy）
# ────────────────────────────────────────────────────────────

def run_episode(mode: str, policy: Optional[ReviewWeightPolicy], seed: int,
                horizon: int) -> dict:
    """跑一个 episode，返回本 episode 的逐项指标。

    mode: "uniform" | "rule" | "supervised" | "rl"
      - uniform / rule 不需要网络；
      - supervised / rl 需要已构造并（可能）训练好的 policy 实例。
    """
    env = ReviewEnv(seed=seed, horizon=horizon)
    feats = env.reset()
    q0 = env.consistency  # 初始质量（50.0）

    total_r = 0.0
    tokens = 0.0
    skips = 0
    streak = 0
    max_streak = 0
    reviews_done = 0
    prec_hits = 0
    steps = 0

    for _ in range(horizon):
        if mode == "uniform":
            idx = 3
        elif mode == "rule":
            idx = _rule_action_idx(feats)
        elif mode.startswith("const:"):
            # 恒定动作消融：用于确定"最优恒定策略"上界（诊断用，非方案）
            idx = int(mode.split(":", 1)[1])
        else:
            idx, _src = policy.select_action(
                feats, deterministic=True, skip_streak=streak, reviews_done=reviews_done)
        idx = int(idx)
        if not (0 <= idx < len(REVIEW_ACTIONS)):
            idx = 3
        # 纪律护栏对**四臂统一**施加，且调用的是生产唯一实现（engines.review_policy.
        # discipline_gate），不在本脚本内复刻规则。
        # 历史教训：本脚本原先完全不施加护栏 ⇒ rule 臂未经 _block_skip 而报出
        # discipline_ok=False / max_skip_streak=2；那是**脚本口径伪影**，不是策略违规。
        idx = discipline_gate(idx, feats, streak, reviews_done)

        if idx == 4:
            skips += 1
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
            reviews_done += 1
        tokens += float(ACTION_TOKENS.get(idx, 0.0))

        feats, r, done = env.step(idx)
        # 精准评审口径：直接读环境**原生判定** `env.last_precision`（其实现为模块级
        # review_precision，唯一真值源），不在本脚本内复刻阈值。
        # 历史教训：本脚本曾硬编码 `thr = 75.0 if idx == 4 else 60.0`（0-100 时代产物），
        # consistency 量纲改 0-1 后该判定恒为 False ⇒ 精准率四臂全 0，而单测全绿。
        if env.last_precision:
            prec_hits += 1

        total_r += float(r)
        steps += 1
        if done:
            break

    return {
        "total_return": total_r,
        "mean_return": total_r / max(1, steps),
        "quality_gain": env.consistency - q0,
        "final_quality": env.consistency,
        "tokens": tokens,
        "skip_count": skips,
        "max_skip_streak": max_streak,
        "reviews_done": reviews_done,
        "precision_hits": prec_hits,
        "precision_rate": prec_hits / max(1, steps),
        "steps": steps,
        "discipline_violation": max_streak >= SKIP_STREAK_LIMIT,
    }


def aggregate(episodes: list[dict]) -> dict:
    n = len(episodes)
    total_steps = sum(e["steps"] for e in episodes)
    viol = sum(1 for e in episodes if e["discipline_violation"])
    return {
        "episodes": n,
        "mean_return": sum(e["total_return"] for e in episodes) / max(1, n),
        "mean_quality_gain": sum(e["quality_gain"] for e in episodes) / max(1, n),
        "mean_final_quality": sum(e["final_quality"] for e in episodes) / max(1, n),
        "mean_tokens": sum(e["tokens"] for e in episodes) / max(1, n),
        "skip_rate": sum(e["skip_count"] for e in episodes) / max(1, total_steps),
        "mean_skip_per_episode": sum(e["skip_count"] for e in episodes) / max(1, n),
        "precision_rate": sum(e["precision_hits"] for e in episodes) / max(1, total_steps),
        "max_skip_streak": max((e["max_skip_streak"] for e in episodes), default=0),
        "discipline_violation_rate": viol / max(1, n),
        "reviews_done_mean": sum(e["reviews_done"] for e in episodes) / max(1, n),
    }


# ────────────────────────────────────────────────────────────
# 策略构建
# ────────────────────────────────────────────────────────────

def build_policy(kind: str, seed: int, warmup_steps: int, ppo_episodes: int,
                 horizon: int, batch_episodes: int = DEFAULT_PPO_BATCH
                 ) -> tuple[Optional[ReviewWeightPolicy], dict]:
    """构建 supervised / rl 策略，返回 (policy, train_stats)。

    torch 不可用 → 返回 (None, {"degraded": True, ...})，由调用方如实标注。
    `batch_episodes` **显式**传入并落盘 `n_updates`，使"是否真训了"可被审计。
    """
    # 必须按 seed 分别播种：否则 ReviewWeightPolicy 默认 seed=42，
    # 3 个 RL 单元会训出同一份策略，"3-seed" 退化为同策略的 3 次评估。
    p = ReviewWeightPolicy(seed=seed)
    if not p.torch_available:
        return None, {"degraded": True, "reason": "torch 不可用", "kind": kind}

    stats: dict = {"degraded": False, "kind": kind, "seed": seed}
    w = p.warmup_with_rules(ReviewEnv(seed=seed, horizon=horizon),
                            steps=warmup_steps, seed=seed)
    stats["warmup"] = {
        "steps": w.get("steps"),
        "mean_loss": w.get("mean_loss"),
        "final_loss": w.get("final_loss"),
    }
    if kind == "rl":
        t = p.train_ppo(env=ReviewEnv(seed=seed, horizon=horizon),
                        episodes=ppo_episodes, horizon=horizon, seed=seed,
                        batch_episodes=batch_episodes)
        stats["ppo"] = {
            "trained": t.get("trained"),
            "episodes": t.get("episodes"),
            "batch_episodes": t.get("batch_episodes"),
            # 真实梯度更新次数（= episodes 缓冲分批刷新后的实际次数）。必须落盘：
            # 只报 episodes 参数会掩盖"批大小变更导致更新次数暴跌"的静默饿死。
            "n_updates": t.get("n_updates"),
            # 注：旧版键名 final_mean_return / first_mean_return 在 train_ppo 重构后
            # 已不存在 → 落盘会得到 null（静默丢失）。此处对齐现行键名。
            "mean_return_first_third": t.get("mean_return_first_third"),
            "mean_return_last_third": t.get("mean_return_last_third"),
            "improved": t.get("improved"),
            "det_return_before": t.get("det_return_before"),
            "det_return_after": t.get("det_return_after"),
            "improved_deterministic": t.get("improved_deterministic"),
            "reason": t.get("reason"),
        }
    return p, stats


# ────────────────────────────────────────────────────────────
# 主流程
# ────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="三元评审权重 3-seed 对比实验")
    ap.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    ap.add_argument("--episodes", type=int, default=DEFAULT_EPISODES,
                    help="每 (方案,seed) 评估 episode 数")
    ap.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    ap.add_argument("--warmup-steps", type=int, default=300)
    # ⚠️ 默认值已从 60 上调：60 episodes 在 batch=48 下只产生 **2 次**梯度更新
    # （旧版每 episode 更新一次时是 60 次）⇒ 训练被静默饿死，曾把结论误判为
    # "RL 不如 uniform"。3000/48 = 62 次更新是与角色 B 3-seed 验证一致的预算。
    ap.add_argument("--ppo-episodes", type=int, default=3000)
    ap.add_argument("--ppo-batch", type=int, default=DEFAULT_PPO_BATCH,
                    help="PPO 批大小（episodes // batch = 真实梯度更新次数，会落盘）")
    ap.add_argument("--ablation", action="store_true",
                    help="额外跑恒定动作消融，用于确定收益上界（诊断）")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    results = {
        "experiment": "review_mappo_3seed_comparison",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_order": "docs/CTO-芒得很职三元评审权重MAPPO化攻坚令-2026-09-14.md 阶段 3",
        "config": {
            "seeds": args.seeds,
            "eval_episodes_per_cell": args.episodes,
            "horizon": args.horizon,
            "warmup_steps": args.warmup_steps,
            "ppo_episodes": args.ppo_episodes,
            "ppo_batch_episodes": args.ppo_batch,
            "schemes": {
                "uniform": "均匀权重（绝对基线 = 灰度关闭现状）",
                "rule": "固定规则 _rule_action_idx（现有规则因子）",
                "supervised": "监督学习 warmup_with_rules（回归规则标签，无 RL）",
                "rl": "warmup 预热 + PPO 微调",
            },
            "discipline": {
                "skip_streak_limit": SKIP_STREAK_LIMIT,
                "review_min_review": REVIEW_MIN_REVIEW,
                "acceptance": "skip 连发 >= 2 发生率必须为 0",
                "guard": "四臂统一施加 engines.review_policy.discipline_gate（生产唯一实现）",
            },
            # 环境口径指纹（实测）：量纲/常量漂移会让新旧 JSON 的此段直接失配，
            # 从而显形，而不是静默污染指标（见 env_fingerprint docstring 的事故记录）。
            "env_fingerprint": env_fingerprint(),
        },
        # 奖励四分量判别力审计：把"某分项名义有权重、实际零判别力"变为可观测事实。
        # 只测量，不改奖励权重。
        "reward_term_audit": reward_term_audit(),
        "per_cell": {},
        "train_stats": [],
        "aggregate_by_scheme": {},
        "degraded": False,
        "notes": [],
    }

    # 评估用 episode 的种子：与训练 seed 派生但独立，避免"自己考自己"
    for scheme in SCHEMES:
        for seed in args.seeds:
            policy = None
            train_stats = None
            if scheme in ("supervised", "rl"):
                policy, train_stats = build_policy(
                    scheme, seed, args.warmup_steps, args.ppo_episodes,
                    args.horizon, args.ppo_batch)
                results["train_stats"].append(train_stats)
                if policy is None:
                    results["degraded"] = True
                    results["notes"].append(
                        f"{scheme}/seed={seed}: torch 不可用，该单元无法评估（如实标注，不伪造）")
                    continue
                # 训练预算硬门：更新次数过少时**显式**标注"结论不可用"，
                # 避免"欠训练"再一次被误读为"方法无效"。
                nu = (train_stats.get("ppo") or {}).get("n_updates")
                if scheme == "rl" and nu is not None and nu < MIN_VIABLE_UPDATES:
                    results["training_budget_ok"] = False
                    results["notes"].append(
                        f"⚠️ rl/seed={seed}: 仅 {nu} 次梯度更新（< {MIN_VIABLE_UPDATES}），"
                        f"训练不足 ⇒ 该单元结论不可用（不是「RL 不行」的证据）。"
                        f"请提高 --ppo-episodes 或减小 --ppo-batch。")

            eps = []
            rng = random.Random(seed * 1000 + 17)
            for _ in range(args.episodes):
                eseed = rng.randint(1, 10**6)
                eps.append(run_episode(scheme, policy, eseed, args.horizon))

            agg = aggregate(eps)
            results["per_cell"][f"{scheme}/seed={seed}"] = {
                "scheme": scheme, "seed": seed, **agg}

    # 跨 seed 汇总
    for scheme in SCHEMES:
        cells = [v for k, v in results["per_cell"].items() if v["scheme"] == scheme]
        if not cells:
            continue
        n = len(cells)
        def avg(key):
            return sum(c[key] for c in cells) / n
        results["aggregate_by_scheme"][scheme] = {
            "seeds": [c["seed"] for c in cells],
            "mean_return": avg("mean_return"),
            "mean_return_std": (sum((c["mean_return"] - avg("mean_return")) ** 2
                                    for c in cells) / n) ** 0.5,
            "mean_quality_gain": avg("mean_quality_gain"),
            "mean_final_quality": avg("mean_final_quality"),
            "mean_tokens": avg("mean_tokens"),
            "skip_rate": avg("skip_rate"),
            "precision_rate": avg("precision_rate"),
            "max_skip_streak": max(c["max_skip_streak"] for c in cells),
            "discipline_violation_rate": avg("discipline_violation_rate"),
        }

    # 诊断：恒定动作消融（确定"最优恒定策略"上界，解释 RL 收益天花板）
    agg = results["aggregate_by_scheme"]
    if args.ablation:
        abl = {}
        for idx, name in enumerate(REVIEW_ACTIONS):
            cells = []
            for seed in args.seeds:
                rng = random.Random(seed * 1000 + 17)
                eps = [run_episode(f"const:{idx}", None, rng.randint(1, 10**6),
                                   args.horizon) for _ in range(args.episodes)]
                cells.append(aggregate(eps))
            n = len(cells)
            abl[f"{idx}:{name}"] = {
                "mean_return": sum(c["mean_return"] for c in cells) / n,
                "mean_quality_gain": sum(c["mean_quality_gain"] for c in cells) / n,
                "mean_tokens": sum(c["mean_tokens"] for c in cells) / n,
                "precision_rate": sum(c["precision_rate"] for c in cells) / n,
                "skip_rate": sum(c["skip_rate"] for c in cells) / n,
            }
        results["constant_action_ablation"] = abl
        best = max(abl.items(), key=lambda kv: kv[1]["mean_return"])
        results["notes"].append(
            f"诊断：最优恒定动作 = {best[0]}（回报 {best[1]['mean_return']:.4f}）；"
            f"该值即「恒定策略」上界，RL 若未超过它说明未学到上下文自适应增益")
        if "rl" in agg:
            verdict_rl_beats_const = agg["rl"]["mean_return"] >= best[1]["mean_return"]
            results["verdict_pre"] = {
                "rl_beats_best_constant": verdict_rl_beats_const,
                "best_constant": best[0],
                "best_constant_return": best[1]["mean_return"],
                "rl_return": agg["rl"]["mean_return"],
            }

    # 验收判定（攻坚令：RL ≥ 规则 ≥ 监督；纪律违规率为 0）
    agg = results["aggregate_by_scheme"]
    verdict = {"available_schemes": list(agg.keys())}
    # 并入诊断判定（恒定动作上界）
    verdict.update(results.pop("verdict_pre", {}))
    if "rl" in agg and "rule" in agg:
        verdict["rl_ge_rule"] = agg["rl"]["mean_return"] >= agg["rule"]["mean_return"]
        verdict["rl_vs_rule_gain_pct"] = (
            (agg["rl"]["mean_return"] - agg["rule"]["mean_return"])
            / abs(agg["rule"]["mean_return"]) * 100.0
            if agg["rule"]["mean_return"] else None)
    if "rule" in agg and "supervised" in agg:
        verdict["rule_ge_supervised"] = (
            agg["rule"]["mean_return"] >= agg["supervised"]["mean_return"])
    all_viol = [v["discipline_violation_rate"]
                for v in agg.values()]
    verdict["discipline_ok"] = all(v == 0.0 for v in all_viol)
    verdict["max_skip_streak_overall"] = max(
        (v["max_skip_streak"] for v in agg.values()), default=0)
    results["verdict"] = verdict

    if not verdict.get("discipline_ok"):
        results["notes"].append("警告：出现 skip 连发 ≥2 的纪律违规，需回查奖励/硬约束")

    out = args.out or str(
        _ROOT / "experiments" / "results"
        / f"review_mappo_eval_{datetime.now().strftime('%Y%m%d')}.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 控制台对比表
    print("=" * 92)
    print(f"三元评审权重 3-seed 对比   episodes/cell={args.episodes} horizon={args.horizon}")
    print("=" * 92)
    hdr = f"{'方案':<12}{'回报':>10}{'质量增益':>10}{'终态质量':>10}{'token':>10}{'skip率':>9}{'精准率':>9}{'连发':>6}"
    print(hdr)
    print("-" * 92)
    for scheme in SCHEMES:
        if scheme not in agg:
            print(f"{scheme:<12}{'(缺评估数据)':>10}")
            continue
        a = agg[scheme]
        print(f"{scheme:<12}{a['mean_return']:>10.4f}{a['mean_quality_gain']:>10.3f}"
              f"{a['mean_final_quality']:>10.2f}{a['mean_tokens']:>10.1f}"
              f"{a['skip_rate']:>9.3f}{a['precision_rate']:>9.3f}"
              f"{a['max_skip_streak']:>6}")
    if "constant_action_ablation" in results:
        print("\n--- 恒定动作消融（诊断：收益上界）---")
        for k, v in results["constant_action_ablation"].items():
            print(f"  {k:<22} 回报={v['mean_return']:>8.4f}  质量增益={v['mean_quality_gain']:>7.3f}"
                  f"  token={v['mean_tokens']:>7.1f}  skip率={v['skip_rate']:.3f}")
    print("-" * 92)
    for k, v in verdict.items():
        print(f"  {k}: {v}")

    # 审计摘要（只陈述事实，不调参）
    aud = results["reward_term_audit"]
    print("\n--- 奖励分项判别力（动作维极差；0 = 该分量不参与决策）---")
    for term in ("gate", "precision", "cost", "discipline"):
        a5 = aud["over_all_5_actions"][term]
        a4 = aud["over_valid_4_actions"][term]
        print(f"  {term:<11} 全5动作 mean_span={a5['mean_span']:.4f} "
              f"零极差率={a5['zero_span_rate']:.3f} | "
              f"有效4动作 mean_span={a4['mean_span']:.4f} "
              f"零极差率={a4['zero_span_rate']:.3f}")
    if aud["zero_discrimination_terms_on_valid_actions"]:
        print(f"  ⚠️ 有效动作集上零判别力分项: "
              f"{aud['zero_discrimination_terms_on_valid_actions']}")
    fp = results["config"]["env_fingerprint"]
    print(f"\n  环境指纹: consistency 区间={fp['consistency_observed_range']} "
          f"步进增益={fp['consistency_step_gain']} "
          f"precision 阈值={fp['precision_threshold_action4']}")
    if not results.get("training_budget_ok", True):
        print("  ⚠️ training_budget_ok=False —— 存在训练不足的单元，其结论不可用")
    print(f"\n落盘: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
