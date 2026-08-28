#!/usr/bin/env python3
"""
验证生产路径 NeuralGroupMixer.mix() 加载的是真实训练权重（而非随机初始化）。

调用链：neural_mixer.mix() → _init_mixer() → _probe_trained_embed_dim() +
       _load_trained_weights() → GroupMixerNet(embed_dim=768)

打印：探测到的 embed_dim / 创建的网络 shape / 权重命中数 / 推理输出
"""
import os
import sys
import asyncio
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


async def main():
    from engines.gomarl_mixer import neural_mixer, _ensure_torch

    torch, _, _ = _ensure_torch()

    # ── 1. 探测训练权重 embed_dim（独立验证）──
    probed = neural_mixer._probe_trained_embed_dim()
    print(f"[1] 训练权重探测 embed_dim = {probed}")

    # ── 2. 调用 mix() 走完整生产路径（会触发 _init_mixer）──
    agent_results = [
        {"agent_name": "teacher",        "content": "TCP三次握手：SYN, SYN-ACK, ACK", "score": 8.5},
        {"agent_name": "quizmaster",     "content": "TCP握手过程的考察重点",          "score": 7.2},
        {"agent_name": "media_designer", "content": "TCP握手状态转换图",              "score": 6.8},
        {"agent_name": "extension",      "content": "TCP与UDP握手对比",               "score": 7.9},
        {"agent_name": "ppt_designer",   "content": "TCP握手要点总结",                "score": 8.1},
        {"agent_name": "code_practice",  "content": "socket实现TCP握手代码",          "score": 6.5},
    ]
    student_profile = {"level": "intermediate", "weak_subjects": ["computer_network"]}
    result = await neural_mixer.mix(agent_results, student_profile, topic="TCP三次握手")

    # ── 3. 检查 _mixer_net 状态 ──
    net = neural_mixer._mixer_net
    print(f"[2] _mixer_net 已初始化: {net is not None}")
    if net is not None:
        print(f"    n_agents       = {net.n_agents}")
        print(f"    embed_dim      = {net.embed_dim}  (应为 768)")
        print(f"    hidden_dim     = {net.hidden_dim}")
        # 检查 hyper_w1 第一层权重 shape
        w = net.hyper_w1[0][0].weight
        print(f"    hyper_w1[0][0].weight shape = {tuple(w.shape)}  (应为 (64, 768))")

    # ── 4. 重新加载权重统计命中数 ──
    matched, total = neural_mixer._load_trained_weights()
    print(f"[3] 权重命中: {matched}/{total}  (应 48/48)")

    # ── 5. mix() 返回结果 ──
    print(f"[4] mix() neural_used = {result.get('neural_used')}")
    print(f"    consensus_score   = {result.get('consensus_score'):.4f}")
    print(f"    agent_count       = {result.get('agent_count')}")
    print(f"    groups            = {result.get('groups')}")

    # ── 6. 判定 ──
    ok = (net is not None and net.embed_dim == 768
          and matched == total and result.get("neural_used") is True)
    print(f"\n[判定] 生产路径加载真实训练权重: {'✅ 通过' if ok else '❌ 失败'}")


if __name__ == "__main__":
    asyncio.run(main())
