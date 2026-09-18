# ============================================================
# MARL DQN 家族 — 教学决策多智能体对比（M4 对比研究）
#
# 在 MARS-408 教学决策 MDP 上实现三类值分解算法，与 MAPPO 对比：
#   - IQL（Independent Q-Learning）：每 Agent 独立 DQN，共享全局奖励（近似）
#   - VDN（Value Decomposition Networks）：Q_total = Σ Q_i（加性分解）
#   - QMIX：超网络单调混合 Q_total（state 生成非负权重）
#
# 多智能体建模：agent0=难度档位(4)，agent1=讲解方式(3)，agent2=评审强度(3)
# 共享状态 s（8 维，encode_state），共享全局奖励 r（compute_reward 口径）
#
# 工程约束：torch 延迟导入（Windows SIGSEGV 同款规避）；训练产物可复现（seed）
# ============================================================

import logging
import random
from collections import deque
from typing import Optional

logger = logging.getLogger("netlearn.marl_dqn")

_TORCH = None
_TORCH_AVAILABLE: Optional[bool] = None


def _ensure_torch():
    """运行时按需导入 torch；失败返回 None。"""
    global _TORCH, _TORCH_AVAILABLE
    if _TORCH_AVAILABLE is not None:
        return _TORCH
    try:
        import torch as _t
        _TORCH = _t
        _TORCH_AVAILABLE = True
    except Exception:
        _TORCH_AVAILABLE = False
        logger.warning("PyTorch 不可用，MARL DQN 家族不可用")
    return _TORCH


# 动作空间（与 mappo_policy 对齐）
DIFFICULTIES = ["basic", "medium", "advanced", "comprehensive"]
TEACHING_MODES = ["sequential", "example_first", "analogy"]
REVIEW_INTENSITIES = ["full", "spot", "skip"]
AGENT_ACTION_SIZES = [len(DIFFICULTIES), len(TEACHING_MODES), len(REVIEW_INTENSITIES)]
AGENT_NAMES = ["difficulty", "teaching_mode", "review_intensity"]


def _build_q_net(torch, state_dim: int, n_actions: int, hidden: int = 64):
    """单 Agent Q 网络：状态 → 各动作 Q 值。"""
    return torch.nn.Sequential(
        torch.nn.Linear(state_dim, hidden),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden, hidden),
        torch.nn.ReLU(),
        torch.nn.Linear(hidden, n_actions),
    )


class MARLValueLearner:
    """DQN 家族基类：经验回放 + target 网络 + epsilon-greedy + 训练步。

    子类实现 _q_total(q_list) 与 _target_value(next_q_list)，以区分 IQL/VDN/QMIX。
    """

    name = "base"

    def __init__(self, state_dim: int = 8, hidden: int = 64, seed: int = 1,
                 lr: float = 1e-3, gamma: float = 0.99, buffer_size: int = 50000,
                 batch_size: int = 64, target_update_every: int = 100,
                 eps_start: float = 0.3, eps_end: float = 0.05, eps_decay_steps: int = 3000):
        torch = _ensure_torch()
        if torch is None:
            raise RuntimeError("torch 不可用")
        self.torch = torch
        self.state_dim = state_dim
        self.hidden = hidden
        self.gamma = gamma
        self.batch_size = batch_size
        self.target_update_every = target_update_every
        self.eps_start = eps_start
        self.eps_end = eps_end
        self.eps_decay_steps = eps_decay_steps

        self.n_agents = len(AGENT_ACTION_SIZES)
        self.q_nets = [
            _build_q_net(torch, state_dim, n, hidden) for n in AGENT_ACTION_SIZES
        ]
        self.target_nets = [
            _build_q_net(torch, state_dim, n, hidden) for n in AGENT_ACTION_SIZES
        ]
        for i in range(self.n_agents):
            self.target_nets[i].load_state_dict(self.q_nets[i].state_dict())
            self.target_nets[i].eval()

        self.optimizers = [
            torch.optim.Adam(net.parameters(), lr=lr) for net in self.q_nets
        ]
        self.replay = deque(maxlen=buffer_size)
        self.train_step = 0
        self.rng = random.Random(seed)
        self.torch.manual_seed(seed)

    # ── 接口：子类实现 ──

    def _q_total(self, q_list: list) -> object:
        """由各 Agent Q 值计算联合 Q。"""
        raise NotImplementedError

    def _target_value(self, next_q_list: list) -> object:
        """目标值：r + γ·max 联合 Q（子类决定 max 方式）。"""
        raise NotImplementedError

    # ── 通用训练 ──

    def _epsilon(self) -> float:
        if self.train_step >= self.eps_decay_steps:
            return self.eps_end
        decay = self.eps_start - self.eps_end
        return self.eps_start - decay * (self.train_step / self.eps_decay_steps)

    def select_actions(self, state: list[float], eval_mode: bool = False) -> dict:
        """epsilon-greedy 联合动作 {agent_id: action_idx}。"""
        if eval_mode or self.rng.random() > self._epsilon():
            actions = {}
            s_t = self.torch.tensor([state], dtype=self.torch.float32)
            with self.torch.no_grad():
                for i, net in enumerate(self.q_nets):
                    actions[i] = int(net(s_t).argmax(dim=-1).item())
            return actions
        return {i: self.rng.randrange(n) for i, n in enumerate(AGENT_ACTION_SIZES)}

    def remember(self, s, a, r, s2, done):
        self.replay.append((s, a, r, s2, done))

    def train_step_once(self) -> float:
        """从回放缓冲采样一次并更新（按算法家族聚合 Q_total）。"""
        if len(self.replay) < self.batch_size:
            return 0.0
        torch = self.torch
        batch = self.rng.sample(self.replay, self.batch_size)
        s = torch.tensor([b[0] for b in batch], dtype=torch.float32)
        a = {i: torch.tensor([b[1][i] for b in batch], dtype=torch.long) for i in range(self.n_agents)}
        r = torch.tensor([b[2] for b in batch], dtype=torch.float32)
        s2 = torch.tensor([b[3] for b in batch], dtype=torch.float32)
        done = torch.tensor([float(b[4]) for b in batch], dtype=torch.float32)

        # 当前联合 Q
        q_list = []
        for i, net in enumerate(self.q_nets):
            q_all = net(s)                      # (B, n_i)
            q_i = q_all.gather(1, a[i].unsqueeze(-1)).squeeze(-1)  # (B,)
            q_list.append(q_i)
        q_total = self._q_total(q_list)         # (B,)

        # 目标联合 Q
        with torch.no_grad():
            next_q_list = [net(s2) for net in self.target_nets]
            target = r + self.gamma * (1 - done) * self._target_value(next_q_list)

        loss = torch.nn.functional.mse_loss(q_total, target)

        # 联合更新：一次 backward，全部 Q 网络共享梯度（VDN/IQL 的 q_total 为各 Q 求和）
        for opt in self.optimizers:
            opt.zero_grad()
        loss.backward()
        for opt in self.optimizers:
            opt.step()

        # target 软更新（每 target_update_every 步硬拷贝）
        self.train_step += 1
        if self.train_step % self.target_update_every == 0:
            for t, q in zip(self.target_nets, self.q_nets):
                t.load_state_dict(q.state_dict())

        return float(loss.item())

    def save(self, path: str) -> str:
        torch = self.torch
        try:
            import os
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            torch.save({"q_nets": [n.state_dict() for n in self.q_nets],
                        "name": self.name}, path)
            return path
        except Exception as e:
            logger.warning(f"MARL DQN checkpoint 保存失败: {e}")
            return ""

    def load(self, path: str) -> bool:
        torch = self.torch
        try:
            import os
            if not os.path.exists(path):
                return False
            ckpt = torch.load(path, map_location="cpu", weights_only=True)
            if ckpt.get("name") != self.name:
                return False
            for net, sd in zip(self.q_nets, ckpt["q_nets"]):
                net.load_state_dict(sd)
            for t, q in zip(self.target_nets, self.q_nets):
                t.load_state_dict(q.state_dict())
            return True
        except Exception as e:
            logger.warning(f"MARL DQN checkpoint 加载失败: {e}")
            return False


class IQLearner(MARLValueLearner):
    """IQL：每 Agent 独立 DQN，各自用全局奖励更新（经典多智能体独立学习）。"""

    name = "iql"

    def _q_total(self, q_list: list):
        # IQL 更新时各 Agent 独立，q_total 仅用于梯度回传（各 Q 独立），此处求和便于统一流程
        return sum(q_list)

    def _target_value(self, next_q_list: list):
        # 各 Agent 独立取自己的 max
        return sum(q.max(dim=-1).values for q in next_q_list)


class VDNLearner(MARLValueLearner):
    """VDN：Q_total = Σ Q_i，联合 max 分解为各 Agent 独立 max（加性保证）。"""

    name = "vdn"

    def _q_total(self, q_list: list):
        return sum(q_list)

    def _target_value(self, next_q_list: list):
        return sum(q.max(dim=-1).values for q in next_q_list)


class QMIXLearner(MARLValueLearner):
    """QMIX：超网络生成非负权重，Q_total = Σ w_i(s)·Q_i + b(s)（单调约束）。"""

    name = "qmix"

    def __init__(self, state_dim: int = 8, hidden: int = 64, seed: int = 1,
                 mix_hidden: int = 32, **kw):
        torch = _ensure_torch()
        if torch is None:
            raise RuntimeError("torch 不可用")
        self.mix_hidden = mix_hidden
        super().__init__(state_dim=state_dim, hidden=hidden, seed=seed, **kw)
        self.mixing_net = torch.nn.Sequential(
            torch.nn.Linear(state_dim, mix_hidden),
            torch.nn.ReLU(),
            torch.nn.Linear(mix_hidden, self.n_agents),
        )
        self.mixing_bias = torch.nn.Sequential(
            torch.nn.Linear(state_dim, mix_hidden),
            torch.nn.ReLU(),
            torch.nn.Linear(mix_hidden, 1),
        )
        self.mix_opt = torch.optim.Adam(
            list(self.mixing_net.parameters()) + list(self.mixing_bias.parameters()),
            lr=kw.get("lr", 1e-3),
        )

    def _q_total(self, q_list: list):
        # 调用处传 (q_list, s)；基类接口只传 q_list，这里在 train_step_once 特殊处理
        raise NotImplementedError("QMIX 使用专用 train_step_once")

    def _target_value(self, next_q_list: list):
        return sum(q.max(dim=-1).values for q in next_q_list)

    def train_step_once(self) -> float:
        if len(self.replay) < self.batch_size:
            return 0.0
        torch = self.torch
        batch = self.rng.sample(self.replay, self.batch_size)
        s = torch.tensor([b[0] for b in batch], dtype=torch.float32)
        a = {i: torch.tensor([b[1][i] for b in batch], dtype=torch.long) for i in range(self.n_agents)}
        r = torch.tensor([b[2] for b in batch], dtype=torch.float32)
        s2 = torch.tensor([b[3] for b in batch], dtype=torch.float32)
        done = torch.tensor([float(b[4]) for b in batch], dtype=torch.float32)

        # 当前：Q_total = Σ w_i(s)·Q_i(s,a_i) + b(s)
        q_list = []
        for i, net in enumerate(self.q_nets):
            q_i = net(s).gather(1, a[i].unsqueeze(-1)).squeeze(-1)
            q_list.append(q_i)
        q_stack = torch.stack(q_list, dim=-1)          # (B, n_agents)
        w = torch.abs(self.mixing_net(s)) + 1e-6       # (B, n_agents) 单调非负
        b = self.mixing_bias(s)                        # (B, 1)
        q_total = (q_stack * w).sum(dim=-1) + b.squeeze(-1)

        # 目标：r + γ·max_a' Q_total(s')（单调 → 各 Agent 独立 max 即联合最优）
        with torch.no_grad():
            next_q_list = [net(s2) for net in self.target_nets]
            next_max = torch.stack(
                [q.max(dim=-1).values for q in next_q_list], dim=-1
            )                                          # (B, n_agents)
            w2 = torch.abs(self.mixing_net(s2)) + 1e-6
            b2 = self.mixing_bias(s2)
            target = r + self.gamma * (1 - done) * (
                (next_max * w2).sum(dim=-1) + b2.squeeze(-1)
            )

        loss = torch.nn.functional.mse_loss(q_total, target)

        self.mix_opt.zero_grad()
        for opt in self.optimizers:
            opt.zero_grad()
        loss.backward()
        self.mix_opt.step()
        for opt in self.optimizers:
            opt.step()

        self.train_step += 1
        if self.train_step % self.target_update_every == 0:
            for t, q in zip(self.target_nets, self.q_nets):
                t.load_state_dict(q.state_dict())
        return float(loss.item())


# ── 多智能体环境适配（TeachingEnv → 3 Agent 联合动作）──

class MultiAgentTeachingEnv:
    """教学决策多智能体包装：agent0=难度(4)，agent1=讲解方式(3)，agent2=评审强度(3)。

    共享 8 维状态（encode_state）、共享全局奖励（compute_reward 口径）。
    """

    def __init__(self, student_level: float = 0.5, seed: int = 42, horizon: int = 4,
                 drift: float = 0.06, curriculum: bool = False):
        from engines.mappo_policy import TeachingEnv, encode_state
        self._env = TeachingEnv(student_level=student_level, seed=seed,
                                horizon=horizon, drift=drift, curriculum=curriculum)
        self._encode = encode_state

    def reset(self) -> list[float]:
        return self._encode(**self._env.reset())

    def step(self, actions: dict) -> tuple[list[float], float, bool]:
        env_action = {
            "difficulty": DIFFICULTIES[actions[0]],
            "teaching_mode": TEACHING_MODES[actions[1]],
            "review_intensity": REVIEW_INTENSITIES[actions[2]],
        }
        state, reward, done = self._env.step(env_action)
        return self._encode(**state), reward, done

    @property
    def env(self):
        return self._env


def train_value_learner(learner: MARLValueLearner, env: MultiAgentTeachingEnv,
                        episodes: int = 1500, seed: int = 1) -> dict:
    """DQN 家族通用训练循环（epsilon-greedy + 经验回放 + target 网络）。"""
    learner.rng = random.Random(seed)
    learner.torch.manual_seed(seed)
    rewards, accs, costs = [], [], []
    from engines.mappo_policy import _COST_FACTOR

    for ep in range(episodes):
        s = env.reset()
        done = False
        ep_r = 0.0
        accs_ep, costs_ep = [], []
        while not done:
            a = learner.select_actions(s)
            s2, r, done = env.step(a)
            learner.remember(s, a, r, s2, done)
            learner.train_step_once()
            s = s2
            ep_r += r
            accs_ep.append(env.env.accuracy)
            costs_ep.append(_COST_FACTOR.get(REVIEW_INTENSITIES[a[2]], 2.0))
        rewards.append(ep_r)
        accs.append(sum(accs_ep) / len(accs_ep) if accs_ep else 0.0)
        costs.append(sum(costs_ep) / len(costs_ep) if costs_ep else 0.0)

    return {
        "trained": True,
        "episodes": episodes,
        "avg_reward": float(sum(rewards) / len(rewards)),
        "last_reward": float(rewards[-1]),
        "avg_accuracy": float(sum(accs) / len(accs)),
        "avg_cost": float(sum(costs) / len(costs)),
    }
