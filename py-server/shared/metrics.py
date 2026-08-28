# ============================================================
# 轻量进程内指标收集（D5 /metrics，Prometheus 文本格式，无外部依赖）
# 仅用标准库：threading + collections。采集：
#   - 各路径请求总数（http_requests_total）
#   - 在途请求数（http_requests_in_flight，gauge）
#   - 5xx 错误数（http_request_errors_total）
#   - 按路径的累计耗时与计数（用于计算平均延迟）
# 多 worker 不适用（本项目 ADR-007 强制 --workers 1），单进程内存计数器即可。
# ============================================================

import threading
from collections import defaultdict
from typing import Dict

# ── 线程安全计数器 ──
_lock = threading.Lock()
_request_total: Dict[str, int] = defaultdict(int)
_request_errors: Dict[str, int] = defaultdict(int)
_latency_sum: Dict[str, float] = defaultdict(float)
_latency_count: Dict[str, int] = defaultdict(int)
_in_flight: int = 0

# D3：请求延迟直方图分桶（秒），用于计算 p95/p99（Prometheus histogram_quantile）
_LATENCY_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_hist: Dict[str, list] = defaultdict(lambda: [0] * (len(_LATENCY_BUCKETS) + 1))

# ── LLM 级指标 (P1-4) ──
# llm_calls_total{channel}：各通道 LLM 调用成功数（xfyun / deepseek）
# llm_fallback_total：运行级通道回退次数（主通道失败→切下一通道）
# langgraph_node_seconds(_sum/_count)：LangGraph 各节点累计耗时（summary 风格）
_llm_calls_total: Dict[str, int] = defaultdict(int)
_llm_fallback_total: int = 0
_lg_node_seconds_sum: Dict[str, float] = defaultdict(float)
_lg_node_seconds_count: Dict[str, int] = defaultdict(int)


def record_llm_call(channel: str) -> None:
    """记录一次 LLM 调用成功（按通道计数）。"""
    with _lock:
        _llm_calls_total[channel] += 1


def record_llm_fallback() -> None:
    """记录一次运行级通道回退（主通道失败，切换下一通道）。"""
    global _llm_fallback_total
    with _lock:
        _llm_fallback_total += 1


def record_langgraph_node_seconds(node: str, seconds: float) -> None:
    """记录 LangGraph 某节点的执行耗时（秒）。"""
    with _lock:
        _lg_node_seconds_sum[node] += seconds
        _lg_node_seconds_count[node] += 1


def record_request(path: str, status_code: int, latency: float) -> None:
    """记录一次已完成请求。"""
    with _lock:
        _request_total[path] += 1
        if status_code >= 500:
            _request_errors[path] += 1
        _latency_sum[path] += latency
        _latency_count[path] += 1
        # 直方图：定位延迟所属分桶（D3：供分位延迟计算）
        _h = _hist[path]
        for i, _b in enumerate(_LATENCY_BUCKETS):
            if latency <= _b:
                _h[i] += 1
                break
        else:
            _h[-1] += 1  # +Inf 桶


def inc_inflight(delta: int) -> None:
    """在途请求数增减（gauge）。"""
    global _in_flight
    with _lock:
        _in_flight = max(0, _in_flight + delta)


def render_prometheus() -> str:
    """渲染 Prometheus exposition 文本格式。"""
    with _lock:
        lines: list[str] = []
        lines.append("# HELP http_requests_total Total HTTP requests by path.")
        lines.append("# TYPE http_requests_total counter")
        for path in sorted(_request_total):
            lines.append(f'http_requests_total{{path="{_esc(path)}"}} {_request_total[path]}')

        lines.append("# HELP http_requests_in_flight Current in-flight requests.")
        lines.append("# TYPE http_requests_in_flight gauge")
        lines.append(f"http_requests_in_flight {_in_flight}")

        lines.append("# HELP http_request_errors_total 5xx errors by path.")
        lines.append("# TYPE http_request_errors_total counter")
        for path in sorted(_request_errors):
            if _request_errors[path]:
                lines.append(
                    f'http_request_errors_total{{path="{_esc(path)}"}} {_request_errors[path]}'
                )

        lines.append("# HELP http_request_duration_seconds_sum Request latency sum by path (seconds).")
        lines.append("# TYPE http_request_duration_seconds_sum counter")
        for path in sorted(_latency_sum):
            lines.append(
                f'http_request_duration_seconds_sum{{path="{_esc(path)}"}} {_latency_sum[path]:.6f}'
            )

        lines.append("# HELP http_request_duration_seconds_count Request latency count by path.")
        lines.append("# TYPE http_request_duration_seconds_count counter")
        for path in sorted(_latency_count):
            lines.append(
                f'http_request_duration_seconds_count{{path="{_esc(path)}"}} {_latency_count[path]}'
            )

        # D3：直方图（分桶累计，供 Prometheus 计算 p95/p99）
        lines.append("# HELP http_request_duration_seconds_bucket Request latency histogram by path (seconds).")
        lines.append("# TYPE http_request_duration_seconds_bucket histogram")
        for path in sorted(_hist):
            _h = _hist[path]
            _cum = 0
            for i, _b in enumerate(_LATENCY_BUCKETS):
                _cum += _h[i]
                lines.append(
                    f'http_request_duration_seconds_bucket{{path="{_esc(path)}",le="{_b}"}} {_cum}'
                )
            _cum += _h[-1]
            lines.append(
                f'http_request_duration_seconds_bucket{{path="{_esc(path)}",le="+Inf"}} {_cum}'
            )

        # ── LLM 级指标 (P1-4) ──
        lines.append("# HELP llm_calls_total Total LLM calls by channel.")
        lines.append("# TYPE llm_calls_total counter")
        for ch in sorted(_llm_calls_total):
            lines.append(f'llm_calls_total{{channel="{_esc(ch)}"}} {_llm_calls_total[ch]}')

        lines.append("# HELP llm_fallback_total Total LLM channel fallback count (primary→next).")
        lines.append("# TYPE llm_fallback_total counter")
        lines.append(f"llm_fallback_total {_llm_fallback_total}")

        lines.append("# HELP langgraph_node_seconds_sum LangGraph node execution time sum by node (seconds).")
        lines.append("# TYPE langgraph_node_seconds_sum counter")
        for node in sorted(_lg_node_seconds_sum):
            lines.append(
                f'langgraph_node_seconds_sum{{node="{_esc(node)}"}} {_lg_node_seconds_sum[node]:.6f}'
            )
        lines.append("# HELP langgraph_node_seconds_count LangGraph node execution count by node.")
        lines.append("# TYPE langgraph_node_seconds_count counter")
        for node in sorted(_lg_node_seconds_count):
            lines.append(
                f'langgraph_node_seconds_count{{node="{_esc(node)}"}} {_lg_node_seconds_count[node]}'
            )

        return "\n".join(lines) + "\n"


def _esc(s: str) -> str:
    """转义 Prometheus label 值中的双引号与反斜杠。"""
    return s.replace("\\", "\\\\").replace('"', '\\"')
