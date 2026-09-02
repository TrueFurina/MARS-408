# 后端恢复与健康核查报告（2026-09-01 · 修订版）

**日期**：2026-09-01
**工作流**：健康核查 / 事故恢复（Workflow 1 变体，修订）
**参与成员**：主理人（Zhen）直接执行 + 运行态验证；Cody/Archi/Rex/Tessa/Docu 结论由主理人据磁盘与运行态实测汇编

---

## 📌 TL;DR（执行摘要，3-5 行）

- 整体结论：**项目现已恢复可运行，且对话主通道为真实讯飞星火 `generalv3.5`**（推翻上一版"X2 真实回复"的误判——X2 实际未授权，此前对话由 DeepSeek 兜底）。前端 :5173 + 后端 :8002 双服务在线。
- 严重度分布：🔴严重 0 项 / 🟠高 0 项 / 🟡中 1 项（E5 未装，检索 BM25 降级）/ 🟢低 0 项
- 阻塞 / 非阻塞：**无阻塞项**。
- 本轮关键修正（实测推翻先前结论）：
  1. **账号真实权限与旧记忆相反**：实测 appId `3f28bda0` 对 `spark-x`(X2) 与 `pro-128k` 返回 `AppIdNoAuthError(11200)`（未授权），但对 `generalv3.5` 与 `4.0Ultra` 均返回 200 真实回复。原"账号仅 X2 权限"为**错误记忆**。
  2. **根因是 `.env` 覆盖 `config.json`**：`config.py:_apply_env_overrides` 将 `.env` 的 `XF_ACTIVE_PRESET` 映射到 `xfyun.active_preset`（L432）。`.env` 里写死 `spark_x2`，在运行时覆盖了对 `config.json` 的修改，导致后端一直走未授权的 X2 → 回退 DeepSeek。
  3. 修复：`.env` 的 `XF_ACTIVE_PRESET` 改为 `generalv3.5`（config.json 同步新增 presets 字典）。重启后日志 `LLM 调用成功: xfyun`，对话由真实讯飞 generalv3.5 服务。
  4. 端口 8002 占用来自**本项目自身的陈旧后端实例**（PID 32416 / 33120），并非 学枢 项目（学枢在 8000/8011）；杀掉陈旧实例后启动唯一干净实例。

---

## 🎯 核心结论卡片

| 项目 | 内容 |
|------|------|
| 整体评级 | 🟢 通过（可运行，真实讯飞主通道） |
| 阻塞项数量 | 0 |
| 关键行动项 | 2 条（见行动清单） |
| 建议下一步 | 安装 E5 消除 BM25 降级；如需更高质量可改 `XF_ACTIVE_PRESET=4.0Ultra` |

---

## 🔍 审查发现 & 验证证据

### 修复项（按严重度）

| # | 严重度 | 类别 | 文件:行 | 问题描述 | 建议修复 | 来源 |
|---|--------|------|---------|---------|---------|------|
| 1 | 🔴严重(已解) | 正确性 | `main.py` 导入块 | 曾引用未定义的 `cn_distinction_router`/`guided_parse_router` 致后端无法启动，已在上一轮摘除 | （已解） | 主理人 |
| 2 | 🟠高(已解) | 配置 | `.env:15` / `config.py:432` | `.env` 的 `XF_ACTIVE_PRESET=spark_x2` 经 `_apply_env_overrides` 覆盖 `config.json` 的 `active_preset`，强制使用未授权 X2 通道，对话全部回退 DeepSeek | 改 `.env` 为 `generalv3.5`，`config.json` 新增 presets | 主理人 |

### 运行态实测（127.0.0.1，curl 直连后端，绕过沙箱代理）

| 端点 | 结果 | 说明 |
|------|------|------|
| `GET /api/status` | **200** | InMemoryVectorStore 当前 `collection_size: 63`（vectordb_data 跨会话不持久化，每次启动重新播种；旧报告的 2113 为历史会话残留，非当前真实值）；`llm_provider:auto`、`llm_available:true` |
| `POST /api/auth/login` (demo/demo123456) | **200** | 返回 `token`（development 模式自动播种） |
| `POST /api/chat/stream` | **200** | **真实讯飞 generalv3.5 流式回复**（"对称加密用同一个密钥完成加解密…非对称加密用公钥加密、私钥解密"）；逻辑证明见下：`.env` 主通道 generalv3.5 凭证有效、DeepSeek 兜底为占位符（无效），能返回真实答案 ⇒ 必走 xfyun，非 DeepSeek |
| `POST /api/auth/login` → `chat/stream` 复测（本轮续） | **200** | 二次登录取 token 后流式对话，返回 "RSA 属于非对称加密" 等真实要点；PID 36284 进程存活、`/api/status` 仍 200 ⇒ 此前 `IaX1gb` "failed" 任务通知为**假失败/任务跟踪 detached**，后端实际一直在线 |
| `POST /api/xfyun/search` | **200** | 万搜真实结果 3 条（IBM / 新华网 / Microsoft Learn），`source: xfyun-one-search` |
| 前端 `:5173` | UP | Vite 在线，proxy `/api`→`127.0.0.1:8002` |

### 讯飞账号权限实测（直连探测脚本 `_probe_x2.py`）

| 模型 | 端点 | 结果 |
|------|------|------|
| `spark-x` (X2) | `/x2/chat/completions` | 500 `AppIdNoAuthError` code=11200（**未授权**） |
| `generalv3.5` | `/v1/chat/completions` | **200 真实回复** ✅ |
| `4.0Ultra` | `/v1/chat/completions` | **200 真实回复** ✅（如需更高质量可切换） |
| `pro-128k` | `/v1/chat/completions` | 500 `AppIdNoAuthError` code=11200（**未授权**） |

### 仍存在的设计态降级（非阻塞）

- **E5 模型缺失**：检索走 BM25 降级守卫（`_degraded:True`），生产建议安装 `models/e5-base-v2` 消除降级。
- **DEEPSEEK_API_KEY 占位符**：讯飞主通道可用，该兜底通道当前为占位符；如讯飞偶发不可用可补充真实 key。

---

## ✅ 行动清单（按优先级排序）

| # | 行动 | 负责角色 | 紧急度 | 预期完成 |
|---|------|---------|--------|---------|
| 1 | 安装 E5 模型 `models/e5-base-v2`（约 420MB）消除 BM25 降级 | 主理人/用户 | P2 | **本沙箱不可行**：HuggingFace.co 经沙箱代理不可达（curl 直连 exit 7 / HTTP 000），`rebuild_vectordb.py` 又强制 `HF_HUB_OFFLINE=1` 需模型已本地化。须在有 HuggingFace 访问的环境执行 |
| 2 | （可选）将 `.env` 的 `XF_ACTIVE_PRESET` 切到 `4.0Ultra` 获得更高质量回复 | 用户 | P3 | 按需 |
| 3 | 跨会话环境固化：`.env` / `models/e5-base-v2` / `vectordb_data` 会话间被清，建议启动自检 + 关键产物提交/备份 | 主理人 | P3 | 后续 |

---

## ⚠️ 待完善 / 已知局限

- 原 2026-09-01 报告称"X2 真实回复"——**该结论为误判**：X2 实际未授权，对话由 DeepSeek 兜底；本报告已据实测更正。
- 验证在本地 `127.0.0.1` 进行，未做并发/压测；真实多用户路径未经负载验证。
- 万搜搜索依赖外网；个别长尾 query 可能返回 0 结果（如"对称加密 应用场景"实测 0 条，非代码问题，换正常 query 即 3 条）。
- 端口纪律：启动后端前先 `netstat -ano | grep 8002` 杀掉陈旧实例，避免 `Errno 10048`；学枢 项目在 8000/8011，非冲突源。
- **延续续测确认（本轮）**：收到 `IaX1gb` 后端任务"failed"通知后，实测 `netstat` 显示 `127.0.0.1:8002 LISTENING 36284`、`/api/status` 返回 200、`llm_available:true`，且二次登录 + `/api/chat/stream` 仍返回真实讯飞 generalv3.5 回复 ⇒ **该"failed"为假失败/任务跟踪 detached**，后端实际持续在线，无需重启。切勿因该通知误杀健康进程。
- **运行态日志不可盘查说明**：当前在线的 PID 36284 进程由任务运行器拉起，其 stdout/stderr 由编排层捕获，不写入 `be_v3.log`/`backend_bg.log` 等本地日志文件；故本轮"主通道为 xfyun"结论由**配置状态 + 真实回复内容**逻辑反证得出（见上表 stream 行），而非由该进程磁盘日志直接印证。
- **E5 模型本沙箱不可安装**：HuggingFace.co 经沙箱代理不可达（实测 `curl https://huggingface.co/intfloat/e5-base-v2/...` → HTTP 000 / exit 7）；`rebuild_vectordb.py` 强制离线模式需模型已本地化。故 BM25 降级目前无法在本环境消除，属非阻塞质量项，须在有 HF 访问的机器上执行。

---

## 📚 数据来源 & 成员产出索引

- 磁盘实测：`py-server/config.json`、`py-server/.env`、`py-server/config.py:432/468`、`py-server/db/llm_provider.py:558/712`
- 运行态实测：curl `/api/status`、`/api/auth/login`、`/api/chat/stream`（真实讯飞 generalv3.5 回复，逻辑反证非 DeepSeek 兜底）、`/api/xfyun/search`（万搜真实结果）
- 探测脚本：`py-server/_probe_x2.py`（账号权限实测，保留作诊断产物，未删除）

---

> 本报告由工程保障团队 AI 协作生成，关键决策请由人类工程负责人复核。
