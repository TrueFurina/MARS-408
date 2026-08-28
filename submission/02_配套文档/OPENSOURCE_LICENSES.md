# MARS-408 开源协议合规标注

> 根据第十五届中国软件杯 A3 赛题要求：
> "若开发过程中使用开源项目、前沿 AI 工具/框架，需在提交文档的显著位置标注名称、来源及相关协议要求"
> "如若使用 AI Coding 工具，给出相关说明"

---

## 〇、科大讯飞工具使用声明（赛题硬性合规要求）

> 赛题要求："开发过程中使用的其他 AI 辅助工具，需选用科大讯飞相关工具。"

本项目深度集成科大讯飞开放平台能力，具体使用情况如下：

| 序号 | 讯飞工具名称 | 用途 | 协议要求 | 来源 |
|:----:|-------------|------|---------|------|
| 1 | **讯飞星火 X2（Spark-X2-Flash）** | 核心大语言模型（LLM 三通道**第一优先级**），文本生成、推理、资源产出 | 商业 API（按量计费，遵守讯飞开放平台服务协议） | https://www.xfyun.cn/doc/spark/Web.html |
| 2 | **TTI 图片生成** | 知识点→教学插图生成 | 商业 API | https://www.xfyun.cn/doc/ai-image-generation/api.html |
| 3 | **图片理解** | 多模态问答（学生上传图片提问） | 商业 API | https://www.xfyun.cn/doc/vision/image-understanding/API.html |
| 4 | **聚合搜索（万搜）** | RAG 联网检索增强 | 商业 API | https://www.xfyun.cn/doc/alisearch/api.html |
| 5 | **智能 PPT 生成** | 演示 PPT 一键生成 | 商业 API | https://www.xfyun.cn/doc/office/PPTGeneration/api.html |
| 6 | **数字人视频大模型** | 演示视频一键生成 | 商业 API | https://www.xfyun.cn/doc/digital-human/api.html |
| 7 | **文本纠错** | 辅导内容拼写/语法纠错 | 商业 API | https://www.xfyun.cn/doc/wordsCorrection/api.html |
| 8 | **公文校对** | 文档校对（不同引擎） | 商业 API | https://www.xfyun.cn/doc/officeProof/api.html |
| 9 | **文本合规** | 内容安全审核（防幻觉/违规检测） | 商业 API | https://www.xfyun.cn/doc/textModeration/api.html |
| 10 | **角色模拟** | 模拟面试官/导师多轮对话 | 商业 API | https://www.xfyun.cn/doc/conv/roleplay/api.html |
| 11 | **智能简历** | 生成可下载考研复试简历（Word） | 商业 API | https://www.xfyun.cn/doc/conv/resume/api.html |
| 12 | **TTS 语音合成（本地 MeloTTS，非讯飞）** | 视频脚本→语音旁白 | 本地开源 | https://github.com/myshell-ai/MeloTTS |

**合规说明**：以上讯飞工具均通过讯飞开放平台正规渠道接入，遵守讯飞开放平台服务协议。星火 X2 为赛题合规要求的 LLM 工具，已接入三通道 LLM 路由作为核心通道之一。

---

## 一、Python 后端依赖

| 项目 | 版本 | 用途 | 许可证 | 来源 |
|------|------|------|--------|------|
| **FastAPI** | ≥0.136 | Web 框架 | MIT | https://github.com/fastapi/fastapi |
| **Uvicorn** | ≥0.49 | ASGI 服务器 | BSD-3-Clause | https://github.com/encode/uvicorn |
| **Pydantic** | ≥2.0 | 数据验证 | MIT | https://github.com/pydantic/pydantic |
| **LangGraph** | ≥1.2 | 多智能体编排框架 | MIT | https://github.com/langchain-ai/langgraph |
| **LangChain-Core** | ≥1.4 | LLM 应用框架核心 | MIT | https://github.com/langchain-ai/langchain |
| **httpx** | ≥0.28 | HTTP 客户端 | BSD-3-Clause | https://github.com/encode/httpx |
| **sentence-transformers** | ≥3.0 | 文本嵌入模型 | Apache-2.0 | https://github.com/UKPLab/sentence-transformers |
| **pymilvus** | ≥2.4 | Milvus 向量数据库客户端 | Apache-2.0 | https://github.com/milvus-io/pymilvus |
| **redis** | ≥5.0 | Redis 客户端 | MIT | https://github.com/redis/redis-py |
| **psycopg2-binary** | ≥2.9 | PostgreSQL 客户端 | LGPL-3.0 | https://github.com/psycopg/psycopg2 |
| **numpy** | ≥2.4 | 数值计算 | BSD-3-Clause | https://github.com/numpy/numpy |
| **PyMuPDF (fitz)** | ≥1.27 | PDF 文本提取（仅离线使用） | AGPL-3.0 | https://github.com/pymupdf/PyMuPDF |
| **python-docx** | ≥1.2 | Word 文档生成 | MIT | https://github.com/python-openxml/python-docx |
| **python-pptx** | — | PPT 文本提取 | MIT | https://github.com/scanny/python-pptx |
| **matplotlib** | ≥3.11 | 数据可视化图表 | PSF-based | https://github.com/matplotlib/matplotlib |
| **sse-starlette** | ≥3.0 | SSE 流式输出 | BSD-3-Clause | https://github.com/sysid/sse-starlette |
| **pytest** | ≥8.0 | 测试框架 | MIT | https://github.com/pytest-dev/pytest |
| **pytest-asyncio** | ≥0.23 | 异步测试支持 | Apache-2.0 | https://github.com/pytest-dev/pytest-asyncio |
| **MCP** | ≥1.28 | Model Context Protocol 工具调用 | MIT | https://github.com/modelcontextprotocol/python-sdk |

## 二、前端依赖

| 项目 | 版本 | 用途 | 许可证 | 来源 |
|------|------|------|--------|------|
| **Vue 3** | ≥3.5 | 前端框架 | MIT | https://github.com/vuejs/core |
| **Vite** | ≥8.0 | 构建工具 | MIT | https://github.com/vitejs/vite |
| **Pinia** | ≥3.0 | 状态管理 | MIT | https://github.com/vuejs/pinia |
| **Vue Router** | ≥5.0 | 路由管理 | MIT | https://github.com/vuejs/router |
| **vue-tsc** | ≥3.2 | TypeScript 类型检查 | MIT | https://github.com/vuejs/language-tools |
| **@tanstack/vue-virtual** | ≥3.13 | 虚拟滚动 | MIT | https://github.com/TanStack/virtual |
| **marked** | ≥18.0 | Markdown 渲染 | MIT | https://github.com/markedjs/marked |
| **katex** | ≥0.16 | LaTeX 公式渲染 | MIT | https://github.com/KaTeX/KaTeX |
| **highlight.js** | ≥11.0 | 代码高亮 | BSD-3-Clause | https://github.com/highlightjs/highlight.js |
| **DOMPurify** | ≥3.4 | XSS 防护（HTML 消毒） | Apache-2.0/MPL-2.0 | https://github.com/cure53/DOMPurify |
| **lucide-vue-next** | ≥0.577 | 图标组件库 | ISC | https://github.com/lucide-icons/lucide |
| **@sigodenjs/marked-katex-extension** | ≥1.0 | marked 的 KaTeX 扩展 | MIT | https://github.com/sigoden/marked-katex-extension |

## 三、AI 模型与工具

| 项目 | 用途 | 许可证 | 来源 |
|------|------|--------|------|
| **intfloat/e5-base-v2** | 文本嵌入模型（768 维向量） | MIT | https://huggingface.co/intfloat/e5-base-v2 |
| **BAAI/bge-reranker-base** | Cross-encoder 检索重排序模型 | MIT | https://huggingface.co/BAAI/bge-reranker-base |
| **讯飞星火 X2 (Spark-X2-Flash)** | 大语言模型（LLM 三通道**第一优先级**）+ 多模态（见上方讯飞声明） | 商业 API | https://www.xfyun.cn |
| **DeepSeek (deepseek-chat)** | 大语言模型（LLM 三通道第二优先级，降级通道） | 商业 API | https://platform.deepseek.com |
| **Qwen2.5 (qwen2.5-7b-instruct)** | 大语言模型（LLM 三通道第三优先级，备用通道） | 商业 API | https://tongyi.aliyun.com |

## 四、开发工具

| 工具 | 用途 | 许可证 | 来源 |
|------|------|--------|------|
| **Node.js** | 前端运行环境 | MIT | https://nodejs.org |
| **Bun** | 前端包管理器/运行器 | MIT | https://bun.sh |
| **Python 3.12+** | 后端运行环境 | PSF | https://python.org |
| **Git** | 版本控制 | GPL-2.0 | https://git-scm.com |
| **FFmpeg** | 视频/音频处理（可选） | LGPL/GPL | https://ffmpeg.org |

## 五、AI Coding 工具使用说明

> 根据赛题要求："如若使用 AI Coding 工具，给出相关说明。"

本项目在开发过程中使用了 **Claude Code (Anthropic)** 和 **AtomCode (AtomGit)** 作为 AI 辅助编程工具，用于：

1. **代码生成与优化**：辅助生成标准化代码结构、数据模型定义、API 路由模板
2. **文档撰写**：辅助生成产品需求文档、技术方案文档、测试说明
3. **代码审查**：辅助进行代码质量检查、类型错误检测
4. **测试用例生成**：辅助生成单元测试和集成测试脚本

所有 AI 生成的代码均经过人工审查和测试验证，确保代码质量和安全性。

---

## 合规声明

本项目严格遵循所有使用的开源项目的许可证要求。各依赖的许可证信息见本文件上方表格，完整许可证文本请参阅各依赖的官方仓库（来源链接已标注）。

**特别声明**：
- **AGPL-3.0（PyMuPDF）**：仅用于离线 PDF 文本提取，不对外提供该服务，符合 AGPL 传染性条款豁免条件。
- **科大讯飞工具**：本项目使用讯飞星火 X2 及 10 项讯飞开放平台能力（详见第〇节），均通过正规渠道接入，遵守讯飞开放平台服务协议。

**最后更新**：2026-07-19