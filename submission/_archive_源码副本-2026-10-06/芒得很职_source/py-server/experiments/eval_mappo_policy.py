# ============================================================
# eval_mappo_policy.py — MAPPO 教学策略层对比实验（M3）
#
# 对比：规则基线（teaching_rules.decide_policy_action） vs MAPPO 策略
#   （engines.mappo_policy.MappoPolicy，规则监督预热 + Actor-Critic + GAE + PPO）
#
# 学生水平：beginner(0.25) / intermediate(0.50) / advanced(0.75)，水平随时间漂移（动态环境）
# 指标：平均回合奖励 / 平均正确率 / 平均 token 成本系数
# 稳健性：多 seed 训练（默认 3），报告均值 ± 标准差
#
# 运行：.venv\Scripts\python.exe experiments\eval_mappo_policy.py
# 产物：experiments/results/mappo_policy_eval_YYYYMMDD.json
# 降级：torch 不可用（Windows SIGSEGV 风险）→ 仅规则基线 + 说明
# ============================================================

import datetime
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.mappo_policy import TeachingEnv, MappoPolicy, _ensure_torch, _COST_FACTOR
from engines.teaching_rules import teaching_rules


STUDENT_LEVELS = [("beginner", 0.25), ("intermediate", 0.50), ("advanced", 0.75)]
EVAL_EPISODES = 50
SEEDS = [1, 42, 2024]


def run_eval(env: TeachingEnv, act_fn, episodes: int = EVAL_EPISODES) -> dict:
    """在给定环境上跑 act_fn 策略，统计回合级指标。"""
    rewards, accs, costs = [], [], []
    for _ in range(episodes):
        state = env.reset()
        done = False
        ep_reward, ep_acc, ep_cost = 0.0, [], []
        while not done:
            action = act_fn(state)
            env_action = {
                k: action[k] for k in ("difficulty", "teaching_mode", "review_intensity")
            }
            state, r, done = env.step(env_action)
            ep_reward += r
            ep_acc.append(env.accuracy)
            ep_cost.append(_COST_FACTOR.get(action["review_intensity"], 2.0))
        rewards.append(ep_reward)
        accs.append(sum(ep_acc) / len(ep_acc) if ep_acc else 0.0)
        costs.append(sum(ep_cost) / len(ep_cost) if ep_cost else 0.0)
    return {
        "avg_reward": round(statistics.mean(rewards), 4),
        "avg_accuracy": round(statistics.mean(accs), 4),
        "avg_cost": round(statistics.mean(costs), 4),
    }


def rule_action(state: dict) -> dict:
    """规则基线：教学规则引擎策略决策。"""
    return teaching_rules.decide_policy_action(
        profile=state["profile"],
        topic="",
        difficulty=state["difficulty"],
        round_num=state["round_num"],
        gate_result=state["gate_result"],
    )


def mappo_action_factory(policy: MappoPolicy):
    def _act(state: dict) -> dict:
        return policy.select_action(
            profile=state["profile"],
            difficulty=state["difficulty"],
            round_num=state["round_num"],
            last_accuracy=state["last_accuracy"],
            gate_result=state["gate_result"],
            topic_weight=state["topic_weight"],
            deterministic=True,
        )
    return _act


def summarize(values: list[float]) -> dict:
    return {
        "mean": round(statistics.mean(values), 4),
        "std": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
        "per_seed": [round(v, 4) for v in values],
    }


def main() -> None:
    print("=" * 70)
    print("M3 对比实验：规则基线 vs MAPPO 教学策略（动态学生环境）")
    print("=" * 70)

    report = {"generated_at": datetime.date.today().isoformat(), "levels": {}}

    # ── 规则基线（水平随时间漂移，考验静态标签失配）──
    for level_name, level_val in STUDENT_LEVELS:
        env = TeachingEnv(student_level=level_val, seed=1, drift=0.06)
        report["levels"].setdefault(level_name, {})["rules"] = run_eval(env, rule_action)

    # ── MAPPO：多 seed 训练 + 评估 ──
    torch = _ensure_torch()
    if torch is None:
        report["mappo"] = {"trained": False, "reason": "torch unavailable（Windows SIGSEGV 降级）"}
        print("[降级] torch 不可用：仅规则基线。")
        return

    from config import get_gomarl_config
    cfg = get_gomarl_config()
    episodes = int(cfg.get("mappo_episodes", 1000))

    seed_metrics = []
    per_level = {name: {"reward": [], "accuracy": [], "cost": []} for name, _, in STUDENT_LEVELS}

    for s_idx, seed in enumerate(SEEDS, start=1):
        print(f"[训练 seed={seed}] 规则监督预热 → MAPPO curriculum（三档水平 + 漂移 0.06），"
              f"episodes={episodes} …")
        policy = MappoPolicy(cfg)
        env_train = TeachingEnv(student_level=0.50, seed=seed, drift=0.06, curriculum=True)
        warmup = policy.warmup_with_rules(env_train, steps=800, seed=seed + 7)
        metrics = policy.train(env_train, episodes=episodes, seed=seed)
        seed_metrics.append(metrics)
        print(f"  seed={seed} 训练完成: warmup_loss={warmup.get('avg_loss')}, "
              f"avg_reward={metrics['avg_reward']:.3f}, avg_acc={metrics['avg_accuracy']:.3f}")

        act = mappo_action_factory(policy)
        for level_name, level_val in STUDENT_LEVELS:
            env = TeachingEnv(student_level=level_val, seed=1, drift=0.06)
            m = run_eval(env, act)
            per_level[level_name]["reward"].append(m["avg_reward"])
            per_level[level_name]["accuracy"].append(m["avg_accuracy"])
            per_level[level_name]["cost"].append(m["avg_cost"])

    report["mappo"] = {"trained": True, "seeds": SEEDS, "train_episodes": episodes}
    for level_name in ("beginner", "intermediate", "advanced"):
        report["levels"][level_name]["mappo"] = {
            "avg_reward": summarize(per_level[level_name]["reward"]),
            "avg_accuracy": summarize(per_level[level_name]["accuracy"]),
            "avg_cost": summarize(per_level[level_name]["cost"]),
        }

    # ── 输出对比表 ──
    print("-" * 70)
    for level_name in ("beginner", "intermediate", "advanced"):
        d = report["levels"][level_name]
        for key, label in (("rules", "规则基线"), ("mappo", "MAPPO")):
            if key in d:
                m = d[key]
                if key == "mappo":
                    print(f"[{level_name}] {label}: 回合奖励 {m['avg_reward']['mean']}±{m['avg_reward']['std']} | "
                          f"正确率 {m['avg_accuracy']['mean']}±{m['avg_accuracy']['std']} | "
                          f"成本 {m['avg_cost']['mean']}±{m['avg_cost']['std']}")
                else:
                    print(f"[{level_name}] {label}: 回合奖励 {m['avg_reward']} | "
                          f"正确率 {m['avg_accuracy']} | 成本 {m['avg_cost']}")

    # ── 保存结果 ──
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"mappo_policy_eval_{datetime.date.today().strftime('%Y%m%d')}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("-" * 70)
    print(f"[产物] {out_path}")


if __name__ == "__main__":
    main()
