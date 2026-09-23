# ============================================================
# career_policy — P3③ 鲶鱼机制 MAPPO 化（决策层）
#
# 按 docs/CTO-芒得很职P3鲶鱼MAPPO化设计-2026-09-12.md 实现：
#   - 只换决策层：decide_career_mode 输出契约与规则版一致（三模式），
#     下游追问生成/评估零改动
#   - 复用 mappo_policy 的 ActorNet/CriticNet 构建框架（_build_networks）
#     与 warmup_with_rules 思路（规则版做监督预热），不复用其模型权重
#   - 默认灰度关闭（config: career.use_career_mappo=False），规则版兜底
# ============================================================

import logging
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger("netlearn.career.policy")

# 动作空间：与现有三模式一一对应（设计文档 0/1/2）
CAREER_ACTIONS = ["normal", "escalating", "catfish"]

# 奖励权重（设计文档初值，可调）
REWARD_W = {"gain": 0.5, "evidence": 0.3, "cost": 0.15, "discipline": 0.05}

CATFISH_MAX_CONTINUE = 2  # 与 career_state 保持一致（纪律项）

# 无证据轮的证据密度默认值。
# 旧值 0.5 的缺陷（CTO 派单一根因 A）：规则判据 `density < 0.35` / `< 0.45` 恒不满足
# → 规则死锁在 normal、escalating/catfish 永不触发。改为与合成环境"卡住型学生"开局
# 0.34 同量级 ⇒ "无证据/低信息"轮触发加压。以"对齐默认值"方式修复，**不改规则判据语义**。
EVIDENCE_DENSITY_DEFAULT = 0.3

# ── 对抗环境动力学调参（决定 P3③ 鲶鱼机制是否"可达"且"值得用"）──
# 旧环境三个缺陷（均已实测复现）：
#   ① 密度只单调上升 → 规则永远选 normal → 鲶鱼从未被选中（阈值不可达，机制形同虚设）；
#   ② token 成本按 /2000 归一（得 0.30~0.55），远大于证据密度增益（0.05×0.3=0.015），
#      成本项压倒收益项 → 奖励与教学效果**反相关**：规则版把密度从 0.11 抬到 0.41，
#      奖励反而更低（-0.0767 vs 恒 normal 的 -0.0669）→ 任何"出手"都被惩罚；
#   ③ **增益上限倒置**：catfish 上限 0.95 高于 escalating 的 0.62，导致密度越高鲶鱼
#      的相对优势越大（与"鲶鱼=打破僵局"的定位相反）→ 实测 reward 最优策略 50% 步数
#      用鲶鱼、token 1350，直接违反设计文档验收表"成本 ≤ 规则版×1.1"。这是
#      "调参改不改得动结论"的关键：属 reward 与验收约束的**真实冲突**，非欠训练。
# 现改为：
#   - 卡住型学生：normal 持续掉密度（-0.06），只有加压/鲶鱼能抬升（鲶鱼瞬时更强）；
#   - **cap_catfish(0.50) < cap_escalating(0.85)**：鲶鱼是"破僵局"的重锤，只在低密度
#     有效；密度一上来边际收益即归零，而它 token 更贵（1100 vs 900）→ 自然收手。
#     温和加压则可持续微调（上限高）。二者定位不再重叠。
#   - 成本归一化基数改为会话量级 8000，使成本项与收益项量纲可比
#     （设计文档只写 "token 归一化"，未规定除数，除数选择属实现细节）。
CAREER_DENSITY_START = 0.34
CAREER_DELTA = {"normal": -0.06, "escalating": 0.05, "catfish": 0.14}
CAREER_DELTA_CAP = {"escalating": 0.85, "catfish": 0.50}  # 密度达此值 → 该模式增益归零
CAREER_TOKEN_BUDGET = 8000.0  # token 归一化基数（一次会话量级）
CAREER_DENSITY_NOISE = 0.025
CAREER_SIX_NOISE = 0.08


try:  # torch 可用才构建网络（与 mappo_policy 同策略：延迟导入）
    from engines.mappo_policy import _build_networks as _mp_build_networks
    _TORCH_HINT = True
except Exception:  # pragma: no cover - torch 缺失环境
    _mp_build_networks = None
    _TORCH_HINT = False


# ────────────────────────────────────────────────────────────
# 状态特征（8 维，设计文档 MDP 定义）
# ────────────────────────────────────────────────────────────

def career_state_features(turns: list[dict], six_scores: Optional[dict] = None,
                          profile_level: str = "intermediate",
                          current_mode: str = "normal",
                          catfish_streak: int = 0,
                          max_turns: int = 8) -> list[float]:
    """对抗上下文 → 8 维状态向量（全部归一化到 0-1）。"""
    turns = turns or []
    n = len(turns)
    turn_ratio = min(1.0, n / max(1, max_turns))

    # 最近 3 轮证据密度均值（无证据轮用 EVIDENCE_DENSITY_DEFAULT，见常量注释）
    dens = [float((t.get("evidence") or {}).get("density", EVIDENCE_DENSITY_DEFAULT))
            for t in turns[-3:]]
    evidence_density = sum(dens) / len(dens) if dens else EVIDENCE_DENSITY_DEFAULT

    # 最近 3 轮规则作答质量（按密度映射 0-5 分，无证据轮计中性 2.5）
    qualities = [min(5.0, 1.0 + d * 4.0) for d in dens] if dens else [2.5]
    answer_quality = sum(qualities) / len(qualities) / 5.0

    mode_ordinal = {"normal": 0.0, "escalating": 0.5, "catfish": 1.0}.get(current_mode, 0.0)
    catfish_ratio = min(1.0, catfish_streak / max(1, CATFISH_MAX_CONTINUE))

    level_code = {"beginner": 0.25, "intermediate": 0.5, "advanced": 0.75}.get(profile_level, 0.5)

    # 六维分数方差（越高越需要加压探测）；无六维评估时改用最近轮密度方差，避免常数维
    scores = [float(v) for v in (six_scores or {}).values() if v is not None]
    if len(scores) >= 2:
        mean = sum(scores) / len(scores)
        variance = sum((x - mean) ** 2 for x in scores) / len(scores)
        dimension_variance = min(1.0, variance / 4.0)  # 5 分制方差上限 ~4
    elif len(dens) >= 2:
        m = sum(dens) / len(dens)
        dv = sum((d - m) ** 2 for d in dens) / len(dens)
        dimension_variance = min(1.0, dv / 0.25)  # 密度 0/1 二分时方差上限 0.25
    else:
        dimension_variance = 0.0  # 无任何信号

    cost_ratio = turn_ratio  # 已消耗轮次预算比例（成本感知）

    return [turn_ratio, evidence_density, answer_quality, mode_ordinal,
            catfish_ratio, level_code, dimension_variance, cost_ratio]


# ────────────────────────────────────────────────────────────
# 奖励（4 分量，可复算）
# ────────────────────────────────────────────────────────────

def career_reward(prev_six: dict, curr_six: dict,
                  prev_density: float, curr_density: float,
                  tokens: float = 0.0, catfish_streak: int = 0) -> float:
    """r = w1*Δ六维均分 + w2*Δ证据密度 - w3*token成本 - w4*鲶鱼滥用"""
    def _avg(d: dict) -> float:
        vals = [float(v) for v in d.values() if v is not None]
        return sum(vals) / len(vals) if vals else 0.0

    gain = _avg(curr_six) - _avg(prev_six)
    evid = curr_density - prev_density
    # 成本归一化：除以会话量级预算（CAREER_TOKEN_BUDGET），而非早期硬编码的 2000。
    # 后者使成本项（0.045~0.083）压过证据增益项（~0.015），奖励与教学效果反相关。
    token_cost = min(1.0, max(0.0, tokens / CAREER_TOKEN_BUDGET))
    abuse = max(0, catfish_streak - CATFISH_MAX_CONTINUE)  # 超限轮数
    return (REWARD_W["gain"] * gain
            + REWARD_W["evidence"] * evid
            - REWARD_W["cost"] * token_cost
            - REWARD_W["discipline"] * abuse * 5.0)


# ────────────────────────────────────────────────────────────
# 合成对抗环境（训练 / 对比实验用）
# ────────────────────────────────────────────────────────────

class CareerAdversaryEnv:
    """模拟学生对抗环境：模式选择 → 学生证据密度/六维响应 → 奖励。

    动力学设计（保证 P3③ 鲶鱼机制既"可达"又"值得用"，见模块顶部调参常量）：
      - 卡住型学生：normal 持续掉密度（-0.06），只有加压/鲶鱼能抬升（鲶鱼 -0.14 更强）；
        开局密度 0.34 偏低 → 规则/RL 在低谷选鲶鱼 → 鲶鱼被真实选中（机制激活）。
      - 收益递减：两模式各有增益上限，且 **cap_catfish(0.50) < cap_escalating(0.85)** ——
        鲶鱼只在低密度"破僵局"有效，密度一高边际收益即归零（而它 token 更贵）；
        温和加压则可持续微调。策略必须在"低谷重锤、高位轻推"之间分状态权衡。
      - 鲶鱼纪律：连压 ≥ CATFISH_MAX_CONTINUE 触发奖励重罚，且 select_action 有硬护栏。
      - 奖励四分量（文档权重 w1=0.5/w2=0.3/w3=0.15/w4=0.05 保持不变），
        但 token 成本改为按会话量级预算归一（见 career_reward 注释）。
    """

    # 各模式 token 成本（设计文档未规定，属实现参数）。鲶鱼需生成"对抗性追问 +
    # 重新评估"，比温和加压更贵；配合 cap_catfish < cap_escalating，使"该用鲶鱼时
    # 才用"成为收益最优，而非靠人为惩罚压制。
    MODE_TOKENS = {"normal": 600.0, "escalating": 900.0, "catfish": 1100.0}

    def __init__(self, seed: int = 42, horizon: int = 8, template_student: bool = False):
        self.rng = random.Random(seed)
        self.horizon = horizon
        self.noisy = True
        # template_student 仅作为"更卡"的极端情形，默认即卡住型学生
        self.template_student = template_student
        self.step_count = 0
        self.density = CAREER_DENSITY_START
        self.six = {d: 2.5 for d in ("expression", "stress", "decompose",
                                     "collab", "presentation", "problem_solving")}
        self.catfish_streak = 0
        self._last_mode = "normal"

    def reset(self) -> list[float]:
        self.step_count = 0
        self.density = max(0.1, CAREER_DENSITY_START - 0.02) if self.template_student else CAREER_DENSITY_START
        self.six = {d: 2.5 for d in ("expression", "stress", "decompose",
                                     "collab", "presentation", "problem_solving")}
        self.catfish_streak = 0
        self._last_mode = "normal"
        return self._features()

    def _features(self) -> list[float]:
        turn_ratio = self.step_count / max(1, self.horizon)
        mode_ordinal = {"normal": 0.0, "escalating": 0.5, "catfish": 1.0}.get(
            self._last_mode, 0.0)
        return [turn_ratio, self.density, self.density, mode_ordinal,
                min(1.0, self.catfish_streak / CATFISH_MAX_CONTINUE),
                0.5, 0.3, turn_ratio]

    def step(self, action: int) -> tuple[list[float], float, bool]:
        """action: 0=normal 1=escalating 2=catfish → (features, reward, done)"""
        self.step_count += 1
        mode = CAREER_ACTIONS[action] if 0 <= action < len(CAREER_ACTIONS) else "normal"
        self._last_mode = mode

        prev_density = self.density
        base = CAREER_DELTA[mode]
        if self.template_student and mode == "normal":
            base = -0.08  # 模板学生：常规模式更无效
        cap = CAREER_DELTA_CAP.get(mode)
        if cap is None:
            delta = base                                       # normal：线性，无收益递减
        else:
            # 收益递减：密度越接近各模式自己的 cap，边际效果越小。
            # cap_catfish(0.50) < cap_escalating(0.85) 是有意为之 —— 鲶鱼只在低密度
            # 破僵局有效，密度一高即失效且它更贵，故策略会自然改用温和加压。
            delta = base * max(0.0, 1.0 - prev_density / cap)
        noise = self.rng.uniform(-CAREER_DENSITY_NOISE, CAREER_DENSITY_NOISE) if self.noisy else 0.0
        self.density = max(0.1, min(0.95, prev_density + delta + noise))

        # 六维均分随证据密度温和变化（密度越低越难提升）
        prev_avg = sum(self.six.values()) / len(self.six)
        lift = (self.density - 0.5) * 0.5 + self.rng.uniform(-CAREER_SIX_NOISE, CAREER_SIX_NOISE) * (0.5 if self.noisy else 0.0)
        self.six = {d: max(1.0, min(5.0, v + lift / len(self.six))) for d, v in self.six.items()}
        curr_avg = sum(self.six.values()) / len(self.six)

        # 鲶鱼纪律：连压计数（select_action 据此在超限时强制回 normal）
        self.catfish_streak = self.catfish_streak + 1 if mode == "catfish" else 0

        reward = career_reward(
            {"avg": prev_avg}, {"avg": curr_avg},
            prev_density, self.density,
            tokens=self.MODE_TOKENS.get(mode, 600.0),
            catfish_streak=self.catfish_streak)
        return self._features(), reward, self.step_count >= self.horizon


# ────────────────────────────────────────────────────────────
# 策略：规则预热 + PPO 微调（复用 mappo_policy 网络构建）
# ────────────────────────────────────────────────────────────

def _rule_action_idx(env_feats: list[float]) -> int:
    """规则版策略（监督预热的安全起点）：低密度加压，连续模板/低分放鲶鱼"""
    density, quality, catfish_ratio = env_feats[1], env_feats[2], env_feats[4]
    if catfish_ratio >= 1.0:
        return 0
    if density < 0.35:
        return 2 if quality < 0.45 else 1
    if density < 0.45:
        return 1
    return 0


def _seed_all(seed: int) -> None:
    """全链路播种：让同一 seed 的实验结果可逐位复算。

    必须在**网络初始化之前**调用（权重初始化走 torch 全局 RNG）；
    PPO 的动作采样 torch.multinomial 同样依赖该 RNG，故一次播种覆盖全流程。

    修复背景：本模块原先未播种（且 warmup 内 `rng = random.Random(seed)` 建而不用，
    属伪播种），实测同 seed 两次 warmup 权重 L2 差异达 110.70，
    即 career_mappo_train_*.json 的 3-seed 结果不可复算。
    """
    random.seed(seed)
    try:
        import numpy as _np
        _np.random.seed(seed % (2 ** 32))
    except Exception:
        pass
    try:
        import torch as _torch
        _torch.manual_seed(seed)
    except Exception:
        pass


class CareerModePolicy:
    """三模式决策策略：规则预热 → PPO 微调；推理失败自动降级规则版。"""

    def __init__(self, hidden: int = 64, lr: float = 3e-4, gamma: float = 0.99,
                 clip_epsilon: float = 0.2, seed: Optional[int] = 42):
        self.state_dim = 8
        self.n_actions = len(CAREER_ACTIONS)
        self.gamma = gamma
        self.clip_epsilon = clip_epsilon
        self._torch = None
        self._actor = None
        self._trained = False
        # 网络权重初始化走 torch 全局 RNG：不播种则每次进程结果都不同，
        # 3-seed 实验将不可复算（见 _seed_all 修复背景）。
        if seed is not None:
            _seed_all(seed)
        try:
            import torch  # noqa: F401
            self._torch = torch
            if _mp_build_networks is not None:
                # 复用 mappo_policy 的网络构建（encoder + 动作头框架）
                ActorNet, _Critic = _mp_build_networks(torch)
                self._actor = ActorNet(self.state_dim, hidden)
                self._critic = _Critic(self.state_dim, hidden)
                self._opt = torch.optim.Adam(
                    list(self._actor.parameters()) + list(self._critic.parameters()), lr=lr)
        except Exception as e:  # pragma: no cover
            logger.warning(f"career 策略网络构建失败（规则版兜底）: {e}")

    # ── 规则预热：用规则版决策做监督训练 ──
    def warmup_with_rules(self, env: CareerAdversaryEnv, steps: int = 800,
                          seed: int = 7) -> dict:
        if self._torch is None or self._actor is None:
            return {"warmed": False, "reason": "torch 不可用"}
        torch = self._torch
        opt = torch.optim.Adam(self._actor.parameters(), lr=3e-4)
        losses = []
        for _ in range(steps):
            feats = env.reset()
            for _t in range(env.horizon):
                target = torch.tensor([_rule_action_idx(feats)], dtype=torch.long)
                x = torch.tensor([feats], dtype=torch.float32)
                probs = self._actor(x)["difficulty"] if isinstance(self._actor(x), dict) else self._actor(x)
                if isinstance(probs, dict):
                    probs = probs["difficulty"]
                loss = torch.nn.functional.cross_entropy(probs, target)
                opt.zero_grad(); loss.backward(); opt.step()
                losses.append(float(loss.item()))
                feats, _r, done = env.step(_rule_action_idx(feats))
                if done:
                    break
        self._trained = True
        return {"warmed": True, "steps": steps, "mean_loss": sum(losses) / max(1, len(losses))}

    # ── PPO 微调（GAE + clip；轨迹来自 CareerAdversaryEnv，零 LLM）──
    def train_ppo(self, env: Optional[CareerAdversaryEnv] = None, episodes: int = 60,
                  horizon: int = 8, seed: int = 42, epochs: int = 4,
                  gamma: float = 0.99, clip_epsilon: float = 0.2,
                  gae_lambda: float = 0.95, batch_episodes: int = 12) -> dict:
        """轻量 PPO：按批收集轨迹 → GAE → clip 更新 actor/critic。

        返回可落盘统计（含每 episode 回报）；torch 不可用 → 诚实降级，不伪造曲线。
        """
        if self._torch is None or self._actor is None or self._critic is None:
            return {"trained": False, "reason": "torch/critic 不可用", "episodes": 0}
        torch = self._torch
        env = env or CareerAdversaryEnv(seed=seed, horizon=horizon)
        returns_curve: list[float] = []
        # batch 化更新：与 review_policy 同因同修 —— 单 episode（8 步）即更新会导致
        # 优势标准化在个位数样本上做，梯度方差过大、策略退化。
        buffer: list[dict] = []
        n_updates = 0

        def _probs_of(x):
            out = self._actor(x)
            return out["difficulty"] if isinstance(out, dict) else out

        def _det_return(n_ep: int = 40) -> float:
            """确定性策略在独立环境实例上的平均回报（部署口径，无采样噪声）。

            与 review_policy.train_ppo 同因同修：returns_curve 用随机采样动作累计，
            会被探索噪声主导，可能与真实策略质量脱钩（review 侧实测 63 次更新后
            `improved=False` 而确定性回报 29.2→43.1）。career 侧此前报告"PPO 无增益"
            用的也是随机回报 ⇒ 必须以确定性回报复核，否则可能把"策略变好"读成"无效"。
            环境实例用 seed+7777 的独立副本，避免与训练轨迹重叠。
            """
            try:
                ev = type(env)(seed=seed + 7777, horizon=horizon)
            except Exception:
                ev = env
            tot = 0.0
            for _ in range(n_ep):
                s_d = ev.reset()
                ep_r = 0.0
                for _t in range(horizon):
                    x = torch.tensor([s_d], dtype=torch.float32)
                    self._actor.eval()
                    with torch.no_grad():
                        a = int(_probs_of(x)[0].argmax().item())
                    s_d, r, done = ev.step(a)
                    ep_r += float(r)
                    if done:
                        break
                tot += ep_r
            self._actor.train()
            return tot / max(1, n_ep)

        det_before = _det_return()

        def _flush(buf: list[dict]) -> None:
            if not buf:
                return
            nonlocal n_updates
            n_updates += 1
            s_t = torch.tensor([s for ep in buf for s in ep["states"]], dtype=torch.float32)
            a_t = torch.tensor([a for ep in buf for a in ep["actions"]], dtype=torch.long)
            old_logp_t = torch.stack([lp for ep in buf for lp in ep["logps"]]).detach()
            adv_flat, ret_flat = [], []
            for ep in buf:
                next_v = 0.0 if ep["dones"][-1] else float(self._critic(
                    torch.tensor([ep["last_state"]], dtype=torch.float32)).item())
                advantages, gae = [], 0.0
                for i in reversed(range(len(ep["rewards"]))):
                    v_i = float(ep["values"][i].item())
                    v_next = (float(ep["values"][i + 1].item())
                              if i + 1 < len(ep["values"]) else next_v)
                    delta = ep["rewards"][i] + gamma * v_next - v_i
                    gae = delta + gamma * gae_lambda * (0.0 if ep["dones"][i] else gae)
                    advantages.insert(0, gae)
                adv_flat.extend(advantages)
                ret_flat.extend(adv + float(ep["values"][i].item())
                                for i, adv in enumerate(advantages))
            adv_t = torch.tensor(adv_flat, dtype=torch.float32)
            ret_t = torch.tensor(ret_flat, dtype=torch.float32)
            if adv_t.numel() > 1:
                adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)
            for _e in range(epochs):
                dist = torch.distributions.Categorical(_probs_of(s_t))
                new_logp = dist.log_prob(a_t)
                ratio = torch.exp(new_logp - old_logp_t)
                surr1 = ratio * adv_t
                surr2 = torch.clamp(ratio, 1 - clip_epsilon, 1 + clip_epsilon) * adv_t
                actor_loss = -torch.min(surr1, surr2).mean()
                critic_loss = torch.nn.functional.mse_loss(self._critic(s_t), ret_t)
                entropy = dist.entropy().mean()
                loss = actor_loss + 0.5 * critic_loss - 0.003 * entropy
                self._opt.zero_grad()
                loss.backward()
                self._opt.step()

        for _ep in range(episodes):
            states, actions, rewards, logps, values, dones = [], [], [], [], [], []
            s = env.reset()
            ep_return = 0.0
            for _t in range(horizon):
                x = torch.tensor([s], dtype=torch.float32)
                probs = _probs_of(x)[0]
                dist = torch.distributions.Categorical(probs)
                a = int(dist.sample().item())
                logp = dist.log_prob(torch.tensor([a], dtype=torch.long))
                v = self._critic(x)
                ns, r, done = env.step(a)
                states.append(s); actions.append(a); rewards.append(float(r))
                logps.append(logp); values.append(v); dones.append(bool(done))
                ep_return += float(r)
                s = ns
                if done:
                    break
            returns_curve.append(ep_return)
            buffer.append({"states": states, "actions": actions, "rewards": rewards,
                           "logps": logps, "values": values, "dones": dones,
                           "last_state": s})
            if len(buffer) >= batch_episodes or _ep == episodes - 1:
                _flush(buffer)
                buffer = []

        self._trained = True
        det_after = _det_return()
        head = returns_curve[:max(1, len(returns_curve) // 3)]
        tail = returns_curve[-max(1, len(returns_curve) // 3):]
        return {
            "trained": True, "episodes": episodes, "horizon": horizon, "seed": seed,
            # 有效预算显式落盘（batch 语义变更会静默改变实际更新次数，见 review 侧同类事故）
            "batch_episodes": int(batch_episodes), "n_updates": n_updates,
            "returns": returns_curve,
            "mean_return": sum(returns_curve) / max(1, len(returns_curve)),
            "mean_return_first_third": sum(head) / max(1, len(head)),
            "mean_return_last_third": sum(tail) / max(1, len(tail)),
            # ⚠️ `improved` 基于随机采样回报，会被探索噪声主导，不得单独作为
            #    "PPO 是否有效"的证据；审计请用 `improved_deterministic`（部署走 argmax）。
            "improved": (sum(tail) / max(1, len(tail))) > (sum(head) / max(1, len(head))),
            "det_return_before": round(det_before, 4),
            "det_return_after": round(det_after, 4),
            "improved_deterministic": det_after > det_before,
        }

    # ── 动作选择：mappo → 失败降级规则 ──
    def select_action(self, features: list[float], deterministic: bool = True) -> tuple[int, str]:
        if self._torch is None or self._actor is None or not self._trained:
            return _rule_action_idx(features), "rule"
        try:
            torch = self._torch
            x = torch.tensor([features], dtype=torch.float32)
            self._actor.eval()
            with torch.no_grad():
                out = self._actor(x)
            probs = out["difficulty"][0] if isinstance(out, dict) else out[0]
            idx = int(probs.argmax().item()) if deterministic else int(torch.multinomial(probs, 1).item())
            # 纪律硬约束：鲶鱼连压超限直接压回 normal（防捷径，不依赖网络自觉）
            if idx == 2 and features[4] >= 1.0:
                idx = 0
            return idx, "mappo"
        except Exception as e:
            logger.warning(f"career MAPPO 推理失败，规则降级: {e}")
            return _rule_action_idx(features), "rule_fallback"

    def save(self, path: str):
        if self._torch is not None and self._actor is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._torch.save(self._actor.state_dict(), path)


# ────────────────────────────────────────────────────────────
# 决策层入口（career_nodes.decide_adversary_mode 委托到本函数）
# ────────────────────────────────────────────────────────────

def _mappo_enabled() -> bool:
    """灰度开关：config career.use_career_mappo，默认 False（规则版）"""
    try:
        import config
        return bool((config.get_career_config() or {}).get("use_career_mappo", False))
    except Exception:
        return False


def maybe_mappo_decide(turns: list[dict], current_mode: str, catfish_continuous: int,
                       rule_fn) -> Optional[tuple[str, bool, int]]:
    """灰度入口：规则注入式决策（避免 career_nodes ↔ career_policy 循环导入）。

    返回 None → 调用方走规则版（灰度关闭 / MAPPO 异常降级）；
    返回 (mode, triggered, cont) → 与规则版同契约。
    """
    if not _mappo_enabled():
        return None
    try:
        from agents.career_state import CATFISH_MAX_CONTINUE as _CMC
        feats = career_state_features(turns, current_mode=current_mode,
                                      catfish_streak=catfish_continuous)
        policy = _get_shared_policy()
        idx, source = policy.select_action(feats, deterministic=True)
        mode = CAREER_ACTIONS[idx] if 0 <= idx < len(CAREER_ACTIONS) else "normal"
        # 契约对齐：触发标记与连压计数语义与规则版一致；纪律超限强制回 normal
        if mode == "catfish":
            cont = catfish_continuous + 1
            if cont > _CMC:
                return "normal", False, 0
        elif mode == "escalating":
            cont = catfish_continuous + 1 if current_mode == "escalating" else 1
        else:
            cont = 0
        triggered = mode in ("escalating", "catfish") and mode != current_mode
        logger.info("career MAPPO 决策 mode=%s source=%s", mode, source)
        return mode, triggered, cont
    except Exception as e:
        logger.warning(f"career MAPPO 决策失败，规则版兜底: {e}")
        return None


_SHARED_POLICY: Optional[CareerModePolicy] = None


def _get_shared_policy() -> CareerModePolicy:
    """进程内共享策略实例（加载 checkpoint；无则规则预热一次）"""
    global _SHARED_POLICY
    if _SHARED_POLICY is None:
        _SHARED_POLICY = CareerModePolicy()
        ckpt = Path(__file__).parent.parent / "models" / "career_mode_policy.pt"
        if ckpt.exists() and _SHARED_POLICY._torch is not None:
            try:
                _SHARED_POLICY._actor.load_state_dict(
                    _SHARED_POLICY._torch.load(str(ckpt), weights_only=True))
                _SHARED_POLICY._trained = True
            except Exception as e:
                logger.warning(f"career 策略 checkpoint 加载失败（预热替代）: {e}")
        if not _SHARED_POLICY._trained:
            _SHARED_POLICY.warmup_with_rules(CareerAdversaryEnv(seed=7), steps=200, seed=7)
    return _SHARED_POLICY


def reset_shared_policy():
    """测试/重训后清空共享实例"""
    global _SHARED_POLICY
    _SHARED_POLICY = None
