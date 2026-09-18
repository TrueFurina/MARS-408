#!/usr/bin/env python3
"""调用讯飞智能 PPT API 生成软件杯演示 PPT

用法:
    cd py-server
    python tools/generate_xfyun_ppt.py
"""

import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.xfyun_services import generate_ppt


async def main():
    print("🚀 正在调用讯飞智能 PPT API 生成演示 PPT...")
    print("   (每次生成消耗 10 点额度，AI 配图另计)")
    print()

    # 生成软件杯演示 PPT
    result = await generate_ppt(
        query="MARS-408 基于GOMARL与FrugalRAG的408考研个性化学习多智能体系统\n\n"
               "系统架构：10节点LangGraph多智能体流水线，包含coordinator/diagnostician/planner/"
               "retriever/generator_cluster/assessor/critic/path_planner\n\n"
               "核心技术：1.GOMARL共识引擎 - 加权投票+一致性校验+NeuralMixer神经网络\n"
               "2.FrugalRAG检索 - E5向量+BM25+个性化重排+Cross-encoder精排\n"
               "3.Neural GroupMixer - PyTorch神经网络动态权重融合\n"
               "4.7种资源并行生成 - 讲解文档/练习题/思维导图/拓展阅读/代码实操/PPT大纲/视频脚本\n\n"
               "覆盖科目：计算机网络(50知识点)/数据结构(16)/计算机组成原理(10)/操作系统(10)\n\n"
               "技术栈：Vue 3 + TypeScript / FastAPI + LangGraph / PyTorch / Milvus",
        is_figure=True,
        ai_image="normal",
        search=True,
    )

    if result.success:
        print(f"✅ PPT 生成成功!")
        print(f"   标题: {result.title}")
        print(f"   下载: {result.ppt_url}")
        print(f"   SID: {result.sid}")
    else:
        print(f"❌ PPT 生成失败: {result.error}")


if __name__ == "__main__":
    asyncio.run(main())