# MARS-408「导入队列服务化」可运维性与可靠性评估（SRE 视角）

> 评估人：雷克斯（Rex）/ SRE 工程师
> 评估对象：`py-server/` 将导入逻辑从「独立脚本进程」收编进「后端进程内 asyncio worker」
> 结论基调：**方向正确（单写者架构消除 last-writer-wins），但当前代码有 3 处会直接导致数据丢失/在线服务卡死的缺陷，必须连同 worker 一起修复才能上线。**

---

## 0. 代码现状速读（已读文件证据）

| 文件 | 关键事实 | 与本次改造的关系 |
|---|---|---|
| `main.py:70-140` | `lifespan()` 目前只做 `vector_db.connect()`、种子、PG/Redis/Admin 初始化。启动段用 `asyncio.gather`，关闭段只 `disconnect()`。**完全没有导入 worker。** | worker 将在这里 `asyncio.create_task` 启动，关闭逻辑需要新增 |
| `import_guard.py` | 跨进程 PID 锁 + filelock，防止「多个导入脚本并发写 `netlearn_kb.json`」。注释明确指向 2026-07-08 P0 事故根因 | 单写者架构下，外部进程写入消失 → 该守卫应废弃 |
| `db/milvus_client.py` | `InMemoryVectorStore.add()` 在 **未持锁** 的情况下修改 `self._collections`（extend/vstack，行 115-129），仅 `_save_unlocked` 持 `threading.Lock`（行 294）；`_save` 每次**整文件重写** `netlearn_kb.json`（行 314-334）；`flush()` 强制落盘（行 131）；跨进程 `filelock` timeout=30s（行 92） | 进程内并发读写 = 真实竞态；整文件重写 = 随库增长 O(n) 写放大 |
| `import_pdfs.py` | `embed_batch` 调 E5（行 414）；写入用 `save=False` + 每 10 批(1000条) `flush`（行 385-407）；**没有去重逻辑**（chunk id = `import_{md5}`，重跑会重复插入） | 是 worker 要复用的核心逻辑；去重缺失会在回滚/重跑时造重复 |
| `import_textbook.py` | 导入前读 `netlearn_kb.json` 的 `seen_ids` 做去重（行 139-166）；按 `textbook_{subject}_{md5}` 生成 id | 去重范本，应统一到共享模块 |
| `db/embedder.py` | `model.encode()` 是 **CPU 密集型同步** 调用（行 51/59）；`SentenceTransformer` 延迟加载（行 17-44） | 若直接在事件循环里跑会阻塞全部在线请求 |
| `docker-compose.yml:24-27` | 仅挂载 `./py-server/vectordb_data`、`milvus_lite_data`、`config.json`；**`documents/` 根本没挂载**；healthcheck 打 `/api/status`（行 32-36）；`restart: unless-stopped` | 容器内 import 读不到 PDF 源；healthcheck 与阻塞 loop 冲突 |
| `Dockerfile:39,65` | `COPY py-server/ ./` → 容器内为 `/app`；CMD 单进程 `uvicorn main:app`（workers=1） | 单写者 OK；但 `import_*.py` 里 `Path(__file__).parent.parent` 在容器内 = `/`（详见维度 6） |
| `api/knowledge.py` | `/upload`、`/preview`、`/batch-commit`、`/upsert`、`/reindex`、`/clear` 均 **同步** 调 `vector_db.insert/get/delete`（行 129/173/337/350 等） | 这些在线写当前就同步阻塞 loop（大 JSON 时）；服务化后写竞争加剧 |

---

## 1. Worker 生命周期管理

**现状**：`lifespan()` 没有 worker。计划用 `asyncio.create_task` 启动协程。

**风险与建议**：

- **启动**：在 `lifespan` 的启动段（gather 之后、`yield` 之前）创建任务并保存引用：
  ```python
  app.state.import_worker = asyncio.create_task(import_worker_loop(app))
  ```
  同时做 **E5 模型预热**（`await asyncio.to_thread(_get_e5_model)`），避免首个 job 在 loop 内加载模型导致首次导入卡死在线服务。

- **优雅停止的正确姿势**——`asyncio.to_thread` 无法中断正在执行的线程，所以「cancel 掉 worker」只会取消到下一个 `await` 点，跑在线程里的解析/embedding 仍会继续。因此必须 **协作式关闭 + 文件粒度边界**：
  ```python
  shutdown_event = asyncio.Event()
  try:
      yield
  finally:
      shutdown_event.set()                 # worker 在处理完「当前文件」后主动退出
      try:
          await asyncio.wait_for(app.state.import_worker, timeout=300)
      except asyncio.TimeoutError:
          app.state.import_worker.cancel() # 兜底强杀（极少触发）
      vector_db.disconnect()
  ```
  worker 主循环每次取到一个 job 后，先 `if shutdown_event.is_set(): break`，并在每个文件处理完（已 flush 落盘）后再检查一次。

- **决策：等待当前 job 完成 or 强制中断？**
  - 推荐 **「完成当前文件后退出」**。`import_pdfs.py` 已是按文件处理（每文件 flush 一次），所以「当前文件」粒度足够小（一个 PDF 的 embedding 通常 < 1-2 分钟）。进程退出时最多丢失「正在处理的那一个文件」的未落盘 chunks，其余已 flush 数据完好。
  - **不要** 用 SIGKILL / `docker restart` 硬杀正在导入的进程——见维度 2。

- **多 worker 陷阱**：`uvicorn` 若以 `--workers N>1` 启动，会起 N 个进程、N 个 worker，每个都是独立写者，**重新引入多写者竞争**。Dockerfile CMD 目前是单 worker（OK）。**必须在部署规范里写死：服务化后禁止 `--workers>1`**；多副本只能通过「共享 Milvus + 分布式 job 归属锁」实现，不在本期范围。

---

## 2. 失败恢复与进度持久化

**核心结论（最重要的一条）**：当前 `InMemoryVectorStore` 的持久化完全依赖 `netlearn_kb.json`，而该文件只在 `flush()` 时整文件重写。**进程在两次 flush 之间崩溃，所有已 insert 但尚未 flush 的 chunks 全部丢失；且没有任何 job 状态记录，重启后既不知道“导入到哪了”，也无法自动续传。**

**具体风险**：
- 若后端被 kill（OOM、部署、Docker 健康检查失败重启）且当前 job 处于「已内存插入 800 条 / 尚未 flush」状态 → 重启后 `_load` 只读到上一次 flush 的内容，这 800 条**静默丢失**。
- `import_pdfs.py` 无去重，崩溃后重跑会把整批重新 `import_{md5}` 插入 → **重复文档**（InMemoryVectorStore 的 `extend` 不查重）。`import_textbook.py` 有 `seen_ids` 去重，相对安全。
- job 状态只存在于 worker 内存，进程一死即蒸发，运维无从判断「是成功、失败还是卡死」。

**建议方案**：
1. **job 状态落盘**：新增 `vectordb_data/import_jobs/<job_id>.json`，字段见维度 4。每次「处理完一个文件 / 一次 flush」后原子写盘（临时文件 + `os.replace`，沿用 `_save_unlocked` 的写法）。
2. **细粒度 checkpoint**：把 `flush` 从「每 1000 条」改为 **每处理完一个文件 flush 一次**（与维度 1 的「文件粒度退出」对齐），把崩溃数据丢失窗口压缩到「单个文件」。
3. **重启自愈**：`lifespan` 启动时扫描 `import_jobs/`，把所有 `status=running` 的 job 标记为 `interrupted`（因为进程刚死过），并可选「自动加入队列重试」——重试前必须保证 chunk id 幂等（见下）。
4. **幂等 chunk id 统一**：所有导入路径（pdf/docling/textbook/上传）统一用 `hashlib.md5(规范文本)` 作 id，且 `insert` 时做「已存在则跳过/覆盖」而非无脑 append。这是回滚重跑不造重复的前提。
5. **生产路径用 Milvus**：Milvus 服务端持久化，insert 天然落盘，崩溃丢失窗口远小于 JSON 全量重写方案。服务化 + 生产部署应强制 `milvus.enabled=true`。

---

## 3. 事件循环阻塞风险

**现状**：`extract_text_from_pdf`（PyMuPDF，CPU/IO）、OCR（Tesseract，3-5s/页，`import_pdfs.py:128`）、`model.encode`（E5，CPU，`embedder.py:51/59`）、`vector_db.insert/flush`（numpy vstack + 整文件 JSON dump，`milvus_client.py:314-334`）**全是同步阻塞函数**。

**若直接在 asyncio worker 协程里调用** → 单一事件循环被占满 → 所有在线请求（聊天 `/chat`、检索、甚至 `/api/status` 健康检查）全部卡死。这正是 `main.py:9-13` 注释里描述的「reranker 阻塞 loop 90s 致后端无响应」同类事故。

**建议（具体落地）**：
```python
# worker 内所有重活都卸到线程池
executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)  # 限制并发，给在线请求留 CPU

async def run_job(job):
    text = await asyncio.to_thread(extract_text_from_pdf, job.path)     # 解析
    chunks = await asyncio.to_thread(semantic_chunk, text)             # 分块(轻)
    async with embed_sem:                                              # 序列化 embedding
        embs = await asyncio.to_thread(embed_batch, [c["text"] for c in chunks])
    await asyncio.to_thread(vector_db.insert, name, chunks, save=False)
    await asyncio.to_thread(vector_db.flush, name)                     # 文件级 checkpoint
```
- 用 **`asyncio.to_thread`（或 `loop.run_in_executor(executor, ...)`）** 包裹每一个阻塞阶段。
- **embedding 串行化**：`SentenceTransformer.encode` 在 CPU 上并发不安全且会抢满核心，用 `asyncio.Semaphore(1)` 包住 embed 调用，避免多文件并行编码。
- **限制并发度**：固定一个 2 线程的 `ThreadPoolExecutor`，不要把所有 PDF 都丢进线程池——否则 CPU 跑满，在线检索延迟飙升。
- **在线写端点同样要卸线程**：`/upload`、`/upsert`、`/batch-commit` 目前是 async 函数里直接同步调 `vector_db.insert(save=True)`，本就会在大 JSON 上阻塞 loop（latent bug）。服务化后务必统一把这些写入也用 `to_thread` 包起来，**并让 import 与在线写共用同一个 executor**，从根本上串行化全部写操作、消除竞态（见维度 3 延伸 + 维度 6）。
- **内存**：embedding 阶段先把整批 texts 攒在内存再 encode，超大 PDF 可能内存尖峰。建议按文件、分批（≤256 条/批）encode+insert，控制驻留。

---

## 4. 监控与可观测性

**现状**：无任何 job 状态接口，只有 `logging.info` 打 stdout；运维无法知道「导入到哪、是否卡住、为何失败」。

**建议新增接口**（挂在 `/api/knowledge/import/*`，admin 鉴权）：
- `POST /api/knowledge/import/submit` —— 提交导入任务（按目录 / 按文件 / 上传），返回 `job_id`
- `GET  /api/knowledge/import/jobs` —— 列出所有 job
- `GET  /api/knowledge/import/jobs/{job_id}` —— 单 job 详情
- `POST /api/knowledge/import/jobs/{job_id}/cancel` —— 取消（协作式，处理完当前文件后停）

**job 状态应暴露的字段**：
```
job_id, submitted_by, submitted_at,
status: queued|running|paused|completed|failed|interrupted|cancelled,
source: {type: pdf_dir|file|upload|url, path/url},
subject_filter, total_files, processed_files,
total_chunks, inserted_chunks, failed_files: [path, reason],
current_stage: scanning|parsing|embedding|inserting|flushing,
progress_pct,
error_message,
heartbeat_at,            # 最近活动时间戳，用于判断卡死
worker_pid, started_at, finished_at
```
- **卡死探测**：若 `heartbeat_at` 超过 N 分钟无更新（且 status=running），或 `current_stage` 长时间不前进 → 告警。用 worker 每次循环/每文件处理写 `heartbeat_at`。
- **日志规范**：统一前缀 `[import][job=<id>][stage=<parsing|embedding|inserting>]`，每个文件处理完打一行 checkpoint（已插入数 / 累计 / 耗时）。现有 `import_pdfs.py` 的 `logger.info` 风格可保留但需加 job_id 维度。
- **`/api/status` 增强**：返回 `import_worker: alive|down`、`active_import_jobs: N`，让健康检查与运维面板一眼可见。
- **指标（可选）**：若接 Prometheus，加 `import_jobs_total`、`import_chunks_inserted`、`import_active` gauge。至少用计数器统计失败 job。

---

## 5. 彻底消除「停服务→导入→重启」

**结论：单写者架构下，理论上可以不再停服务，导入随时可在线进行。✅ 但前提是维度 3（不阻塞 loop）和维度 6（路径/挂载）都修好，否则“在线”会变成“在线但卡死/读不到文件”。**

- 改造后唯一写者是后端进程内的 worker，不再有独立导入脚本进程 → 彻底消除跨进程 last-writer-wins（`import_guard.py` 文档里描述的 P0 根因）。
- **`import_guard.py` 是否可以删除？** 可以，但**分两步**：
  1. 短期（过渡期）：保留 `import_guard.py` 与三个 `import_*.py` 作为**遗留回滚通道**（见维度 7），但明确「禁止在后端运行时手动跑脚本」。此时 `import_guard.py` 的跨进程锁仍有价值——万一有人误跑旧脚本，它能拦住，避免二次 P0。
  2. 稳定后：删除 `import_pdfs.py` / `import_docling.py` / `import_textbook.py` 与 `import_guard.py`，把它们的核心逻辑抽到共享模块 `db/importer.py`，**仅由 worker 与回滚脚本 import**。
- **`milvus_client.py` 里的 `filelock`（`_file_lock`）**：单写者下已无跨进程写者，该锁理论多余；但它现在还承担着「import 的 flush」与「在线 upsert 的 save=True 全量重写」之间的串行化（见维度 6）。在把所有写统一到单一 executor + 单一线程前，**先保留 filelock**，待写路径收敛后再移除，避免留下竞态窗口。

---

## 6. Docker 部署影响（现状问题清单）

**问题 1（致命）：`documents/` 没挂载，容器内读不到 PDF。**
`docker-compose.yml:24-27` 只挂了 `vectordb_data`/`milvus_lite_data`/`config.json`。教材源 `documents/教材/` 在仓库根目录，**完全没挂进容器**。服务化后 import 在容器内跑 → 找不到任何 PDF。
→ 修复：新增 `- ./documents:/app/documents:ro`（只读），并在 `import_*` 里把 `DOCS_DIR` 改为**容器感知**：
```python
DOCS_DIR = Path(os.environ.get("DOCS_DIR", str(Path(__file__).parent.parent / "documents" / "教材")))
```
注意：现有 `PROJECT_ROOT = Path(__file__).parent.parent` 在容器内 = `/`（因为 `/app` 是 py-server 内容，其 parent 是 `/`），**当前路径计算在容器里会解析成 `/documents/教材`（不存在）**——这是必须在服务化时顺手修掉的 bug。

**问题 2（致命）：健康检查与阻塞 loop 互相伤害。**
`docker-compose.yml:32-36` 的 healthcheck 打 `/api/status`。若实现不当（维度 3 没做）导致 loop 被 import 阻塞 → `/api/status` 超时 → 连续 3 次失败 → Docker 按 `restart: unless-stopped` **杀掉并重启容器** → 正在进行的导入被杀 → 数据丢失（维度 2）→ 若 job 状态没落盘还会反复重启。
→ 修复：① 确保 loop 永不被 import 阻塞（维度 3）；② import 期间给 healthcheck 留余量（或 healthcheck 只探「进程存活」而非「loop 空闲」）；③ 大导入期间考虑临时 `docker update --restart=no` 或提高 healthcheck 容忍。

**问题 3：在线写与导入写在同一份大 JSON 上抢锁。**
`InMemoryVectorStore._save` 对每次写都用 `filelock` timeout=30s（行 92）。导入 flush（整文件重写 13MB+，且随库增长）与在线 `upsert`/`batch-commit`（`save=True` 每次全量重写）会互相阻塞；若某次 flush 持锁过久，在线写可能 30s 超时被判失败并**静默丢弃**（见 `milvus_client.py:300-304`）。
→ 修复：在线写也卸到线程（维度 3）+ 所有写共用单一 executor 串行化；生产环境切 Milvus（无此问题）。

**问题 4：OCR / Docling 在容器内不可用。**
`Dockerfile` 基于 `python:3.12-slim`，未装 `tesseract`/`pytesseract`，也未装 `docling`。容器内 import 只能走 PyMuPDF + python-docx 的路径；扫描版 PDF（需 OCR）和 Docling 解析会失败降级。
→ 要么在 Dockerfile 装依赖（tesseract + docling，体积/构建成本上升），要么明确「容器内仅支持文字版 PDF/DOCX/TXT，扫描版走宿主机 legacy 脚本」。

**问题 5（信息项）：E5 模型路径在容器内 OK。**
`config.py:107` 把 `local_model_repo` 解析为 `CONFIG_DIR/models/e5-base-v2`，容器内 `CONFIG_DIR=/app`，且 Dockerfile `COPY py-server/ ./` 已把 `models/` 拷进 `/app`。所以 embedding 在容器内可用（前提是 `models/e5-base-v2` 已存在且 `sentence-transformers` 在依赖里）。需确认 `pyproject.toml` 含 `sentence-transformers`、`pymupdf`、`python-docx`。

---

## 7. 回滚方案

**目标**：新 worker 出 bug 时，能快速、低风险退回「独立脚本导入」模式，且不丢数据。

**推荐回滚设计**：
1. **开关（kill-switch）**：新增环境变量 `ENABLE_IMPORT_WORKER`（默认 `true`）。置 `false` 时，`lifespan` 不启动 worker，`/api/knowledge/import/*` 端点返回 `503 Service Unavailable (legacy mode)`。
2. **共享核心逻辑**：把 `process_file` / `semantic_chunk` / `embed_batch` / `vectordb.insert` 抽到 `db/importer.py`，让 worker 与遗留脚本**共用同一份代码**。这样「关掉 worker → 停后端 → 跑 `import_textbook.py`（带 `import_guard`）→ 起后端」这条旧路径依然有效，且语义一致。
3. **数据无需回滚**：由于 chunk id 幂等（维度 2.4），代码回滚不要求数据回滚。若某次 buggy import 污染了 `netlearn_kb.json`：
   - 小损：用 `_load` 的损坏备份机制（`milvus_client.py:354-369` 会把坏文件改名 `.corrupted.*`）恢复；
   - 大损：从定期快照（`cp vectordb_data/netlearn_kb.json` 到备份目录，建议在 import 前自动做一次）恢复。
4. **容器化回滚**：Docker 镜像按 tag 发布（如 `netlearn:1.4.0` / `netlearn:1.3.0-legacy`），出问题时 `docker-compose up -d` 切回上一 tag 即可，无需改代码。
5. **运维 SOP**：见下方 Runbook「回滚」段。

---

## 导入运维 Runbook 要点（改造后）

**触发导入**
- 常规：运维/管理员在 Admin 面板或 `curl -X POST /api/knowledge/import/submit -d '{"source":{"type":"pdf_dir","path":"/app/documents/教材"}}'` 提交；返回 `job_id`。
- 上传单文件：走现有 `/knowledge/upload` 或新 `/import/submit` 的 `upload` 类型。
- 提交后**立即** `GET /api/knowledge/import/jobs/<job_id>` 确认 `status=running`、看到 `heartbeat_at` 在更新。

**查看进度 / 是否卡住**
- `GET /api/knowledge/import/jobs` 看全局；`GET .../jobs/<job_id>` 看单 job 的 `progress_pct`、`current_stage`、`processed_files/total_files`、`heartbeat_at`。
- 卡死判定：`heartbeat_at` 距 now > 5 min 且 `status=running` → 视为卡死，先查日志 `[import][job=...]`。
- 全局健康：`GET /api/status` 看 `import_worker: alive`、`active_import_jobs`。

**排查失败**
- `status=failed` / `interrupted`：读 `error_message` 与 `failed_files`（含每文件失败原因）。
- 常见原因：PDF 解析失败（扫描版未 OCR）、E5 模型未加载（离线环境 `HF_HUB_OFFLINE=1` 已设，需本地 `models/e5-base-v2` 存在）、OOM、`vectordb_data` 磁盘满、`filelock` 30s 超时丢写（见维度 6.3）。
- 日志：`docker logs -f <container>` 或宿主机 `tail -f` 后端日志，过滤 `[import]`。

**取消**
- `POST /api/knowledge/import/jobs/<job_id>/cancel` → worker 在处理完当前文件后停止，已 flush 数据保留。
- 紧急停：停服务（`stop.bat` / `docker stop`）会触发维度 1 的优雅退出（完成当前文件后退出）。

**回滚**
1. 置 `ENABLE_IMPORT_WORKER=false`，重启后端 → 关闭新 worker。
2. 停后端 → 运行遗留 `import_textbook.py`（仍带 `import_guard` 跨进程锁兜底）→ 起后端。
3. 或容器：`docker-compose up -d` 切回上一镜像 tag。
4. 数据恢复：从 `vectordb_data/` 的定期快照或 `.corrupted.*` 备份恢复。

**上线前必做检查**
- [ ] worker 在 `lifespan` 启动、`shutdown_event` 协作式退出（维度 1）
- [ ] 所有阻塞调用（解析/OCR/embed/insert/flush）走 `to_thread` + 有限 executor（维度 3）
- [ ] job 状态落盘 + 重启自愈标记 `interrupted`（维度 2）
- [ ] chunk id 幂等 + insert 查重（维度 2.4，修复 `import_pdfs` 无去重）
- [ ] `documents/` 挂载 + `DOCS_DIR` 容器感知（维度 6.1）—— **致命，必须修**
- [ ] 在线写端点同样卸线程 + 与 import 共用 executor（维度 3/6.3）
- [ ] healthcheck 在导入期间不误杀容器（维度 6.2）
- [ ] kill-switch `ENABLE_IMPORT_WORKER` 到位 + 镜像 tag 化（维度 7）
- [ ] `uvicorn` 禁止 `--workers>1`（维度 1）

---

## 风险清单（按严重度）

### 🔴 P0 — 上线前必须修复（会导致数据丢失 / 在线服务不可用）

| # | 风险 | 根因（文件:行） | 后果 | 修复 |
|---|---|---|---|---|
| P0-1 | **容器内读不到 PDF 源** | `docker-compose.yml:24-27` 未挂 `documents/`；`import_*.py` 用 `Path(__file__).parent.parent` 在容器内解析为 `/` | 服务化后容器内 import 100% 失败 | 挂 `./documents:/app/documents:ro`；`DOCS_DIR` 改 env 可配 + 容器感知 |
| P0-2 | **事件循环被 import 阻塞 → 全站卡死** | `embedder.py:51/59`、`import_pdfs.py` 解析/OCR/embedding 全同步；worker 若直接 await 同步函数 | 聊天/检索/`/api/status` 全阻塞；Docker 健康检查失败 → 容器被杀 → 导入中断 | 全部 `asyncio.to_thread` + 有限 `ThreadPoolExecutor` + embed 串行 |
| P0-3 | **崩溃丢失未 flush 数据 + 无续传** | `milvus_client.py:131/314` flush 才落盘；job 状态仅存内存 | 进程在两次 flush 间崩溃 → 已插入 chunks 静默丢失、重启不知进度 | job 状态落盘 + 每文件 flush checkpoint + 重启标记 `interrupted` |
| P0-4 | **在线写与 import 抢同一大 JSON 锁 → 在线写超时丢数据** | `milvus_client.py:92/300-304` filelock 30s；在线 `upsert`/`batch-commit` 同步 `save=True` 全量重写 | import flush 持锁时在线写可能 30s 超时被判失败并丢弃 | 在线写卸线程 + 与 import 共用单一 executor 串行化；生产切 Milvus |

### 🟠 P1 — 强烈建议修复（可靠性 / 正确性隐患）

| # | 风险 | 根因 | 后果 | 修复 |
|---|---|---|---|---|
| P1-1 | **`InMemoryVectorStore` 读写竞态** | `milvus_client.py:115-129` `add()` 在**未持锁**下 mutate `self._collections`；`query()` 读也不持锁 | import 并发写 + 在线检索同时发生 → 读到半更新状态 / index 越界 | `add()` 整段包 `_save_lock`；`query` 读时也取锁或读副本 |
| P1-2 | **`import_pdfs.py` 无去重，重跑造重复** | 行 303 `import_{md5}` + `extend` 不查重 | 回滚重跑 / 误提交 → 知识库重复文档、检索污染 | 统一幂等 id + insert 查重/覆盖（学 `import_textbook.py:139`） |
| P1-3 | **健康检查误杀导入中容器** | `docker-compose.yml:32-36` healthcheck 探 `/api/status` + `restart: unless-stopped` | 若 loop 短暂繁忙，连续失败 → 容器重启 → 导入中断（叠 P0-2/P0-3） | 维度 6.2 措施；导入期放宽容忍 |
| P1-4 | **E5 首次加载阻塞 loop** | `embedder.py:17-44` 延迟加载，首个 job 触发 | 首次导入首个文件时在线服务卡顿数秒~数十秒 | `lifespan` 内预热 `_get_e5_model`（`to_thread`） |

### 🟡 P2 — 运维体验 / 技术债

| # | 风险 | 建议 |
|---|---|---|
| P2-1 | 无 job 状态接口与卡死告警 | 实现维度 4 的 `/api/knowledge/import/*` + `heartbeat_at` 探测 |
| P2-2 | `import_guard.py` 去留不清 | 过渡期保留作兜底，稳定后删除（维度 5） |
| P2-3 | OCR/Docling 容器内不可用 | Dockerfile 补依赖或明确「容器内仅文字版 PDF」 |
| P2-4 | 整文件 JSON 重写 O(n) 写放大 | 长期迁 Milvus；短期控制 KB 规模、降低 flush 频率 |
| P2-5 | 多 uvicorn worker 会重引多写者 | 部署规范写死 `--workers 1` |

---

### 一句话总结
> 单写者服务化方向对，但**必须先修 4 个 P0**（容器挂 `documents`+路径修正、全链路 `to_thread` 卸载、job 状态落盘 + 每文件 checkpoint、在线写与 import 共用串行 executor），否则会从「偶发跨进程覆盖」变成「在线卡死 + 崩溃丢数据 + 容器误杀」的更糟局面。回滚靠 `ENABLE_IMPORT_WORKER` 开关 + 共享 `db/importer.py` + 镜像 tag 化。
