# MARS-408 后端 (py-server)

FastAPI 后端：聊天 / 多智能体 / RAG 检索 / 知识库 / 导入队列。

## 环境要求

- Python ≥ 3.12
- Milvus 2.4+（P0 默认启用，不可达时自动降级 InMemoryVectorStore）
- 可选：PostgreSQL 14+（自动降级 SQLite）
- 可选：Redis 7+（缓存加速）

## 安装

```bash
# 创建虚拟环境（推荐）
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

# 安装依赖
pip install -e .
```

## 配置

复制 `.env.example` 为 `.env`，填入 API 密钥：

```bash
cp .env.example .env
# Windows: copy .env.example .env
```

至少需要一个 LLM 通道（DeepSeek 或 讯飞星火）。

## 启动

```bash
# 开发模式（热重载）
python main.py

# 生产模式（无热重载）
UVICORN_RELOAD=0 python main.py
```

服务启动在 **http://127.0.0.1:8002**

## 健康检查

```bash
curl http://127.0.0.1:8002/api/status
```

正常响应：`{"status":"ok","vector_db":"inmemory","collection_size":1883,...}`

## 测试

```bash
# 运行全量测试
python -m pytest -q

# 运行特定模块测试
python -m pytest tests/test_engine_modules.py -v
```

## 项目结构

```
py-server/
├── api/           # API 路由（25 模块, 97 端点）
├── agents/        # 多智能体节点（9 个 LangGraph 节点）
├── engines/       # 核心引擎
│   ├── gomarl.py          # GOMARL 共识聚合
│   ├── gomarl_mixer.py    # Neural GroupMixer 神经网络
│   ├── gomarl_conflict.py # 证据冲突消解
│   ├── frugal_rag.py      # 节俭检索增强生成
│   ├── frugal_rag_sft.py  # SFT 风格检索优化
│   ├── agent_debate.py    # 多智能体辩论协议
│   └── teaching_rules.py  # 408 教学规则引擎
├── db/           # 数据层
│   ├── llm_provider.py    # LLM 三通道路由器
│   ├── milvus_client.py   # 向量数据库抽象层
│   ├── embedder.py        # E5 文本嵌入
│   ├── pg_client.py       # PostgreSQL 客户端
│   └── redis_client.py    # Redis 缓存客户端
├── shared/       # 共享工具
│   ├── auth.py            # JWT 认证
│   ├── errors.py          # 统一错误处理
│   └── audit.py           # 安全审计日志
├── models/       # 预训练模型权重
├── tools/        # 工具脚本
├── tests/        # 测试（281+ 个）
├── main.py       # 应用入口
├── config.py     # 配置管理
├── prompts.py    # 提示词模板
└── seed_data.py  # 种子数据
```

## 导入工具

向量库导入已服务化，所有导入任务经进程内队列串行处理：

```bash
# CLI 客户端
python tools/import_client.py --type pdf --rebuild
python tools/import_client.py --type textbook --max-pages 50
```

## 注意

- ⚠️ 生产部署必须设置 `ADMIN_PASSWORD` 和 `AUTH_SECRET` 环境变量
- ⚠️ uvicorn 必须 `--workers 1`（单进程），避免多写者冲突
- ⚠️ `.env` 文件包含敏感密钥，不要提交到版本控制
- ⚠️ `.env` 权限应设为 `600`（`chmod 600 py-server/.env`）；真实密钥经 Docker / K8s secrets 注入，**不随镜像或仓库分发**，并应定期轮换（F-001）

## CI / 自动化测试（GitHub Actions）

后端测试工作流见 `.github/workflows/backend-test.yml`，**仅在 `ubuntu-latest`（Linux）runner 上运行**。

### 为什么必须用 Linux runner

Windows 原生 `torch` / `numpy` 在「实际调用模型 / 向量路径」的测试中会触发
`SIGSEGV(139)` 段错误——这是**环境级问题、与代码正确性无关**。`tests/conftest.py`
在 `win32` 下会跳过这些模块（`segv_env`），但会导致整轮 pytest 崩溃、拿不到结果。
干净 Linux 环境历史上 `pytest py-server/tests` 可 **281/281 全绿**，因此 CI 在
Linux 跑才能拿到权威的全量测试结果。

### 本地如何跑测试

```bash
cd py-server
cp .env.example .env          # 占位值即可；conftest 会 mock LLM / auth
python -m pytest -q           # 默认档：离线单元 / 集成 / E2E
python -m pytest tests/test_p0_incremental.py --noconftest   # 隔离测试单独跑
```

> Windows 本地直接 `pytest` 会因 SIGSEGV 崩溃（前 ~56% 纯 Python 用例仍可跑）。
> 本地仅用于验证纯逻辑；**权威回归以 Linux CI 为准**。

### CI 如何触发

| 触发方式 | 跑哪些用例 |
| --- | --- |
| `push` 改到 `py-server/**` | 默认档（离线单元/集成/E2E，自动排除 system/requires_milvus/slow） |
| `pull_request` 改到 `py-server/**` | 同上 |
| `workflow_dispatch`（不带 `run_heavy`） | 同上 |
| `workflow_dispatch`（带 `run_heavy=true`） | 重用例档：覆盖 system / requires_milvus，加 `--timeout=180` |

- 安装方式：`pip install -e ".[test]"`（pyproject 的 `test` extra 含 pytest / pytest-asyncio / pytest-timeout / pytest-cov / respx）。
- 默认档依赖 `pyproject.toml` 的 `addopts = ["-m", "not system and not requires_milvus and not slow"]` 自动过滤重用例；`tests/conftest.py` 用 autouse fixture（mock_llm / mock_auth / fake_embedder / isolate_vectordb）保证无需真实密钥或网络即可通过。
- JUnit 报告（`pytest-report.xml`）在跑完后（含失败）作为 artifact 上传，便于查看失败日志。

### 密钥与 .env

- CI 运行时会基于 `.env.example` 生成最小 `py-server/.env`；若仓库配置了对应
  GitHub Secret（`XF_APP_ID` / `XF_API_KEY` / `XF_API_SECRET` / `DEEPSEEK_API_KEY` 等），
  则以真实值覆盖占位符。
- **默认档不需要真实密钥**即可全绿（conftest 已 mock）。重用例档（`run_heavy=true`）
  若需真实模型 / 讯飞凭证，请在仓库 Settings → Secrets 中配置。
- 工作流**不打印任何密钥值**，且只上传 `pytest-report.xml`，绝不回传 `.env`。