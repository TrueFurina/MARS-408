#!/usr/bin/env python3
"""
NeuralMixer 真实训练脚本 — 用 E5 编码 seed data 训练 GroupMixerNet

与 train_mixer.py（随机噪声训练）不同，本脚本：
1. 从 seed_data 加载真实文本
2. 用本地 E5 模型编码为 768 维向量
3. 生成有意义的训练数据（同类知识点相似度高，异类相似度低）
4. 训练后保存权重 → 推理时加载

用法：
    cd py-server
    HUGGINGFACE_OFFLINE=1 python train_mixer_real.py --epochs 200
"""

import sys, os, json, argparse, logging, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

# ── 项目模块 ──
from seed_data import SEED_KNOWLEDGE_CHUNKS
from config import load_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger('train_mixer_real')

# ── 延迟加载 E5 + torch ──
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
    # _ensure_torch 已经通过 global 更新了模块级 GroupMixerNet
    import engines.gomarl_mixer as _gm
    if _gm.GroupMixerNet is None:
        raise RuntimeError('GroupMixerNet 未加载')
    return _torch, _nn, _F, _gm.GroupMixerNet

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--epochs', type=int, default=200)
    parser.add_argument('--lr', type=float, default=0.001)
    parser.add_argument('--hidden-dim', type=int, default=64)
    parser.add_argument('--n-agents', type=int, default=6)
    args = parser.parse_args()

    # 1. 加载 E5 + torch
    logger.info('正在加载 E5 模型...')
    e5 = _load_e5()
    torch, nn, F, GroupMixerNet = _load_torch_and_mixer()

    # 2. 从 seed data 构建训练样本
    # 按 subject 分组，同类作为"高质量 Agent 输出"，异类作为"低质量"
    by_subject = {}
    for c in SEED_KNOWLEDGE_CHUNKS:
        subj = c['metadata']['subject']
        text = c['content']
        if subj not in by_subject:
            by_subject[subj] = []
        by_subject[subj].append(text)

    subject_list = list(by_subject.keys())
    logger.info(f'共 {len(by_subject)} 个科目分组')

    # 编码所有文本
    logger.info('正在编码 seed data (E5)...')
    all_texts = []
    all_subjects = []
    for subj, texts in by_subject.items():
        for t in texts[:20]:  # 每科最多 20 条
            all_texts.append(f'passage: {t[:512]}')
            all_subjects.append(subj)

    if not all_texts:
        logger.error('seed_data 为空')
        return

    embeddings = e5.encode(all_texts, normalize_embeddings=True, show_progress_bar=True)
    logger.info(f'编码完成: {len(embeddings)} 条向量')

    # 构建训练数据：每组样本 = 6 个 Agent 的 (score, embedding, consensus)
    # 同类 Agent 相似度高 → 高共识分数；异类低 → 低共识分数
    train_data = []
    import hashlib
    for _ in range(500):
        n_agents = 6
        indices = random.sample(range(len(all_texts)), min(n_agents, len(all_texts)))
        if len(indices) < n_agents:
            # 填充
            while len(indices) < n_agents:
                indices.append(random.randrange(len(all_texts)))
            indices = indices[:n_agents]

        selected_embs = embeddings[indices]
        selected_subjs = [all_subjects[i] for i in indices]

        # 质量评分：同类高异类低
        scores = []
        for s in selected_subjs:
            same_count = sum(1 for t in selected_subjs if t == s)
            base = 5.0 + same_count * 0.8  # 同类越多分越高
            scores.append(min(10.0, base + random.uniform(-0.3, 0.3)))

        scores = np.array(scores, dtype=np.float32)

        # 真实共识分数 = 加权平均
        weights = np.array([1.0 + same_count * 0.15 for same_count in
                          [sum(1 for t in selected_subjs if t == s) for s in selected_subjs]])
        true_consensus = float(np.average(scores, weights=weights))

        train_data.append((scores, selected_embs, true_consensus))

    logger.info(f'训练数据: {len(train_data)} 条')

    # 3. 训练
    embed_dim = embeddings.shape[1]
    net = GroupMixerNet(n_agents=args.n_agents, embed_dim=embed_dim, hidden_dim=args.hidden_dim)
    optimizer = torch.optim.Adam(net.parameters(), lr=args.lr)

    logger.info(f'开始训练: epochs={args.epochs}, lr={args.lr}')
    for epoch in range(args.epochs):
        epoch_loss = 0.0
        random.shuffle(train_data)

        for scores_np, embs_np, true_cs in train_data:
            optimizer.zero_grad()
            scores_t = torch.from_numpy(scores_np)
            embs_t = torch.from_numpy(embs_np.astype(np.float32))

            cs, w1, sd_loss = net(scores_t, embs_t)
            mse = nn.functional.mse_loss(cs.unsqueeze(0), torch.tensor([true_cs]))
            total = mse + 0.1 * sd_loss
            total.backward()
            optimizer.step()
            epoch_loss += total.item()

        if (epoch + 1) % 20 == 0:
            logger.info(f'Epoch {epoch+1}/{args.epochs}: loss={epoch_loss/len(train_data):.4f}')

    net.eval()

    # 4. 保存（带时间戳，避免与现有权重文件锁冲突）
    from datetime import datetime
    _ts = datetime.now().strftime('%Y-%m-%d')
    weights_path = Path(__file__).parent / 'models' / f'neural_mixer_trained_{_ts}.pt'
    torch.save(net.state_dict(), str(weights_path))
    logger.info(f'权重已保存(时间戳): {weights_path} ({os.path.getsize(weights_path)//1024}KB)')
    # 同步覆盖默认权重（推理加载用）
    default_path = Path(__file__).parent / 'models' / 'neural_mixer_trained.pt'
    try:
        import shutil
        shutil.copy2(str(weights_path), str(default_path))
        logger.info(f'已同步覆盖默认权重: {default_path}')
    except Exception as _e:
        logger.warning(f'默认权重覆盖失败(非致命，权重仍保存于时间戳文件): {_e}')
    print('训练完成')

if __name__ == '__main__':
    main()
