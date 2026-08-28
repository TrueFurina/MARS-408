# ADR-008 — 并发与水平扩展模型（Concurrency & Horizontal Scaling Model）

- **状态**：Proposed
- **日期**：2026-07-15
- **决策人**：架构师（architect）
- **相关**：ADR-007（导入队列单写者）；ADR-012（异步任务外置，待立）；debt #1（5/5/4）、debt #2（4/4/3）

## 背景

ADR-007 强制 `--workers 1`（单写者导入队列）以避免 `import_store` 竞态。当前实现把**整个 uvicorn 进程**钉死为单 worker：`main.py:162-169` 在 `UVICORN_WORKERS > 1` 时直接 `raise RuntimeError` fail-fast。

这带来一个未被言明的副作用：进程内共享状态（如 `api/xfyun.py:28-29` 的 `_ppt_tasks` / `_video_tasks` 异步任务字典、session 缓存）与 import 单写锁一起，被绑死在单进程上。结果——**整个 API 层的吞吐与水平扩展能力被一并封死**，即便 API 请求本身无共享写冲突。

## 决策（原则性）

1. **要水平扩展，必须把进程内共享状态外置**：包括 task/session 缓存（`api/xfyun.py:28-29`）与 import 单写锁。
2. **扩展机制细节不在此 ADR 展开**，交给 **ADR-012（异步任务外置）** 定义落地方案。
3. **原则落点**：API 层允许跑 **N workers**；import 单写锁（ADR-007）收敛到**专属 import worker**，而非整个进程。即「单写者」约束只覆盖导入队列，不再绑架 API 并发。

## 影响

- **API 层**：解除 `--workers 1` 对 API 并发的封印，可随 CPU/负载水平扩容。
- **导入队列**：保留 ADR-007 单写者语义，但由专属 import worker 承载，不再要求整个进程单 worker。
- **依赖变化**：需引入 Redis + 任务队列（Celery / RQ / ARQ）以承载外置的 task/session 状态；具体选型与迁移路径见 ADR-012。

## 权衡

- **引入 Redis + 任务队列**带来额外运维成本（部署、监控、故障域）。
- 但**解锁真版水平扩展**，对应架构债 debt #1（Impact 5 / Risk 5 / Effort 4）与 debt #2（Impact 4 / Risk 4 / Effort 3），是规模化阶段的必要前置。

## 与 ADR-012 的边界

- **ADR-008** 定「**为什么**单 worker + **扩展原则**」（现状约束、外置原则、N workers 落点）。
- **ADR-012** 定「**怎么**外置异步任务」（队列选型、状态存储、worker 拓扑）。
- 两者不重复：本 ADR 不规定具体队列实现，ADR-012 不重新讨论单写者约束的必要性。

## 备选方案（被否决/待 ADR-012）

- **保持全进程单 worker**：安全但彻底放弃水平扩展，否决（真版不可接受）。
- **仅放开 API workers 而不外置状态**：多 worker 下 task/session 缓存失效、import 竞态回归，否决。
