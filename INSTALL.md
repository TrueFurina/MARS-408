# MARS-408 安装与运行说明

> 第十五届中国软件杯 A3 赛题参赛作品
> 基于 GOMARL 与 FrugalRAG 的 408 考研个性化学习多智能体系统

---

## 一、环境要求

| 组件 | 最低版本 | 说明 |
|------|---------|------|
| Python | ≥ 3.12 | 必须 |
| Node.js | ≥ 20.19 或 ≥ 22.12 | 用于构建前端（可选，有预构建文件） |
| 操作系统 | Windows 10/11 | 其他系统需自行适配 |
| 内存 | ≥ 8GB | 推荐 16GB |
| 硬盘 | ≥ 5GB 空闲 | 依赖和模型文件 |

---

## 二、快速安装（推荐）

### 方式 1：一键启动（Windows）

1. 解压 `mars-408-portable.zip`
2. 双击 **`start.bat`**（或右键 → 以管理员身份运行）
3. 等待终端显示 `启动完成！请访问：http://localhost:8002`
4. 打开浏览器访问 `http://localhost:8002`
5. 登录 **用户名：`demo` 密码：`demo123456`**

> 首次启动会自动创建虚拟环境、安装依赖，耗时约 2-5 分钟（视网络情况）。

### 方式 2：PowerShell 启动

1. 解压后，在项目根目录右键 → **在终端中打开**
2. 执行：
```powershell
.\start.ps1
```

### 方式 3：手动启动

```bash
# 终端 A：启动后端
cd py-server
python -m venv .venv
.venv\Scripts\activate
pip install -e .
python main.py

# 终端 B：启动前端（可选，有预构建文件时后端直接提供前端页面）
cd study-help-pro
npm install
npm run dev
```

---

## 三、访问方式

| 地址 | 说明 | 是否需要登录 |
|------|------|:----------:|
| `http://localhost:8002` | 主页面（后端直接提供） | ✅ |
| `http://localhost:8002/api/status` | 健康检查 | ❌ |
| `http://localhost:5173` | Vite 开发服务器（仅前端开发时使用） | ✅ |

---

## 四、账号说明

| 账号 | 密码 | 角色 | 说明 |
|------|------|------|------|
| `demo` | `demo123456` | 学生 | 演示账号，含预填对话和画像数据 |
| `admin` | 由 `ADMIN_PASSWORD` 环境变量指定 | 管理员 | 未设置则随机生成（重启失效） |

---

## 五、配置说明

### 环境变量

复制 `py-server/.env.example` 为 `py-server/.env`，按需修改：

```ini
# ── LLM 通道（至少填一个，否则 LLM 功能不可用）──
DEEPSEEK_API_KEY=sk-your-key-here

# 或讯飞星火
XF_APP_ID=your_app_id
XF_API_KEY=your_api_key
XF_API_SECRET=your_api_secret

# ── 安全（生产环境必填）──
AUTH_SECRET=your_random_secret
ADMIN_PASSWORD=your_admin_password

# ── 日志级别（可选）──
LOG_LEVEL=INFO
```

> 没有 API 密钥也可启动，LLM 相关功能会显示降级提示，其他功能（知识图谱、TTS 朗读等）正常使用。

---

## 六、TTS 语音朗读

系统内置双引擎 TTS 语音朗读：

| 引擎 | 类型 | 语言 | 首次使用 |
|------|------|------|---------|
| **MeloTTS** | 本地离线 | 中/英/日/韩/西/法 | 自动下载模型（约 500MB，需联网） |
| **讯飞 TTS API** | 在线 | 中/英 | 需配置讯飞凭证 |

**首次使用注意事项：**
- MeloTTS 首次加载时会从 HuggingFace 下载模型文件，请确保网络畅通
- 如网络不可达，系统会自动降级到英文模型或讯飞 API
- 日语合成需要额外词典：`python -m unidic download`

---

## 七、功能清单

| 功能 | 入口 | 说明 |
|------|------|------|
| 智能对话 | `/chat` | 9 节点多智能体流水线，自动生成学习资源 |
| 智能出题 | `/practice` | 按科目/章节/难度生成练习题 |
| 知识图谱 | `/knowledge` | 四科知识图谱可视化 |
| 学习路径 | `/learning-path` | 个性化学习路径规划 |
| 资源生成 | `/resource` | 7 种资源并行生成 |
| 语音朗读 | 对话/资源页 🔊 按钮 | 双引擎 TTS，6 种语言 |
| 代码沙箱 | `/sandbox` | 在线 Python 代码执行 |
| 学习评估 | `/assessment` | 多维学习效果评估 |
| 教师看板 | `/teacher` | 学生进度、知识库统计 |

---

## 八、常见问题

**Q: 启动后页面空白？**
A: 确保后端已启动且 `http://localhost:8002/api/status` 返回 200。

**Q: LLM 无响应？**
A: 检查 `.env` 中的 API 密钥是否正确配置。

**Q: TTS 语音朗读不工作？**
A: 首次运行需要联网下载模型。执行 `curl http://localhost:8002/api/tts/status` 查看引擎状态。

**Q: 端口 8002 被占用？**
A: 修改 `py-server/main.py` 中的端口号，同步修改 `vite.config.ts` 中的 proxy target。

**Q: 如何重置数据？**
A: 删除 `py-server/vectordb_data/` 目录后重启后端。

---

## 九、提交材料

| 材料 | 位置 |
|------|------|
| 项目源码 | 项目根目录完整代码 |
| 演示 PPT | `MARS-408_软件杯演示.pptx` |
| 演示视频 | 需自行录制（≤7 分钟） |
| 开发说明书 | `documents/开发说明书.md` |
| 测试说明书 | `documents/测试说明书.md` |
| 系统架构设计 | `documents/系统架构设计文档.md` |
| 技术方案文档 | `documents/技术方案文档.md` |
| AI Coding 声明 | `documents/提交清单与录视频指南.md` |