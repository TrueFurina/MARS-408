# 一键启动绿色包：获取与运行

> 目标：拿到本仓库的人，在本机**只跑一条命令**就能把后端服务跑起来。
> 本目录下的脚本只做「前置自检 + 拉起后端」，**不修改任何既有文件**，也**不会替你杀掉别人的进程**。

| 平台 | 启动命令（在仓库根执行） |
| --- | --- |
| Windows | `deploy\start_windows.bat` |
| Linux / macOS / WSL / Git Bash | `bash deploy/start_linux.sh` |

脚本成功退出后，后端监听 `http://127.0.0.1:8002`，健康检查地址为 `http://127.0.0.1:8002/api/status`。

---

## 0. 你需要先准备什么（一次性）

后端是 Python FastAPI，启动命令为 `uvicorn main:app --port 8002`，首次启动约需 30 秒（要加载 embedding 模型），因此脚本会轮询等待最长 60 秒。

| 前置项 | 要求 | 获取方式 |
| --- | --- | --- |
| Python | >= 3.12（本项目 `pyproject.toml` 声明 `requires-python = ">=3.12"`，`.python-version` 为 `3.12`） | <https://www.python.org/downloads/> 或 `winget install -e --id Python.Python.3.12` |
| 虚拟环境 | `py-server/.venv` | **首选**：`cd py-server && uv sync --frozen`（依据 `uv.lock`，权威方式）<br>无 `uv` 时回退：`cd py-server && python -m venv .venv` 然后 `./.venv/Scripts/pip install -e .`（Windows）或 `./.venv/bin/pip install -e .`（Linux）<br>安装 uv：`winget install -e --id astral-sh.uv` 或 `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| E5 embedding 模型 | `py-server/models/e5-base-v2`（`intfloat/e5-base-v2`，768 维） | **模型不在版本库内**，缺失时执行：<br>`cd py-server && python ../scripts/fetch_e5_model.py`<br>（该脚本位于**仓库根** `scripts/` 目录，不在 `py-server/scripts/`；Windows 用 `.venv\Scripts\python.exe`） |
| 前端依赖（可选） | `node_modules` | `npm install`（仅在需要跑前端时） |

> 端口 `8002` 必须空闲。若已被占用，脚本会**明确报错并停下**，把处置权交给你（见第 3 节）。

---

## 1. 一键启动（Windows）

```bat
cd E:\Program\MARL\study-help-pro
deploy\start_windows.bat
```

脚本控制台输出全部为 **ASCII 英文**，在 GBK（代码页 936）控制台下不会出现中文乱码；脚本首行已执行 `chcp 65001`。

## 2. 一键启动（Linux / macOS / WSL / Git Bash）

```bash
cd /path/to/study-help-pro
bash deploy/start_linux.sh
# 或
chmod +x deploy/start_linux.sh && ./deploy/start_linux.sh
```

脚本使用 `#!/usr/bin/env bash` 与 `set -euo pipefail`，任何一步失败即带提示退出。

---

## 3. 脚本会做什么（6 步契约，两个平台语义一致）

| 步骤 | 检查/动作 | 不通过时的行为 |
| --- | --- | --- |
| 1/6 | 找到 Python 解释器（优先 `py-server/.venv`，其次系统 `python`），校验版本 >= 3.12 | 打印安装指引，`exit 2` |
| 2/6 | 检查 `py-server/.venv` 是否存在 | 打印 `uv sync --frozen` / `python -m venv .venv` 指引，`exit 2` |
| 3/6 | 检查 `py-server/models/e5-base-v2` 是否存在 | 打印 `fetch_e5_model.py` 指引，`exit 2` |
| 4/6 | 检查 `8002` 端口是否被占用 | 打印占用提示 + `netstat` / `lsof` 排查命令 + 换端口办法，**不擅自 kill**，`exit 2` |
| 5/6 | 在 `py-server/` 下后台启动 `uvicorn main:app`，轮询 `GET /api/status`，超时 60 秒 | 打印日志尾部 + 停止方法，`exit 2` |
| 6/6 | 成功：打印访问地址、日志文件路径、停止方法、前端启动方式 | `exit 0` |

### 退出码

| 码 | 含义 |
| --- | --- |
| `0` | 后端已就绪 |
| `2` | 任一前置检查未通过，或启动超时（脚本已给出可复制的修复命令） |

### 可配置项（环境变量）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8002` | 后端端口。被占用时可临时换端口排障：`PORT=8007 bash deploy/start_linux.sh`（Windows：`set PORT=8007 && deploy\start_windows.bat`） |
| `HOST` | `127.0.0.1` | 监听地址 |
| `HEALTH_PATH` | `/api/status` | 健康检查路径 |
| `STARTUP_TIMEOUT` | `60` | 就绪等待上限（秒） |
| `POLL_INTERVAL` | `2` | 轮询间隔（秒） |
| `PY_MIN_MAJOR` / `PY_MIN_MINOR` | `3` / `12` | Python 版本门槛。默认取项目事实源（`pyproject.toml` / `.python-version`）；如需收紧到 3.13+，运行前 `export PY_MIN_MINOR=13`（Windows：`set PY_MIN_MINOR=13`）即可，无需改脚本 |

---

## 4. 启动前端

后端跑起来后，在**另一个终端**、于**仓库根**执行：

```bash
npm install      # 首次
npm run dev      # 开发模式（vite dev server）
# 或者直接用已构建产物 dist/：
npm run preview
```

---

## 5. 停止服务与查看日志

**Linux / macOS**

```bash
kill "$(cat deploy/logs/backend.pid)"     # 停止后端
tail -f deploy/logs/backend-*.log         # 看日志
```

**Windows**（脚本不写 PID 文件，按端口定位）

```bat
netstat -ano | findstr :8002      :: 最后一列即 PID
taskkill /PID <pid> /F
type deploy\logs\backend.log      :: 看日志
```

日志文件位于 `deploy/logs/`：Linux 下为带时间戳的 `backend-<YYYYmmdd-HHMMSS>.log`（同时写入 `backend.pid`）；Windows 下为 `backend.log`，每次启动会把上一份改名为 `backend.log.old`。`logs` 与 `*.log` 均已被仓库 `.gitignore` 忽略，不会污染 `git status`。

---

## 6. 常见失败与处置

| 现象 | 处置 |
| --- | --- |
| `No Python interpreter found` | 安装 Python 3.12+，再建 venv（第 0 节）后重跑 |
| `Python version x.y is too old` | 升级 Python 并重建 venv：`cd py-server && uv sync --frozen` |
| `Virtual environment not found` | `cd py-server && uv sync --frozen`；或 `python -m venv .venv` + `pip install -e .` |
| `Embedding model not found` | `cd py-server && python ../scripts/fetch_e5_model.py` |
| `Port 8002 is ALREADY IN USE` | 先查占用者（`netstat -ano \| findstr :8002` / `sudo lsof -i :8002`）并**自行**决定是否停掉；或换端口 `PORT=8007 ...` |
| `Backend process exited before becoming ready` + 日志里出现 `F6 单写者锁获取失败` | **这是应用的保护机制，不是脚本故障**：`main.py` 用 `py-server/vectordb_data/.import_writer.lock` 强制「单写者」，同一时刻只允许一个后端进程。先停掉已在运行的那个实例（`netstat -ano \| findstr :8002` 找 PID），再启动。**换端口也不能绕过**该锁。脚本已固定传 `--workers 1`，请勿改成多 worker |
| `did not become ready within 60s` | 看脚本打印的日志尾部；首次启动含模型加载约 30 秒，若确属慢启动可加大 `STARTUP_TIMEOUT=120` |

---

## 7. 本脚本的验证状态（如实记录，未验证的部分不做声称）

**Linux 侧（`start_linux.sh`，已实测）**

- `bash -n deploy/start_linux.sh` 语法检查通过。
- 实跑 `bash deploy/start_linux.sh`：第 1 步识别出 `.venv` 的 Python `3.12.10`，第 2 步找到 `.venv`，第 3 步找到 E5 模型，第 4 步检出 `8002` 已被占用 → 打印排查指引并 `exit 2`（**正确行为**，未 kill 任何进程）。
- 用 `PORT=8007` 复跑，验证到第 5 步：端口探测通过、进程成功拉起、日志落盘到 `deploy/logs/backend-*.log`；随后 uvicorn 因**单写者锁**被已有实例持有而退出，脚本正确检出「进程在就绪前退出」、打印日志尾部并 `exit 2`（**正确行为**）。
- **未验证到 6/6 成功分支**：验证时本机已有一个后端实例占用 8002 并持有 `vectordb_data/.import_writer.lock`，而该锁禁止并发第二个实例，因此在不停掉它的前提下无法走通成功路径。健康探测逻辑已单独验证：`GET http://127.0.0.1:8002/api/status` 返回 200，探测单行命令 `exit 0`。

**Windows 侧（`start_windows.bat`，未实测）**

- **Windows 侧未实测**：本环境禁止从 shell 调用 `cmd.exe`，`.bat` 无法在此执行，故不对整体运行做任何声称。
- 已完成的静态与局部校验：文件为**纯 ASCII**（`grep '[^ -~\r]'` 无命中）、行尾为 **CRLF**（CR 与 LF 字节数均为 190）、首行 `chcp 65001`；脚本内嵌的 3 条 Python 单行命令（版本打印 / 版本门槛 / 端口探测 / 健康探测）已在项目 venv 的 Python 下**单独实测通过**，包括门槛 `3.12→exit 0`、`3.13→exit 1`、端口 `8002→exit 0`（占用）、`8007→exit 1`（空闲）、健康探测 `→exit 0`。
- 仍需人工确认的部分：`start "title" /B cmd /c "..."` 的后台拉起与输出重定向、以及 `timeout /t` 轮询循环，需在真实 `cmd.exe` 下双击或 `cmd /c` 运行一次。
