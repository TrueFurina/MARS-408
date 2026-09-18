# ============================================================
# SSE 客户端断开检测 — 避免慢/断客户端空转消耗 LLM 算力
# ============================================================

import logging
from typing import AsyncIterator, Optional

from fastapi import Request

logger = logging.getLogger("netlearn.sse")

# 每 N 个事件检测一次客户端断开（避免每次 yield 都 await is_disconnected 的额外开销）
_DISCONNECT_CHECK_EVERY = 10


async def sse_disconnect_guard(
    request: Optional[Request],
    agen: AsyncIterator[str],
) -> AsyncIterator[str]:
    """包装 SSE async generator：定期检测客户端是否断开，断开则提前终止生成。

    优点：
    - 不修改各 event_stream() 内部逻辑（零侵入、低风险）
    - 客户端中途关闭页面/网络时，立即停止后续 LLM 调用与向量检索，节省算力
    - request 为 None（非 HTTP 上下文）时降级为不检测，向后兼容
    """
    if request is None:
        async for chunk in agen:
            yield chunk
        return

    count = 0
    async for chunk in agen:
        count += 1
        if count % _DISCONNECT_CHECK_EVERY == 0:
            try:
                if await request.is_disconnected():
                    logger.info("SSE 客户端已断开，提前终止生成（节省 LLM 算力）")
                    return
            except Exception:
                # 检测异常不应中断正常事件流
                pass
        yield chunk
