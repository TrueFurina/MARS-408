# MARS-408 — 部署文档

> 基于 GOMARL 与 FrugalRAG 的 408 考研个性化学习系统
> 中国软件杯 A3 赛题参赛作品

---

## 一、环境要求

### 系统要求
- **操作系统**：Windows 10/11、macOS 12+、Ubuntu 20.04+
- **Python**：3.12+（项目自带 venv）
- **Node.js**：18+（建议 20 LTS）
- **npm**：9+

### 依赖服务（可选，开发期可不启动）
| 服务 | 版本 | 说明 | 是否必需 |
|------|------|------|----------|
| Milvus | 2.3+ | 向量数据库 | ❌ 不可用时自动回退 InMemoryVectorStore |
| PostgreSQL | 16+ | 关系数据库 | ❌ 不可用时静默降级 |
| Redis | 7+ | 缓存 | ❌ 不可用时静默降级 |

> **核心特性**：系统在 PG/Redis/Milvus 不可用时**优雅降级**，核心对话与知识检索功能不受影响。

### LLM 配置（必需）
至少配置一个 LLM API Key：
- **讯飞星火**：`XF_APP_ID` + `XF_API_KEY` 或 config.json 中 `xfyun` 字段（赛题合规要求，第一优先级）
- **DeepSeek**：`DEEPSEEK_API_KEY` 环境变量 或 config.json 中 `deepseek.api_key`（降级通道）
- **通义千问**：`QWEN_API_KEY` 或 config.json 中 `qwen.api_key`（备用通道）

---

## 二、项目结构

```
study-help-pro/
├── start.bat              # Windows 一键启动脚本
├── start.sh               # Linux/macOS 一键启动脚本
├── dist/                  # 前端构建产物（已包含 index.html + assets）
│   ├── index.html
│   ├── favicon.ico
│   └── assets/            # JS/CSS/字体/图片等
├── py-server/             # 后端 FastAPI
│   ├── main.py            # 入口（host=127.0.0.1:8002）
│   ├── config.json        # 运行配置（LLM Key 等）
│   ├── config.py           # 配置管理（支持环境变量覆盖）
│   ├── .venv/             # Python 虚拟环境（含所有依赖）
│   ├── db/                # 数据层（Milvus/PG/Redis 客户端）
│   ├── api/               # API 路由模块
│   ├── engines/           # FrugalRAG + GOMARL 引擎
│   ├── agents/            # 多智能体定义
│   ├── vectordb_data/     # InMemory 向量库持久化数据
│   └── pyproject.toml     # Python 依赖声明
├── submission/02_配套文档/             # 项目文档
│   ├── 开发说明书.md
│   ├── 测试说明书.md
│   ├── 技术方案说明书-特等奖版.md
│   ├── 系统架构设计文档.md
│   └── 演示脚本.md
│   └ ...
└── package.json           # 前端依赖
```

---

## 三、启动步骤

### 方式 A：一键启动（推荐）

#### Windows
```cmd
# 1. 复制配置文件并填入 LLM API Key
copy py-server\config.json py-server\config.json.bak
# 编辑 py-server\config.json，填入 deepseek.api_key 或 xfyun 字段

# 2. 一键启动
start.bat
```

#### Linux/macOS
```bash
# 1. 复制配置文件并填入 LLM API Key
cp py-server/config.json py-server/config.json.bak
# 编辑 py-server/config.json

# 2. 一键启动
chmod +x start.sh
./start.sh
```

### 方式 B：手动分步启动

#### 1. 启动后端
```bash
cd py-server
# Windows:
.venv\Scripts\python.exe main.py
# Linux/macOS:
.venv/bin/python main.py
```

后端将在 `http://127.0.0.1:8002` 启动，首次启动需加载 E5-base-v2 模型（约10-30秒）。

#### 2. 启动前端（开发模式）
```bash
npm install   # 首次需安装依赖
npm run dev   # 启动开发服务器 http://localhost:5173
```

Vite 开发服务器会将 `/api` 和 `/plots` 请求代理到后端 8002 端口。

#### 3. 启动前端（生产模式 / 使用预构建 dist）
如果已有 `dist/` 目录，可通过后端直接托管静态文件（需修改 main.py 添加 StaticFiles），或使用任意静态文件服务器。

---

## 四、验证步骤

### 1. 健康检查
```bash
curl http://127.0.0.1:8002/api/status
```

预期响应：
```json
{
  "status": "ok",
  "vector_db": "inmemory",        // 或 "milvus"（若 Milvus 已连接）
  "collection_size": <N>,          // 种子数据条数
  "pg_enabled": false,             // 或 true
  "redis_enabled": false,          // 或 true
  "llm_provider": "xfyun",         // 当前 LLM 通道
  "llm_available": true            // 至少一个 Key 已配置
}
```

**关键检查项**：
- `status` = `"ok"` → 后端正常运行
- `vector_db` = `"inmemory"` 或 `"milvus"` → 向量库可用
- `llm_available` = `true` → LLM 通道可用

### 2. 前端页面可达性
浏览器访问 `http://localhost:5173`，应看到 MARS-408 登录/主页界面。

### 3. 核心流程验证
1. **创建学习画像**：进入画像构建页面，填写基本信息
2. **对话交互**：进入 Chat 页面，发送一条学习问题，确认收到 AI 回复
3. **知识检索**：进入知识库页面，确认 408 四科知识点可见
4. **练习答题**：进入 Practice 页面，完成一道题目

### 4. 降级验证（PG/Redis/Milvus 不可用）
当 PG/Redis/Milvus 服务不可用时：
- 后端**不会崩溃**，仅输出 warning 日志
- `/api/status` 中 `pg_enabled`/`redis_enabled` 为 `false`
- 核心对话和知识检索功能**正常工作**（使用 InMemoryVectorStore）
- 画像持久化、答题记录等功能降级为**内存临时存储**

---

## 五、配置说明

### config.json 关键字段
| 字段 | 说明 | 默认值 |
|------|------|--------|
| `llm_provider` | LLM 通道选择：deepseek/xfyun/qwen/auto | `"xfyun"` |
| `deepseek.api_key` | DeepSeek API 密钥 | `""`（需填写） |
| `xfyun.app_id` | 讯飞星火 App ID | `""`（需填写） |
| `milvus.enabled` | 是否启用 Milvus | `false` |
| `postgresql.enabled` | 是否启用 PG | `false` |
| `redis.enabled` | 是否启用 Redis | `false` |
| `embedding.mode` | Embedding 模式 | `"local"`（E5-base-v2 本地推理） |

### 环境变量覆盖
可在启动前设置环境变量覆盖 config.json：
```bash
export DEEPSEEK_API_KEY="sk-xxx"    # DeepSeek Key
export XF_APP_ID="xxx"              # 讯飞 App ID
export XF_API_KEY="xxx"             # 讯飞 API Key
export MILVUS_HOST="localhost"       # Milvus 地址
```

---

## 六、回滚方案

### 版本回滚
1. Git 回滚：`git checkout <上一个稳定版本的commit>`
2. 重新启动服务即可

### 数据回滚
- InMemoryVectorStore：`vectordb_data/netlearn_kb.json` 为自动持久化文件，可备份/恢复
- PostgreSQL：若启用，需通过 pg_dump 备份
- Redis：缓存数据，丢失不影响核心功能

### 配置回滚
- `config.json.bak` 为启动前的备份，可随时恢复

---

## 七、交付包清单

| 文件/目录 | 状态 | 说明 |
|-----------|------|------|
| `start.bat` | ✅ 已创建 | Windows 一键启动脚本 |
| `start.sh` | ✅ 已创建 | Linux/macOS 一键启动脚本 |
| `dist/` | ✅ 已构建 | 前端构建产物（index.html + assets） |
| `py-server/.venv/` | ✅ 已就绪 | Python 虚拟环境（所有依赖已安装） |
| `py-server/config.json` | ⚠️ 需填写 Key | LLM API Key 待配置 |
| `02_配套文档/开发说明书.md` | ✅ 已存在 | 开发文档（v2.0） |
| `02_配套文档/测试说明书.md` | ✅ 已存在 | 测试文档（v2.0） |
| `02_配套文档/技术方案说明书-特等奖版.md` | ✅ 已存在 | 技术方案（含开源声明） |
| `02_配套文档/演示脚本.md` | ✅ 已存在 | 演示流程脚本 |
| 演示视频 | ⚠️ 待制作（提交物，非开发阻塞） | 系统就绪后由 PM/设计师制作 |

---

## 八、常见问题

### Q: 首次启动很慢？
A: 首次启动需加载 E5-base-v2 embedding 模型（~400MB），约10-30秒。后续启动会从本地缓存加载。

### Q: 后端启动报 "无可用 LLM 通道"？
A: 需在 `py-server/config.json` 或环境变量中配置至少一个 LLM API Key。

### Q: 前端 5173 端口被占用？
A: Vite 配置了 `strictPort: false`，会自动尝试下一个可用端口。

### Q: Milvus/PG/Redis 连接失败？
A: 开发期无需这些服务，系统会自动降级。如需启用，修改 config.json 中对应 `enabled: true` 并确保服务运行。
