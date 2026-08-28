#!/usr/bin/env python3
"""调用讯飞数字人视频 API 生成软件杯演示讲解视频

用法:
    cd py-server
    python tools/generate_demo_video.py
"""

import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.xfyun_services import generate_video


async def main():
    print("🚀 正在调用讯飞数字人视频 API 生成演示讲解视频...")
    print("   (每次生成消耗一定额度，控制台剩余约 300 秒)")
    print()

    result = await generate_video(
        prompt="今天为大家演示 MARS-408 基于 GOMARL 与 FrugalRAG 的 408 考研个性化学习多智能体系统。"
               "本系统采用 10 节点 LangGraph 多智能体流水线架构，包含全局协调、学情诊断、任务规划、"
               "检索优化、资源生成集群、评估反馈、质量校验和路径规划八大智能体。"
               "核心创新在于 GOMARL 共识引擎，通过 NeuralMixer 神经网络对多个 Agent 的输出进行"
               "质量评分和动态权重融合，确保输出内容的准确性和个性化适配。"
               "FrugalRAG 检索引擎采用 E5 向量加 BM25 混合检索策略，结合学生画像实现个性化重排。"
               "系统可并行生成 7 种学习资源，包括讲解文档、练习题、思维导图、拓展阅读、"
               "代码实操案例、PPT 大纲和视频脚本。"
               "覆盖计算机网络、数据结构、计算机组成原理和操作系统四门 408 考研科目。"
               "整个系统经过全面安全审计，281 个测试全部通过，已具备上线条件。",
        word_count=180,
    )

    if result.success:
        print(f"✅ 视频生成成功!")
        print(f"   视频地址: {result.video_url}")
        if result.audio_url:
            print(f"   音频地址: {result.audio_url}")
        print(f"   Task ID: {result.task_id}")
    else:
        print(f"❌ 视频生成失败: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())