# 审计报告 — MARL 值分解与教学环境奖励（2026-11-02）

**日期**：2026-11-02
**工作流**：工程保障（源码审读 + 定向性质测试）
**严重度**：🟠 **SEV-2（训练正确性）** — 均已修复并带回归
**状态**：✅ 已闭环（2 处修复已推 `main`）

---

## 📌 TL;DR

本轮对 `py-server/engines/` 的值分解算法与教学环境做定向审计，发现 **2 处训练正确性缺陷**：

1. **QMIX 缺 target mixing network**：TD 目标用了**在线**混合器，而 target Q 网络是单独一份、定期同步的——目标随梯度漂移。
2. **教学环境奖励失真**：奖励里的 Δ正确率用的是**意图增益**而非**实际变化**，正确率饱和到 1.0 后仍在发正奖励。

两处均已修复并补回归。**第 2 处已本地真跑验证**；第 1 处因本机 torch 坏装（`shm.dll` 缺失）只能由 CI 做运行时验证。

---

## 🎯 结论卡片

| 项目 | 内容 |
|------|------|
| 审计范围 | `py-server/engines/marl_dqn.py`、`py-server/engines/mappo_policy.py` |
| 发现缺陷 | 2 处（训练正确性） |
| 已修复 | 2/2 |
| 新增回归 | `test_qmix_target_mixer.py`（torch 守卫）、`test_teaching_env_reward.py`（纯 stdlib） |
| 验证 | 奖励修复：2 passed；mappo 相关 40 passed / 10 skipped。QMIX 修复：本机 skip，待 CI |

---

## 1. QMIX 缺 target mixing network（`marl_dqn.py`，commit `9133846`）

### 根因
`QMIXLearner.train_step_once` 计算 TD 目标时用的是**在线**混合器：

```python
w2 = torch.abs(self.mixing_net(s2)) + 1e-6
b2 = self.mixing_bias(s2)
```

但 target Q 网络是单独一份、每 `target_update_every` 步 `load_state_dict` 同步的。混合器没有目标副本，等于**目标函数随正在优化的参数一起移动**。

### 影响
标准 QMIX（Rashid et al. 2018）要求 TD 目标用慢更新的 target mixing network。用在线混合器会让目标有偏、训练不稳定；在多智能体对比实验里会污染 IQL/VDN/QMIX 的横向结论。

### 修复
- `QMIXLearner.__init__` 增加 `target_mixing_net` / `target_mixing_bias`（初值拷贝，`requires_grad_(False)`）
- `train_step_once` 的目标改用 target mixer
- target 同步时一并 `load_state_dict` 混合器

### 验证
`tests/test_qmix_target_mixer.py` 两条：初始一致、同步后一致。
⚠️ 本机 torch 为坏装（`OSError: shm.dll`），测试显示 `2 skipped`；**运行时验证需由 CI 完成**。

---

## 2. 教学环境奖励失真（`mappo_policy.py`，commit `1a6d820`）

### 根因
`TeachingEnv.step` 把**意图增益**当作 Δ正确率传给 `compute_reward`：

```python
delta_accuracy = max(-0.2, min(base_gain + noise, 0.4))   # 意图增益
self.accuracy = max(0.1, min(self.accuracy + delta_accuracy, 1.0))  # 被夹到 1.0
reward = compute_reward(delta_accuracy, ...)              # 用意图增益发奖
```

正确率饱和后，实际学习为 0，但奖励仍按 ~0.4 的增益发放。

### 复现（修复前，`drift=0`）

| step | 正确率变化 | 实际 Δ | reward |
|---|---|---|---|
| 1 | 0.500 → 0.863 | +0.363 | 0.4249 |
| 2 | 0.863 → 1.000 | +0.137 | 0.4450 |
| 3 | 1.000 → 1.000 | **+0.000** | **0.4450** |
| 4 | 1.000 → 1.000 | +0.000 | 0.4315 |
| 5 | 1.000 → 1.000 | +0.000 | 0.4447 |

策略会学会「**重复无效动作**」——不学习也有奖励。

### 修复
先更新 `accuracy` 并夹到 `[0.1, 1.0]`，再用 `self.accuracy - prev_accuracy` 作为奖励里的 Δ。

### 验证（修复后）

| step | 实际 Δ | reward |
|---|---|---|
| 1 | +0.363 | 0.4249 |
| 2 | +0.137 | 0.3001 |
| 3–5 | +0.000 | **0.2250**（只剩参与度/完成度/成本项） |

`tests/test_teaching_env_reward.py` 2 条回归；mappo 相关 40 passed / 10 skipped。

---

## 验证口径

```
pytest tests/test_teaching_env_reward.py                      # 2 passed
pytest tests/test_m3_mappo_policy.py tests/test_mappo_budget_audit.py \
       tests/test_review_mappo.py                             # 40 passed / 10 skipped
pytest tests/test_qmix_target_mixer.py                        # 本机 2 skipped（torch 坏装）
```

## 剩余风险（诚实说明）

- 本次是**定向**审计（读源码 + 构造判据），不是全量形式化验证；未覆盖路径不能据此认为安全。
- `test_qmix_target_mixer.py` 在本机被 skip：本机 torch 安装损坏（`shm.dll` 缺失），修复的运行时正确性需 CI 确认。
- 值分解的**收敛性/最终收益**未做端到端训练对比；本次只保证「目标计算口径正确」。
