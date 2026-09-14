# ADR-007 — 导入队列服务化（进程内导入 Worker + 单写者）

- **状态**：Accepted（已落进生产，单写者约束生效）
- **日期**：2026-07-11
- **更新**：2026-09-14 由 Proposed 提升为 Accepted（验收证据见下）
- **作者**：Archi（系统架构师）
- **相关**：2026-07-08 P0 事故根因；Q5（filelock 并发写）、Q6（批量延迟落盘）修复；`import_guard` 跨进程守卫；ADR-008（并发与水平扩展）；ADR-011/015
- **归位说明**：本 ADR 正文原存于 `archive/`（被 `.gitignore` 忽略、非版本受控）；2026-09-14 归位至 `docs/adr/` 规范目录（archive/ 旧副本保留不动，符合只读+追加红线）。

## 验收证据（2026-09-14）

- 跨进程写锁缺陷已修：`py-server/services/import_worker.py:127` 由原 no-op（`acquire(blocking=False)`，等同未加锁）修为**真阻塞** `self._writer_lock.acquire(blocking=True, timeout=2)`；`lifespan` 启动期持锁。
- CI gate：`pytest -m import_queue` → **13 passed / 1 xfailed**（`main.py:262-278` CLI/env workers 解析 fail-fast）。
- 运行约束三重兜底：`main.py:720` `uvicorn.run(..., workers=1)` + `main.py:262-278` env/CLI `UVICORN_WORKERS > 1` 直接 `raise` + import_worker filelock 真阻塞。
- 新代码未引入第二写者：career 线走独立 `db.career_store`，不写 `vectordb`（见 ADR-015）。

---

## 0. 结论速览（TL;DR）

- **决策**：把"读文件 → 解析 → 分块 → embedding → insert"全部收编进后端进程，由一个**进程内 `asyncio` 导入队列 + 单消费者 Worker** 在后端进程内串行执行。后端成为向量库的**唯一写者（single writer）**，从根上消除"导入脚本 vs 在线后端"的跨进程 last-writer-wins。
- **不引入** RabbitMQ / Celery 等外部中间件（模块化单体，避免过度工程）。
- **保留** 现有 E5 embedding、分块、PDF/docling/textbook 解析逻辑，仅重构为可被后端 import 的**无副作用共享模块**。
- **import_guard.py 可废弃**：它只挡"导入器 vs 导入器"，而导入器进程被彻底移除后，已无跨进程导入场景；`InMemoryVectorStore._save` 内部的 filelock 保留作纵深防御。
- **硬约束**：`uvicorn ... --workers 1`（单进程）。多 worker 会重新引入多进程 last-writer-wins —— 本方案只在单进程下成立。
- **导入脚本最终形态**：改为"提交 job 的 CLI 客户端"（POST 到后端 API + 轮询状态），或直接由前端 Admin 面板触发；脚本本身**不再接触向量库**。

---

## 1. 背景（Background）

### 1.1 现状（已确认代码）
- 向量库封装：`db/milvus_client.py` 中的 `VectorDB`（`vector_db` 模块级单例），底层 `InMemoryVectorStore`（开发期）或 Milvus（生产）。
- 关键接口（已读源码确认签名）：
  - `VectorDB.insert(collection_name, chunks, save=True) -> int`：InMemory 路径透传 `save` 给 `InMemoryVectorStore.add`（默认 `save=True` 即时落盘；批量设 `False` + 末尾 `flush()`）；Milvus 路径忽略 `save`、`flush` 为 no-op。
  - `VectorDB.flush(collection_name=None)`；`VectorDB.count`；`VectorDB.delete_by_ids`；`VectorDB.get_all_metadata(collection_name, filter_dict=None)`。
  - `InMemoryVectorStore.add(name, ids, texts, metas, embeddings, save=True)`：直接 `coll["ids"].extend(...)` 并（可选）`_save()`。**不按 id 去重**。
  - `_save()` 用 `threading.Lock`（`_save_lock`）+ `filelock`（`_file_lock`，跨进程，timeout=30s）保护落盘；`_load()` 损坏时备份原文件防静默覆盖。
- **在线写路径**（全部在 `api/knowledge.py`，`require_admin`）：`/upload`、`/upsert`、`/batch-commit`、`/reindex`、`/clear`、`/delete`。它们**同步**调用 `vector_db.insert(...)`，运行在事件循环线程。
- **独立导入进程**（3 个脚本）：`import_pdfs.py` / `import_docling.py` / `import_textbook.py`，各自 `if __name__ == "__main__"` 中调用 `acquire_import_lock()`，然后 `vector_db.insert(save=False)` + `flush()` 写 `netlearn_kb` 集合。

### 1.2 问题根因（为什么现有修复不够）
- 后端（`main.py`，uvicorn 端口 8002）与三个导入脚本是**两个独立进程**，各自持有一份 `InMemoryVectorStore` 内存视图。
- 导入脚本的 `insert(save=False)` + `flush()` 直接改写 `netlearn_kb.json`。后端在线时若跑导入脚本，二者各自 `_save()` 时互相覆盖（last-writer-wins），且 `InMemoryVectorStore.add` / `delete_by_ids` 对内存列表的变更**未在 `_save_lock` 之外加锁**，跨线程/跨进程并发会损坏内存结构。
- `import_guard.py` 的 `acquire_import_lock()` **只挡"两个导入脚本同跑"**（PID + filelock 互斥），**挡不住"导入脚本 vs 在线后端"**。这正是历史 QA 报告注明的残留缺口："导入器 vs 在线服务并发仍未互斥…彻底解法见 ADR-007（导入队列服务化）"。

### 1.3 设计目标
使**后端成为向量库的唯一写者**：导入任务通过 API 提交给后端，由后端内部后台 worker 在**后端进程内**完成全链路写入，全程只有后端这一份内存视图在操作 store。

---

## 2. 决策（Decision）

**采用「进程内导入队列 + 单写者」架构**：
1. 新增模块 `services/import_worker.py`，在 `main.py` 的 `lifespan()` 中拉起，进程内常驻。
2. 导入逻辑（解析/分块/embedding/insert）全部在后端进程内执行，由单个消费者协程串行驱动。
3. 所有对向量库的**变更**（Worker 的导入 + 在线的 `/upload` `/upsert` `/batch-commit` `/reindex` `/clear` `/delete`）统一经过同一把 `asyncio.Lock` 串行化。
4. 文件落盘语义复用既有 `save=False` + checkpoint `flush()`（Q6 批量机制），不重写。

### 2.1 备选方案对比

| 方案 | 是否消除 LWW | 复杂度 | 外部依赖 | 在线可用性 | 结论 |
|------|------------|--------|---------|-----------|------|
| **A. 进程内导入队列 + 单写者（采纳）** | ✅ 彻底（同一进程同一份内存视图） | 中 | 无（仅 asyncio + ThreadPoolExecutor） | ✅ 解析/embedding 卸载线程池，事件循环不冻结 | **采纳** |
| B. 保留独立脚本 + 全局文件锁 | ❌ 不彻底（两进程内存视图仍独立，flush 互覆盖） | 低 | filelock（已有） | ✅ | 已被证伪（即当前根因） |
| C. 引入 Celery/RabbitMQ 任务队列 | ✅ | 高 | 消息中间件 + broker | ✅（但过度工程） | 否决：单体规模不需要 |
| D. 导入时强制停服（运维约束） | ✅ 但靠人 | 极低 | 无 | ❌ 导入期间服务不可用 | 否决：不可靠、易误操作 |
| E. 数据库级乐观并发（Milvus 版本号/条件写） | ⚠️ 仅 Milvus 有效 | 高 | 依赖存储特性 | ✅ | 否决：InMemory 不支持，且与"单写者"目标不符 |

**为何选 A 而非 C**：模块化单体、团队规模小、导入是低频特权操作，进程内 `asyncio.Queue` + 单消费者足以满足，引入 broker 显著增加运维面。

---

## 3. 高层设计（High-Level Design）

### 3.1 架构图

```
                          ┌──────────────────────────────────────────────┐
                          │           后端进程 (uvicorn --workers 1)        │
                          │                                                │
   Admin (前端 / CLI)     │   ┌──────────── FastAPI 路由 ──────────────┐   │
        │  POST /imports  │   │ /knowledge/* (在线写: upload/upsert/..) │   │
        │  GET  /imports  │   │ /imports/*    (提交/查询导入 job)       │   │
        ├─────────────────┼──▶│        │                    │            │   │
                          │   └────────┬────────────────────┬────────────┘   │
                          │            │ 所有 store 变更      │ 提交 job        │
                          │            ▼                     ▼               │
                          │   ┌─────────────────┐   ┌──────────────────────┐ │
                          │   │ asyncio.Lock    │   │  asyncio.Queue        │ │
                          │   │ (单写者串行化)   │   │  (job 队列)            │ │
                          │   └────────┬────────┘   └───────────┬──────────┘ │
                          │            │                         │            │
                          │            │            ┌────────────▼─────────┐ │
                          │            │            │ 单消费者协程 _consume  │ │
                          │            │            │  (一次处理一个 job)     │ │
                          │            │            └────────────┬─────────┘ │
                          │            │          CPU 重活卸载到   │           │
                          │            │          ThreadPoolExecutor          │
                          │            │              │   │   │               │
                          │            └──────────────┼───┼───┼───────────────┘
                          │                           ▼   ▼   ▼
                          │                 解析→分块→embed→insert(save=False)
                          │                           │
                          │                           ▼
                          │                  VectorDB (vector_db 单例)
                          │                  ├─ InMemoryVectorStore (+filelock 纵深防御)
                          │                  └─ Milvus (生产)
                          └──────────────────────────────────────────────┘
```

### 3.2 新模块 `services/import_worker.py` 的职责
- 持有：`asyncio.Queue`（job 队列）、单消费者 `Task`、共享 `asyncio.Lock`（`_store_lock`）、`jobs: dict[str, ImportJob]`（状态表）、当前事件循环引用。
- 对外方法：
  - `async def start()`：在 `lifespan` 启动期调用，`asyncio.get_running_loop()` 绑定循环，`create_task(self._consume())` 拉起消费者。
  - `async def stop()`：`task.cancel()` + `await task`，优雅退出（不强制丢弃正在处理的 job；见 §6 持久化）。
  - `async def submit(spec, submitted_by) -> job_id`：创建 job、登记、入队、返回 id。
  - `def get_job(job_id) / list_jobs(status=None)`：状态查询（供 API 调用）。
  - `async def write_store(fn)`：**统一写入口**——`async with self._store_lock: return await loop.run_in_executor(None, fn)`。在线写端点与 Worker 都经此入口，保证串行化（§3.5）。
- 内部：`_consume()` 循环 `await queue.get()` → `_run(job)` → 解析/embedding/insert（均卸载线程池）→ 更新状态 → `queue.task_done()`。

### 3.3 任务队列数据结构（job spec）
内部用 `dataclass`，API 用 pydantic 请求体。

```python
# 提交规格（API 入参）
class ImportSubmitRequest(BaseModel):
    type: Literal["pdf", "docling", "textbook"]
    source: Optional[str] = None        # "scan"=扫描 documents/教材；或显式文件路径
    file: Optional[UploadFile] = None   # 直接上传文件（替代本地路径）
    params: ImportParams = ImportParams()

class ImportParams(BaseModel):
    rebuild: bool = False               # True=先清该 type 旧数据再导入
    use_ocr: bool = False               # PDF 扫描版 OCR
    max_pages: int = 100                # docling 页数上限
    subject_filter: Optional[str] = None

# 内部 job 状态
@dataclass
class ImportJob:
    id: str
    type: str
    spec: dict
    submitted_by: str
    status: str = "queued"              # queued|running|succeeded|failed|cancelled
    progress: dict = field(default_factory=dict)  # total_files/processed/total_chunks/inserted/current_file
    error: Optional[str] = None
    created_at / started_at / finished_at: float
```

### 3.4 Worker 生命周期（在 `lifespan` 中）
`main.py` 的 `lifespan()`（第 70–140 行）：在 `vector_db.connect()` 之后、yield 之前拉起：

```python
# lifespan 启动段（vector_db.connect() 之后）
from services.import_worker import import_worker
await import_worker.start()     # 绑定当前事件循环 + create_task(_consume)

yield   # ← 应用服务中

# 关闭段（yield 之后）
await import_worker.stop()      # cancel + await 消费者
```

- 单例 `import_worker = ImportWorker()` 放在 `services/import_worker.py` 模块级，路由与 worker 共享同一实例。
- 消费者是**单协程** → 同一时刻只有一个 job 在跑 → 天然串行，避免 store 并发。
- 重活（解析/embedding）在消费者内 `await loop.run_in_executor(None, ...)` 卸载到线程池（§6.1）。

### 3.5 单写者保证（为何 asyncio 单线程下仍需锁）
**直觉误区**：asyncio 单线程，代码不 `await` 就不会被抢占，那还需要锁吗？
**需要，原因有二**：
1. **Worker 的重活被故意卸载到线程池**（`run_in_executor`）。一旦解析/embedding 在**另一条 OS 线程**执行并调用 `vector_db.insert`，它就会与事件循环线程里的在线 `vector_db.insert`（如 `/upload`）**真正并发**地修改 `InMemoryVectorStore` 的内存列表（`coll["ids"].extend` / `np.vstack` / `delete_by_ids` 的切片重建）——`InMemoryVectorStore` 只在 `_save` 上有 `threading.Lock`，**`add`/`delete` 对内存结构的变更本身无锁**，跨线程即数据竞争。
2. **串行化 `_save`**：即便只关心落盘，也需要保证"一次只写一个完整快照"，避免两处写入交错产生半截 JSON。

**方案**：所有 store 变更（Worker + 在线端点）统一经 `asyncio.Lock`：
```python
# 在线端点（api/knowledge.py）改造示例
async with import_worker.store_lock:
    inserted = vector_db.insert(COLLECTION_NAME, chunks)   # 同步调用，持锁期间不 yield，原子
# Worker 侧
async with self._store_lock:
    await loop.run_in_executor(None, self._insert_chunks, chunks, job)
```
- 锁由事件循环协程持有，跨 executor 调用期间不释放 → 同一时刻只有一个写事务（无论来自事件循环线程还是线程池线程）。
- **`--workers 1` 硬约束**：`asyncio.Lock` 是**进程内**的。若 `uvicorn --workers N (N>1)`，每个进程有独立循环、独立锁、独立 `InMemoryVectorStore` → 多进程 again → last-writer-wins 重现。故**运行约束必须是单进程**；建议在 `lifespan` 启动期检测并 `logger.warning`（或断言）提醒。`reload` 模式仅父进程做监控、子进程单实例服务，不受影响。

### 3.6 任务状态的存储与查询
- **MVP（推荐）**：`jobs: dict` 内存存储，API 经 `get_job` / `list_jobs` 查询。重启即清空——可接受，因：
  - 数据本身由 `InMemoryVectorStore` 的 checkpoint `flush()` 周期落盘（每 10 批一次），崩溃最多丢最后未 flush 的一批 chunks，而非整库。
  - 导入是低频特权操作，运维更关心"数据是否进库"（查 `count` / `/knowledge/list`），而非"job 历史"。
- **可选增强（stretch）**：追加写 journal 文件 `vectordb_data/import_jobs.json`（append-only），重启时把 `running` 标记的 job 置为 `failed/cancelled`，便于审计。不阻塞 MVP。

---

## 4. API 设计

建议新增**独立路由文件** `api/imports.py`（`imports_router`，prefix `/imports`），需同步在 `api/__init__.py` 增加 `from api.imports import router as imports_router` 并在 `main.py` 的 `import` 列表与 `_all_routers` 中登记（与现有路由接入方式一致，改动局部）。

| 方法 & 路径 | 权限 | 请求体 / 参数 | 响应 | 说明 |
|---|---|---|---|---|
| `POST /api/imports/submit` | `require_admin` | `ImportSubmitRequest`（type/source/file/params） | `{job_id, status}` | 提交单个导入任务（pdf/docling/textbook）。支持直接上传文件或指定路径/`scan` |
| `POST /api/imports/scan` | `require_admin` | `{type?, use_ocr?, max_pages?}` | `{job_ids: [...]}` | 便捷：扫描 `documents/教材`，按文件/科目拆分为若干 job 提交 |
| `GET /api/imports/jobs` | `require_admin` | `?status=running`（可选） | `{jobs: [ImportJob...]}` | 列出任务（可按状态过滤） |
| `GET /api/imports/jobs/{job_id}` | `require_admin` | — | `ImportJob`（含 progress/error） | 查询单任务进度 |
| `POST /api/imports/jobs/{job_id}/cancel` | `require_admin` | — | `{status}` | **可选/stretch**：协作式取消（在当前文件处理完的间隙检查取消标志；无法中断正在进行的 blocking `model.encode`） |

**权限**：复用 `shared/auth.py` 的 `require_admin`（`user: dict = Depends(require_admin)`，校验 `role=="admin"`），与既有 `/knowledge/*` 写端点一致，保持导入为特权操作。

**`import_guard.py` 是否还需要 —— 结论：可废弃**
- `import_guard.acquire_import_lock()` 仅在三个脚本的 `__main__` 调用（grep 全仓确认无任何 CI/subprocess/其他调用）。
- 本方案移除"独立导入进程"，`acquire_import_lock` 已无防护对象；其 PID/filelock 互斥逻辑可删除。
- `InMemoryVectorStore._save` 内部的 `filelock`（跨进程锁）**保留**作纵深防御（例如未来有人临时直跑脚本、或误起多后端实例时仍不互毁）。
- 行动项：迁移完成后从脚本入口删除 `acquire_import_lock()` 调用，并归档/删除 `import_guard.py`。

---

## 5. 现有解析逻辑复用方案

### 5.1 目标
把三脚本里的**纯解析函数**抽成后端可 import 的**共享模块 `services/ingest`**（或 `services/ingest.py`），**严禁顶层副作用**：不得调用 `vector_db.insert/connect`、`acquire_import_lock`、`embed_batch`，也不得有 `__main__` 运行块。

### 5.2 抽取清单（已读源码定位）
- **来自 `import_pdfs.py`**：`extract_text_from_pdf`、`extract_text_from_pdf_ocr`、`extract_text_from_pptx`、`extract_text_from_docx`、`extract_text_from_doc`、`semantic_chunk`（PDF 版，max_chars=600）、`detect_subject`、`extract_chapter`、`SUBJECT_MAP`、`FILENAME_SUBJECT_RULES`。
- **来自 `import_docling.py`**：`convert_with_docling`（含降级 Tesseract OCR）。
- **来自 `import_textbook.py`**：`extract_pdf_text`、`detect_chapter`（关键词章节映射版）、`find_pdfs`、`SUBJECT_CHAPTERS`、`TEXTBOOKS`。
- **统一 `semantic_chunk`**：三处实现略有差异（PDF 600 / textbook 800 / knowledge.py `_semantic_chunk` 800），建议收敛为一个带 `max_chars`/`mode` 参数的 canonical 函数，更新调用方。清理属 nice-to-have，MVP 可暂保留各自版本。
- **embedding 留在 Worker**：共享模块只返回 `text/chunks`，embedding 由 Worker 在持锁写入口前统一调用 `db.embedder.embed_batch`（可被线程池卸载）。这保证"embedding 时机"与"持锁写入"都在后端进程内、可控。

### 5.3 避免脚本顶层副作用
- 三脚本顶层仅有常量定义 + `logging.basicConfig`（幂等、无害）+ `if __name__=="__main__"` 块。**直接 `import import_pdfs` 不会触发运行块**，故：
  - **MVP 低风险提示**：Worker 在线程池内**懒导入** `from import_pdfs import process_file, semantic_chunk, detect_subject` 等（首次跑 job 才 import，避免后端启动即加载 docling/sentence-transformers，契合 `HF_HUB_OFFLINE` 约束）。零代码重复、最快落地。
  - **推荐长期方案**：抽取为 `services/ingest` 后，删除脚本内的 `import_all`/`main`/`__main__` 及 `acquire_import_lock` 调用，脚本退化为 CLI 客户端（§6）。

---

## 6. 导入脚本的最终形态 & 风险权衡

### 6.1 导入脚本最终形态：改为"提交 job 的 CLI 客户端"
不再让脚本直接写向量库。两种触发路径：
1. **前端 Admin 面板（主要路径，推荐）**：新增"知识库导入"面板 → 选类型/上传文件/扫目录 → 调 `POST /api/imports/submit` 或 `/scan` → 轮询 `GET /api/imports/jobs/{id}` 展示进度。
2. **CLI 客户端（次要/自动化，推荐保留）**：把三个脚本合并为一个 `tools/import_client.py`：
   - 扫描 `documents/教材`；
   - 用 admin token（`AUTH_SECRET` 签发或命令行传入）`POST /api/imports/scan`；
   - 轮询状态直到 `succeeded/failed`。
   - 保留终端/CI/备份自动化的人体工学，**且完全不碰向量库**。
- 结论：脚本**不再是 writer**，而是**job 提交者**。重活（解析/embedding/insert）永远在后端 worker 内。

### 6.2 风险与权衡

| # | 风险 / 权衡 | 影响 | 缓解 |
|---|---|---|---|
| 1 | **阻塞事件循环**（PDF 解析、OCR ~3–5s/页、E5 `model.encode` 是 CPU 重活） | 若在线程池外执行，事件循环冻结 → 所有 HTTP（chat/search/`/status`）挂起，看似宕机 | **全部 CPU 重活 `await loop.run_in_executor(None, ...)` 卸载线程池**；单消费者保证一次只一个 job，避免线程耗尽 |
| 2 | **单消费者串行** → 大语料导入耗时与单线程相当 | 导入总时长未缩短 | 可接受：导入是非阻塞的（应用其余部分照常服务）；后续可"多文件并行 embedding + 串行 insert"优化 |
| 3 | **`--workers 1` 硬约束** | 多 worker 多进程 → 多写者 → LWW 重现 | `lifespan` 启动期 warning/断言提醒；运行文档明确写 `--workers 1`（`reload` 模式 OK） |
| 4 | **job 状态内存存储，重启丢失** | 重启后看不到历史 job | MVP 接受（数据由 checkpoint flush 保全）；可选 append-only journal 增强审计 |
| 5 | **失败重试** | 部分文件失败导致 job 失败 | MVP 不自动重试 → `failed` + error，管理员重提；chunk id 基于内容哈希，`rebuild` 标志先清旧 type 再导入 |
| 6 | **InMemory 不去重**（`add` 直接 extend） | 同文件重导产生重复条目 | Worker 用 `vector_db.get_all_metadata` 预建 `seen_ids` 过滤；或 `rebuild` 先 `delete_by_ids(type=...)`；Milvus 用 auto_id 天然避免 |
| 7 | **Milvus 下的行为差异** | `flush` 是 no-op；`insert` 是网络 append、不覆盖 | LWW 问题本就不发生；但仍经 worker 以获得 job 跟踪/权限/统一写路径；embedding 仍 CPU 重 → 仍需卸载线程池 |
| 8 | **内存峰值**（import_pdfs 旧 `import_all` 先累积所有文件 chunks 再统一 encode） | 大书同时驻留内存 + embeddings 列表 → 单进程 OOM 风险（与在线服务争内存） | Worker **逐文件处理**（解析→分块→embed→insert→释放），不全局累积；批次上限沿用 Q6 的 100/批 + 每 10 批 checkpoint flush |
| 9 | **取消困难** | 无法中断正在进行中的 `model.encode` | 仅支持协作式取消（文件间隙检查标志）；文档注明限制 |
| 10 | **上传文件生命周期** | Worker 读后端落盘的临时文件，需保证清理与路径安全 | 沿用 `knowledge.py` 的 `os.path.basename` 防穿越 + `finally` 删除；Worker 处理完即删临时文件 |

### 6.3 与既有在线写路径的兼容性
- `/upload`、`/upsert`、`/batch-commit`、`/reindex`、`/clear`、`/delete` **保持不变的对外行为**，仅在内部分支改为经 `import_worker.store_lock` 串行化（§3.5）。在线批量端点（如 `/upload` 的 100/批循环）亦可后续统一走 `write_store()` 以进一步提升事件循环响应——属增强，不阻塞 MVP。
- 种子数据写入（`_seed_vector_db`，`lifespan` 启动期）发生在 `import_worker.start()` 之前，且启动期无并发 job，无需持锁。

---

## 7. 影响（Consequences）

**变容易**
- 从根上消除"导入脚本 vs 在线后端"的 last-writer-wins 数据覆盖（P0 事故类根因闭环）。
- 导入有统一任务跟踪 / 权限控制 / 进度可见性。
- 运维不再需要"导入前停服"的脆弱约束。

**变困难 / 需注意**
- 解析/embedding 必须在后端进程内执行 → 后端进程内存/CPU 占用上升（与在线服务争资源）；需逐文件处理 + 线程池卸载缓解。
- 引入 `--workers 1` 运行约束（水平扩展需改架构，如未来迁 Milvus + 独立 worker 服务）。
- 单消费者串行，导入吞吐受限于单进程；大语料导入时间未缩短（但不再阻塞服务）。

**需重新审视**
- `import_guard.py`：迁移完成后废弃。
- 三个导入脚本：重构为 CLI 客户端或直接删除（由前端触发取代）。
- 运行文档：补充 `--workers 1` 约束；补充"如何触发导入"（前端面板 / CLI）。

---

## 8. 落地步骤建议（供 team-lead 编排）
1. **Cody（代码审查）**：抽查 `InMemoryVectorStore.add`/`delete_by_ids` 无锁变更的确认，确保 `asyncio.Lock` 覆盖所有写路径。
2. **Archi（本 ADR）**：定稿 `services/import_worker.py` 接口与 `api/imports.py` 契约。
3. **Dev（实现）**：抽取 `services/ingest` → 实现 worker + 路由 → 改造 `api/knowledge.py` 写端点走 `store_lock` → 改造 `main.py` `lifespan` → 改写导入脚本为 CLI 客户端 → 废弃 `import_guard.py`。
4. **Rex（SRE）**：补充运行约束（`--workers 1`）、监控（job 队列积压、导入耗时、store 写锁等待）、演练导入期间 `/status` 仍可用。
5. **测试**：在线导入与 worker 导入并发压测验证无数据丢失/重复；崩溃恢复（checkpoint）验证。
