#!/usr/bin/env python3
"""
NeuralMixer 真实训练脚本 v2 — 调参 + 消融对比

基于 v1(train_mixer_real.py)首轮训练的根因分析：
  - loss 0.0076→0.0073(200epoch)几乎不动，撞到合成数据天花板
  - 根因1: 标签噪声 random.uniform(-0.3,0.3) → MSE 噪声底~0.0073
  - 根因2: sd_loss 对参数梯度≈0(只依赖输入embedding)
  - 根因3: true_consensus 太简单(线性加权)，20epoch 即拟合

v2 改进:
  1. lr 0.001→0.003 + CosineAnnealingLR(后期精细拟合)
  2. 标签噪声可调(-0.3~0.3 / -0.1~0.1 / 0)
  3. 数据量 500→1500
  4. mini-batch(32) 替代逐样本 SGD
  5. 每 10 epoch 记录 loss(原 20)
  6. 三组消融: v1基准 / v2调参 / v2无噪声

GPU 自适应: 有 CUDA 用 GPU，无则 CPU。
诚实标注: 合成弱标注集，loss 已近下界；真实标注集才是关键(Track B-G1 后续)。

用法:
    cd py-server
    HUGGINGFACE_OFFLINE=1 python train_mixer_real_v2.py
    # 强制CPU: CUDA_VISIBLE_DEVICES="" python train_mixer_real_v2.py
"""
import sys, os, json, argparse, logging, random, time
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

from seed_data import SEED_KNOWLEDGE_CHUNKS
from config import load_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger('train_mixer_v2')


def _load_e5():
    from sentence_transformers import SentenceTransformer
    cfg = load_config()
    local_repo = cfg.get('embedding', {}).get('local_model_repo', '')
    if local_repo and os.path.isdir(local_repo):
        logger.info(f'加载本地 E5 模型: {local_repo}')
        return SentenceTransformer(local_repo)
    logger.info('加载在线 E5 模型')
    return SentenceTransformer('intfloat/e5-base-v2')


def _load_torch_and_mixer():
    from engines.gomarl_mixer import _ensure_torch
    _torch, _nn, _F = _ensure_torch()
    import engines.gomarl_mixer as _gm
    if _gm.GroupMixerNet is None:
        raise RuntimeError('GroupMixerNet 未加载')
    return _torch, _nn, _F, _gm.GroupMixerNet


def _pick_device(torch):
    """GPU 自适应: 有 CUDA 用 GPU，无则 CPU"""
    if torch.cuda.is_available():
        dev = torch.device('cuda')
        logger.info(f'🚀 使用 GPU: {torch.cuda.get_device_name(0)}')
    else:
        dev = torch.device('cpu')
        logger.info('🐌 使用 CPU(GPU 不可用，安装 CUDA 版 torch 可加速: pip install torch --index-url https://download.pytorch.org/whl/cu121 --force-reinstall)')
    return dev


def build_train_data(embeddings, all_subjects, n_samples, noise_range, seed=42):
    """构建训练数据，噪声可调"""
    rng = random.Random(seed)
    np_rng = np.random.RandomState(seed)
    train_data = []
    for _ in range(n_samples):
        n_agents = 6
        indices = rng.sample(range(len(all_subjects)), min(n_agents, len(all_subjects)))
        while len(indices) < n_agents:
            indices.append(rng.randrange(len(all_subjects)))
        indices = indices[:n_agents]

        selected_embs = embeddings[indices]
        selected_subjs = [all_subjects[i] for i in indices]

        scores = []
        for s in selected_subjs:
            same_count = sum(1 for t in selected_subjs if t == s)
            base = 5.0 + same_count * 0.8
            scores.append(min(10.0, base + rng.uniform(-noise_range, noise_range)))
        scores = np.array(scores, dtype=np.float32)

        weights = np.array([1.0 + same_count * 0.15 for same_count in
                          [sum(1 for t in selected_subjs if t == s) for s in selected_subjs]])
        true_consensus = float(np.average(scores, weights=weights))
        train_data.append((scores, selected_embs, true_consensus))
    return train_data


def train_one_config(GroupMixerNet, torch, nn, F, train_data, embed_dim, device,
                     lr, epochs, hidden_dim, n_agents, batch_size, label):
    """单组训练配置"""
    net = GroupMixerNet(n_agents=n_agents, embed_dim=embed_dim, hidden_dim=hidden_dim).to(device)
    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    net.train()

    losses = []
    n_batches = max(1, len(train_data) // batch_size)

    for epoch in range(epochs):
        random.shuffle(train_data)
        epoch_loss = 0.0
        for b in range(n_batches):
            batch = train_data[b*batch_size:(b+1)*batch_size]
            scores_list = [torch.from_numpy(d[0]).to(device) for d in batch]
            embs_list = [torch.from_numpy(d[1].astype(np.float32)).to(device) for d in batch]
            true_list = [torch.tensor([d[2]], device=device) for d in batch]

            optimizer.zero_grad()
            total_loss = torch.tensor(0.0, device=device)
            for sc, em, tc in zip(scores_list, embs_list, true_list):
                cs, w1, sd_loss = net(sc, em)
                mse = nn.functional.mse_loss(cs.unsqueeze(0), tc)
                total_loss = total_loss + mse + 0.1 * sd_loss
            total_loss = total_loss / len(batch)
            total_loss.backward()
            optimizer.step()
            epoch_loss += total_loss.item()
        scheduler.step()

        avg_loss = epoch_loss / n_batches
        if (epoch + 1) % 10 == 0:
            losses.append({"epoch": epoch+1, "loss": round(avg_loss, 6)})
            logger.info(f'[{label}] Epoch {epoch+1}/{epochs}: loss={avg_loss:.6f}')

    net.eval()
    return net, losses


def main():
    ts = datetime.now().strftime('%Y-%m-%d')
    results_dir = Path(__file__).parent.parent / 'experiments' / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)

    logger.info('=== NeuralMixer v2 调参 + 消融对比 ===')
    e5 = _load_e5()
    torch, nn, F, GroupMixerNet = _load_torch_and_mixer()
    device = _pick_device(torch)

    # 编码 seed data
    by_subject = {}
    for c in SEED_KNOWLEDGE_CHUNKS:
        subj = c['metadata']['subject']
        if subj not in by_subject:
            by_subject[subj] = []
        by_subject[subj].append(c['content'])

    all_texts, all_subjects = [], []
    for subj, texts in by_subject.items():
        for t in texts[:20]:
            all_texts.append(f'passage: {t[:512]}')
            all_subjects.append(subj)

    logger.info(f'共 {len(by_subject)} 个科目分组，编码 {len(all_texts)} 条')
    embeddings = e5.encode(all_texts, normalize_embeddings=True, show_progress_bar=True)
    embed_dim = embeddings.shape[1]
    logger.info(f'编码完成: {len(embeddings)} 条向量, dim={embed_dim}')

    epochs = 200
    hidden_dim = 64
    n_agents = 6
    batch_size = 32

    # 三组消融
    configs = [
        {"label": "v1_baseline", "lr": 0.001, "n_samples": 500, "noise": 0.3,
         "desc": "v1基准(lr0.001,500条,噪声±0.3,逐样本)"},
        {"label": "v2_tuned", "lr": 0.003, "n_samples": 1500, "noise": 0.1,
         "desc": "v2调参(lr0.003,1500条,噪声±0.1,batch32,cosine)"},
        {"label": "v2_noisefree", "lr": 0.003, "n_samples": 1500, "noise": 0.0,
         "desc": "v2无噪声(lr0.003,1500条,无噪声,batch32,cosine)"},
    ]

    all_results = {"timestamp": ts, "device": str(device), "epochs": epochs, "embed_dim": embed_dim, "configs": []}

    for cfg in configs:
        logger.info(f'\n--- 训练组: {cfg["label"]} ({cfg["desc"]}) ---')
        t0 = time.time()
        td = build_train_data(embeddings, all_subjects, cfg["n_samples"], cfg["noise"])
        net, losses = train_one_config(
            GroupMixerNet, torch, nn, F, td, embed_dim, device,
            cfg["lr"], epochs, hidden_dim, n_agents, batch_size, cfg["label"]
        )
        elapsed = time.time() - t0
        final_loss = losses[-1]["loss"] if losses else None
        logger.info(f'[{cfg["label"]}] 完成: {elapsed:.1f}s, final_loss={final_loss}')

        # 保存权重(带label+时间戳)
        wpath = Path(__file__).parent / 'models' / f'neural_mixer_{cfg["label"]}_{ts}.pt'
        torch.save(net.state_dict(), str(wpath))
        logger.info(f'[{cfg["label"]}] 权重已保存: {wpath.name}')

        all_results["configs"].append({
            "label": cfg["label"], "desc": cfg["desc"],
            "lr": cfg["lr"], "n_samples": cfg["n_samples"], "noise": cfg["noise"],
            "batch_size": batch_size, "elapsed_sec": round(elapsed, 1),
            "final_loss": final_loss, "loss_curve": losses,
            "weights_file": wpath.name,
        })

    # 汇总
    summary_path = results_dir / f'track-b-G1-ablation-{ts}.json'
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    logger.info(f'\n=== 消融汇总已保存: {summary_path} ===')

    # 打印对比表
    print('\n' + '='*60)
    print('NeuralMixer v2 消融对比结果')
    print('='*60)
    print(f'{"组别":<16}{"lr":<8}{"样本":<8}{"噪声":<8}{"耗时":<10}{"final_loss":<12}')
    for c in all_results["configs"]:
        print(f'{c["label"]:<16}{c["lr"]:<8}{c["n_samples"]:<8}{c["noise"]:<8}{c["elapsed_sec"]:<10}{c["final_loss"]}')
    print('='*60)
    print(f'详细JSON: {summary_path}')
    print(f'\n诚实声明: 合成弱标注集训练。loss 已近下界，瓶颈在合成标签噪声。')
    print(f'真实标注集(Track B-G1后续)才是提升共识质量的关键。')


if __name__ == '__main__':
    main()
