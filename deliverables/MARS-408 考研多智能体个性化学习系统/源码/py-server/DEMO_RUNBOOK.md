# MARS-408 演示日 Runbook（省赛硬门槛冲刺）

> 形态：**单端口 `:8002` + `development` 模式 + InMemory(2083 条) + SQLite 回退 + 双 LLM（讯飞 X2 主 → DeepSeek 兜底）**。
> 后端已托管前端 SPA，**不开 Vite**（规避 CORS/端口漂移）。本机入口 `127.0.0.1:8002`，同网段裁判可用 `http://<LAN-IP>:8002`（dev CORS 正则已放行 LAN）。

## 1. 启动顺序（务必按序）

```bat
:: (0) 杀 8002 残留，避免旧进程占端口 / 双写竞争
netstat -ano | findstr :8002
:: 命中后取最后一列 PID，强制结束（含子进程）
taskkill /PID <PID> /F /T
netstat -ano | findstr :8002        :: 应无输出

:: (1) 进目录并启动守护（guardian.bat 内部以 --workers 1 拉起 uvicorn :8002）
cd /d E:\Program\MARL\study-help-pro\py-server
guardian.bat
```

- 后端自挂载 SPA：dev 下读 `../dist/index.html`（`STATIC_DIR`/Docker 下读 `/app/static`）。**确认 `dist` 已构建**，否则只跑 API 模式、裁判看不到界面。
- 启动后等待首次 `lifespan` 完成：InMemory 空则写种子、`<500` 条再导入教材 PDF，约 30–90s 后 `collection_size≈2083`。

## 1.5 启动冒烟验证（含 career 功能）

每次演示前，后端 `lifespan` 完成、端口 `:8002` LISTENING 后，**逐项勾选；全绿才可继续**，任一 ❌ 即按本 Runbook 回滚/排查。

### 通用后端冒烟
- [ ] ✅/❌ **状态绿**：`GET /api/status` 返回 `status=ok`、`collection_size>0`、`llm_available=true`
- [ ] ✅/❌ **功能就绪**：`GET /api/status/competition` 五项功能 + 加分项就绪

### career 功能冒烟（三创赛演示线，`/api/career/*`）
- [ ] ✅/❌ **① 启动 career 服务**：`import career_training_router` 无异常；`GET /api/career/scenarios` 返回场景列表（HTTP 200，非空）
- [ ] ✅/❌ **② 调一次 career 训练/评审端点返回 200**：用 demo 学生账号
  `POST /api/career/session/start` 建会话 → 200；
  `POST /api/career/session/{sid}/answer` 推一轮 → 200；
  `POST /api/career/session/{sid}/end` 出六维报告 → 200
- [ ] ✅/❌ **③ career 政策默认值 `EVIDENCE_DENSITY_DEFAULT=0.3` 生效**（鲶鱼机制对齐基线、避免规则死锁）：
  ```bat
  ".\.venv\Scripts\python.exe" -c "from engines.career_policy import EVIDENCE_DENSITY_DEFAULT; assert EVIDENCE_DENSITY_DEFAULT==0.3, EVIDENCE_DENSITY_DEFAULT; print('OK', EVIDENCE_DENSITY_DEFAULT)"
  ```
  预期打印 `OK 0.3`；若非 0.3 说明政策模块被改坏，回退该提交。
- [ ] ✅/❌ **④ 教师端角色校验**：`POST /api/career/classes`（student 角色）→ 403；teacher/admin → 200（确认 `_require_teacher` 门禁在位）

> 说明：career 端点与 408 路由前缀隔离，互不影响；以上冒烟不触动既有 408 功能。career 决策默认规则版（`use_career_mappo=False`），若标榜"AI 对抗"须按 GoNoGo G1–G4 标注"v1 规则原型"。

## 2. `--workers 1` 显式固化（ADR-007 硬约束）

`main.py` 已对 `WEB_CONCURRENCY/UVICORN_WORKERS>1` 做启动期 `raise`（fail-fast），但**编排可能注入环境变量**。两处写死 CLI，让 `--workers 1` 优先级高于任何 env：

- `guardian.bat`：启动行改为
  `start "py-server-guardian" /min "!PY!" -m uvicorn main:app --host 127.0.0.1 --port !PORT! --workers 1`，并在 `setlocal` 后加 `set "WEB_CONCURRENCY=1"`。
- `Dockerfile`：`CMD` 增加 `"--workers","1"`，并加 `ENV WEB_CONCURRENCY=1`。

## 3. 盯盘清单（每 5 分钟一轮）

```bat
curl -s http://127.0.0.1:8002/api/status
:: 绿：{"status":"ok","vector_db":"inmemory","collection_size":2083,"llm_available":true}
curl -s http://127.0.0.1:8002/metrics | findstr http_requests_in_flight
```

| 指标 | 绿线 | 红线（连续 2 次）|
|---|---|---|
| `collection_size` | `>0`（理想 2083）| `=0` → 回滚 |
| `llm_available` | `true` | `false` → 切兜底/停演示 |
| `http_requests_in_flight` | `<50` | `>200` 且涨 → 卡死排查 |
| `/metrics` `5xx` 计数 | 持平 | 突增 → 看 uvicorn 日志 |

## 4. 备用机切换

- **预热**：演示前在备用机同目录跑一次 `guardian.bat`，确认 `status` 绿后正常关闭（InMemory 每次启动从种子重建，无状态迁移）。
- **切换**：主机关键失效（端口死、5xx 雪崩、LLM 双通道断）时，备用机 `guardian.bat` 拉起，把裁判浏览器指向 `http://<备用机LAN-IP>:8002`。dev CORS 正则已含 LAN，无需改配置。

## 5. 回滚

InMemory + SQLite(`data/pg_fallback.db`) 每次启动自重建，**回滚=停旧启新**：`taskkill /PID <PID> /F /T` → `guardian.bat`。数据零损失（知识来自种子+教材，会话/用户来自 SQLite 回退）。

## 6. 故障速查

- 端口被占：重复第 1 步 `netstat/taskkill`。
- `WEB_CONCURRENCY` 告警：确认 `guardian.bat`/`Dockerfile` 已加 `--workers 1`。
- 知识为空：删 `data/pg_fallback.db` 与 `milvus_lite_data` 后重启，触发重新种子。
- LLM 断：先确认 `.env` 中 `XF_*` 与 `DEEPSEEK_API_KEY` 存在；X2 主断会自动走 DeepSeek。
