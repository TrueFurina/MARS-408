# 开源与第三方依赖许可证清单（NetLearn / MARS-408）

> 软件杯 A3 赛题要求：使用开源项目、前沿 AI 工具/框架，须在提交文档显著位置标注名称、来源及相关协议。
> 本文件为清单索引；各依赖的实际 LICENSE 文本副本见同目录 `docs/licenses/` 下对应子目录/文件。

| 依赖 | 版本 | 许可证 | 来源 | 副本 |
|------|------|--------|------|------|
| FastAPI | 0.136.3 | MIT | https://github.com/fastapi/fastapi | `fastapi-licenses/` |
| LangGraph | 1.2.7 | MIT | https://github.com/langchain-ai/langgraph | `langgraph-licenses/` |
| LangChain（langchain-core） | 1.4.8 | MIT | https://github.com/langchain-ai/langchain | 见官方仓库（dist-info 未单列 LICENSE 文件） |
| PyTorch（torch） | 2.7.1+cpu | BSD-3-Clause | https://github.com/pytorch/pytorch | `torch-LICENSE` + `torch-LICENSES/` |
| Transformers | 5.10.4 | Apache-2.0 | https://github.com/huggingface/transformers | `transformers-licenses/` |
| NumPy | 2.5.0 | BSD-3-Clause | https://github.com/numpy/numpy | `numpy-licenses/` |
| Vue | 3.x | MIT | https://github.com/vuejs/core | `vue-LICENSE` |
| 科大讯飞开放平台（星火 X2 / 万搜 / TTI 等 10 项能力） | — | 商用授权（开放平台协议） | https://www.xfyun.cn/ | 云服务 API（REST），无独立 SDK 包 |

## AI Coding 工具说明
- 本项目开发过程使用 AI 辅助编程工具（WorkBuddy / Claude Code 类工具）进行代码生成、审查与文档编写。
- 自研核心算法（团队著作权所有）：FrugalRAG 节俭检索、改进 GOMARL 共识（NeuralMixer + 证据冲突消解）、Agent 辩论协议、KG-DAG 拓扑路径规划。

## 自研模块许可
- NetLearn 团队自主开发部分的软件作品著作权归参赛团队所有；具有市场应用及拓展的优秀作品，出题企业具有优先权（可优先合作开发或优先购买）。
