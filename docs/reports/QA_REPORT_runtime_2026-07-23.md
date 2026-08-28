# 功能与运行期 QA 质检报告 — MARS-408

- **质检人**：严过关（Yan），QA 工程师
- **维度**：功能与运行期 QA（仅检查与报告，未改动任何源码）
- **日期**：2026-07-23
- **后端**：FastAPI @ `127.0.0.1:8002`，serve `dist/`（SPA fallback）
- **结论**：系统**可直接演示**（YES，前提见文末）

---

## 1. 后端就绪
- 探测时后端**已在运行**：`GET /health` 立即返回 **HTTP 200**，**无需重启/拉起**。
- 启动耗时：0（服务本来就在线）。
- ⚠️ 注意：`/health` 返回的是 **SPA 的 index.html（HTML）**，并非 JSON 健康对象。根因：`py-server/main.py` 的 `spa_fallback` 中间件会捕获所有未命中路由的 GET 404/307 请求并返回 `index.html`，而项目**没有定义专门的 `/health` JSON 路由**（grep 仅见 `llm_health_router` 等 `/api/...` 路由）。对"演示就绪"无阻断，但对监控/探活是盲区（详见 §9 P2-1）。

## 2. 页面可达性（8 个关键页面）

| 页面 | HTTP | 引用 hash | id=app | 结论 |
|------|------|-----------|--------|------|
| `/` | 200 | index-0O9gFRNI.js | 1 | PASS |
| `/showcase` | 200 | index-0O9gFRNI.js | 1 | PASS |
| `/knowledge-base` | 200 | index-0O9gFRNI.js | 1 | PASS |
| `/practice` | 200 | index-0O9gFRNI.js | 1 | PASS |
| `/review` | 200 | index-0O9gFRNI.js | 1 | PASS |
| `/assessment` | 200 | index-0O9gFRNI.js | 1 | PASS |
| `/chat` | 200 | index-0O9gFRNI.js | 1 | PASS |
| `/dashboard` | 200 | index-0O9gFRNI.js | 1 | PASS |

8/8 全部 200，引用**最新 hash `index-0O9gFRNI.js`**（与任务给定一致），均含 `<div id="app">`。

## 3. 核心 API（带 demo token，10 个）

| 接口 | HTTP | 关键返回字段 | 结论 |
|------|------|--------------|------|
| `/api/auth/me` | 200 | id, username, display_name, role, created_at | PASS |
| `/api/quiz/history` | 200 | total=31, correct, accuracy, records | PASS |
| `/api/knowledge-graph` | 200 | nodes, edges | PASS |
| `/api/engine/status` | 200 | status, modules, torch_available… | PASS |
| `/api/xfyun/status` | 200 | credentials_configured, services | PASS |
| `/api/subjects` | 200 | subjects, knowledge_graph | PASS |
| `/api/user/stats` | 200 | studyTime, questionsDone, mastery, streak | PASS |
| `/api/review/summary` | 200 | by_subject_len=16, weak_topics, wrong_questions | PASS |
| `/api/knowledge-base/textbooks` | 200 | **total=0**, textbooks_len=0 | PASS（见 Bug2） |
| `/api/rag/status` | 200 | total_docs, by_subject, embedding_model | PASS |

10/10 全部 200，字段结构符合预期。

## 4. 聊天端到端（演示命脉）
- 登录 → `/api/chat/send`（venv python urllib），message=`用一句话解释TCP三次握手为什么不是两次`，subject=`network`。
- 结果：**HTTP 200**，返回真实 LLM 答案（讯飞 X2 主 / DeepSeek 兜底）。
- 答案长度：实体内容约 180 字（>20 字，满足"有实质答案"）。
- 示例：`{"response":"TCP三次握手不是两次，因为两次握手无法防止客户端已失效的连接请求（如网络延迟导致的重传请求）误传到服务器……只有通过第三次握手，客户端确认收到服务器的SYN-ACK后，服务器才能确认客户端确实在主动发起连接……"}`
- 结论：**PASS**。

## 5. 四历史 Bug 回归

- **Bug1 /showcase：PASS**
  - `/showcase` 返回 200 + Vue SPA（`id="app"`），不再是 307/404。
  - 11 个 `/showcase/*.html` 静态文件**全部 200**（含 `index.html`、`MARS-408_dachuang_deck.html`、`MARS-408_dashboard.html`、`netlearn-architecture.html` 等）。
  - `py-server/main.py:601` 的 `spa_fallback` 仍含 `if response.status_code in (307, 404) and request.method == "GET" ...`（第 596–606 行），且明确排除 `/showcase/` 前缀以让 StaticFiles 直出静态文件。兜底逻辑完好。

- **Bug2 /knowledge-base：PASS（7-22 改动未破坏兜底）**
  - `src/data/seedTextbooks.ts` 仍导出 `SEED_TEXTBOOK_LIST`（L214）、`getSeedTextbook`（L224）、`isSeedTextbook`（L229）。
  - `src/views/KnowledgeBaseView.vue`（7-22 改过）仍：
    - `import { SEED_TEXTBOOK_LIST, getSeedTextbook, isSeedTextbook }`（L6）；
    - 初始 `textbooks = ref(SEED_TEXTBOOK_LIST)`（L9）；
    - `onMounted` 仅在 `list.length > 0` 时才覆盖（L31–33），否则保留种子兜底；
    - `loadTextbook` 用 `isSeedTextbook`/`getSeedTextbook` 走本地种子（L57–61），`doSearch` 后端无结果时回退 `searchSeedTextbooks()`（L76–84）。
  - 实测 `/api/knowledge-base/textbooks` 返回 **total=0 / textbooks_len=0** → 后端确无 PDF，前端正确以 `SEED_TEXTBOOK_LIST` 兜底展示。7-22 改动**未破坏**种子逻辑。

- **Bug3 /review 科目统计：PASS**
  - `src/views/ReviewView.vue` `byCourse` computed 仍存活（L20–55），将后端章节级 `by_subject`（实测 16 项）按 `SUBJECT_TO_COURSE`→`COURSE_MAP` 聚合为 **408 四科中文名**（数据结构 `subject / subject_name / total / wrong / accuracy`）。
  - 模板仍用 `byCourse`（L97 `v-if="byCourse.length"`、L99 `v-for="s in byCourse"`，点击进入对应练习）。聚合逻辑与渲染绑定完好。

- **Bug4 /practice 图标乱飞：PASS**
  - `.empty-quiz-icon` CSS 尺寸约束仍在（L363–369：`width:64px; height:64px; margin:0 auto 12px; opacity:0.3`）+ `:deep(svg){width:100%;height:100%}`（L370–373）。
  - `<template v-if>` 与 `v-for` 已分离：空态 `<div v-else-if="...questions.length === 0...">` 内 `<div class="empty-quiz-icon" v-html="icons.quiz">`（L216–220），题目列表 `<div v-else-if="questions.length > 0" class="quiz-list">` 内 `v-for`（L223–224），二者在不同元素上，无单元素同用 v-if+v-for。

## 6. 懒加载 chunk 白屏风险
- `dist/assets/` 共 **1359** 个资源文件，逐个（线程化 urllib HEAD）探测：
  - **TOTAL_ASSETS = 1359，NON200 = 0**。
- 全部 200，**无 404 缺失 chunk** → 点击进任意懒加载页面**无白屏风险**。

## 7. 构建健康
- 命令：`cd E:/Program/MARL/study-help-pro && npx vite build`
- 结果：**成功**，`✓ built in 7.72s`，**无 error、无 warning**。
- 产出入口 hash：**`index-0O9gFRNI.js`**（与线上部署 hash 完全一致 → 构建可复现、源码与产物一致）。
- 类型检查：`npx vue-tsc --build` 与 `npx vue-tsc --build --force`（强制全量）均 **EXIT=0，0 个类型错误**。
  - 任务提到的 `ChatView.vue:160` 预存 TS2322 **当前已不存在**：现 L160 为 `s.content!.replace(...)`（非空断言，类型安全），`useVirtualizer` 配 `computed(...)` 在 `@tanstack/vue-virtual@3.13.29` 下被正常接受。该历史类型错误已被修复/不复现。
- 注：`vite build` 会清空 `dist/` 后重建；`public/showcase/`（11 个 HTML）会被拷贝回 `dist/showcase/`，已复测仍 200（见 §5 Bug1 与下方复验）。

## 8. 安全抽查（点到为止）
- `POST /api/admin/users`：
  - 携带 student token（demo）→ **HTTP 403**（正确拒绝非 admin）。
  - 无 token → **HTTP 401**（正确拒绝未认证）。
  - 管理接口鉴权有效。
- 限流：在 `main.py` 仅发现 `CORSMiddleware` + `GZipMiddleware`（L350/353），**未发现 slowapi/Limiter 等应用级限流中间件**。LLM 类接口（如 `/api/chat/send`）目前未做单用户限流（主动压测限流非强测项，仅作观察，见 §9 P2-2）。

## 9. 问题清单（按严重度）

### P0（演示阻断）
- **无**。所有关键页面、核心 API、端到端聊天、历史 Bug 回归、懒加载 chunk、构建与类型检查均通过。

### P1（明显瑕疵）
- **无阻断性瑕疵**。

### P2（minor / 观察项，不阻断演示）
- **P2-1 `/health` 非真实健康端点**（文件：`py-server/main.py:592-606` spa_fallback）
  - 现象：`GET /health` 返回 200 但内容为 SPA `index.html`，无 JSON 健康对象；根因是 SPA fallback 兜底了所有未知 GET 路由，且项目无专门 `/health` 路由。
  - 建议：若需自动化探活/监控，新增一个返回 JSON 的 `/health` 或 `/api/health`（与 SPA fallback 区分），避免"任何 404 都返回 200+HTML"掩盖后端异常。
- **P2-2 LLM 接口缺少应用级限流**（文件：`py-server/main.py:31,350,353`）
  - 现象：仅 CORS + GZip 中间件，无 slowapi/Limiter；`/api/chat/send` 等未做单用户频率限制。
  - 建议：公开展示前对 LLM/聊天类接口加 per-user 限流，防滥用/误刷导致配额或费用风险（任务标注为可选，仅观察）。
- **P2-3 后端知识库/向量库为空（设计如此，需确认）**（接口：`/api/knowledge-base/textbooks`、`/api/rag/status`）
  - 现象：textbooks `total=0`、rag `total_docs=0`；演示完全依赖前端 `SEED_TEXTBOOK_LIST` 种子兜底，真实 PDF/RAG 检索路径未填充。
  - 建议：与产品/主理人确认省赛演示是否只需种子教材即可；若需展示"真实 PDF 问答/RAG 检索"，至少 ingest 1 本教材后再演示。当前不影响页面可达性与展示。

## 总体结论
- **系统可否直接演示：YES**
- **前提**：
  1. 后端已在 `127.0.0.1:8002` 运行（本次探测时即在线；若重启需约 30s 加载向量库 + E5 嵌入）。
  2. 登录账号 `demo / demo123456` 可用，Bearer token 正常下发。
  3. 当前 `dist/` 入口为 `index-0O9gFRNI.js`（构建可复现，已验证 1359 个资源全 200）。
- **说明**：8 页面全 200、10 核心 API 全 200、端到端聊天真实 LLM 200、4 个历史 Bug 全部未回归、懒加载无缺失、构建与类型检查全绿。仅余 3 个 P2 观察项（探活端点、限流、知识库空），均不阻断演示，建议主理人按 §9 评估是否纳入赛前收尾。
