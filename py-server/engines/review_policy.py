# ============================================================
# review_policy — 三元评审权重 MAPPO 化（评审权重学习器）
#
# 按 docs/CTO-芒得很职三元评审权重MAPPO化攻坚令-2026-09-14.md 实现：
#   - MDP：12 维评审上下文状态 → 5 档权重动作（诚实/批评者/共识 三元权重）
#   - 奖励：4 分量（评审质量增益 + 精准评审 - 成本 - skip 纪律）
#   - 学习：规则预热（监督）→ PPO 微调（CTDE + GAE + clip）
#   - 灰度：config gomarl.use_review_mappo 默认 False；推理异常 → 均匀权重（fail-open）
#   - 纪律：skip 连发 ≥2 重罚 + review_min_review 硬约束（防"一律 skip 省钱"捷径）
#
# 与 P3③ career_policy 的边界（攻坚令第 6 节风险项）：
#   本模块 = 评审权重（输出质量控制）；career_policy = 对抗模式（教学过程控制）。
#   两者 MDP 独立、状态维度不同（12 vs 8）、不共享网络权重，勿混用。
#
# 诚信约束：所有对外数字必须来自落盘 JSON；torch 不可用时如实标注降级，不伪造训练结果。
# ============================================================

import json
import logging
import math
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger("netlearn.review.policy")

# ── 动作空间：5 档离散权重（攻坚令 3.1 动作表）──
REVIEW_ACTIONS = ["trust_honest", "trust_critic", "trust_consensus", "balanced", "skip_review"]

# 每档对应的三元权重向量 (w_honest, w_critic, w_consensus)
REVIEW_WEIGHTS = {
    0: (0.6, 0.2, 0.2),      # 证据强 → 信诚实 Agent
    1: (0.2, 0.6, 0.2),      # 批评质量高 → 信批评者（多挑错）
    2: (0.2, 0.2, 0.6),      # 共识分歧小 → 信共识（保稳定）
    3: (1 / 3, 1 / 3, 1 / 3),  # 默认均衡（= 现状无加权语义）
    4: (0.0, 0.0, 0.0),      # skip：不评审直接放行（受纪律硬约束）
}

# 均匀权重：灰度关闭 / 降级时的行为（等价于现状，零侵入）
UNIFORM_WEIGHTS = {"honest": 1 / 3, "critic": 1 / 3, "consensus": 1 / 3}

# 奖励权重（攻坚令 3.1 初值）
REWARD_W = {"gate": 0.4, "precision": 0.35, "cost": 0.15, "discipline": 0.10}

# 纪律常量（攻坚令 3.3 灰度配置）
REVIEW_MIN_REVIEW = 2      # 每会话至少 2 次真实评审（防 skip 捷径）
SKIP_STREAK_LIMIT = 2      # skip 连发 ≥2 触发重罚 + 硬约束压回

# 各档位 token 成本（用于成本项与 ReviewEnv 模拟，相对量纲）
ACTION_TOKENS = {0: 900.0, 1: 1000.0, 2: 800.0, 3: 950.0, 4: 0.0}

# 状态维度（攻坚令 3.1 状态表，共 12 维）
STATE_DIM = 12


# ────────────────────────────────────────────────────────────
# 状态特征（12 维，确定性可复算）
# ────────────────────────────────────────────────────────────

def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


def review_state_features(
    evidence: Optional[dict] = None,
    critic: Optional[dict] = None,
    consensus: Optional[dict] = None,
    state: Optional[dict] = None,
    mode_encoding: float = 0.5,
    round_ratio: float = 0.5,
) -> list[float]:
    """评审上下文 → 12 维状态向量（全部归一到 0-1，缺失字段取中性值）。

    维度顺序严格对齐攻坚令 3.1 状态表，便于跨模块复算与测试断言。
    """
    evidence = evidence or {}
    critic = critic or {}
    consensus = consensus or {}
    state = state or {}

    # 1 critic_confidence：规则值，仅作输入特征（不当训练标签，攻坚令第 6 节）
    f1 = _clamp01(float(critic.get("confidence", 0.5)))
    # 2 evidence_consistency：0-100 分制 → /100
    f2 = _clamp01(float(evidence.get("consistency_score", 50.0)) / 100.0)
    # 3 evidence_coverage：覆盖条目 / 期望条目
    expected = float(evidence.get("expected_coverage") or 0)
    covered = float(evidence.get("coverage") or 0)
    f3 = _clamp01(covered / expected) if expected > 0 else _clamp01(covered / 5.0)
    # 4 consensus_status：pass/conflict/none → 0/1/2 → /2
    status = str(consensus.get("status", "none")).lower()
    f4 = {"pass": 0.0, "conflict": 0.5, "none": 1.0}.get(status, 1.0)
    # 5 gate_retry_count：clamp /3
    f5 = _clamp01(float(state.get("gate_retry_count", 0)) / 3.0)
    # 6 disagreement_level：辩论分歧代理（0-1 原值）
    f6 = _clamp01(float(consensus.get("disagreement", state.get("disagreement", 0.5))))
    # 7 valid_critic_count：有效质疑 /5
    f7 = _clamp01(float(critic.get("valid_count", 0)) / 5.0)
    # 8 invalid_critic_count：无效质疑 /5
    f8 = _clamp01(float(critic.get("invalid_count", 0)) / 5.0)
    # 9 quality_delta：本轮 vs 上轮 consistency 差（clamp -1..1 → 映射到 0-1 便于网络输入）
    last_c = state.get("last_consistency")
    if last_c is None:
        f9 = 0.5
    else:
        delta = (float(evidence.get("consistency_score", 50.0)) - float(last_c)) / 100.0
        f9 = _clamp01((max(-1.0, min(1.0, delta)) + 1.0) / 2.0)
    # 10 cost_ratio：已消耗 token / 预算
    budget = float(state.get("token_budget") or 0)
    used = float(state.get("tokens_used") or 0)
    f10 = _clamp01(used / budget) if budget > 0 else _clamp01(used / 4000.0)
    # 11 mode_encoding：教学模式编码（0-1）
    f11 = _clamp01(float(mode_encoding))
    # 12 round_ratio：当前轮 / max_rounds
    f12 = _clamp01(float(round_ratio))

    return [f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12]


# ────────────────────────────────────────────────────────────
# 权重协议（校验 + 归一化）
# ────────────────────────────────────────────────────────────

def review_weight_schema(w: Optional[dict] = None) -> dict:
    """校验并归一化三元权重：w_h + w_c + w_k ≈ 1.0（skip 时全 0）。

    非法/缺失输入 → 均匀权重（fail-open，等价于现状）。
    """
    if not isinstance(w, dict):
        return dict(UNIFORM_WEIGHTS)
    try:
        h = max(0.0, float(w.get("honest", 0.0)))
        c = max(0.0, float(w.get("critic", 0.0)))
        k = max(0.0, float(w.get("consensus", 0.0)))
    except (TypeError, ValueError):
        return dict(UNIFORM_WEIGHTS)

    total = h + c + k
    if total <= 1e-9:
        # 全 0 = skip 语义：合法，但不归一化（保持 skip 可识别）
        return {"honest": 0.0, "critic": 0.0, "consensus": 0.0}
    return {"honest": h / total, "critic": c / total, "consensus": k / total}


def _weights_of(action_idx: int) -> dict:
    """动作索引 → 三元权重 dict（越界 → 均匀权重）。"""
    if action_idx not in REVIEW_WEIGHTS:
        return dict(UNIFORM_WEIGHTS)
    h, c, k = REVIEW_WEIGHTS[action_idx]
    return {"honest": h, "critic": c, "consensus": k}


def _features_valid(features) -> bool:
    """状态特征合法性：必须 12 维且全部有限（非 NaN/Inf）。

    NaN 进入线性层不会抛异常，会静默产出任意权重 —— 因此必须显式拦截，
    否则"fail-open 到均匀权重"的兜底形同虚设。
    """
    if not features or len(features) != STATE_DIM:
        return False
    try:
        return all(math.isfinite(float(v)) for v in features)
    except (TypeError, ValueError):
        return False


# ────────────────────────────────────────────────────────────
# 奖励（4 分量，可复算，防捷径）
# ────────────────────────────────────────────────────────────

def review_reward(
    gate_before: float,
    gate_after: float,
    precision: bool,
    tokens: float = 0.0,
    skip_streak: int = 0,
) -> float:
    """r = w1·Δgate_quality + w2·precision_bonus - w3·cost_penalty - w4·skip_abuse

    - Δgate_quality：返工后 consistency / 通过判定改善（+）
    - precision_bonus：正确放行优质产物 +；错误放行 −（精准评审）
    - cost_penalty：本轮 token 归一化（−）
    - skip_abuse：skip 连发 ≥ SKIP_STREAK_LIMIT 重罚（防"全 skip 省钱"捷径）
    """
    delta_gate = float(gate_after) - float(gate_before)
    precision_bonus = 1.0 if precision else -1.0
    cost = min(1.0, max(0.0, float(tokens) / 2000.0))
    abuse = max(0, int(skip_streak) - SKIP_STREAK_LIMIT + 1) if skip_streak >= SKIP_STREAK_LIMIT else 0
    return (REWARD_W["gate"] * delta_gate
            + REWARD_W["precision"] * precision_bonus
            - REWARD_W["cost"] * cost
            - REWARD_W["discipline"] * abuse * 5.0)


# ────────────────────────────────────────────────────────────
# 合成评审环境（训练 / 对比实验用，零 LLM）
# ────────────────────────────────────────────────────────────

class ReviewEnv:
    """模拟评审环境：权重档位选择 → 评审质量 / 成本 → 奖励。

    设计意图（答辩可讲，且与奖励设计同源）：
      - 证据强（consistency 高）时 trust_honest 收益最大；
      - 批评者有效质疑多时 trust_critic 收益最大；
      - 共识分歧小时 trust_consensus 稳定增益；
      - skip 省成本但质量零提升，且连发触发纪律惩罚（防捷径）；
      - 每个档位有不同 token 成本（skip=0，评审档位 800-1000）。

    关键：环境对"选对档位"给出更高奖励，使 RL 相对固定规则存在可学增益。
    """

    def __init__(self, seed: int = 42, horizon: int = 6, noisy: bool = True):
        self.rng = random.Random(seed)
        self.horizon = horizon
        self.noisy = noisy
        self.step_count = 0
        self.consistency = 50.0
        self.skip_streak = 0
        self.reviews_done = 0
        self._last_action = 3

    def reset(self) -> list[float]:
        self.step_count = 0
        self.consistency = 50.0
        self.skip_streak = 0
        self.reviews_done = 0
        self._last_action = 3
        return self._features()

    def _features(self) -> list[float]:
        noise = (lambda: self.rng.uniform(-0.02, 0.02)) if self.noisy else (lambda: 0.0)
        return [
            0.5 + noise(),                                    # 1 critic_confidence
            self.consistency / 100.0,                          # 2 evidence_consistency
            0.5 + noise(),                                    # 3 evidence_coverage
            0.0 + abs(noise()),                               # 4 consensus_status（偏 pass）
            min(1.0, self.step_count / 3.0),                  # 5 gate_retry_count
            0.4 + noise(),                                    # 6 disagreement_level
            0.4 + noise(),                                    # 7 valid_critic_count
            0.2 + abs(noise()),                               # 8 invalid_critic_count
            0.5 + noise(),                                    # 9 quality_delta
            min(1.0, self.step_count / self.horizon),         # 10 cost_ratio
            0.5,                                              # 11 mode_encoding
            min(1.0, (self.step_count + 1) / self.horizon),   # 12 round_ratio
        ]

    def step(self, action: int) -> tuple[list[float], float, bool]:
        """action ∈ [0,4] → (features, reward, done)"""
        self.step_count += 1
        action = int(action) if 0 <= int(action) < len(REVIEW_ACTIONS) else 3
        self._last_action = action

        before = self.consistency

        # 环境动力学：档位收益取决于当前评审上下文（证据强度 / 批评有效性）
        feats = self._features()
        consistency_now, valid_c, invalid_c = feats[1], feats[6], feats[7]
        critic_quality = valid_c - invalid_c  # 批评者信噪比代理

        if action == 4:  # skip：零成本、零质量增益
            delta_q = 0.0
            self.skip_streak += 1
        else:
            self.skip_streak = 0
            self.reviews_done += 1
            if action == 0:      # trust_honest：证据越强越有效
                delta_q = 6.0 * (consistency_now - 0.35)
            elif action == 1:    # trust_critic：批评者信噪比越高越有效
                delta_q = 6.0 * (critic_quality + 0.05)
            elif action == 2:    # trust_consensus：稳定小幅
                delta_q = 2.5
            else:                # balanced：温和
                delta_q = 3.0
            # 边际递减：质量越高越难再提升
            delta_q *= max(0.2, 1.0 - (self.consistency - 50.0) / 120.0)

        noise = self.rng.uniform(-1.0, 1.0) if self.noisy else 0.0
        self.consistency = max(0.0, min(100.0, self.consistency + delta_q + noise))
        after = self.consistency

        # 精准评审：质量达标（≥60）且未 skip → 判定为正确放行
        precision = (after >= 60.0) if action != 4 else (after >= 75.0)

        reward = review_reward(
            gate_before=before, gate_after=after, precision=precision,
            tokens=ACTION_TOKENS.get(action, 0.0), skip_streak=self.skip_streak,
        )
        return self._features(), reward, self.step_count >= self.horizon


# ────────────────────────────────────────────────────────────
# 规则版策略（warmup 监督标签来源，安全起点）
# ────────────────────────────────────────────────────────────

def _rule_action_idx(features: list[float]) -> int:
    """规则版评审权重选择（对齐攻坚令 1.2 现有规则精神：按上下文挑信任对象）。

    - 证据强（consistency ≥ 0.6）→ trust_honest
    - 批评者信噪比高（valid 明显多于 invalid）→ trust_critic
    - 共识已 pass 且分歧低 → trust_consensus
    - 否则 → balanced
    - skip 仅在成本已高且质量已达标时允许（且受纪律硬约束，不由此函数放行连发）
    """
    if not features or len(features) < STATE_DIM:
        return 3
    confidence, consistency, _cov, status, _retry, disagree, valid_c, invalid_c = features[:8]
    cost_ratio, _mode, round_ratio = features[9], features[10], features[11]

    # 成本高压 + 质量已达标 → 允许 skip（真实评审已由调用方按 review_min_review 保证）
    if consistency >= 0.75 and cost_ratio >= 0.6:
        return 4
    if consistency >= 0.6:
        return 0
    if (valid_c - invalid_c) >= 0.25:
        return 1
    if status <= 0.1 and disagree <= 0.35:
        return 2
    return 3


# ────────────────────────────────────────────────────────────
# 策略网络（独立 12→5 头，不污染 mappo_policy 现有 3 动作头）
# ────────────────────────────────────────────────────────────

class ReviewWeightPolicy:
    """三元评审权重策略：规则预热 → PPO 微调；推理失败自动降级规则/均匀权重。"""

    def __init__(self, hidden: int = 64, lr: float = 3e-4, gamma: float = 0.99,
                 clip_epsilon: float = 0.2, gae_lambda: float = 0.95):
        self.state_dim = STATE_DIM
        self.n_actions = len(REVIEW_ACTIONS)
        self.gamma = gamma
        self.clip_epsilon = clip_epsilon
        self.gae_lambda = gae_lambda
        self.lr = lr
        self._torch = None
        self._actor = None
        self._critic = None
        self._trained = False
        try:
            import torch  # 延迟导入（torch 缺失环境走规则降级）
            self._torch = torch
            self._actor = self._build_actor(torch, hidden)
            self._critic = self._build_critic(torch, hidden)
            self._opt = torch.optim.Adam(
                list(self._actor.parameters()) + list(self._critic.parameters()), lr=lr)
        except Exception as e:  # pragma: no cover - torch 缺失
            logger.warning(f"评审权重策略网络构建失败（规则版兜底）: {e}")

    # ── 网络（独立构建，风格对齐 mappo_policy._build_networks）──
    def _build_actor(self, torch, hidden: int):
        n_actions, state_dim = self.n_actions, self.state_dim

        class _Actor(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.encoder = torch.nn.Sequential(
                    torch.nn.Linear(state_dim, hidden), torch.nn.Tanh(),
                    torch.nn.Linear(hidden, hidden), torch.nn.Tanh(),
                )
                self.head = torch.nn.Linear(hidden, n_actions)

            def forward(self, s):
                return torch.softmax(self.head(self.encoder(s)), dim=-1)

        return _Actor()

    def _build_critic(self, torch, hidden: int):
        state_dim = self.state_dim

        class _Critic(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.net = torch.nn.Sequential(
                    torch.nn.Linear(state_dim, hidden), torch.nn.Tanh(),
                    torch.nn.Linear(hidden, hidden), torch.nn.Tanh(),
                    torch.nn.Linear(hidden, 1),
                )

            def forward(self, s):
                return self.net(s).squeeze(-1)

        return _Critic()

    @property
    def torch_available(self) -> bool:
        return self._torch is not None and self._actor is not None

    # ── 规则预热：用规则版决策做监督训练（安全起点）──
    def warmup_with_rules(self, env: Optional[ReviewEnv] = None, steps: int = 800,
                          seed: int = 7) -> dict:
        if not self.torch_available:
            return {"warmed": False, "reason": "torch 不可用", "steps": 0}
        torch = self._torch
        env = env or ReviewEnv(seed=seed)
        rng = random.Random(seed)
        opt = torch.optim.Adam(self._actor.parameters(), lr=self.lr)
        losses = []
        for _ in range(steps):
            feats = env.reset()
            for _t in range(env.horizon):
                target = torch.tensor([_rule_action_idx(feats)], dtype=torch.long)
                x = torch.tensor([feats], dtype=torch.float32)
                probs = self._actor(x)
                loss = torch.nn.functional.cross_entropy(probs, target)
                opt.zero_grad()
                loss.backward()
                opt.step()
                losses.append(float(loss.item()))
                feats, _r, done = env.step(_rule_action_idx(feats))
                if done:
                    break
            _ = rng  # 保留 seed 语义（环境已按 seed 构造）
        self._trained = True
        return {"warmed": True, "steps": steps,
                "mean_loss": sum(losses) / max(1, len(losses)),
                "final_loss": losses[-1] if losses else None}

    # ── PPO 微调（GAE + clip；轨迹来自 ReviewEnv，零 LLM）──
    def train_ppo(self, env: Optional[ReviewEnv] = None, episodes: int = 60,
                  horizon: int = 6, seed: int = 42, epochs: int = 4) -> dict:
        """轻量 PPO：按 episode 收集轨迹 → GAE → clip 更新 actor/critic。

        返回可落盘统计（含每 episode 回报，用于绘制收敛曲线）。
        torch 不可用 → 如实返回 {"trained": False, "reason": ...}，不伪造曲线。
        """
        if not self.torch_available:
            return {"trained": False, "reason": "torch 不可用", "episodes": 0}
        torch = self._torch
        env = env or ReviewEnv(seed=seed, horizon=horizon)
        returns_curve = []
        rng = random.Random(seed)

        for _ep in range(episodes):
            states, actions, rewards, logps, values, dones = [], [], [], [], [], []
            s = env.reset()
            ep_return = 0.0
            for _t in range(horizon):
                x = torch.tensor([s], dtype=torch.float32)
                probs = self._actor(x)
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

            # GAE(λ) 优势估计
            next_v = 0.0 if dones[-1] else float(self._critic(
                torch.tensor([s], dtype=torch.float32)).item())
            advantages, gae = [], 0.0
            for i in reversed(range(len(rewards))):
                v_i = float(values[i].item())
                v_next = float(values[i + 1].item()) if i + 1 < len(values) else next_v
                delta = rewards[i] + self.gamma * v_next - v_i
                gae = delta + self.gamma * self.gae_lambda * (0.0 if dones[i] else gae)
                advantages.insert(0, gae)
            returns = [adv + float(values[i].item()) for i, adv in enumerate(advantages)]

            s_t = torch.tensor(states, dtype=torch.float32)
            a_t = torch.tensor(actions, dtype=torch.long)
            old_logp_t = torch.stack(logps).detach()
            adv_t = torch.tensor(advantages, dtype=torch.float32)
            ret_t = torch.tensor(returns, dtype=torch.float32)
            if adv_t.numel() > 1:
                adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

            for _e in range(epochs):
                probs = self._actor(s_t)
                dist = torch.distributions.Categorical(probs)
                new_logp = dist.log_prob(a_t)
                ratio = torch.exp(new_logp - old_logp_t)
                surr1 = ratio * adv_t
                surr2 = torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon) * adv_t
                actor_loss = -torch.min(surr1, surr2).mean()
                critic_loss = torch.nn.functional.mse_loss(self._critic(s_t), ret_t)
                entropy = dist.entropy().mean()
                loss = actor_loss + 0.5 * critic_loss - 0.01 * entropy
                self._opt.zero_grad()
                loss.backward()
                self._opt.step()
            _ = rng

        self._trained = True
        head = returns_curve[:max(1, len(returns_curve) // 3)]
        tail = returns_curve[-max(1, len(returns_curve) // 3):]
        return {
            "trained": True, "episodes": episodes, "horizon": horizon, "seed": seed,
            "returns": returns_curve,
            "mean_return": sum(returns_curve) / max(1, len(returns_curve)),
            "mean_return_first_third": sum(head) / max(1, len(head)),
            "mean_return_last_third": sum(tail) / max(1, len(tail)),
            "improved": (sum(tail) / max(1, len(tail))) > (sum(head) / max(1, len(head))),
        }

    # ── 动作选择：mappo → 失败降级规则 ──
    def select_action(self, features: list[float], deterministic: bool = True,
                      skip_streak: int = 0, reviews_done: int = 0) -> tuple[int, str]:
        """返回 (action_idx, source)；source ∈ {"mappo", "rule", "rule_fallback"}。

        纪律硬约束（不依赖网络自觉）：
          - 真实评审次数 < REVIEW_MIN_REVIEW → 禁止 skip；
          - skip 连发 ≥ SKIP_STREAK_LIMIT → 禁止 skip，压回 balanced。
        """
        def _block_skip(idx: int) -> int:
            if idx == 4 and (reviews_done < REVIEW_MIN_REVIEW or skip_streak >= SKIP_STREAK_LIMIT):
                return 0 if (features and len(features) > 1 and features[1] >= 0.6) else 3
            return idx

        if not _features_valid(features):
            logger.warning("评审状态特征非法（NaN/Inf/维度不符），规则层直接均衡兜底")
            return 3, "rule_fallback"

        if not self.torch_available or not self._trained:
            return _block_skip(_rule_action_idx(features)), "rule"
        try:
            torch = self._torch
            x = torch.tensor([features], dtype=torch.float32)
            self._actor.eval()
            with torch.no_grad():
                probs = self._actor(x)[0]
            idx = int(probs.argmax().item()) if deterministic else \
                int(torch.multinomial(probs, 1).item())
            return _block_skip(idx), "mappo"
        except Exception as e:
            logger.warning(f"评审权重 MAPPO 推理失败，规则降级: {e}")
            return _block_skip(_rule_action_idx(features)), "rule_fallback"

    def save(self, path: str):
        if not self.torch_available:
            return False
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._torch.save({"actor": self._actor.state_dict(),
                          "critic": self._critic.state_dict()}, path)
        return True


# ────────────────────────────────────────────────────────────
# 协议入口（攻坚令 3.3 签名）
# ────────────────────────────────────────────────────────────

def _mappo_enabled() -> bool:
    """灰度开关：优先复用 config.use_review_mappo()（单点真值），默认 False（=现状均匀权重）。

    优先调用 config 的专用访问器，避免本模块与 config 各读一次 gomarl 段导致口径漂移；
    访问器不存在（旧版 config）时回退直读 gomarl 段，仍默认关闭。
    """
    try:
        import config
        accessor = getattr(config, "use_review_mappo", None)
        if callable(accessor):
            return bool(accessor())
        return bool((config.get_gomarl_config() or {}).get("use_review_mappo", False))
    except Exception:
        return False


def decide_review_weight(
    features: list[float],
    use_mappo: bool = False,
    skip_streak: int = 0,
    reviews_done: int = 0,
) -> dict:
    """三元评审权重决策（攻坚令 3.3 接口签名）。

    use_mappo=False → 均匀权重（= 现状，灰度安全，行为零变化）；
    use_mappo=True  → 策略推理；任何异常 → 均匀权重（fail-open）。
    返回 {"weights": {...}, "source": "mappo"/"rules"/"uniform", "action": int}
    """
    if not use_mappo:
        return {"weights": dict(UNIFORM_WEIGHTS), "source": "uniform", "action": 3}
    if not _features_valid(features):
        logger.warning("评审权重决策输入特征非法，均匀权重兜底")
        return {"weights": dict(UNIFORM_WEIGHTS), "source": "uniform", "action": 3}
    try:
        policy = _get_shared_policy()
        idx, source = policy.select_action(
            features, deterministic=True, skip_streak=skip_streak, reviews_done=reviews_done)
        weights = review_weight_schema(_weights_of(idx))
        return {"weights": weights, "source": source, "action": idx}
    except Exception as e:
        logger.warning(f"评审权重决策失败，均匀权重兜底: {e}")
        return {"weights": dict(UNIFORM_WEIGHTS), "source": "uniform", "action": 3}


_SHARED_POLICY: Optional[ReviewWeightPolicy] = None


def _get_shared_policy() -> ReviewWeightPolicy:
    """进程内共享策略实例：优先加载 checkpoint，否则规则预热一次。"""
    global _SHARED_POLICY
    if _SHARED_POLICY is None:
        _SHARED_POLICY = ReviewWeightPolicy()
        ckpt = Path(__file__).parent.parent / "models" / "review_weight_policy.pt"
        if ckpt.exists() and _SHARED_POLICY.torch_available:
            try:
                state = _SHARED_POLICY._torch.load(str(ckpt), weights_only=True)
                _SHARED_POLICY._actor.load_state_dict(state["actor"])
                _SHARED_POLICY._trained = True
            except Exception as e:
                logger.warning(f"评审权重 checkpoint 加载失败（预热替代）: {e}")
        if not _SHARED_POLICY._trained:
            _SHARED_POLICY.warmup_with_rules(ReviewEnv(seed=7), steps=200, seed=7)
    return _SHARED_POLICY


def reset_shared_policy():
    """测试 / 重训后清空共享实例"""
    global _SHARED_POLICY
    _SHARED_POLICY = None


# ────────────────────────────────────────────────────────────
# 评估：三方案对比（A=RL / B=固定规则 / C=均匀基线）
# ────────────────────────────────────────────────────────────

def evaluate_policy(policy_or_mode, env: ReviewEnv, horizon: int = 6) -> dict:
    """在给定环境下评估一个决策方式的平均回报与 skip 行为。

    policy_or_mode: "rule" | "uniform" | ReviewWeightPolicy 实例
    """
    feats = env.reset()
    total, skips, skip_streak, reviews_done, max_skip_streak = 0.0, 0, 0, 0, 0
    for _ in range(horizon):
        if policy_or_mode == "rule":
            idx, _src = _rule_action_idx(feats), "rule"
        elif policy_or_mode == "uniform":
            idx = 3
        else:
            idx, _src = policy_or_mode.select_action(
                feats, deterministic=True, skip_streak=skip_streak, reviews_done=reviews_done)
            if idx == 4 and (reviews_done < REVIEW_MIN_REVIEW or skip_streak >= SKIP_STREAK_LIMIT):
                idx = 3
        if idx == 4:
            skips += 1
            skip_streak += 1
            max_skip_streak = max(max_skip_streak, skip_streak)
        else:
            skip_streak = 0
            reviews_done += 1
        feats, r, done = env.step(idx)
        total += r
        if done:
            break
    return {
        "mean_return": total / max(1, horizon),
        "total_return": total,
        "skip_count": skips,
        "max_skip_streak": max_skip_streak,
        "reviews_done": reviews_done,
        "discipline_violation": max_skip_streak >= SKIP_STREAK_LIMIT,
    }
