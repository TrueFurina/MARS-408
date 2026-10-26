# R1 部署可达性 · 决策简报（P0-B，待用户拍板）

> 目的：把 next-steps P0-B 的拍板所需事实集中到一页。裁决后落 `plans/decisions.md`。
> 前置事实：取证闸 `experiments/pilot_evidence_report.py` 契约完好（2026-10-18 复验：裁决 ❌ + 真实退出码 1）；
> 判据 = 单班 ≥3 非测试学生等四项，当前 max_bound_class=2（全部为开发/测试数据）。

> 🔴 **2026-10-21 状态更新——本简报性质已变**
> 1. 真实试点由用户明确**略过**（`plans/pilot-material-2026-10-21.md`）。所以 A/B/C 不再是「先有试点、再谈上线」的
>    依赖链，而是**纯部署/演示决策**：拼图③ 已登记为文档化缺口，不再阻塞 R1 拍板。
> 2. **新增硬前置**：`deploy/career-pilot/` 与 HEAD 存在 **13 处已知漂移**（`scripts/build_career_pilot_package.py --check`
>    实测 exit 1：**12 个文件内容不一致** + `shared/limits.py` 缺失，含 `main.py` / `openapi.json` / `api/auth.py` /
>    `api/chat.py` / `db/career_store.py` / `tools/generate_demo_ppt.py` 等）。其中 deploy 侧 `openapi.json` 的
>    `info.description` 仍自称 **246/259**，而同一文件的 `paths`/操作数实测为 **244/262** —— 部署物内部自相矛盾。
>    已核：这批漂移在**提交树**即存在（`git show HEAD:py-server/...` 与 deploy 副本字节比对不一致），非未提交改动所致。
>    **执行 A 或 B 之前必须先跑打包脚本重建**，否则上线/演示的是旧包，数字与仓库 HEAD 不一致。
>    ✅ **2026-10-26 复核：该硬前置已消除** —— 包已被重建至与 HEAD 零漂移
>    （`6fb628e` 取消 `vectordb_data` 的 PRESERVE；今日含 `a03a585`/`010e5a3` 零向量读写双侧过滤）。
>    实测 `--check` exit 0、两份 `openapi.json` 的 `info.description` 同为 `95.02%（248/261）`、`paths` 同为 244
>    ⇒ 上文「13 处漂移 / 仍自称 246/259」是 10-21 时点快照，已不成立。**若选择 A 或 B，现在可直接用现成的包。**
>    ⚠️ 唯一保留约束：脚本以 `py-server/` 工作树为源，打包前须 `git status` 干净、打包后须重跑 `--check`。
> 3. **打包时机约束**：另一会话有未提交的 `py-server/services/import_worker.py` 等改动，此刻打包会把半成品带进部署包——
>    须等那些改动提交后再打包。
> 4. 下表 2026-10-18 的通道事实仍然有效，未变。
> 5. 🟢 **2026-10-26 拍板：R1 的「目的口径」改述** —— 由「真实学生试用可达」改为
>    **「评委 / 现场可访问」**。依据：当日实测线上 `/api/status` 200、`status:ok`、零降级项，
>    「可访问」是事实；「试用可达」会暗示有真实学生用过，与「零真实用户」相冲突。
>    **技术决策不变**：仍维持云托管（C 已落地），不升级 VPS、不改局域网。

## 现状事实（2026-10-18 实测）

| 通道 | 状态 | 证据 |
|---|---|---|
| 静态站 `https://mangdehenzhi.app.workbuddy.host/` | ✅ 已发布 | web-page + hash 路由；无后端，`/api/status` 404 属预期 |
| VPS staging（`deploy/career-pilot/` + `deploy/vps/*.service/nginx.conf`） | 🟡 在飞未验证 | service 指向 `/opt/career-pilot/backend`，nginx :80→8000；**VPS 主机地址/凭据在用户手中，本机无从探测** |
| 云 BaaS 托管后端 | 🔴 阻塞 | 服务端 401 `invalid_grant`，依赖平台方（P2-B） |
| 实验服务器 `172.16.222.99` | ✅ SSH 可达 | 但它是算力服务器，非对外服务位 |

## 三个选项

| 选项 | 内容 | 代价 | 风险 |
|---|---|---|---|
| **A. VPS 上线 career-pilot（推荐）** | 用户提供 VPS IP+SSH → 按 deploy/README 部署 → `curl /api/status` 200 验收 | S–M（半天内） | 需用户提供主机；公网暴露需确认 safety 已就位（JWT_SECRET 等 P0 遗留须先清） |
| B. 局域网演示版 | 对外材料写"演示版，未开放试用"，拼图③继续等 | S | 拼图③继续冻结 |
| C. 等云 BaaS 修复 | 平台方修复 401 后走托管 | 不可控 | 同 B |

## 拍板前前置项实测（2026-10-18，代码取证）

| 检查项 | 状态 | 证据 |
|---|---|---|
| 令牌签名密钥 | ✅ **已 fail-closed** | `shared/auth.py:19-32`（F-005）：硬编码旧密钥已移除；生产缺 `AUTH_SECRET`（<32 字符）直接 raise；开发随机生成+警告 |
| admin 口令 | ✅ 环境注入 | `db/user_store.py:269 ensure_admin(username, password)`，无硬编码默认值；PBKDF2-HMAC + compare_digest |
| 密钥不落盘 | ✅ 机制在位 | `config.py:401-420 _strip_secrets`：api_key 类字段 save_config 自动剥离 |
| 速率限制 | ✅ 在位 | ~~README:78 宣称与实现一致~~（2026-10-19 独立审计：该引用失实——README 无限流宣称，实际阈值 20 次/小时/IP，`api/auth.py:43`，10-15 真人演练校准；机制比原宣称更强） |
| `.env` 凭据 | ⬜ 部署时操作 | 只放 VPS 侧 chmod 600，不入库（gitignore 已覆盖） |
| 验收命令 | ⬜ 部署后执行 | `curl -sI http://<vps>/api/status` 返回 200 且 `fallback_zero_docs` 如实上报 |

> 结论：**旧「14 个 P0 阻塞」中的安全项（JWT_SECRET 为空等）已在代码层解决**——选 A 的前置主要是运维操作（VPS 主机 + .env + 验收），非代码改造。
