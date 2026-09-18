# MARS-408 可观测性最小补强清单（P2，零外部依赖）

> 现状：`shared/metrics.py` 仅暴露 `http_requests_total`、`http_requests_in_flight`(gauge)、`http_request_errors_total`(5xx) 及 `duration_sum/count`(计数器)。**无 Histogram、无后端 gauge、无导入队列深度**——无法看 p95/p99，也难判断 InMemory vs Milvus、导入是否积压。以下为最小补强（纯标准库，挂到现有 `/metrics`）。

## 1. p95 / p99 时延 Histogram

**补法**：在 `metrics.py` 引入全局样本池 `deque(maxlen=2000)` 记录每次请求时延，渲染时计算分位并输出为 gauge（同时保留 Histogram bucket 兼容 Prometheus）。

```python
from collections import deque
_latency_samples: deque = deque(maxlen=2000)

# record_request() 内追加：_latency_samples.append(latency)
def _pct(p):
    if not _latency_samples: return 0.0
    s = sorted(_latency_samples); k = max(0, int(len(s)*p)-1); return s[k]

# render_prometheus() 追加：
lines += ["# TYPE http_request_duration_seconds_p95 gauge",
          f"http_request_duration_seconds_p95 {_pct(0.95):.3f}",
          "# TYPE http_request_duration_seconds_p99 gauge",
          f"http_request_duration_seconds_p99 {_pct(0.99):.3f}"]
```

- **阈值（演示人工盯盘）**：p95 `< 2s`、p99 `< 5s`；若 p95 `> 3s` 连续 2 轮 → 卡顿排查（embedding/LLM 限速）。

## 2. `vector_db_backend` gauge

**补法**：渲染时读取 `vector_db._milvus_connected`（与 `/api/status` 同源）。

```python
from db.milvus_client import vector_db
backend = "milvus" if vector_db._milvus_connected else "inmemory"
lines += ["# TYPE vector_db_backend gauge",
          f'vector_db_backend{{backend="{backend}"}} 1']
```

- **阈值**：演示应恒为 `inmemory`（=1）。若意外 `milvus` 且连接不稳，按 Runbook 回退到 InMemory。

## 3. `import_queue_depth` gauge

**补法**：`import_worker` 增加公开方法，挂队列深度（与 `submit()/asyncio.Queue` 同源）。

```python
# services/import_worker.py
def queue_depth(self) -> int:
    return self._queue.qsize() if self._queue else 0

# metrics.py 渲染：
from services.import_worker import import_worker
lines += ["# TYPE import_queue_depth gauge",
          f"import_queue_depth {import_worker.queue_depth()}"]
```

- **阈值**：演示常态 `=0`（无活动导入）。`>0` 持续 → 查导入任务；`>50` → 疑似积压/卡死。

## 4. 无告警系统下的人工盯盘节奏

每 5 分钟（与 Runbook 同拍）取数：

```bat
curl -s http://127.0.0.1:8002/metrics | findstr /R "p95 p99 vector_db_backend import_queue_depth http_requests_in_flight"
```

记入盯盘表，连续 2 轮越线即触发 Runbook 的回滚/切换。三项指标与 `/api/status` 互为印证：`collection_size>0` + `vector_db_backend=1` + `import_queue_depth≈0` = 知识底座健康。
