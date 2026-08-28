# MARS-408 部署核对表

> 第十五届中国软件杯 A3 赛题 — 提交物可运行性核对
> 目标：评委在常规环境下开箱即跑，无需额外配置即可体验核心功能

---

## 一、环境依赖清单

### 必需依赖

| 组件 | 版本要求 | 验证命令 | 说明 |
|------|---------|---------|------|
| Python | >= 3.12 | `python3 --version` | 后端运行时 |
| Node.js | >= 20.19 或 >= 22.12 | `node --version` | 前端构建/开发服务器（有预构建 dist 时可选） |
| pip / uv | pip >= 24.0 或 uv >= 0.4 | `pip --version` | 依赖安装（uv 更快） |
| npm | >= 10 | `npm --version` | 前端依赖管理 |

### 已预打包（无需下载）

| 资源 | 位置 | 说明 |
|------|------|------|
| E5 嵌入模型 | `py-server/models/e5-base-v2/` | 768 维 Sentence Transformer，含 model.safetensors |
| NeuralMixer 权重 | `py-server/models/neural_mixer.onnx` | GOMARL 共识引擎神经网络（ONNX 格式，跨平台） |
| 知识库数据 | `py-server/vectordb_data/netlearn_kb.json` | 571 知识 chunks + 200 题，启动时自动加载 |
| 前端构建产物 | `dist/` | Vue 3 SPA 已构建（后端可直接托管） |
| 种子数据 | `py-server/seed_data.py` | 内置知识 chunks + 题目（向量库为空时自动播种） |
| 演示数据 | `py-server/seed_demo_data.py` | demo/demo123456 账号预填数据（非生产自动播种） |

### 可选依赖（缺任一均可降级运行）

| 组件 | 用途 | 缺失时降级行为 | 启用方式 |
|------|------|--------------|---------|
| Milvus | 向量检索 | 自动回退 InMemoryVectorStore（内存向量库，功能完整） | `docker-compose --profile milvus up -d` |
| PostgreSQL | 持久化存储 | 自动回退 SQLite（本地文件数据库） | 设置 `PG_HOST` + `config.json` 启用 |
| Redis | 缓存/会话 | 内存降级，功能不受影响（仅性能略降） | `docker-compose --profile production up -d` |
| LLM API Key | 智能对话/出题 | demo 模式：返回降级提示，核心链路用内置样例 | 配置 `.env` 中 `DEEPSEEK_API_KEY` 或讯飞凭证 |
| 讯飞 TTS | 语音合成 | 降级为 MeloTTS 本地离线引擎（首次需下载模型） | 配置讯飞 TTS 凭证 |
| 讯飞 TTI | AI 图片生成 | 降级为 SVG 编程绘图 | 配置讯飞 TTI 凭证 + `tti_enabled=true` |

---

## 二、启动方式核对

### 方式 1: Docker（推荐评委使用）

```bash
# 开箱即跑（development 模式，含 demo 账号）
docker-compose up -d

# 验证
curl http://localhost:8002/api/status
# 期望: {"status":"ok","vector_db":"inmemory","collection_size":571,...}

# 访问
# 浏览器打开 http://localhost:8002
# 登录: demo / demo123456
```

**生产部署（含 Milvus + Redis）:**

```bash
# 1. 创建 .env 配置生产密钥
cat > .env << 'EOF'
NETLEARN_ENV=production
AUTH_SECRET=<your-random-secret-at-least-32-chars>
ADMIN_PASSWORD=<your-strong-password-at-least-16-chars>
DEEPSEEK_API_KEY=<your-key>
EOF

# 2. 启动完整服务栈
docker-compose --profile production up -d
```

### 方式 2: 一键脚本

| 平台 | 脚本 | 说明 |
|------|------|------|
| Windows | `start.bat` / `start.ps1` | 自动创建 venv、装依赖、启动后端 |
| Linux/macOS | `scripts/start.sh` | 同上，含版本检查、健康检查、访问地址打印 |

```bash
# Linux/macOS
chmod +x scripts/start.sh
./scripts/start.sh
```

### 方式 3: 手动启动

```bash
# 后端
cd py-server
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e .
python main.py

# 前端（新终端，可选 — 有预构建 dist 时后端直接托管）
cd study-help-pro
npm install
npm run dev
```

---

## 三、快速验证清单

启动后逐项验证：

| # | 验证项 | 命令 | 期望结果 |
|---|--------|------|---------|
| 1 | 后端健康检查 | `curl http://127.0.0.1:8002/api/status` | `{"status":"ok",...}` |
| 2 | 向量库状态 | 同上，检查 `vector_db` 字段 | `inmemory`（无 Milvus）或 `milvus` |
| 3 | 知识库已加载 | 同上，检查 `collection_size` | `> 0`（通常 571+） |
| 4 | 指标端点 | `curl http://127.0.0.1:8002/metrics` | Prometheus 文本格式输出 |
| 5 | 前端页面 | 浏览器访问 `http://127.0.0.1:8002` | 登录页正常显示 |
| 6 | Demo 登录 | 用 `demo` / `demo123456` 登录 | 登录成功，进入主页 |
| 7 | API 文档 | 浏览器访问 `http://127.0.0.1:8002/docs` | Swagger UI 正常 |

### `/api/status` 响应字段说明

```json
{
  "status": "ok",              // 后端运行状态
  "vector_db": "inmemory",     // 向量库类型: inmemory(降级) | milvus(完整)
  "collection_size": 571,      // 知识库文档数（>0 表示种子数据已加载）
  "pg_enabled": false,         // PostgreSQL 是否启用
  "redis_enabled": false,      // Redis 是否启用
  "llm_provider": "auto",      // LLM 通道选择策略
  "llm_available": false       // 是否配置了 LLM 凭证（false=demo模式）
}
```

---

## 四、Demo 模式说明

当未配置 LLM 凭证（DEEPSEEK_API_KEY / XF_API_KEY / XF_API_PASSWORD 均为空）时：

- **启动日志**会输出降级提示：`未检测到 LLM 凭证，已进入 demo 模式...`
- **智能对话**等 LLM 功能返回友好降级提示（不报 500 错误）
- **核心链路正常运行**：
  - 学习画像：使用内置样例数据
  - 资源生成：返回预置模板内容
  - 学习路径：基于内置知识图谱规划
  - 知识图谱：四科完整可视化
  - 代码沙箱：正常执行
  - TTS 朗读：MeloTTS 本地引擎（需首次下载模型）
- 配置 LLM 凭证后重启即恢复完整 AI 能力

---

## 五、安全配置核对（生产部署）

| 配置项 | 开发模式（默认） | 生产模式 | 验证方式 |
|--------|----------------|---------|---------|
| `NETLEARN_ENV` | `development` | `production` | 环境变量 |
| `AUTH_SECRET` | 自动随机生成（重启失效） | **必填**，>= 32 字符 | `.env` 文件 |
| `ADMIN_PASSWORD` | 自动随机生成（重启失效） | **必填**，>= 16 字符 | `.env` 文件 |
| Demo 账号 | 自动播种 demo/demo123456 | **不创建** | 登录测试 |
| CORS | 放行 LAN/loopback | 仅白名单 | 浏览器跨域测试 |
| HSTS | 不发送（HTTP） | 强制（HTTPS） | 响应头检查 |
| 错误消息 | 返回详细 detail | 脱敏通用文案 | API 调用 |

> 生产模式下缺失 `AUTH_SECRET` 或 `ADMIN_PASSWORD` 会导致 fail-fast 启动失败（RuntimeError），这是安全设计，非 bug。

---

## 六、常见问题

**Q: `docker-compose up` 启动失败？**
A: 检查 Docker 和 Docker Compose 是否安装。确认端口 8002 未被占用：`lsof -i :8002`（Linux/Mac）或 `netstat -ano | findstr 8002`（Windows）。

**Q: 前端页面空白？**
A: 检查后端是否正常：`curl http://127.0.0.1:8002/api/status`。若返回非 200，查看后端日志。

**Q: 登录提示"凭证无效"？**
A: 确认使用 `demo` / `demo123456`（非生产模式）。生产模式不创建 demo 账号，需用 admin + ADMIN_PASSWORD。

**Q: 向量库显示 `inmemory` 而非 `milvus`？**
A: 正常行为。无 Milvus 时自动降级为内存向量库，功能完整。需 Milvus 时运行 `docker-compose --profile milvus up -d`。

**Q: LLM 功能返回降级提示？**
A: 未配置 LLM 凭证。在 `py-server/.env` 中配置 `DEEPSEEK_API_KEY` 或讯飞凭证后重启。
