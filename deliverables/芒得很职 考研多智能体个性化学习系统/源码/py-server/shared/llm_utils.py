# ============================================================
# 共享工具函数 — 供 agent / engine / API 复用
# 避免 JSON 提取 / LLM 输出解析逻辑在多处重复
# ============================================================

import json
import logging
from typing import Optional

logger = logging.getLogger("netlearn.utils")


def extract_json_from_llm_output(text: str, default: Optional[dict] = None) -> dict:
    """从 LLM 文本输出中提取 JSON 对象。

    处理常见格式：
      - 纯 JSON 文本
      - Markdown 代码块包裹 (```json ... ```)
      - 混合文本+JSON（提取第一个完整 {} 块）

    Args:
        text: LLM 原始输出文本。
        default: JSON 解析失败时返回的默认值（缺省为 {}）。

    Returns:
        解析后的 dict；永远不抛异常。
    """
    if not text or not isinstance(text, str):
        return default or {}

    content = text.strip()

    # 1. 尝试直接解析纯 JSON
    try:
        obj = json.loads(content)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. 尝试提取 Markdown JSON 代码块 ```json ... ```
    try:
        start_md = content.find("```json")
        if start_md != -1:
            start_md = content.find("\n", start_md) + 1
            end_md = content.find("```", start_md)
            if end_md != -1:
                obj = json.loads(content[start_md:end_md].strip())
                if isinstance(obj, dict):
                    return obj
    except (json.JSONDecodeError, ValueError):
        pass

    # 3. 尝试提取第一个 { ... } 块
    try:
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            obj = json.loads(content[start:end + 1])
            if isinstance(obj, dict):
                return obj
    except (json.JSONDecodeError, ValueError):
        pass

    logger.debug("LLM JSON 提取全部失败，返回默认值; preview=%s", text[:200])
    return default or {}
