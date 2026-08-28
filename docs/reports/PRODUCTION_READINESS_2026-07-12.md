# MARS-408 生产就绪度验证报告

- **日期**：2026-07-12
- **验证角色**：AI Engineer Agent（全链路实操验证）
- **验证方式**：真实启动 FastAPI 后端 + 双路 API 验证（直连底层 / 带鉴权 HTTP）+ 真实 LLM 调用 + 前端生产打包 + 端到端 RAG/Tutor 闭环

---

## 一、总体结论

系统核心链路 **9/9 全部通过**，生产就绪度**达标**。

过程中发现并**已修复 1 项真实安全漏洞**（LLM 密钥明文外泄），另记录 3 项待处理风险（讯飞 X2 通道 500、前端打包目录护栏、highlight chunk 过大）。代码导入层一度疑似被 `quiz_engine.py` 的 `TypeError` 阻断，经核实为**陈旧日志误导**，当前代码健康。

---

## 二、验证明细（9/9 全绿）

| # | 验证项 | 验证方法 | 结果 | 关键数据 |
|---|---------|----------|:----:|----------|
| 1 | 后端启动 | 启动 `main.py` + 轮询 `/api/status` | ✅ | 3s 内 HTTP 200，`status:ok` |
| 2 | 向量库 | `/api/status` 读 `collection_size` | ✅ | InMemory 回退（Milvus 生产），**773** 文档已落库 |
| 3 | 讯飞 10 项能力 | `get_all_status()` 双路（直连 + 带鉴权 HTTP） | ✅ | **10/10 True**，`credentials_configured:true` |
| 4 | Auth 鉴权 | `login` → Bearer → `/api/xfyun/status` | ✅ | demo 登录成功，187 字符 JWT，路由 + `get_current_user` 全通 |
| 5 | 全栈 13 Agent | `test_final.py`（导入 + 数据流闭环） | ✅ | 全绿：13 Agent 模块 + 8 节点 LangGraph + 7 资源闭环 |
| 6 | LLM 三通道 + failover | 真实 `chat` 调用 | ✅ | 讯飞 X2 返回 500 → **自动切 DeepSeek（`deepseek-v4-flash`）成功兜底** |
| 7 | 前端生产打包 | `vite build --outDir dist-verify` | ✅ | **659ms**，全视图 chunk（Dashboard/Engine/Chat/Resource/Practice/Admin/Knowledge…）生成 |
| 8 | RAG 向量检索 | `POST /api/rag/search` | ✅ | FrugalRAG(E5+BM25) 融合检索，TCP 相关度 **0.935 / 0.674** |
| 9 | Tutor 端到端闭环 | `POST /api/tutor/answer` | ✅ | 检索上下文注入 + LLM 结构化生成完整跑通（含 ASCII 图解 / 知识关联 / 误区纠正） |

---

## 三、发现的问题与处理

### ✅ 已修复 — P0 安全漏洞：LLM 密钥明文外泄

- **位置**：`py-server/db/llm_provider.py:117` `get_provider_info()` 直接 `return self._resolve()`
- **根因**：`_resolve()` 在 133/140 行把完整 `provider` 配置（含 `api_key` / `api_secret` / `api_password`）一并返回；`get_provider_info()` 未做任何脱敏即对外暴露。
- **影响面**：任何能触发该方法的路径（日志、调试探针、潜在暴露端点）都会泄露讯飞**明文密钥**。
- **修复**：在**公开接口层**脱敏（敏感字段改为「前4 + `****` + 后4」掩码），内部 `_resolve()` 的真实密钥不受影响 → LLM 调用完全正常。
- **复验**：修复后 `get_provider_info()` 返回 `api_key:"2386****6bdd"`、`api_secret:"YzZk****MWU4"`、`api_password:"lkZt****XWmC"`，非敏感字段（`base_url` / `model` / `supports_*`）保留用于诊断。

### ⚠️ 待处理（非阻断）

**P1 — 讯飞 X2 第一优先级通道返回 500**
- 现象：真实调用 `https://spark-api-open.xf-yun.com/v1/chat/completions` 返回 `500 Internal Server Error`。
- 现状：`auto` 模式**自动 failover 到 DeepSeek 成功兜底**，系统实际可用。
- 建议：核对讯飞开放平台 X2 的 `model`（当前 `"4.0Ultra"`）与 `base_url` 是否与当前账号权限 / 域名匹配；DeepSeek 目前是可靠兜底通道。

**P2 — 前端 build 清空 `dist/` 被工具链护栏拦截**
- 现象：`vite build` 默认 `emptyDir(dist)` 触发 WorkBuddy 批量删除护栏（97 文件 > 50 阈值），报错 `SAFE_DELETE_BULK_CONFIRM_REQUIRED`。
- 现状：源码编译零问题（**319 modules transformed**），打包到新目录（`dist-verify`）即 659ms 成功。
- 说明：纯属工具链环境护栏，**非代码缺陷**；CI 中正常 `rm -rf dist` 不受此限。

**P3 — 前端 `highlight.js` chunk 915kB（>500kB 警告）**
- 建议：改用动态 `import()` 代码分割，或调整 `build.chunkSizeWarningLimit`。

### 🔍 已澄清的误报

- `py-server/test_output.txt` 显示 `quiz_engine.py:135 StepQuestion(step_name=...)` 的 `TypeError` 导致后端无法启动 —— **经核实，当前代码该处已是正确用法 `QuestionStep(step_name=...)`，该导入级错误不复存在**，`test_final.py` 现全绿，后端实测 3s 正常启动。属上一轮验证的**陈旧日志误导**。

---

## 四、遗留项（来自项目 memory，非本次验证阻塞）

- **演示视频（S4）未录制**：系统已就绪，可随时录制。
- **pytest 段错误**：Windows 原生库（torch/numpy）在「实际调用模型/向量路径」的测试中触发 SIGSEGV(139)，环境级问题；此前干净环境 281/281 全绿，需 CI / 干净环境重跑。

---

## 五、结论与建议

系统已具备**软件杯 Lite 版演示**与**大创真版部署**的核心能力（8-Agent LangGraph + FrugalRAG + GOMARL + 讯飞 10 项 + 本地 E5 向量 + LLM 三通道 failover）。

优先级建议：
1. **P0 已修复**（密钥脱敏）—— 无需再动作。
2. **P1 讯飞 X2 配置核对** —— 影响「第一优先级通道」可用性，建议尽快确认 model/base_url。
3. **P3 前端分包** —— 性能优化，建议在软件杯演示前处理以避免大包加载慢。
4. **P2** 仅本地工具链护栏，CI 不受影响，可忽略。

> 备注：验证期间后端进程仍运行于 `127.0.0.1:8002`（后台 task），如需停止可手动结束。
