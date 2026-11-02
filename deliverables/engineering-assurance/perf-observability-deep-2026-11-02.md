# 性能与可观测性深度验证（WS4 p95/p99 + 慢请求告警）

- 仓库：`E:\Program\MARL\study-help-pro`　分支：`merge/ws1-ws4-20261102`　HEAD：`35af837`
- 日期：2026-11-02　平台：Windows 11 / Git Bash，CPU 单机实测（未上服务器）
- 运行时：Python 3.12.10，numpy 2.4.6，starlette 1.2.1，fastapi 0.136.3
- 方法：全部为 **in-process 微基准**（不起真实 uvicorn，不跑全量 pytest）；源码**只读**，工作区 `git status --porcelain` 为空
- 临时脚本（均在 `C:/Users/Lenovo/AppData/Local/Temp/`）：`qprec_20261102.py`、`bench_tail_20261102.py`、`t3.py`、`bench_mw_20261102.py`、`bench_decomp_20261102.py`、`bench_log_20261102.py`、`bench_sse_20261102.py`、`bench_hotpath_20261102.py`、`bench_mem3_20261102.py`、`bench_metrics_ep_20261102.py`、`t4.py`、`t5.py`

> 口径声明：所有数字均为本机实测；标注「未测」的项在正文说明原因。桶内插值类误差用 `numpy.percentile`（linear）作为精确参考。

---

## 零、一句话结论

**算得基本对（p95 长跑误差 <1%，p99 有 +25%…+55% 的结构性高估），开销可忽略（记账 7 µs/请求），但「定位问题」这一项在关键路径上是失效的：5 个 SSE 端点的真实耗时被记成 0.7 ms（3 s 的流只记 0.68 ms），`/metrics` 本身又是无鉴权、无基数上限、单次可冻结事件循环 ~700 ms 的放大器。** 详见 §5。

---

## ① 分位数估计精度

被测实现：`py-server/shared/metrics.py:25`（分桶）→ `:58-73`（`record_request` 落桶）→ `:83-102`（`_approx_quantile` 桶内线性插值）→ `:159-175`（p95/p99 gauge 暴露）。

分桶（秒）：`0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0` + `+Inf`。

### 1.1 六种分布：估算 vs 精确（n=20000）

| 分布 | 精确 p95 | 估算 p95 | 误差 (ms) | 误差 % | 精确 p99 | 估算 p99 | 误差 (ms) | 误差 % |
|---|---|---|---|---|---|---|---|---|
| 均匀 U(5,800) ms | 760.4 | 933.3 | +172.9 | **+22.73%** | 791.6 | 986.7 | +195.1 | **+24.65%** |
| 正态 N(300,120) ms | 496.9 | 499.0 | +2.1 | +0.42% | 580.0 | 895.0 | +315.0 | **+54.31%** |
| 帕累托(α=1.3) 长尾 | 149.6 | 190.0 | +40.4 | +27.00% | 511.8 | 542.0 | +30.1 | +5.89% |
| 双峰 80/1800 ms | 1877.0 | 2350.0 | +473.0 | +25.20% | 1924.0 | 2470.0 | +546.0 | +28.38% |
| 离群 3% >30 s | 506.7 | 570.8 | +64.1 | +12.66% | 88903.4 | **SKIP（无指标）** | — | — |
| 全部 >30 s | 86828.1 | **SKIP** | — | — | 89469.2 | **SKIP** | — | — |

### 1.2 形状接近真实 API 的组合（90% 20–120 ms + 9% 300–900 ms + 1% 2–9 s）

| 分位 | 精确 | 估算 | 误差 |
|---|---|---|---|
| p50 | 75.6 ms | 76.0 ms | +0.50% |
| p95 | 642.0 ms | 669.4 ms | **+4.27%** |
| p99 | 909.9 ms | 1000.0 ms | **+9.91%** |

### 1.3 误差来源归因（实测）

1. **桶宽 ×2 的几何分桶 + 桶内「均匀分布」假设**：尾部在桶内是衰减的，插值会**系统性偏高**。p99 落在 `[0.5,1.0]` 或 `[1.0,2.5]` 桶时偏差稳定在 +25%…+55%，且**不随样本量收敛**（n=1e5 时 p99 仍 +54.6%）——这是偏差，不是噪声。
2. **`[10,30]` 桶宽 20 s 是最坏的绝对误差源**：94% @100 ms + 6% @10.05 s → 精确 p95 = 10 050 ms，估算 **13 333 ms（+3 283 ms，+33%）**。桶上限从 10 s 抬到 30 s，在「>10 s 的慢请求」这一段把最大绝对误差从秒级放大到**数秒级**（换来了尾部不再被截断，是合理权衡，但要写进口径）。
3. **小样本（n<50）失真严重**（同一 N(300,120)，200 次重复取中位误差）：

| n | p95 中位误差 | p95 最差 | p99 中位误差 | p99 最差 |
|---|---|---|---|---|
| 2 | +33.9% | ±93% | +35.6% | ±97% |
| 5 | +30.1% | ±92% | +30.7% | ±97% |
| 20 | +12.0% | ±65% | +60.5% | ±89% |
| 100 | +3.8% | ±40% | +58.0% | ±77% |
| 1000 | +1.4% | ±24% | +55.4% | ±63% |
| 100000 | +0.3% | ±1% | +54.6% | ±56% |

仓库自带的守护测试已经把这个偏差固化成断言：`tests/test_wave_b_sre.py:139-140` 断言 p95≈0.778 / p99=1.0。用两个样本 `[100 ms, 300 ms]` 复算：精确 p95=290 ms / p99=298 ms，**估算 475 ms / 495 ms（+64% / +66%）**。→ 该测试锁的是「当前算法行为」，不是「分位数正确性」。

**结论（精度）**：p95 在 n≥1e3 时可用于**告警**（误差 <2%，且偏保守）；但 **p99 不能用于对外报 SLO 或与 Prometheus `histogram_quantile` 对账**（结构 +55% 高估），n<20 的任何分位数都只能当「有慢请求」的二值信号看。

---

## ② 中间件每请求增量开销（in-process）

### 2.1 纯函数（200k 次平均）

| 操作 | 成本 |
|---|---|
| `record_request(path, code, lat)`（含 9 桶定位 + 5 个 dict 更新） | **0.712 µs/次** |
| `inc_inflight(±1)` | **0.461 µs/次** |

`metrics_middleware`（`app/middleware.py:155-175`）每请求调用：`inc_inflight` ×2 + `record_request` ×1 = **≈1.6 µs 记账**。

### 2.2 全链路 A/B（同一中间件栈，只差 metrics 本体；ASGI in-process，n=3000，取中位）

| 栈 | 中位 | p95 | 均值 |
|---|---|---|---|
| 无中间件 | 192.6 µs | 294.2 µs | 203.7 µs |
| 空中间件（只 `perf_counter`） | 832.4 µs | 1637.7 µs | 954.6 µs |
| 空中间件 + 记账（无日志） | 839.4 µs | 1515.5 µs | 940.0 µs |
| 完整 `metrics_middleware` | 888.0 µs | 1424.1 µs | 971.4 µs |

分解：**记账净增量 +7.0 µs/请求**，**每请求 INFO 日志净增量 +48.6 µs**（本机 StreamHandler→StringIO）。

> 注意：上表 640 µs 的「空中间件」差值是 Starlette `BaseHTTPMiddleware` 自身在 `httpx.ASGITransport` 下的放大效应（每层中间件一条 anyio task group + 双向内存流），**不是 metrics 的账**；真实 uvicorn 下该层成本显著低于此，故本文只采用「同栈 A/B 差值」。

### 2.3 日志落盘成本（生产 `JSONFormatter` → 文件）

| Handler | 成本 |
|---|---|
| FileHandler + JSONFormatter | **24.6 µs/条** |
| FileHandler + 纯文本 | 18.7 µs/条 |
| NullHandler（仅 record 构造） | 8.2 µs/条 |
| level 过滤后（LOG_LEVEL≥WARNING，info 被短路） | 0.15 µs/条 |

### 2.4 高 QPS 占比估算（单进程单事件循环）

以 **记账 7 µs + 日志 25 µs ≈ 32 µs/请求** 计：

| QPS | 记账占比（单核） | + 日志占比（单核） | 对照：一次 LLM 请求 3 s 的占比 |
|---|---|---|---|
| 100 | 0.07% | 0.32% | 0.001% |
| 500 | 0.35% | 1.60% | 0.005% |
| 1000 | 0.70% | 3.20% | 0.011% |

**结论（开销）**：可接受，不构成瓶颈。真正的成本不在「每请求」，在 `/metrics` 抓取时的**单次长停顿**（见 §5.4）。

### 2.5 锁与全局排序（实测，非推断）

- 写路径：**一把进程级 `threading.Lock`**（`shared/metrics.py:16`），`record_request` 在锁内做 9 次比较 + 5 次 dict 自增。单线程 1.40 M ops/s；**8 线程聚合 205 k ops/s（扩展比 0.15×）** —— 锁是真串行。当前 uvicorn 单事件循环下影响有限，但任何 `run_in_threadpool`/`to_thread` 化的改造会立刻打到这把锁。
- 读路径：`render_prometheus`（`:105-200`）**在整段序列化期间持有同一把锁**，内含 **8 次 `sorted()` 全量排序**（request_total / errors / latency_sum / count / hist / llm_calls / node_sum / node_count）。
- 实测阻塞：2000 条路径时 render 持锁 **23 ms**，期间并发写线程单次 `record_request` **最大阻塞 9.5 ms**；20000 条路径时 render **268 ms**。
- **没有**任何地方做全局排序/扫描于请求路径上（排序只发生在 scrape 时）——这点符合预期。

---

## ③ 尾部跳过与慢请求误报

### 3.1 >30 s 尾部：**大部分正确跳过，但存在「恰好卡边界」的假数字**

`_approx_quantile` 在目标计数落进 `+Inf` 桶时返回 `inf`，调用方 `continue`（`:171-172`）→ **不暴露该 gauge**（不是把 30 s 当答案）。实测：

| 场景 | 结果 |
|---|---|
| 全部 >30 s（n=5000） | p50/p95/p99 全部返回 `inf` → 指标整条消失（直方图 `+Inf`=5000，正确） |
| 3% >30 s（n=20000） | p95 = 570.8 ms（正常插值），p99 跳过（真实 88 903 ms） |
| 99.5% N(300,100) + 0.5% U(31 s,120 s) | p95=491/468、p99=884/556、p99.5=1000/867 —— 均在有限桶内，符合分位定义 |

**边界缺陷（实测可复现）**：当 `>(1-q)` 的样本**恰好等于**比例时，`target == cum(le=30)`，代码走 `frac=1.0` 分支，**返回精确的 30 000.0 ms**——把桶上限当成测量值输出：

| n | 尾部（>30 s） | cum(le=30) | target | 估算 p99 | 精确 p99 |
|---|---|---|---|---|---|
| 100 | 1 | 99 | 99.000000 | **30 000.00 ms** | 12 480 ms |
| 2 000 | 20 | 1980 | 1980.000000 | **30 000.00 ms** | ≈12 480 ms |
| 20 000 | 200 | 19 800 | 19 800.000000 | **30 000.00 ms** | ≈12 480 ms |

即「恰好 1% 的请求超 30 s」这条最常见的慢路径形态，p99 会被写成 `30.000000`（一个整数上限），下游看板显示「p99 = 30 s 整」——既可能高估（真实 12.5 s）也可能低估（若那 1% 是 60 s）。这是**唯一一条会产生「假数字」而非「无数字」的路径**，建议在 `:96-100` 增加 `if cum == target and hist[-1] > 0: return inf`（或在 `frac>=1.0` 且存在 `+Inf` 时返回 `inf`）。

另：**跳过 = 指标消失**。3% 超 30 s 的路径，p99 这一行不存在，看板/Grafana 会显示「无数据」，很容易被读成「健康」。告警规则若写 `p99 > 2s`，该路径**永远不会触发**。

### 3.2 慢请求告警与 SSE：**不误报，但完全看不见真实长对话**

`SLOW_REQUEST_MS`（`app/middleware.py:72`，默认 2000）判定在 `finally` 里，测的是 `await call_next(request)` 的**返回时刻**。对 `StreamingResponse`，`call_next` 在**响应头发出时**即返回，body 仍在后续流式产出 → 测到的是 **TTFB，不是端到端时长**。

实测（ASGI，端点每 200 ms 推一块、共 15 块 ≈ 3.0 s）：

| 观测项 | 数值 |
|---|---|
| 真实挂钟（客户端读完整个流） | **3 079 ms** |
| `record_request` 记录值 | **0.68 ms** |
| 偏差 | **+3 079 ms（记录值的 4 528 倍）** |
| 是否触发 SLOW（阈值 2000 ms） | **否**（WARNING 计数 = 0） |
| 同一进程内非流式 2.5 s 端点（对照） | 记录 2 503.24 ms，**WARNING 正常触发** |

受影响的 5 个 SSE 端点（全部 `text/event-stream`）：
`api/chat.py:1217`、`api/agents.py:331`、`api/langgraph.py:282`、`api/multimodal.py:594`、`api/skills.py:707`。

后果有三条，都可观测地坏：

1. **不会误报**（问题 3 的原始担心不成立）；
2. **等于永远不报警**——LLM 长对话（最可能真的慢的路径）记录恒为 ~1 ms，`SLOW_REQUEST_MS=2000` 对它形同关闭；
3. **污染分位数**：这些路径的 p95/p99 恒为亚毫秒级，把「用户等 30 s」的路由在 SLO 表里显示成全场最快的一条；同时流中途报错时 `status` 仍是 200（`status = response.status_code`），5xx 计数也看不到。

建议（只提方向，未改代码）：对 SSE 用生成器的 `try/finally` 单独记一条 `http_request_total_duration_seconds`（首字节 + 流总时长两个口径分开），或在 `StreamingResponse` 外包一层计时的 send 包装；单靠 `SLOW_REQUEST_MS` 这一层中间件无法覆盖流式语义。

---

## ④ 热路径问题清单（`py-server/api/` 及直接下游）

> 所有耗时为本机在**临时目录复刻相同 schema/数据形状**测得（避免污染仓库 `data/`），非全量端到端。

| # | 位置 | 问题 | 实测影响 | 建议 |
|---|---|---|---|---|
| 1 | `api/sessions.py:98-113`（`session_list`） | async def 里 **`os.listdir` + 对每个文件 `json.load` 全量解析**（只为了 title / msg_count）；`:113` 再全量 `sort` | 200 个会话（7.3 MiB）→ **198.3 ms/请求**，全程阻塞事件循环（对照：仅 `listdir+getmtime` 32.7 ms，差距 **6×**）。并发 5 个用户即叠加 ≈1 s 全站停顿 | 落一份 `meta.json`（title/msg_count/mtime）或改名为 `{id}.meta`，列表只读 meta；解析移入 `to_thread`；加 `limit/offset` |
| 2 | `api/career_training.py:81` + `services/career_service.py:94` | 同一请求内 **加载会话状态两次**（`_check_owner` 一次、`answer_turn` 再一次）：每次 `SELECT state` + `json.loads`（28 KiB state） | **≈445 µs/请求** 纯重复开销（229.5 µs × 2）；且两次都在 `pg_client._lock`（单文件全局锁）内 → 8 线程吞吐 **4 436 → 1 515 q/s（扩展比 0.34×）** | `_check_owner` 返回 state，直接透传给 `answer_turn`；DB 调用改 `await anyio.to_thread.run_sync(...)` |
| 3 | `db/career_store.py:328-347`（`save_session_state`） | 每轮把**整份 state** 序列化后 `UPDATE` 全字段（`_dumps(state)`），state 随轮次单调增长 | `json.dumps` 28 KiB = **401.6 µs**，加上 UPDATE 写放大 → 单场 8 轮累计写入 O(n²)；`career_dialogue_turns` 表已存在却未用于存轮次 | 轮次写 `career_dialogue_turns`（已有 `idx_career_turns_session`），`state` 只留指针/汇总 |
| 4 | `agents/career_nodes.py:69-75`（`_load_scenario_file`） | **无缓存**，每次 `open` + `json.load`（7.9 KiB）；`list_scenarios()` 调它两次并额外查库 | 单次加载 **158 µs**；`list_scenarios()` 整体 **3.79 ms/次**，被 `/career/tasks`、`/career/my-tasks`、`/career/tasks`(POST)、`start_session` 每次请求调用 → 50 QPS 即占单核 **≈19%** | 模块级缓存 + mtime 失效（或 `functools.lru_cache` 包一层带 mtime 的 key） |
| 5 | `db/career_store.py:365-377`、`:890-909`；`api/career_training.py:737-746` | **无索引全表扫描**：`career_sessions` 只有 `career_dialogue_turns/class_students/feedback` 建了索引，`user_id`、`task_id`、`started_at` 均无；`list_tasks` 对每个 task 调 `task_stats`（内部 2 条查询）→ **N+1** | 2N 条查询 + N 次全表扫描（`WHERE task_id=` 无索引）；教师端 20 个任务即 40 条查询 | `CREATE INDEX ... ON career_sessions(user_id, started_at DESC)`、`(task_id)`；`task_stats` 改为一条 `GROUP BY task_id` 聚合 |
| 6 | `app/status.py:42`（`vector_db.count`） | Milvus 模式下**每次健康探针新建线程**并 `join(timeout=5.0)`，在事件循环线程上等待 | 线程 spawn+join 本身 **141 µs（p95 231 µs）**/次；Milvus 挂起时**单次最多冻结事件循环 5 s**（探针被编排系统高频轮询 → 连续 5 s 停顿） | 缓存 count（TTL 10 s）或改 `await anyio.to_thread`；探针只读 `_milvus_connected` 不做 RPC |
| 7 | `api/chat.py:64`（`build_memory_context`，同步调用在 async def 内） | 缓存 TTL=5 s（`services/memory_service.py:54`），聊天间隔 >5 s 必 miss → 同步 SQLite/网络查询阻塞事件循环 | 有真实数据（300 episode/120 掌握点）时 miss **0.25–0.45 ms**，冷启动 **106 ms**；SQLite 下可接受，切 PG 后每次 miss 变成一次网络往返（预计 1–10 ms，**未测**：本机无可用 PG） | `await to_thread`；TTL 提到 30–60 s 或事件驱动失效 |
| 8 | `db/career_store.py` 全部查询 | 所有 SQL 均为**同步 sqlite3/psycopg2**，且在 `async def` 路径上直接调用；回退路径共用**单连接 + 单把 `threading.Lock`** | 见 #2 的 0.34× 扩展比；这就是「async 里做阻塞 IO」的系统性版本 | 统一 `to_thread` 或换 async 驱动（asyncpg / aiosqlite） |

补充（非阻塞性、但影响成本）：`api/chat.py:1181` 的 `_execute_tool` 是同步纯字符串拼装，实测 µs 级，**不构成问题**；`api/career_training.py:763` 的 `student_detail`、`:789` `class_dashboard` 未见循环查库。未发现「循环里加载模型」的路径（`LLMProvider()` 每次 new，但构造只读 `get_container().settings`，`load_config` 有全局缓存 —— 实测构造开销含在 §2 的端到端数字内，未单独拆分：**未测**）。

---

## ⑤ `/metrics` 端点自身

`app/status.py:217-218`（处理函数），`:241`（`app.get("/metrics")` 注册，无 `Depends`）。

### 5.1 序列化开销随「路径基数」线性膨胀（实测）

| 唯一 path 数 | `/metrics` 渲染 | 响应体积 | 行数 | gzip-9（Starlette GZipMiddleware 在事件循环内同步压缩） |
|---|---|---|---|---|
| 10 | 0.24 ms | 15.0 KiB | 176 | — |
| 50 | 0.99 ms | 69.3 KiB | 776 | — |
| 200 | 4.66 ms | 272.9 KiB | 3 026 | — |
| 1 000 | 23.31 ms | 1 358.9 KiB | 15 026 | — |
| 2 000 | 23 ms（持锁） | 2.86 MiB | — | 48.8 ms |
| 20 000 | **268 ms** | **28.59 MiB** | 300 026 | **425.7 ms** |

→ 20 000 条路径下一次抓取 ≈ **268 ms 渲染 + 426 ms 压缩 ≈ 0.7 s 事件循环完全冻结**；且渲染期间持有 `_lock`，所有请求的 `record_request` 被阻塞（实测单次最长 **9.5 ms**）。GZip 在 starlette 1.2.1 中是 `send` 内**同步**执行（`.venv/.../middleware/gzip.py:109` `apply_compression`，无线程池），所以这 426 ms 是实打实的停顿。

### 5.2 基数无上限（两个来源，均实测）

1. **路径参数直接进 label**：59 条路由带路径参数，`record_request(request.url.path, ...)` 用的是**原始 URL path**，不是路由模板。实测输出：
   `http_requests_total{path="/api/career/session/cs_9f3a1c2b7d4e5f60/answer"} 1`。
2. **未匹配路由也记账**：中间件对所有请求生效，`/scan-0 … /scan-4999` 全部成为独立 label（实测 5000 条）。任意爬虫打随机路径 = 无成本的内存放大。

内存实测：**330 B/唯一路径**（5 张 dict + 10 元素 list）；20 000 条 = **6.29 MiB** 常驻，且**永不回收**（无淘汰）。

### 5.3 敏感信息暴露（实测）

`/metrics` 无鉴权（`app.get("/metrics")` 无 `Depends`，且 `scripts/verify_auth_coverage.py` 只统计 `/api` 前缀，明确把 `/metrics` 排除在覆盖口径外）。实测输出直接包含用户可控标识：

| 出现于 `/metrics` 的字符串 | 来源路由 |
|---|---|
| `cs_9f3a1c2b7d4e5f60`（实训会话 ID） | `/api/career/session/{session_id}/answer` |
| `u_1024`（用户 ID） | `/api/literacy/report/{user_id}` |
| `conv_abc123`（对话存档 ID） | `/api/sessions/load/{conv_id}` |
| `alice`（管理员用户名） | `/api/admin/users/{username}` |

→ 无需登录即可枚举：会话 ID、用户 ID、对话 ID、管理员用户名、以及全部内部路由结构。这是**信息泄露 + 基数膨胀**同一个根因（用原始 path 当 label）。

### 5.4 修复方向（仅建议）

- 用**路由模板**做 label：`request.scope.get("route").path`（FastAPI 在路由匹配后写入 scope），未匹配统一归 `/__unmatched__`；
- `/metrics` 加内网/令牌鉴权，或绑定 loopback；
- 给 path 数量设上限（超出部分聚合到 `other`），并对 `_hist` 加固定容量；
- 渲染改增量/预聚合（或至少把 gzip 移出事件循环）。

---

## ⑥ 结论：这套可观测性能不能用于生产定位？

**分项判定：**

| 维度 | 判定 | 依据 |
|---|---|---|
| 分位数算得对 | **部分** | p95（n≥1e3）误差 <2%，可告警；**p99 结构 +25%…+55% 高估**，不可对外报数；n<20 全部不可信；「恰好 1% 尾部」会输出假的 `30.000000` |
| >30 s 尾部不被截断 | **基本正确** | 严格越界 → 跳过（不输出 30 s 假数字）；但「跳过」= 指标消失，告警静默失效；边界等值 → 输出 30 s 上限 |
| 开销可接受 | **是** | 记账 7 µs/请求（100 QPS 占单核 0.07%）；日志 25 µs（0.32%）；无请求路径上的全局排序 |
| 能定位问题 | **否（关键路径失效）** | SSE 记录 0.68 ms / 真实 3 079 ms；5 个流式端点 p95 恒亚毫秒；流中途错误仍记 200；`/metrics` 无鉴权泄露 ID 且可被基数打爆成 0.7 s 停顿 |

**总体：作为「进程内健康快照」够用，作为「生产定位依据」不够用。** 具体地：

1. **能回答**「整体是否变慢、哪个普通端点 5xx、QPS 多少」——这些结论 p95 长跑误差 <2%，可信。
2. **不能回答**「用户为什么等 30 秒」——最慢的那 5 条 SSE 路由在该体系里显示为全场最快；慢请求告警对它们永远不响。这是本次验证最严重的一条。
3. **不能对外引用 p99**，也不能与 Prometheus 的 `histogram_quantile` 对账（同一批样本两者会差 25%–55%）。
4. `/metrics` 本身目前是**风险项**：无鉴权 + 输出会话/用户 ID + 无基数上限 + 单次抓取可冻结循环 0.7 s。

**最小整改优先级**（按「投入/收益」）：
① `/metrics` 鉴权 + 用路由模板做 label（同时解决泄露与基数两个问题）；
② SSE 单独记端到端时长（否则整套慢请求观测对 LLM 路径等于不存在）；
③ `_approx_quantile` 边界守卫（`frac>=1.0 且 +Inf>0 → inf`）；
④ 给 p99 加「高估 +25%~+55%」的口径注释或直接改为对外只暴露 `histogram_quantile`；
⑤ §4 的 #1/#2/#5（sessions/list 198 ms、双次加载 445 µs、缺索引）按序修。

---

## 附：未测项与原因

| 项 | 原因 |
|---|---|
| 真实 uvicorn 下的端到端 QPS/延迟曲线 | 任务要求「不要起真实服务」，仅做 in-process 微基准；`BaseHTTPMiddleware` 的绝对值会被 ASGITransport 放大，故只采用同栈差值 |
| PostgreSQL 模式下的查询阻塞时长 | 本机无可用 PG 实例，无法测网络往返；仅测 SQLite 回退路径 |
| Milvus 挂起时的实际 5 s 停顿 | 无 Milvus 实例，只测了线程 spawn+join 的 141 µs 与代码路径上的 `join(timeout=5.0)` |
| 全量 pytest / `verify_metrics --update` | 红线禁止 |
| `LLMProvider()` 单次构造耗时拆分 | 未单独拆分（构造走 `get_container().settings` 缓存，估计 µs 级），未测 |
