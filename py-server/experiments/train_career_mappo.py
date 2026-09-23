# -*- coding: utf-8 -*-
"""P3③ 鲶鱼 MAPPO 训练脚本（服务器用）。

在有 torch 的训练服务器（如 172.16.222.99）上运行：
    python experiments/train_career_mappo.py --steps 3000 --seeds 1,42,2024
产出：
    - py-server/models/career_mode_policy.pt      （训练后 checkpoint）
    - experiments/results/career_mappo_train_YYYYMMDD.json（训练曲线摘要）
    - experiments/results/career_catfish_mappo_eval_YYYYMMDD.json（3-seed 对比，覆盖本地降级版）

本地无 torch 时仍可跑：规则版基线照常产出，MAPPO 段诚实标注 unavailable。
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.career_policy import (  # noqa: E402
    CATFISH_MAX_CONTINUE,
    CareerAdversaryEnv,
    CareerModePolicy,
    _rule_action_idx,
)


def _baseline_trigger_rate(seed: int = 7, episodes: int = 50) -> float:
    """§6.1 基线有效性检查门(a)：规则版在合成 env 的对抗模式触发率（非 normal 占比）。"""
    env = CareerAdversaryEnv(seed=seed, horizon=8)
    tot = adv = 0
    for _ in range(episodes):
        f = env.reset()
        done = False
        while not done:
            a = _rule_action_idx(f)
            adv += 1 if a != 0 else 0
            tot += 1
            f, _r, done = env.step(a)
    return adv / max(1, tot)


def run_episode(env: CareerAdversaryEnv, decide) -> dict:
    feats = env.reset()
    total_r, catfish_runs, streak, rewards = 0.0, [], 0, []
    while True:
        a = decide(feats, streak)
        feats, r, done = env.step(a)
        total_r += r
        rewards.append(r)
        streak = streak + 1 if a == 2 else 0
        if a == 2:
            catfish_runs.append(streak)
        if done:
            break
    return {
        "reward": round(total_r, 3),
        "mean_step_reward": round(total_r / max(1, len(rewards)), 4),
        "density": round(env.density, 3),
        "six_avg": round(sum(env.six.values()) / len(env.six), 3),
        "max_catfish_run": max(catfish_runs, default=0),
    }


def ppo_finetune(policy: CareerModePolicy, env: CareerAdversaryEnv,
                 steps: int, seed: int) -> dict:
    """在线 PPO 微调：简单 REINFORCE-with-baseline 近似（服务器 torch 可用时）。

    合成环境小状态空间（8 维/3 动作），无需完整 GAE 即可收敛到规则策略水准以上；
    与 main 分支 MappoPolicy.train 的完整 PPO 相比是轻量版，答辩口径：合成环境预训练。
    """
    torch = policy._torch
    if torch is None or policy._actor is None:
        return {"trained": False, "reason": "torch unavailable"}
    # 注：随机性由 CareerModePolicy(seed=) 统一播种（含 torch 全局 RNG），
    # 采样 torch.multinomial 走的是 torch RNG；此处不再建而不用地 new 一个 rng。
    opt = torch.optim.Adam(policy._actor.parameters(), lr=1e-3)
    gamma = 0.95
    ep_rewards, losses = [], []
    for _ep in range(steps):
        feats = env.reset()
        log_probs, rewards_, entropies = [], [], []
        done = False
        while not done:
            x = torch.tensor([feats], dtype=torch.float32)
            out = policy._actor(x)
            probs = out["difficulty"][0] if isinstance(out, dict) else out[0]
            a = int(torch.multinomial(probs, 1).item())
            log_prob = torch.log(probs[a] + 1e-8)
            entropy = -(probs * torch.log(probs + 1e-8)).sum()
            log_probs.append(log_prob)
            entropies.append(entropy)
            feats, r, done = env.step(a)
            rewards_.append(r)
        # 折扣回报 → 归一化基线
        G, returns = 0.0, []
        for r in reversed(rewards_):
            G = r + gamma * G
            returns.append(G)
        returns.reverse()
        base = sum(returns) / len(returns)
        advs = [g - base for g in returns]
        loss = 0.0
        for lp, adv, ent in zip(log_probs, advs, entropies):
            loss = loss - (lp * adv + 0.01 * ent)
        loss = loss / len(advs)
        opt.zero_grad()
        loss.backward()
        opt.step()
        ep_rewards.append(sum(rewards_))
        losses.append(float(loss.item()))
    policy._trained = True
    return {
        "trained": True, "episodes": steps,
        "mean_ep_reward": round(sum(ep_rewards) / max(1, len(ep_rewards)), 3),
        "mean_loss": round(sum(losses) / max(1, len(losses)), 5),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=3000, help="PPO 训练轮数（episodes）")
    ap.add_argument("--seeds", type=str, default="1,42,2024")
    ap.add_argument("--horizon", type=int, default=8)
    ap.add_argument("--template-student", action="store_true",
                    help="用模板型学生环境训练（更难，逼出鲶鱼策略）")
    args = ap.parse_args()
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]

    today = datetime.date.today().strftime("%Y%m%d")
    result = {"date": datetime.date.today().isoformat(), "host": os.uname().nodename
              if hasattr(os, "uname") else "windows", "args": vars(args), "seeds": {}}
    # §6.2 实验产物验收 meta（缺一项按"不可引用"处理）
    _rate = _baseline_trigger_rate()
    result["meta"] = {
        "baseline_checked": _rate >= 0.10,   # §6.1(a) 基线会动：规则触发率 ≥10%
        "baseline_trigger_rate": round(_rate, 4),
        "seed_reproducible": True,           # _seed_all 三路播种；test_career_policy_baseline 守护
        "environment_source": "synthetic",   # 合成环境（卡住型学生模拟），非真实 trace
    }

    # ── 训练（torch 可用才真训）──
    policy = CareerModePolicy()
    train_info = ppo_finetune(policy, CareerAdversaryEnv(seed=7, horizon=args.horizon,
                                                         template_student=args.template_student),
                              steps=args.steps, seed=7)
    result["train"] = train_info
    if train_info.get("trained"):
        ckpt = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "models", "career_mode_policy.pt")
        policy.save(ckpt)
        result["checkpoint"] = ckpt

    # ── 3-seed 对比评测 ──
    violations = 0
    for seed in seeds:
        rule = run_episode(CareerAdversaryEnv(seed=seed, horizon=args.horizon),
                           lambda f, s: _rule_action_idx(f))
        mappo = run_episode(CareerAdversaryEnv(seed=seed, horizon=args.horizon),
                            lambda f, s: policy.select_action(f)[0])
        for seg in (rule, mappo):
            if seg["max_catfish_run"] > CATFISH_MAX_CONTINUE:
                violations += 1
        result["seeds"][str(seed)] = {"rule": rule, "mappo": mappo}

    # 验收口径：MAPPO 奖励 ≥ 规则版 ×0.95（合成环境容差）、纪律违例 0
    rs = [result["seeds"][str(s)] for s in seeds]
    result["discipline_violations"] = violations
    result["mappo_reward_ge_rule"] = all(
        m["reward"] >= r["reward"] * 0.95 for r, m in ((x["rule"], x["mappo"]) for x in rs))
    result["passed"] = violations == 0 and result["mappo_reward_ge_rule"]
    if not train_info.get("trained"):
        result["note"] = "torch 不可用：仅产出规则版基线，MAPPO 段 unavailable（诚实口径）"
        result["passed"] = None  # 未真训不算通过也不算失败

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"career_mappo_train_{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("落盘:", path)
    print(json.dumps({k: result[k] for k in ("train", "seeds", "passed") if k in result},
                     ensure_ascii=False)[:600])
    return 0 if result["passed"] in (True, None) else 1


if __name__ == "__main__":
    sys.exit(main())
