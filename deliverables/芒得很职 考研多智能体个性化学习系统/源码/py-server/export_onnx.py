#!/usr/bin/env python3
"""
NeuralMixer ONNX 导出脚本
将训练后的 GroupMixerNet PyTorch 模型导出为 ONNX 格式，
使推理时无需安装 PyTorch（仅需 ~50MB onnxruntime）。

使用方法：
    cd py-server
    python export_onnx.py [--weights models/neural_mixer_trained.pt] [--output models/neural_mixer.onnx]
"""

import sys
import os
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    print("❌ 需要 PyTorch 来导出 ONNX。请先安装: pip install torch")
    sys.exit(1)

try:
    import onnx
    import onnxruntime
    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False
    print("⚠️ 建议安装 onnx + onnxruntime 以验证导出: pip install onnx onnxruntime")

from engines.gomarl_mixer import _define_group_mixer_net


def export_onnx(weights_path: str, output_path: str, n_agents: int = 8, embed_dim: int = 384):
    """导出 GroupMixerNet 到 ONNX 格式"""
    print(f"📦 导出 ONNX 模型: n_agents={n_agents}, embed_dim={embed_dim}")
    print(f"   权重: {weights_path}")
    print(f"   输出: {output_path}")

    # 1. 创建模型
    GroupMixerNet = _define_group_mixer_net(torch, nn, torch.nn.functional)
    model = GroupMixerNet(n_agents=n_agents, embed_dim=embed_dim)
    model.eval()

    # 2. 加载训练权重（若存在）
    weights_file = Path(weights_path)
    if weights_file.exists():
        state_dict = torch.load(weights_file, map_location="cpu", weights_only=True)
        model_dict = model.state_dict()
        matched = {k: v for k, v in state_dict.items()
                   if k in model_dict and v.shape == model_dict[k].shape}
        if matched:
            model_dict.update(matched)
            model.load_state_dict(model_dict)
            print(f"   ✅ 加载权重: {len(matched)}/{len(model_dict)} 参数匹配")
        else:
            print("   ⚠️ 权重形状不匹配，使用随机权重")
    else:
        print("   ⚠️ 未找到权重文件，使用随机权重（仅验证结构）")

    # 3. 导出 ONNX（使用静态形状，GroupMixerNet 在实际运行中 n_agents 固定）
    dummy_scores = torch.randn(n_agents)
    dummy_embeddings = torch.randn(n_agents, embed_dim)

    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        model,
        (dummy_scores, dummy_embeddings),
        output_path,
        input_names=["agent_scores", "agent_embeddings"],
        output_names=["consensus_score", "group_weights", "sd_loss"],
        opset_version=17,
        dynamo=False,  # 使用传统导出器，避免 dynamo 的严格形状检查
    )

    # 4. 验证 ONNX 模型
    onnx_model = onnx.load(output_path)
    onnx.checker.check_model(onnx_model)
    print(f"   ✅ ONNX 模型验证通过")

    # 5. 测试 ONNX Runtime 推理
    if HAS_ONNX:
        session = onnxruntime.InferenceSession(output_path)
        test_scores = np.random.randn(n_agents).astype(np.float32)
        test_embeddings = np.random.randn(n_agents, embed_dim).astype(np.float32)
        outputs = session.run(None, {
            "agent_scores": test_scores,
            "agent_embeddings": test_embeddings,
        })
        print(f"   ✅ ONNX Runtime 推理测试通过")
        print(f"      输出: consensus_score={outputs[0]:.4f}, weights_shape={outputs[1].shape}")

    file_size = Path(output_path).stat().st_size
    print(f"   📏 文件大小: {file_size / 1024:.1f} KB ({file_size / 1024 / 1024:.2f} MB)")
    print(f"🚀 导出完成: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NeuralMixer ONNX Export")
    parser.add_argument("--weights", default="models/neural_mixer_trained.pt",
                        help="训练权重路径")
    parser.add_argument("--output", default="models/neural_mixer.onnx",
                        help="输出 ONNX 文件路径")
    parser.add_argument("--n-agents", type=int, default=8,
                        help="Agent 数量")
    parser.add_argument("--embed-dim", type=int, default=384,
                        help="嵌入向量维度")
    args = parser.parse_args()
    export_onnx(args.weights, args.output, args.n_agents, args.embed_dim)