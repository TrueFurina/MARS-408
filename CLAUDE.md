# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概要

**双分支 · 双身份**（同一技术底座服务两个项目）：
- **\main\ 分支 — MARS-408**：第十五届中国软件杯 A3 赛题参赛作品（出题企业：科大讯飞），基于 LangGraph 多智能体 + GOMARL 共识引擎 + FrugalRAG 检索的 408 考研个性化学习平台。国家级大创项目，结题中。
- **\career-literacy\ 分支 — 芒得很职**：新一代多智能体赋能的计算机类学生职业素养对抗实训平台，第十六届三创赛参赛作品。基于 ECD（证据中心设计）的大模型多智能体对话式软素养评估，所有新增代码使用 \career_*\ 前缀，零侵入 408 代码。

> 当前分支为 \career-literacy\，开发芒得很职。408 考研代码在 \main\ 分支，通过 \main → career-literacy\ 单向同步共享底座改进。芒得很职已完成 P0 后端（e5c6fb\）和 P1 学生端前端（ņ5f7b\），详见 \docs/职业素养对抗实训改造方案.md\。

技术栈：**FastAPI + LangGraph + PyTorch**（后端）· **Vue 3 + TypeScript + Pinia**（前端）· **Milvus / SQLite / Redis**（数据层）

## 常用命令

### 后端 (py-server/)

```bash
cd py-server
pip install -e .                           # 安装依赖
python main.py                              # 启动后端 (localhost:8002)

# 测试 — 注意：全量 pytest 会因 FastAPI 版本兼容问题全部报错。
# 必须使用功能级直接验证或分文件运行：
python -m pytest tests/test_wave_c_security.py -v --timeout=30    # 安全测试 (12 个)
python -m pytest tests/test_safety_redline.py -v --timeout=30     # 安全红线 (42 个)
python -m pytest -m "not system and not requires_milvus and not slow" --timeout=60 -q

# 功能验证（绕过 FastAPI Router 版本问题）：
python -c "
from shared.prompt_guard import sanitize_user_input
from engines.gomarl_conflict import ConsistencyChecker
# ... direct function tests
"
```

### 前端 (项目根目录)

```bash
npm run dev        # Vite 开发服务器 (5173, 代理 → 8002)
npm run build      # 生产构建 → dist/
npm run type-check # TypeScript 类型检查
npm run lint       # ESLint 检查
```

### Docker

```bash
docker-compose up -d                        # 开发模式（自动生成密钥 + demo 账号）
docker-compose --profile production up -d   # 生产模式（需 AUTH_SECRET + ADMIN_PASSWORD 环境变量）
```

## 核心架构

### 后端多智能体流水线（py-server/agents/）

LangGraph StateGraph，10 节点单向主流程 + 条件回环：

```
coordinator → diagnostician → planner → retriever
  → generator_cluster (7 并行子 Agent) → assessor → critic
  → evidence_check → quality_gate → path_planner → END

条件回环:
  retriever 结果空 → 回 planner
  critic/quality_gate 不通过 → 回 retriever 或 generator_cluster
  quality_gate REJECT → END（硬性阻断）
```

**关键设计决策**：
- `AgentState` 定义在 `agents/state.py`，TypedDict，所有节点共享读写
- `regenerate_round` 由对应节点**自增**，路由函数**只读不写**
- Quality Gate 是 **fail-open**（异常降级通过），教学场景优先保障内容交付
- 7 个 generator 子 Agent (`generator_cluster.py`) 并行生成：Teacher / QuizMaster / MindMap / Extension / CodePractice / PPT / VideoScript

### GOMARL 共识引擎（py-server/engines/gomarl*.py）

- LLM 评分 → 知识一致性校验 (E5) → 证据冲突消解 → NeuralMixer (PyTorch) → 动态权重 (EWMA)
- 当前 `algorithm.version = "lite"`（规则版），`"real"` 版通过 feature flag 灰度
- 冲突检测分三级：单 Agent 事实错误 (`_scan_factual`) → 跨 Agent 矛盾对 (`_scan_cross_agent`) → E5 语义分歧
- **重要**：`gomarl_conflict.py` 的句子分割包含逗号（防 "路由器在网络层，交换机在数据链路层" 误报），修改正则时务必保持此逻辑

### FrugalRAG 检索（py-server/engines/frugal_rag*.py）

- E5 向量 (768d) + BM25 混合检索，余弦阈值 0.65，BM25 权重 0.3
- 含 SFT 风格查询优化、GRPO 停止决策、ReAct 迭代（最多 3 轮）
- E5 嵌入缓存 (`db/embedder.py`): 内存上限 100k 条，磁盘上限 500k 条，文件锁防跨进程损坏

### 前端路由与状态（src/）

- **Pinia Store**: `studyStore.ts` 是核心（对话/画像/科目/评估），`authStore.ts`（认证），`skillStore.ts`（技能市场），`achievementStore.ts`（成就）
- **Vue Router**: 25+ 视图，`/chat`（对话学习）、`/dashboard`（仪表盘）、`/assessment`（评估）、`/knowledge-graph`（知识图谱）等
- **API 客户端**: `src/utils/api.ts` 统一封装，Token 存 localStorage key=`mars408_token`，请求头 `Authorization: Bearer`

### 数据层

- **Milvus** (向量库) → `db/milvus_client.py`，不可达时自动回退 InMemoryVectorStore。`.emb.npy` 二进制缓存加速冷启动
- **PostgreSQL** → `db/pg_client.py`，不可达时自动回退 SQLite (`data/pg_fallback.db`)
- **Redis** → `db/redis_client.py`，不可达时 fail-open（开发放行 / 生产配置 `REDIS_STRICT` 硬拒绝）
- **种子数据**: 1883 chunks + 200 题，启动时向量库为空才写入（幂等）

## 关键约束与约定

### ADR-007：导入队列单写者

`services/import_worker.py` 在进程内串行处理知识库导入。**硬约束：uvicorn 必须 `--workers 1`**，多进程会重新引入多写者 (last-writer-wins)。`main.py:250-255` 有启动期检查。

### LLM 通道优先级

讯飞星火 X2 为第一优先级（赛题合规），DeepSeek 为第二。**P0 不接 Qwen2.5**。`llm_provider.py` 提供运行级三通道回退（xfyun → deepseek），每通道限流类错误指数退避重试 3 次。

### 凭证管理（F-001）

- 所有密钥只能从 `.env` / 环境变量加载，`config.json` 的密钥字段由 `save_config()` 自动剥离
- `AUTH_SECRET` 生产环境缺失即 fail-fast 启动失败，开发环境自动生成随机密钥（重启失效）
- `ADMIN_PASSWORD` 生产模式必须设置且 ≥16 字符

### 安全中间件

`main.py` 按顺序注册：指标收集 → 安全响应头（CSP/HSTS/X-Frame-Options） → 请求体大小限制（默认 10MB） → SPA fallback。
- 生产 CSP: `script-src 'self'`，**但 `/showcase` 路径降级为开发 CSP**（评委展示原型 HTML 含内联脚本）
- 生产环境错误消息自动脱敏

### 数据库迁移 (D6)

`db/migrations/runner.py` — 幂等迁移框架，已应用版本记录在 `db/migrations/versions/applied.json`。迁移在 lifespan 阶段执行，失败不阻塞启动。

### 前端三条硬约束（2026-09-15 前端证据链 P0 确立）

1. **数据必须可溯源，禁止合成兜底。** 视图/组件展示的每个量化数字都必须来自后端真产物或真实接口。
   接口失败时**一律渲染空态**（`—` / 空态卡片），**不得回退到示例值、合成值、或"上次已知值"**。
   展示聚合数的页面必须同时展示 provenance（来源文件 / 产出时间 / 样本量 / 随机种子）。
   > 反面案例（已修复）：`BenchmarkView.vue` 曾把四组聚合数硬编码，注释却写"来自
   > `scripts/benchmark.py --demo` 的真实输出"——`--demo` 恰恰是**合成数据**模式。

2. **view 禁止裸 `fetch`。** 所有 HTTP 调用一律走 `src/utils/api.ts`（统一 baseURL、鉴权头、
   退避重试、友好错误）。组件层应进一步只通过 composable 取数，不在组件内直接 `api.*`。
   > 仍在整改中的裸 fetch 点：`CompareProfilesPanel` / `TeachingRulesPanel` 已于本次收敛为试点。

3. **缺失指标不许改口径硬凑，只能删或换。** 若后端真产物里不存在某个指标（例：原"矛盾检出数"），
   **不得用别的字段近似替代或沿用旧值**，必须移除该展示项，或换成真产物中确实存在的指标
   （例：改为准确率 + Cohen's κ），并在页面显式说明口径变更原因。

### 测试分层

- `unit` — 纯逻辑无网络
- `integration` — 真实 InMemoryVectorStore + 进程内 worker
- `e2e` — TestClient 全链路
- `system` — 真实 uvicorn 子进程
- `p0_regression` — 门禁必过
- `segv_env` — Windows 原生 torch 下 SIGSEGV 自动 skip

## 已知问题与环境陷阱

### FastAPI 版本兼容（历史环境陷阱）

pyproject.toml 声明 `fastapi>=0.136.3`；**当前 venv 实测安装 FastAPI 0.141.1**（2026-09-14 验证）。
早期环境曾安装 FastAPI 0.115.0，其 `Router.__init__` 不接受 `on_startup=...`，曾导致全量 pytest 报 `TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'`。
**这不是我们的代码问题**——项目代码中无 `on_startup` 用法，是某个测试 fixture 的依赖链触发。
**现状**：实测 0.141.1 的 `APIRouter.__init__` 已支持 `on_startup` 参数（`APIRouter(on_startup=[])` 可正常构造），该兼容问题预计已消除（尚未做全量回归确认）。
**绕过方式（如仍遇 Router 相关报错）**：用功能级直接验证替代 pytest，或单独运行不涉及 Router 的测试文件。

### 异步事件循环阻塞（6 处已知）

uvicorn `--workers 1` 下 sync 阻塞会串行化所有请求：
1. **E5 嵌入推理** (`api/agents.py`, `agents/evidence_check.py`) — 每次 100-500ms，最热路径
2. **MeloTTS 合成** (`services/tts_service.py`) — 每次数秒
3. **PDF 解析** (`api/knowledge_base.py`) — `api/knowledge.py` 已有正确的 `run_in_threadpool` 示范
4. **Redis 同步调用** (`frugal_rag.py`) — 换 `redis.asyncio` 可解
5. **Sandbox subprocess** — 已改为 `asyncio.create_subprocess_exec`（我们的修复）
6. **Python-pptx 构建** (`agents/ppt_builder.py`) — 100-300ms

修复模式：在 async 端点中调用同步重操作时包裹 `await asyncio.to_thread(...)` 或 `run_in_threadpool(...)`。

### Git Remote 与分支矩阵

本仓库已配置两个 remote：`origin`（GitHub `TrueFurina/MARS-408`）与 `mars408`（本地 `E:/Code/MARS-408` 副本）。分支矩阵：
- `main` — **MARS-408** 考研系统，已冻结（末次提交 `8065295`，2026-09-04），用于大创结题；
- `career-literacy` — **芒得很职** 三创赛作品，当前活跃开发分支（HEAD `90fd377`，2026-09-14），已跟踪 upstream `origin/career-literacy`。

两条分支共享底座，`main → career-literacy` 单向同步；`career-literacy` 的提交可 `git push origin career-literacy`。

## 并发会话提交纪律（多 AI 会话同仓协作必读）

本仓常有多个 AI 会话并发编辑（design-system / a11y / docs / 后端 / 物料线）。**提交前必须守住以下红线**，2026-09-15 已发生一次真实事故：

1. **提交前必 `git status` 筛查预暂存的 `D`/`M` 标记**：并发会话若跑过 `git add -A`，会把**它自己的删除/改动预存进 index**；你即便只 `git add` 自己的文件，这些预暂存项仍会被一并提交（曾把两个受跟踪 PNG 误删进提交）。正确做法：先 `git status --short` 看清暂存区全貌，确认没有别人的 `D` 才提交。
2. **只 add 自己的文件**：`git add <具体路径>`，禁止 `git add -A` / `git add .` / `git add -u`；提交前若发现 index 里有非自己的改动，先 `git restore --staged <路径>` 退出暂存，交还原 owner。
3. **`.workbuddy/` 已 gitignore**：协作记忆/技能勿入库。
4. **改动他人 WIP 文件前先确认归属**：`src/router/*`、`src/views/*` 多数处于并发会话未提交批次，勿裸改；新增独立文件（新 view / 新 composable / 新 api 路由）是零冲突的安全增量。
5. **每次提交后用 `git log -1 --stat` 复核落库内容**，确认没有混入他人改动、没有意外删除。

## 最近安全加固的约定（修改代码时务必遵守）

### Prompt Guard（`shared/prompt_guard.py`）

指令注入检测使用 **9 条注入模式**（`shared/prompt_guard.py:_INJECTION_PATTERNS`），并非单一正则：
```
# 动词门控类（instructions 后需紧跟越权动词，避免误伤正常提问）
ignore|disregard|forget|override ... (previous|prior|above) instructions
(new|updated) instructions: <ignore|disregard|you are|...|忽略|忘记|覆盖>
# 无动词类（按固定标记/锚点匹配，低误报，有意保留）
you are/will be now a/an   # 角色伪造
developer mode             # 越权请求
jail break                # 越权请求
(^|\n) system:            # 伪造系统提示（仅行首锚点，不误伤 "operating system:"）
```
动词门控规则避免误伤 "updated instructions: 请解释TCP" 等正常学术提问；无动词规则（developer mode / jail break / "you are now a" / 行首 `system:`）为**有意保留**的低误报标记，`system:` 用行首锚点规避 "operating system:" 等正常表述。

### GOMARL 冲突检测

`_split_sentences_local` 在**逗号处也切分**。修改正则规则时，用逗号分割的单句测试防止互补事实误报。

### 前端 XSS

所有动态 v-html 必须通过 `renderMarkdownSafe()` 或 `sanitizeSvg()`（均基于 DOMPurify）。SVG 图标 (`v-html="icons.xxx"`) 来自 `components/icons.ts` 信任常量。

### 认证与密码学

- `user_store.py`: PBKDF2 迭代次数 `600_000`，防时序枚举的 dummy hash **必须匹配相同迭代数**
- `auth.py`: `RegisterRequest.password` 后端 `min_length=8`，**前端 LoginView.vue 同步校验**

### 错误处理

禁止 `except Exception: pass` 无声吞错。至少加 `logger.debug/warning`。关键路径（向量搜索、RAG 检索、Agent 评分落库）必须 warning 级别。

## OS_course 借鉴特性

| 特性 | 位置 | 说明 |
|------|------|------|
| 追问指代识别 | `api/chat.py:45-54` | 检测 "那/这/它/呢" 短追问，自动拼接上一问 |
| 测验快照不可变 | `api/quiz.py:333-344` | 生成时快照到 `data/quiz_snapshots/` |
| 内容哈希去重 | `api/knowledge.py:159-172` | SHA256 去重防重复入库 |
| Skill regex 回退 | `agents/skill_agent.py:21-48` | `extract_params_regex()` LLM 不可用时提取参数 |
| 构件生命周期清理 | `main.py:259-281` | 每小时清理 >7 天旧 session 文件 |
