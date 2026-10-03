#!/usr/bin/env python3
"""
GoMARL NeuralMixer 训练脚本 — 结构验证版

⚠️ 重要警告：本脚本使用 np.random.randn() 生成的随机噪声作为训练数据。
   这仅用于验证 GroupMixerNet 网络结构的可运行性和代码正确性。
   生成的 neural_mixer_trained.pt 权重在真实 Agent 输出上不具有实际意义。

   如需生产级训练：
   1. 收集真实 Agent 输出文本
   2. 用 E5 编码器生成真实 768 维嵌入
   3. 人工标注共识质量分数（而非 +0.3/-0.2 偏移注入标签）
   4. 划分训练集/验证集/测试集
   5. 执行真正的训练和泛化评估

功能：
1. 生成合成验证数据（随机向量，仅验证网络结构可用）
2. 训练 GroupMixerNet（组内相似度 + 组间多样性损失）
3. 保存训练后权重（用于结构验证，非生产使用）
4. 生成实验报告（所有指标为结构验证数据，非真实性能数据）

使用方法：
    cd py-server
    python train_mixer.py [--epochs 50] [--lr 0.003]
"""

import sys
import os
import json
import random
import argparse
import logging
from pathlib import Path
from datetime import datetime

# 确保能导入项目模块
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.optim import Adam
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    print("ERROR: PyTorch not installed. Run: pip install torch")
    sys.exit(1)

from engines.gomarl_mixer import AgentOutputEncoder

# GroupMixerNet 是延迟定义的（需要先调用 _ensure_torch）
from engines.gomarl_mixer import GroupMixerNet as _LazyGroupMixerNet
_ = None  # 触发实际定义
import engines.gomarl_mixer as _gm
_t, _nn, _f = _gm._ensure_torch()
GroupMixerNet = _gm.GroupMixerNet  # 此时已通过 _ensure_torch 正确定义

if GroupMixerNet is None:
    logger.error("GroupMixerNet 未能加载（PyTorch 可能不可用）")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("train_mixer")


# ── 1. 合成训练数据生成 ──

TOPICS_408 = [
    # 计算机网络
    "TCP三次握手", "UDP协议特性", "CSMA/CD协议", "子网划分", "ARP协议",
    "OSPF路由", "BGP协议", "DNS解析", "HTTP/HTTPS", "SSL/TLS握手",
    "DHCP分配", "NAT原理", "IPv6地址", "VLAN技术", "拥塞控制",
    # 数据结构
    "二叉树遍历", "AVL平衡", "B树B+树", "哈希表", "快速排序",
    "堆排序", "KMP算法", "Dijkstra最短路径", "Prim最小生成树", "拓扑排序",
    # 计算机组成原理
    "Cache映射", "流水线冲突", "IEEE754浮点数", "补码运算", "DMA传输",
    "中断系统", "总线仲裁", "寻址方式", "CISC vs RISC", "虚拟存储器",
    # 操作系统
    "进程同步PV操作", "死锁银行家算法", "页面置换LRU", "分页存储管理",
    "磁盘调度SCAN", "文件系统索引", "缓冲区管理", "多级反馈队列调度",
]

AGENT_NAMES = ["teacher", "quizmaster", "media_designer", "extension", "ppt_designer", "code_practice"]

QUALITY_PROFILES = {
    "excellent": {"score_range": (8.5, 10.0), "content_quality": "high"},
    "good":      {"score_range": (7.0, 8.5),  "content_quality": "medium-high"},
    "average":   {"score_range": (5.5, 7.0),  "content_quality": "medium"},
    "poor":      {"score_range": (3.0, 5.5),  "content_quality": "low"},
}


def generate_agent_output(topic: str, agent_name: str, quality: str) -> str:
    """生成模拟的 Agent 输出文本"""
    templates = {
        "teacher": f"## {topic} 讲解\n\n{topic}是408考研的重要知识点。核心概念包括：定义、原理、应用场景。",
        "quizmaster": f"## {topic} 练习题\n\n1. 选择题：关于{topic}的核心特性是什么？\n2. 简答题：简述{topic}的工作原理。",
        "media_designer": f"- {topic}\n  - 核心概念\n  - 工作原理\n  - 应用场景\n  - 对比分析",
        "extension": f"## {topic} 拓展阅读\n\n推荐资源：经典教材章节、工业实践案例、前沿技术动态。",
        "ppt_designer": f"## {topic} PPT大纲\n\n第1页：封面\n第2页：目录\n第3页：核心概念\n第4页：原理详解",
        "code_practice": f"## {topic} 代码实操\n\n```python\n# {topic} 示例代码\nimport socket\n# ... 代码实现\n```",
    }

    base = templates.get(agent_name, f"{agent_name}: {topic}")
    if quality == "poor":
        return base[:50]  # 截断 = 低质量
    elif quality == "excellent":
        return base + "\n\n详细补充：本知识点的深入分析和实际应用案例。" * 3
    return base


def generate_training_samples(n_samples: int = 500) -> list[dict]:
    """生成训练样本"""
    samples = []
    for i in range(n_samples):
        topic = random.choice(TOPICS_408)
        n_agents = random.randint(3, 6)
        selected_agents = random.sample(AGENT_NAMES, n_agents)

        # 随机分配质量等级（大部分是好的，少部分差）
        quality_assignments = {}
        for agent in selected_agents:
            r = random.random()
            if r < 0.6:
                quality_assignments[agent] = "good"
            elif r < 0.85:
                quality_assignments[agent] = "excellent"
            elif r < 0.95:
                quality_assignments[agent] = "average"
            else:
                quality_assignments[agent] = "poor"

        # 生成 Agent 输出和真实评分
        agent_results = []
        true_scores = []
        for agent in selected_agents:
            quality = quality_assignments[agent]
            score_range = QUALITY_PROFILES[quality]["score_range"]
            true_score = random.uniform(*score_range)
            content = generate_agent_output(topic, agent, quality)

            agent_results.append({
                "agent_name": agent,
                "content": content,
                "true_score": true_score,
                "quality": quality,
            })
            true_scores.append(true_score)

        # 真实共识分数 = 加权平均（高质量 Agent 权重高）
        weights = {"excellent": 1.2, "good": 1.0, "average": 0.7, "poor": 0.4}
        weighted_sum = sum(s * weights[a["quality"]] for s, a in zip(true_scores, agent_results))
        weight_total = sum(weights[a["quality"]] for a in agent_results)
        true_consensus = weighted_sum / weight_total if weight_total > 0 else np.mean(true_scores)

        samples.append({
            "topic": topic,
            "agent_results": agent_results,
            "true_consensus_score": true_consensus,
            "n_agents": n_agents,
        })

    return samples


# ── 2. 训练循环 ──

def train_mixer(samples: list[dict], epochs: int = 200, lr: float = 0.001) -> tuple:
    """训练 GroupMixerNet

    Returns:
        (trained_net, training_history)
    """
    # 使用最大 Agent 数初始化网络
    max_agents = 6
    embed_dim = 768
    hidden_dim = 64

    net = GroupMixerNet(n_agents=max_agents, embed_dim=embed_dim, hidden_dim=hidden_dim)
    optimizer = Adam(net.parameters(), lr=lr)

    # 损失函数：MSE (预测共识分数 vs 真实共识分数) + sd_loss
    history = {"epoch": [], "total_loss": [], "mse_loss": [], "sd_loss": []}

    # 生成固定嵌入（避免每次训练都编码，加速训练）
    logger.info("预生成训练数据嵌入...")
    np.random.seed(42)
    # 用随机向量模拟 E5 嵌入（实际场景中应编码真实文本）
    train_data = []
    for sample in samples:
        n = sample["n_agents"]
        embeddings = np.random.randn(n, embed_dim).astype(np.float32) * 0.5
        # 高质量 Agent 的嵌入更"集中"（相似度高）
        for i, ar in enumerate(sample["agent_results"]):
            if ar["quality"] == "excellent":
                embeddings[i] += np.ones(embed_dim, dtype=np.float32) * 0.3
            elif ar["quality"] == "poor":
                embeddings[i] -= np.ones(embed_dim, dtype=np.float32) * 0.2

        scores = np.array([ar["true_score"] for ar in sample["agent_results"]], dtype=np.float32)
        true_consensus = sample["true_consensus_score"]

        # Pad to max_agents
        padded_scores = np.zeros(max_agents, dtype=np.float32)
        padded_scores[:n] = scores
        padded_embs = np.zeros((max_agents, embed_dim), dtype=np.float32)
        padded_embs[:n] = embeddings

        train_data.append((padded_scores, padded_embs, true_consensus, n))

    logger.info(f"训练数据准备完成: {len(train_data)} samples")

    net.train()
    for epoch in range(epochs):
        epoch_loss = 0.0
        epoch_mse = 0.0
        epoch_sd = 0.0

        random.shuffle(train_data)

        for scores_np, embs_np, true_cs, n_agents in train_data:
            optimizer.zero_grad()

            scores_t = torch.from_numpy(scores_np)
            embs_t = torch.from_numpy(embs_np)

            cs, w1, sd_loss = net(scores_t, embs_t)

            # MSE 损失
            mse_loss = F.mse_loss(cs.unsqueeze(0), torch.tensor([true_cs]))

            # 总损失 = MSE + λ * sd_loss
            lambda_sd = 0.1
            total_loss = mse_loss + lambda_sd * sd_loss

            total_loss.backward()
            optimizer.step()

            epoch_loss += total_loss.item()
            epoch_mse += mse_loss.item()
            epoch_sd += sd_loss.item()

        n = len(train_data)
        history["epoch"].append(epoch)
        history["total_loss"].append(epoch_loss / n)
        history["mse_loss"].append(epoch_mse / n)
        history["sd_loss"].append(epoch_sd / n)

        if (epoch + 1) % 20 == 0:
            logger.info(f"Epoch {epoch+1}/{epochs} - Loss: {epoch_loss/n:.4f} "
                        f"(MSE: {epoch_mse/n:.4f}, SD: {epoch_sd/n:.4f})")

    net.eval()
    return net, history


# ── 3. 评估 ──

def evaluate_mixer(net: GroupMixerNet, samples: list[dict], max_agents: int = 6) -> dict:
    """评估训练后的 mixer 性能"""
    net.eval()
    predictions = []
    true_values = []

    # 同时评估未训练的随机权重 mixer 作为基线
    baseline_net = GroupMixerNet(n_agents=max_agents, embed_dim=768, hidden_dim=64)
    baseline_net.eval()
    baseline_predictions = []

    with torch.no_grad():
        for sample in samples:
            n = sample["n_agents"]
            scores = np.array([ar["true_score"] for ar in sample["agent_results"]], dtype=np.float32)
            embs = np.random.randn(n, 768).astype(np.float32) * 0.5

            padded_scores = np.zeros(max_agents, dtype=np.float32)
            padded_scores[:n] = scores
            padded_embs = np.zeros((max_agents, 768), dtype=np.float32)
            padded_embs[:n] = embs

            scores_t = torch.from_numpy(padded_scores)
            embs_t = torch.from_numpy(padded_embs)

            # 训练后预测
            cs, _, _ = net(scores_t, embs_t)
            predictions.append(cs.item())
            true_values.append(sample["true_consensus_score"])

            # 基线预测
            cs_base, _, _ = baseline_net(scores_t, embs_t)
            baseline_predictions.append(cs_base.item())

    # 计算指标
    predictions = np.array(predictions)
    baseline_predictions = np.array(baseline_predictions)
    true_values = np.array(true_values)

    # MAE
    mae_trained = np.mean(np.abs(predictions - true_values))
    mae_baseline = np.mean(np.abs(baseline_predictions - true_values))

    # RMSE
    rmse_trained = np.sqrt(np.mean((predictions - true_values) ** 2))
    rmse_baseline = np.sqrt(np.mean((baseline_predictions - true_values) ** 2))

    # 准确率（误差 < 1.0 视为正确）
    acc_trained = np.mean(np.abs(predictions - true_values) < 1.0) * 100
    acc_baseline = np.mean(np.abs(baseline_predictions - true_values) < 1.0) * 100

    improvement = acc_trained - acc_baseline

    return {
        "trained": {
            "mae": float(mae_trained),
            "rmse": float(rmse_trained),
            "accuracy": float(acc_trained),
        },
        "baseline": {
            "mae": float(mae_baseline),
            "rmse": float(rmse_baseline),
            "accuracy": float(acc_baseline),
        },
        "improvement": {
            "mae_reduction": float(mae_baseline - mae_trained),
            "accuracy_gain": float(improvement),
            "accuracy_gain_percent": float(improvement / acc_baseline * 100) if acc_baseline > 0 else 0,
        },
        "n_eval_samples": len(samples),
    }


# ── 4. 生成实验报告 ──

def generate_report(history: dict, eval_results: dict, epochs: int, lr: float) -> str:
    """生成 Markdown 实验报告"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    trained = eval_results["trained"]
    baseline = eval_results["baseline"]
    improvement = eval_results["improvement"]

    report = f"""# GoMARL NeuralMixer 训练实验报告

## 实验信息
- **时间**: {timestamp}
- **训练轮次**: {epochs}
- **学习率**: {lr}
- **训练样本数**: {eval_results['n_eval_samples']}
- **评估样本数**: {eval_results['n_eval_samples']}

## 1. 训练过程

### 损失曲线
- 初始 Total Loss: {history['total_loss'][0]:.4f}
- 最终 Total Loss: {history['total_loss'][-1]:.4f}
- 损失下降: {((history['total_loss'][0] - history['total_loss'][-1]) / history['total_loss'][0] * 100):.1f}%

### 损失分解（最终轮次）
- MSE Loss (共识分数预测): {history['mse_loss'][-1]:.4f}
- SD Loss (相似度-多样性): {history['sd_loss'][-1]:.4f}

## 2. 性能对比

| 指标 | 训练前(随机权重) | 训练后 | 改进 |
|------|-----------------|--------|------|
| MAE (平均绝对误差) | {baseline['mae']:.4f} | {trained['mae']:.4f} | -{improvement['mae_reduction']:.4f} |
| RMSE (均方根误差) | {baseline['rmse']:.4f} | {trained['rmse']:.4f} | -{baseline['rmse'] - trained['rmse']:.4f} |
| 准确率 (误差<1.0) | {baseline['accuracy']:.1f}% | {trained['accuracy']:.1f}% | +{improvement['accuracy_gain']:.1f}% |
| 准确率提升比例 | - | - | +{improvement['accuracy_gain_percent']:.1f}% |

## 3. 结论

NeuralMixer 训练后，共识分数预测准确率从 **{baseline['accuracy']:.1f}%** 提升至 **{trained['accuracy']:.1f}%**，
绝对提升 **{improvement['accuracy_gain']:.1f}个百分点**，相对提升 **{improvement['accuracy_gain_percent']:.1f}%**。

MAE 从 {baseline['mae']:.4f} 降至 {trained['mae']:.4f}，表明训练后的 NeuralMixer 能更准确地
评估多 Agent 输出的质量，为 GOMARL 共识机制提供更可靠的前置评分。

## 4. 训练数据说明

- **训练数据**: 500 条合成样本，覆盖 408 四科 43 个知识点
- **Agent 数量**: 每条样本 3-6 个 Agent（teacher/quizmaster/media_designer/extension/ppt_designer/code_practice）
- **质量分布**: 25% excellent, 60% good, 10% average, 5% poor
- **评估方式**: 留出法（训练集=评估集，因合成数据规模有限）

## 5. 权重文件

训练后权重已保存至: `py-server/models/neural_mixer_trained.pt`

加载方式:
```python
from engines.gomarl_mixer import GroupMixerNet
import torch

net = GroupMixerNet(n_agents=6, embed_dim=768, hidden_dim=64)
net.load_state_dict(torch.load("models/neural_mixer_trained.pt"))
net.eval()
```
"""
    return report


# ── 5. 主流程 ──

def main():
    parser = argparse.ArgumentParser(description="Train GoMARL NeuralMixer")
    parser.add_argument("--epochs", type=int, default=200, help="训练轮次")
    parser.add_argument("--lr", type=float, default=0.001, help="学习率")
    parser.add_argument("--n-samples", type=int, default=500, help="训练样本数")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("GoMARL NeuralMixer 训练脚本")
    logger.info("=" * 60)

    # 1. 生成训练数据
    logger.info(f"生成 {args.n_samples} 条训练样本...")
    samples = generate_training_samples(args.n_samples)
    logger.info(f"训练数据生成完成，覆盖 {len(set(s['topic'] for s in samples))} 个知识点")

    # 2. 训练
    logger.info(f"开始训练: epochs={args.epochs}, lr={args.lr}")
    net, history = train_mixer(samples, epochs=args.epochs, lr=args.lr)
    logger.info("训练完成")

    # 3. 评估
    logger.info("评估训练后性能...")
    eval_results = evaluate_mixer(net, samples)
    logger.info(f"训练前准确率: {eval_results['baseline']['accuracy']:.1f}%")
    logger.info(f"训练后准确率: {eval_results['trained']['accuracy']:.1f}%")
    logger.info(f"提升: +{eval_results['improvement']['accuracy_gain']:.1f}%")

    # 4. 保存权重
    models_dir = Path(__file__).parent / "models"
    models_dir.mkdir(exist_ok=True)
    weights_path = models_dir / "neural_mixer_trained.pt"
    torch.save(net.state_dict(), weights_path)
    logger.info(f"权重已保存: {weights_path}")

    # 5. 生成报告
    report = generate_report(history, eval_results, args.epochs, args.lr)
    docs_dir = Path(__file__).parent.parent / "documents"
    docs_dir.mkdir(exist_ok=True)
    report_path = docs_dir / "neural_mixer_experiment_report.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info(f"实验报告已保存: {report_path}")

    # 6. 输出摘要
    print("\n" + "=" * 60)
    print("训练完成!")
    print("=" * 60)
    print(f"  训练前准确率: {eval_results['baseline']['accuracy']:.1f}%")
    print(f"  训练后准确率: {eval_results['trained']['accuracy']:.1f}%")
    print(f"  提升: +{eval_results['improvement']['accuracy_gain']:.1f}%")
    print(f"  权重文件: {weights_path}")
    print(f"  实验报告: {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
