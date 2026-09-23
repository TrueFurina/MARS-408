# ============================================================
# MappoPolicy — MAPPO 教学策略层（三评审集成·增量四）
#
# 定位：把「NeuralMixer 权重（EWMA 规则）」升级为「MAPPO 训练的教学策略」，
#   填补 README 中 "GoMARL 加权共识真训未执行" 的缺口。
#
# 设计：
#   状态 s = {掌握度, 薄弱点个数, 偏好难度, 当前难度, 轮次, 上次正确率, 知识点考查权重}
#   动作 a = {难度档位(4), 讲解方式(3), 评审强度(3)}  —— 3 个离散动作头
#   奖励 r = w1·Δ正确率 + w2·参与度 + w3·完成度 − w4·token成本 − w5·时延惩罚
#   算法   = MAPPO（CTDE）：Actor-Critic + GAE + PPO clip，多智能体共享 Critic
#
# 工程约束：
#   - torch 延迟导入（仿 gomarl_mixer：Windows 原生 torch 触发 SIGSEGV，模块级导入会崩）
#   - 无 torch / 未训练 / 推理失败 → 规则降级（绝不中断调用方）
#   - 供 gomarl_mixer._compute_dynamic_weights 通过 flag 灰度接入（默认关闭）
# ============================================================

import logging
import os
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger("netlearn.mappo_policy")

# ── torch 延迟导入（与 gomarl_mixer 同模式）──
_TORCH = None
_TORCH_AVAILABLE: Optional[bool] = None


def _ensure_torch():
    """运行时按需导入 torch；失败返回 None（规则降级）。"""
    global _TORCH, _TORCH_AVAILABLE
    if _TORCH_AVAILABLE is not None:
        return _TORCH
    try:
        import torch as _t
        _TORCH = _t
        _TORCH_AVAILABLE = True
        logger.info("PyTorch 可用，MAPPO 教学策略启用神经网络模式")
    except Exception:
        _TORCH_AVAILABLE = False
        logger.warning("PyTorch 不可用，MAPPO 教学策略降级为规则模式")
    return _TORCH


# ── 动作空间常量 ──
DIFFICULTIES = ["basic", "medium", "advanced", "comprehensive"]
TEACHING_MODES = ["sequential", "example_first", "analogy"]
REVIEW_INTENSITIES = ["full", "spot", "skip"]

# 难度档位 → 数值（匹配度计算用）
_DIFF_VALUES = {"basic": 0.25, "medium": 0.5, "advanced": 0.75, "comprehensive": 1.0}
# 评审强度 → token 成本系数（full=全评审，spot=抽查，skip=跳过）
_COST_FACTOR = {"full": 3.0, "spot": 2.0, "skip": 1.0}
# 讲解方式 → 参与度加成
_PARTICIPATION_BONUS = {"sequential": 0.0, "example_first": 0.15, "analogy": 0.10}

# 默认奖励权重（质量优先：学习效果为主导，成本是次要约束；
# 评审（full/spot）是防幻觉手段，skip 有质量风险 → completion 拉开差距）
DEFAULT_REWARD_WEIGHTS = {"acc": 0.55, "part": 0.15, "comp": 0.20, "cost": 0.05, "lat": 0.05}


def encode_state(
    profile: Optional[dict] = None,
    difficulty: str = "",
    round_num: int = 0,
    last_accuracy: float = 0.5,
    gate_result: Optional[dict] = None,
    topic_weight: float = 0.5,
) -> list[float]:
    """状态编码：画像 + 教学上下文 → 8 维数值向量（确定性、可复现）。

    维度：掌握度 / 薄弱点个数(归一化) / 偏好难度 / 当前难度 / 轮次 / 上次正确率 / 考查权重 / 是否重试过
    """
    profile = profile or {}
    level_map = {"beginner": 0.25, "intermediate": 0.5, "advanced": 0.75, "expert": 1.0}
    mastery = level_map.get(profile.get("level", "intermediate"), 0.5)

    weak_count = len(profile.get("weak_topics", []) or []) + len(profile.get("weak_subjects", []) or [])
    weak_norm = min(weak_count / 5.0, 1.0)

    pref_diff = _DIFF_VALUES.get(profile.get("preferred_difficulty", "medium"), 0.5)
    cur_diff = _DIFF_VALUES.get(difficulty, 0.5)
    round_norm = min(max(round_num, 0), 5) / 5.0
    acc = max(0.0, min(float(last_accuracy), 1.0))
    weight = max(0.0, min(float(topic_weight), 1.0))
    retried = 1.0 if (gate_result or {}).get("verdict") in ("fix", "reject") else 0.0

    return [mastery, weak_norm, pref_diff, cur_diff, round_norm, acc, weight, retried]


def compute_reward(
    delta_accuracy: float,
    participation: float,
    completion: float,
    review_intensity: str,
    weights: Optional[dict] = None,
) -> float:
    """奖励函数：学习效果 − 成本。可解释、可复算（答辩口径）。

    r = w1·Δ正确率 + w2·参与度 + w3·完成度 − w4·token成本 − w5·时延惩罚
    """
    w = weights or DEFAULT_REWARD_WEIGHTS
    cost = _COST_FACTOR.get(review_intensity, 2.0)
    latency_penalty = cost * 0.1
    return (
        w["acc"] * max(-1.0, min(float(delta_accuracy), 1.0))
        + w["part"] * max(0.0, min(float(participation), 1.0))
        + w["comp"] * max(0.0, min(float(completion), 1.0))
        - w["cost"] * (cost / 3.0)
        - w["lat"] * latency_penalty
    )


# ── 合成教学环境（用于训练 / 对比实验）──

class TeachingEnv:
    """模拟教学环境：学生水平 vs 难度匹配度 → 学习效果；评审强度 → 成本/质量。

    设计意图（答辩可讲）：
      - 难度匹配度 |difficulty − student_level| 越小，正确率提升越大；
      - 讲解方式影响参与度（例题先行/类比 > 顺序讲解）；
      - 评审强度影响完成度与成本（full 质量最高但 token 成本 3 倍）。
    """

    def __init__(self, student_level: float = 0.5, seed: int = 42, horizon: int = 4,
                 drift: float = 0.06, curriculum: bool = False):
        """教学环境。

        Args:
            student_level: 初始学生水平（0-1）
            drift: 每步水平漂移幅度（模拟学习过程中能力变化）；0=静态
            curriculum: reset 时随机采样学生水平（训练用，让策略学会跨水平泛化）
        """
        self.student_level = max(0.1, min(student_level, 0.9))
        self.rng = random.Random(seed)
        self.horizon = horizon
        self.drift = drift
        self.curriculum = curriculum
        self.step_count = 0
        self.last_accuracy = 0.5
        self.accuracy = 0.5

    def reset(self) -> dict:
        if self.curriculum:
            # 训练课程：三档学生水平等概率采样（对应 basic/medium/advanced 难度锚点）
            self.student_level = self.rng.choice([0.25, 0.5, 0.75])
        self.step_count = 0
        self.last_accuracy = 0.5
        self.accuracy = 0.5
        return self._state()

    def _state(self) -> dict:
        return {
            "profile": {"level": self._level_name(), "weak_topics": ["tcp"]},
            "difficulty": "",
            "round_num": 0,
            "last_accuracy": self.accuracy,
            "gate_result": {},
            "topic_weight": 0.5,
        }

    def _level_name(self) -> str:
        if self.student_level < 0.35:
            return "beginner"
        if self.student_level < 0.65:
            return "intermediate"
        return "advanced"

    def step(self, action: dict) -> tuple[dict, float, bool]:
        """执行教学动作，返回 (next_state, reward, done)。"""
        self.step_count += 1

        difficulty = action.get("difficulty", "medium")
        mode = action.get("teaching_mode", "sequential")
        intensity = action.get("review_intensity", "full")

        # 难度匹配度：|difficulty − 当前学生水平| 小 → 提升大
        diff_val = _DIFF_VALUES.get(difficulty, 0.5)
        mismatch = abs(diff_val - self.student_level)
        base_gain = max(0.0, 0.40 - mismatch * 0.6)

        # 噪声：真实环境有随机性
        noise = self.rng.uniform(-0.05, 0.05)

        # 正确率提升（带记忆：之前学过的会累积一点）
        delta_accuracy = max(-0.2, min(base_gain + noise, 0.4))
        self.accuracy = max(0.1, min(self.accuracy + delta_accuracy, 1.0))

        # 参与度：讲解方式加成 + 匹配度
        participation = max(
            0.0, min(0.4 + _PARTICIPATION_BONUS.get(mode, 0.0) + (0.2 - mismatch * 0.4), 1.0)
        )

        # 完成度：full 与 spot 质量差距小（抽查仅略降），skip 明显有幻觉/遗漏风险
        quality = {"full": 1.0, "spot": 0.92, "skip": 0.72}
        completion = quality.get(intensity, 0.85) * (0.9 + 0.1 * (1.0 - mismatch))

        reward = compute_reward(delta_accuracy, participation, completion, intensity)

        # 难度适配奖励：教学系统直接评价「难度 vs 掌握度标签」的匹配度
        # （信号与 acc 捷径解耦；答辩口径：难度与掌握度错配 = 教学低效）
        _tag_map = {"beginner": "basic", "intermediate": "medium", "advanced": "advanced"}
        ideal_val = _DIFF_VALUES.get(_tag_map.get(self._level_name(), "medium"), 0.5)
        reward = reward - 0.25 * abs(diff_val - ideal_val)

        # 学生水平漂移（能力随学习变化；静态环境 drift=0 时不受影响）
        if self.drift > 0:
            self.student_level = max(
                0.1, min(0.9, self.student_level + self.rng.uniform(-self.drift, self.drift))
            )

        done = self.step_count >= self.horizon
        return self._state(), reward, done


# ── 网络定义（torch 可用后延迟构建）──

def _build_networks(torch):
    """返回 (ActorNet, CriticNet) 类。"""

    class ActorNet(torch.nn.Module):
        """策略网络：共享 encoder + 3 个离散动作头。"""

        def __init__(self, state_dim: int, hidden: int = 64):
            super().__init__()
            self.encoder = torch.nn.Sequential(
                torch.nn.Linear(state_dim, hidden),
                torch.nn.Tanh(),
                torch.nn.Linear(hidden, hidden),
                torch.nn.Tanh(),
            )
            self.difficulty_head = torch.nn.Linear(hidden, len(DIFFICULTIES))
            self.mode_head = torch.nn.Linear(hidden, len(TEACHING_MODES))
            self.intensity_head = torch.nn.Linear(hidden, len(REVIEW_INTENSITIES))

        def forward(self, s: torch.Tensor) -> dict:
            h = self.encoder(s)
            return {
                "difficulty": torch.softmax(self.difficulty_head(h), dim=-1),
                "teaching_mode": torch.softmax(self.mode_head(h), dim=-1),
                "review_intensity": torch.softmax(self.intensity_head(h), dim=-1),
            }

        def log_probs(self, s: torch.Tensor, actions: dict) -> dict:
            probs = self.forward(s)
            logs = {}
            for name, a_idx in actions.items():
                dist = torch.distributions.Categorical(probs[name])
                if not isinstance(a_idx, torch.Tensor):
                    a_idx = torch.tensor([a_idx], dtype=torch.long)
                logs[name] = dist.log_prob(a_idx)
            return logs

        def entropy(self, s: torch.Tensor) -> torch.Tensor:
            probs = self.forward(s)
            ent = torch.zeros((), device=s.device)
            for name in ("difficulty", "teaching_mode", "review_intensity"):
                dist = torch.distributions.Categorical(probs[name])
                ent = ent + dist.entropy()
            return ent

    class CriticNet(torch.nn.Module):
        """共享 Critic：状态 → 价值标量（CTDE 中心价值函数）。"""

        def __init__(self, state_dim: int, hidden: int = 64):
            super().__init__()
            self.net = torch.nn.Sequential(
                torch.nn.Linear(state_dim, hidden),
                torch.nn.Tanh(),
                torch.nn.Linear(hidden, hidden),
                torch.nn.Tanh(),
                torch.nn.Linear(hidden, 1),
            )

        def forward(self, s: torch.Tensor) -> torch.Tensor:
            return self.net(s).squeeze(-1)

    return ActorNet, CriticNet


# ── MAPPO 主策略 ──

class MappoPolicy:
    """MAPPO 教学策略（CTDE：策略网络 + 共享 Critic，GAE + PPO clip 更新）。

    接口：
      - select_action(profile, difficulty, round_num, last_accuracy, gate_result)
          → {difficulty, teaching_mode, review_intensity}（网络推理 / 规则降级）
      - agent_weight_adjust(profile, action) → dict（供 Mixer 权重调整，flag 灰度）
      - train(env, episodes, ...) → metrics（PPO 训练）
      - save / load（checkpoint 持久化）
    """

    def __init__(self, config: Optional[dict] = None):
        self.cfg = config or {}
        self.state_dim = 8
        self.hidden = int(self.cfg.get("mappo_hidden_dim", 64))
        self.lr = float(self.cfg.get("mappo_lr", 3e-4))
        self.gamma = float(self.cfg.get("mappo_gamma", 0.99))
        self.gae_lambda = float(self.cfg.get("mappo_gae_lambda", 0.95))
        self.clip_epsilon = float(self.cfg.get("mappo_clip_epsilon", 0.2))
        self.ppo_epochs = int(self.cfg.get("mappo_ppo_epochs", 4))
        self.mini_batch = int(self.cfg.get("mappo_mini_batch", 64))
        self.entropy_coef = float(self.cfg.get("mappo_entropy_coef", 0.02))

        self._torch = _ensure_torch()
        self._actor = None
        self._critic = None
        self._optimizer = None
        self._trained = False

        # checkpoint 路径：配置 > 默认 models/mappo_policy.pt
        ckpt = self.cfg.get("mappo_checkpoint", "")
        if not ckpt:
            ckpt = str(Path(__file__).parent.parent / "models" / "mappo_policy.pt")
        self.checkpoint_path = ckpt

        if self._torch is not None:
            ActorNet, CriticNet = _build_networks(self._torch)
            self._actor = ActorNet(self.state_dim, self.hidden)
            self._critic = CriticNet(self.state_dim, self.hidden)
            self._optimizer = self._torch.optim.Adam(
                list(self._actor.parameters()) + list(self._critic.parameters()),
                lr=self.lr,
            )
            self.load()

    # ── 规则降级动作（无 torch / 未训练 / 推理失败）──

    def _rule_action(
        self,
        profile: Optional[dict],
        difficulty: str,
        round_num: int,
        gate_result: Optional[dict],
    ) -> dict:
        profile = profile or {}
        level = profile.get("level", "intermediate")
        diff_map = {"beginner": "basic", "intermediate": "medium", "advanced": "advanced"}
        d = difficulty or diff_map.get(level, "medium")
        mode = "sequential"
        retried = (gate_result or {}).get("verdict") in ("fix", "reject")
        intensity = "full" if (round_num > 0 or retried) else "spot"
        return {
            "difficulty": d,
            "teaching_mode": mode,
            "review_intensity": intensity,
            "source": "rule",
        }

    # ── 动作选择 ──

    def select_action(
        self,
        profile: Optional[dict] = None,
        difficulty: str = "",
        round_num: int = 0,
        last_accuracy: float = 0.5,
        gate_result: Optional[dict] = None,
        topic_weight: float = 0.5,
        deterministic: bool = True,
    ) -> dict:
        """选择教学策略动作。网络不可用 / 未训练 / 失败 → 规则降级。"""
        if self._torch is None or self._actor is None or not self._trained:
            return self._rule_action(profile, difficulty, round_num, gate_result)

        try:
            s = encode_state(profile, difficulty, round_num, last_accuracy, gate_result, topic_weight)
            s_t = self._torch.tensor([s], dtype=self._torch.float32)
            self._actor.eval()
            with self._torch.no_grad():
                probs = self._actor(s_t)
            action = {}
            for name, choices in (
                ("difficulty", DIFFICULTIES),
                ("teaching_mode", TEACHING_MODES),
                ("review_intensity", REVIEW_INTENSITIES),
            ):
                p = probs[name][0]
                if deterministic:
                    idx = int(p.argmax().item())
                else:
                    idx = int(self._torch.multinomial(p, 1).item())
                action[name] = choices[idx]
            action["source"] = "mappo"
            return action
        except Exception as e:
            logger.warning(f"MAPPO 推理失败，规则降级: {e}")
            return self._rule_action(profile, difficulty, round_num, gate_result)

    # ── Agent 权重调整（供 gomarl_mixer 灰度接入）──

    def agent_weight_adjust(
        self, profile: Optional[dict] = None, action: Optional[dict] = None
    ) -> dict:
        """基于策略动作的 Agent 权重调整因子（乘性）。

        - basic 难度 → teacher 权重提升（重讲解）；
        - advanced/comprehensive → code_practice / assessor 权重提升（重练习与评估）；
        - 评审强度 skip → 各 Agent 权重略降（省成本信号）。
        规则未训练时返回 {}（对 Mixer 零影响）。
        """
        action = action or self._rule_action(profile, "", 0, None)
        adjust: dict[str, float] = {}
        d = action.get("difficulty", "medium")
        if d == "basic":
            adjust["teacher"] = 1.15
        elif d in ("advanced", "comprehensive"):
            adjust["code_practice"] = 1.10
            adjust["assessor"] = 1.08
        intensity = action.get("review_intensity", "spot")
        if intensity == "skip":
            adjust = {k: v * 0.95 for k, v in adjust.items()} if adjust else {}
        return adjust

    # ── 训练（rollout + GAE + PPO）──

    def warmup_with_rules(self, env: TeachingEnv, steps: int = 800, seed: int = 7) -> dict:
        """规则监督预训练（behavior cloning）：用规则动作预热 Actor。

        冷启动阶段纯 RL 探索慢、易次优收敛；先让策略模仿规则的难度匹配
        （基础→basic、中等→medium、进阶→advanced），再交给 PPO 微调
        （AlphaStar 同款两阶段范式，答辩可讲）。torch 不可用则跳过。
        """
        if self._torch is None or self._actor is None:
            return {"warmup": False, "reason": "torch unavailable"}

        torch = self._torch
        random.seed(seed)
        torch.manual_seed(seed)

        states, targets = [], []
        for _ in range(steps):
            state = env.reset()
            action = self._rule_action(state["profile"], state["difficulty"],
                                       state["round_num"], state["gate_result"])
            s = encode_state(**state)
            states.append(s)
            targets.append({
                "difficulty": DIFFICULTIES.index(action["difficulty"]),
                "teaching_mode": TEACHING_MODES.index(action["teaching_mode"]),
                "review_intensity": REVIEW_INTENSITIES.index(action["review_intensity"]),
            })

        s_batch = torch.tensor(states, dtype=torch.float32)
        act_batch = {
            k: torch.tensor([t[k] for t in targets], dtype=torch.long)
            for k in ("difficulty", "teaching_mode", "review_intensity")
        }
        warmup_opt = torch.optim.Adam(self._actor.parameters(), lr=1e-3)

        total_loss = 0.0
        for _ in range(30):
            warmup_opt.zero_grad()
            probs = self._actor(s_batch)
            loss = torch.zeros((), dtype=torch.float32)
            for k in act_batch:
                dist = torch.distributions.Categorical(probs[k])
                loss = loss - dist.log_prob(act_batch[k]).mean()
            loss.backward()
            warmup_opt.step()
            total_loss += float(loss.item())

        self._trained = True
        logger.info(f"MAPPO 规则监督预训练完成 steps={steps}, avg_loss={total_loss / 20:.4f}")
        return {"warmup": True, "steps": steps, "avg_loss": round(total_loss / 20, 4)}

    def train(self, env: TeachingEnv, episodes: int = 300, seed: int = 42) -> dict:
        """在模拟教学环境上训练 MAPPO，返回训练指标。"""
        if self._torch is None or self._actor is None:
            logger.warning("torch 不可用，跳过 MAPPO 训练")
            return {"trained": False, "reason": "torch unavailable"}

        torch = self._torch
        random.seed(seed)
        torch.manual_seed(seed)

        episode_rewards: list[float] = []
        episode_accs: list[float] = []
        episode_costs: list[float] = []

        for ep in range(episodes):
            # ── 收集 rollout ──
            states, actions, rewards, dones, values, old_logs = [], [], [], [], [], []
            state = env.reset()
            done = False
            total_reward = 0.0
            accs, costs = [], []

            while not done:
                s = encode_state(**state)
                s_t = torch.tensor([s], dtype=torch.float32)

                self._actor.eval()
                with torch.no_grad():
                    probs = self._actor(s_t)
                    value = self._critic(s_t).item()
                # 采样动作
                action_dict = {}
                for name, choices in (
                    ("difficulty", DIFFICULTIES),
                    ("teaching_mode", TEACHING_MODES),
                    ("review_intensity", REVIEW_INTENSITIES),
                ):
                    p = probs[name][0]
                    idx = int(torch.multinomial(p, 1).item())
                    action_dict[name] = idx
                # 记录 log_prob
                self._actor.train()
                logs = self._actor.log_probs(s_t, action_dict)
                old_log = sum(logs.values()).detach()

                states.append(s)
                actions.append(action_dict)
                old_logs.append(old_log)
                values.append(value)

                action_str = {
                    k: v for k, v in action_dict.items()
                }
                env_action = {
                    "difficulty": DIFFICULTIES[action_dict["difficulty"]],
                    "teaching_mode": TEACHING_MODES[action_dict["teaching_mode"]],
                    "review_intensity": REVIEW_INTENSITIES[action_dict["review_intensity"]],
                }
                next_state, reward, done = env.step(env_action)
                rewards.append(reward)
                dones.append(done)

                total_reward += reward
                accs.append(env.accuracy)
                costs.append(_COST_FACTOR.get(env_action["review_intensity"], 2.0))
                state = next_state

            episode_rewards.append(total_reward)
            episode_accs.append(sum(accs) / len(accs) if accs else 0.0)
            episode_costs.append(sum(costs) / len(costs) if costs else 0.0)

            # 每 200 回合打印一次训练曲线（诊断收敛）
            if (ep + 1) % 200 == 0:
                recent = episode_rewards[-200:]
                logger.info(
                    f"MAPPO 训练 [ep={ep + 1}] avg_reward(近200)={sum(recent) / len(recent):.3f} "
                    f"avg_acc={sum(episode_accs[-200:]) / 200:.3f}"
                )

            # ── GAE 计算 ──
            T = len(rewards)
            with torch.no_grad():
                s_last = torch.tensor([states[-1]], dtype=torch.float32)
                next_value = self._critic(s_last).item() if not dones[-1] else 0.0
            gae = 0.0
            advantages = [0.0] * T
            returns = [0.0] * T
            for t in reversed(range(T)):
                if t == T - 1:
                    next_v = next_value
                else:
                    next_v = values[t + 1]
                delta = rewards[t] + self.gamma * next_v * (1 - int(dones[t])) - values[t]
                gae = delta + self.gamma * self.gae_lambda * (1 - int(dones[t])) * gae
                advantages[t] = gae
                returns[t] = advantages[t] + values[t]

            # ── PPO 更新 ──
            s_batch = torch.tensor(states, dtype=torch.float32)
            ret_batch = torch.tensor(returns, dtype=torch.float32)
            adv_batch = torch.tensor(advantages, dtype=torch.float32)
            old_log_batch = torch.stack(old_logs).squeeze(-1)  # (T,)
            act_batch = {
                k: torch.tensor([a[k] for a in actions], dtype=torch.long)
                for k in ("difficulty", "teaching_mode", "review_intensity")
            }

            for _ in range(self.ppo_epochs):
                self._actor.train()
                self._critic.train()
                logs_new = self._actor.log_probs(s_batch, act_batch)
                new_log = sum(logs_new.values())
                ratio = torch.exp(new_log - old_log_batch)
                adv = (adv_batch - adv_batch.mean()) / (adv_batch.std() + 1e-8)
                surr1 = ratio * adv
                surr2 = torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon) * adv
                policy_loss = -torch.min(surr1, surr2).mean()
                value_loss = torch.nn.functional.mse_loss(self._critic(s_batch), ret_batch)
                entropy_bonus = -self.entropy_coef * self._actor.entropy(s_batch).mean()

                self._optimizer.zero_grad()
                (policy_loss + 0.5 * value_loss + entropy_bonus).backward()
                self._optimizer.step()

            self._trained = True

        self.save()
        return {
            "trained": True,
            "episodes": episodes,
            "avg_reward": float(sum(episode_rewards) / len(episode_rewards)),
            "last_reward": float(episode_rewards[-1]),
            "avg_accuracy": float(sum(episode_accs) / len(episode_accs)),
            "avg_cost": float(sum(episode_costs) / len(episode_costs)),
            "checkpoint": self.checkpoint_path,
        }

    # ── checkpoint 持久化 ──

    def save(self, path: str = "") -> str:
        path = path or self.checkpoint_path
        if self._torch is None or self._actor is None:
            return ""
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._torch.save(
                {
                    "actor": self._actor.state_dict(),
                    "critic": self._critic.state_dict(),
                    "state_dim": self.state_dim,
                    "hidden": self.hidden,
                },
                path,
            )
            self._trained = True
            logger.info(f"MAPPO checkpoint 已保存: {path}")
            return path
        except Exception as e:
            logger.warning(f"MAPPO checkpoint 保存失败: {e}")
            return ""

    def load(self, path: str = "") -> bool:
        path = path or self.checkpoint_path
        if self._torch is None or self._actor is None:
            return False
        try:
            if not os.path.exists(path):
                logger.info(f"MAPPO checkpoint 不存在（未训练，规则模式）: {path}")
                return False
            ckpt = self._torch.load(path, map_location="cpu", weights_only=True)
            if ckpt.get("state_dim") != self.state_dim:
                logger.warning("MAPPO checkpoint state_dim 不匹配，忽略")
                return False
            self._actor.load_state_dict(ckpt["actor"])
            self._critic.load_state_dict(ckpt["critic"])
            self._trained = True
            logger.info(f"MAPPO checkpoint 已加载: {path}")
            return True
        except Exception as e:
            logger.warning(f"MAPPO checkpoint 加载失败: {e}")
            return False


# ── 全局单例（供 Mixer / 规则引擎灰度接入）──

def get_mappo_policy() -> MappoPolicy:
    """按 config 构造策略（读 gomarl.mappo_* 配置）。"""
    try:
        from config import get_gomarl_config
        cfg = get_gomarl_config()
    except Exception:
        cfg = {}
    return MappoPolicy(cfg)


mappo_policy = get_mappo_policy()
