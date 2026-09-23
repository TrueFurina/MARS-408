# ============================================================
# eval_marl_algorithms.py — MARL 算法实测对比（M4 对比研究）
#
# 在 MARS-408 教学决策 MDP（动态学生环境）上对比四类算法：
#   IQL / VDN / QMIX（DQN 家族，engines/marl_dqn.py）vs MAPPO（engines/mappo_policy.py）
#
# 多智能体建模：agent0=难度档位(4)，agent1=讲解方式(3)，agent2=评审强度(3)
# 共享 8 维状态、共享全局奖励；学生水平三档 + 漂移（动态环境）
#
# 运行：.venv\Scripts\python.exe experiments\eval_marl_algorithms.py
# 产物：experiments/results/marl_algorithms_eval_YYYYMMDD.json
# ============================================================

import datetime
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.mappo_policy import TeachingEnv as _TeachingEnv
from engines.mappo_policy import MappoPolicy, _COST_FACTOR
from engines.marl_dqn import (
    _ensure_torch, MultiAgentTeachingEnv, IQLearner, VDNLearner, QMIXLearner,
    train_value_learner, REVIEW_INTENSITIES,
)
from engines.teaching_rules import teaching_rules

STUDENT_LEVELS = [("beginner", 0.25), ("intermediate", 0.50), ("advanced", 0.75)]
EVAL_EPISODES = 50
SEEDS = [1, 42, 2024]
VALUE_EPISODES = 1200


# ── 评估统一入口 ──

def eval_mappo(policy, level_val):
    """MAPPO 评估（单决策者多动作头 → 联合动作）。"""
    env = _TeachingEnv(student_level=level_val, seed=1, drift=0.06)
    rewards, accs, costs = [], [], []
    for _ in range(EVAL_EPISODES):
        state = env.reset()
        done = False
        ep_r, ep_a, ep_c = 0.0, [], []
        while not done:
            action = policy.select_action(
                profile=state["profile"], difficulty=state["difficulty"],
                round_num=state["round_num"], last_accuracy=state["last_accuracy"],
                gate_result=state["gate_result"], topic_weight=state["topic_weight"],
                deterministic=True,
            )
            state, r, done = env.step({k: action[k] for k in
                                       ("difficulty", "teaching_mode", "review_intensity")})
            ep_r += r
            ep_a.append(env.accuracy)
            ep_c.append(_COST_FACTOR.get(action["review_intensity"], 2.0))
        rewards.append(ep_r)
        accs.append(sum(ep_a) / len(ep_a))
        costs.append(sum(ep_c) / len(ep_c))
    return {
        "avg_reward": statistics.mean(rewards),
        "avg_accuracy": statistics.mean(accs),
        "avg_cost": statistics.mean(costs),
    }


def eval_value_learner(learner, level_val):
    """DQN 家族评估（确定性 argmax）。"""
    env = MultiAgentTeachingEnv(student_level=level_val, seed=1, drift=0.06)
    rewards, accs, costs = [], [], []
    for _ in range(EVAL_EPISODES):
        s = env.reset()
        done = False
        ep_r, ep_a, ep_c = 0.0, [], []
        while not done:
            a = learner.select_actions(s, eval_mode=True)
            s, r, done = env.step(a)
            ep_r += r
            ep_a.append(env.env.accuracy)
            ep_c.append(_COST_FACTOR.get(REVIEW_INTENSITIES[a[2]], 2.0))
        rewards.append(ep_r)
        accs.append(sum(ep_a) / len(ep_a))
        costs.append(sum(ep_c) / len(ep_c))
    return {
        "avg_reward": statistics.mean(rewards),
        "avg_accuracy": statistics.mean(accs),
        "avg_cost": statistics.mean(costs),
    }


def summarize(values: list) -> dict:
    return {
        "mean": round(statistics.mean(values), 4),
        "std": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
        "per_seed": [round(v, 4) for v in values],
    }


def main() -> None:
    print("=" * 74)
    print("M4 对比研究：IQL / VDN / QMIX / MAPPO 教学决策实测对比")
    print("=" * 74)

    report = {
        "generated_at": datetime.date.today().isoformat(),
        "algorithms": ["iql", "vdn", "qmix", "mappo"],
        "levels": {},
        "train": {},
    }
    for lv in ("beginner", "intermediate", "advanced"):
        report["levels"][lv] = {}

    torch = _ensure_torch()
    if torch is None:
        print("[降级] torch 不可用，仅规则基线")
        return

    from config import get_gomarl_config
    cfg = get_gomarl_config()
    mappo_episodes = int(cfg.get("mappo_episodes", 1000))

    # ── 规则基线（参考线）──
    print("[基线] 规则教学策略")
    for level_name, level_val in STUDENT_LEVELS:
        env = _TeachingEnv(student_level=level_val, seed=1, drift=0.06)
        rewards, accs, costs = [], [], []
        for _ in range(EVAL_EPISODES):
            state = env.reset()
            done = False
            ep_r, ep_a, ep_c = 0.0, [], []
            while not done:
                act = teaching_rules.decide_policy_action(
                    profile=state["profile"], difficulty=state["difficulty"],
                    round_num=state["round_num"], gate_result=state["gate_result"])
                state, r, done = env.step({k: act[k] for k in
                                           ("difficulty", "teaching_mode", "review_intensity")})
                ep_r += r
                ep_a.append(env.accuracy)
                ep_c.append(_COST_FACTOR.get(act["review_intensity"], 2.0))
            rewards.append(ep_r); accs.append(sum(ep_a) / len(ep_a)); costs.append(sum(ep_c) / len(ep_c))
        report["levels"][level_name]["rules"] = {
            "avg_reward": round(statistics.mean(rewards), 4),
            "avg_accuracy": round(statistics.mean(accs), 4),
            "avg_cost": round(statistics.mean(costs), 4),
        }

    # ── MAPPO（3-seed）──
    print(f"[训练] MAPPO × {len(SEEDS)} seeds（episodes={mappo_episodes}）…")
    mappo_per_level = {lv: {"reward": [], "accuracy": [], "cost": []} for lv, _ in STUDENT_LEVELS}
    for seed in SEEDS:
        policy = MappoPolicy(cfg)
        env_train = _TeachingEnv(student_level=0.5, seed=seed, drift=0.06, curriculum=True)
        policy.warmup_with_rules(env_train, steps=800, seed=seed + 7)
        metrics = policy.train(env_train, episodes=mappo_episodes, seed=seed)
        print(f"  seed={seed}: avg_reward={metrics['avg_reward']:.3f}, avg_acc={metrics['avg_accuracy']:.3f}")
        for level_name, level_val in STUDENT_LEVELS:
            m = eval_mappo(policy, level_val)
            mappo_per_level[level_name]["reward"].append(m["avg_reward"])
            mappo_per_level[level_name]["accuracy"].append(m["avg_accuracy"])
            mappo_per_level[level_name]["cost"].append(m["avg_cost"])
    report["train"]["mappo"] = {"episodes": mappo_episodes}
    for level_name in ("beginner", "intermediate", "advanced"):
        report["levels"][level_name]["mappo"] = {
            "avg_reward": summarize(mappo_per_level[level_name]["reward"]),
            "avg_accuracy": summarize(mappo_per_level[level_name]["accuracy"]),
            "avg_cost": summarize(mappo_per_level[level_name]["cost"]),
        }

    # ── DQN 家族（IQL / VDN / QMIX，3-seed）──
    for algo_name, cls in (("iql", IQLearner), ("vdn", VDNLearner), ("qmix", QMIXLearner)):
        print(f"[训练] {algo_name.upper()} × {len(SEEDS)} seeds（episodes={VALUE_EPISODES}）…")
        per_level = {lv: {"reward": [], "accuracy": [], "cost": []} for lv, _ in STUDENT_LEVELS}
        for seed in SEEDS:
            learner = cls(seed=seed)
            env_train = MultiAgentTeachingEnv(student_level=0.5, seed=seed, drift=0.06, curriculum=True)
            metrics = train_value_learner(learner, env_train, episodes=VALUE_EPISODES, seed=seed)
            print(f"  seed={seed}: avg_reward={metrics['avg_reward']:.3f}, avg_acc={metrics['avg_accuracy']:.3f}")
            for level_name, level_val in STUDENT_LEVELS:
                m = eval_value_learner(learner, level_val)
                per_level[level_name]["reward"].append(m["avg_reward"])
                per_level[level_name]["accuracy"].append(m["avg_accuracy"])
                per_level[level_name]["cost"].append(m["avg_cost"])
        report["train"][algo_name] = {"episodes": VALUE_EPISODES}
        for level_name in ("beginner", "intermediate", "advanced"):
            report["levels"][level_name][algo_name] = {
                "avg_reward": summarize(per_level[level_name]["reward"]),
                "avg_accuracy": summarize(per_level[level_name]["accuracy"]),
                "avg_cost": summarize(per_level[level_name]["cost"]),
            }

    # ── 输出汇总表 ──
    print("-" * 74)
    for level_name in ("beginner", "intermediate", "advanced"):
        d = report["levels"][level_name]
        print(f"[{level_name}]")
        for key in ("rules", "iql", "vdn", "qmix", "mappo"):
            m = d.get(key)
            if not m:
                continue
            if key == "rules":
                print(f"  rules : 奖励 {m['avg_reward']:.3f} | 正确率 {m['avg_accuracy']:.3f} | 成本 {m['avg_cost']:.2f}")
            else:
                print(f"  {key:<6}: 奖励 {m['avg_reward']['mean']:.3f}±{m['avg_reward']['std']:.3f} | "
                      f"正确率 {m['avg_accuracy']['mean']:.3f}±{m['avg_accuracy']['std']:.3f} | "
                      f"成本 {m['avg_cost']['mean']:.2f}±{m['avg_cost']['std']:.2f}")

    # ── 保存 ──
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"marl_algorithms_eval_{datetime.date.today().strftime('%Y%m%d')}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("-" * 74)
    print(f"[产物] {out_path}")


if __name__ == "__main__":
    main()
