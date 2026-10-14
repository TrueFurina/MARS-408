# ⚠️ 本目录内 `mixer_consensus_bench_2026-10-06.json` 是「规则兜底」产物，不是神经共识分

> 诚信红线守护文件。请勿把本 JSON 的均值误读成产品对外使用的共识分。

## 本文件的真实身份
- `mixer_state.mixer_neural_mode = "rule"`
- `mixer_state.mixer_trained_loaded = False` ← 神经网络权重**未加载**，跑的是规则兜底
- `config.seed = 20261008`（注意：不是对外口径里的 20261006）
- 产出：`stratified` mean **6.8266** / std 0.2723；`overall(192)` mean 6.9304 / std 0.5192

## 与对外口径的关系
- 产品 / 路演 PPT 引用的共识分 **7.0446 ± 0.2857** 是**神经模式（neural）真值**，对应：
  - 配置：`seed 20261006` / `stratified` / `n=96` / `n_agents=6` / 神经权重 `neural_mixer_trained.pt` 已加载（`trained_loaded: True`）
  - 复现：2026-10-14 在服务器 `172.16.222.99`（all-in-rag 环境，torch 2.10+cu128 / numpy 2.2.6）用提交版 `py-server/engines/gomarl_mixer.py` + 权重复跑确认，`stratified mean=7.0446 std=0.2857`，逐位一致。
- 两者口径不同（规则兜底 vs 神经权重）、seed 不同，**不可互相替换**。

## 给未来读者的提示
- 要复现 7.0446：确保服务器存在 `py-server/models/neural_mixer_trained.pt`，然后
  `python experiments/bench_mixer_consensus.py --samples 96 --seed 20261006 --n-agents 6 --distribution all`
- 本 JSON 仅作为「规则兜底基线」存档，用于对照神经模式带来的增益，**不代表产品共识质量**。
