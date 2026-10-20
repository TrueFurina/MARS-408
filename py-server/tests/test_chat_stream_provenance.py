# -*- coding: utf-8 -*-
"""流式聊天的来源标记（provenance）回归 —— REA #22「回答出自哪里必须可判」

问题：一次 /api/chat/stream 的回答可能是
  (a) 纯模型文本；
  (b) 模型 + 工具循环（多轮）；
  (c) 某个通道回退后由**另一个**通道产出；
  (d) 压根没产出（通道全灭）——但客户端只看到空内容 + 一条 error。
此前四者在事件流里没有任何可区分字段，"这段话到底谁生成的"只能去翻服务端日志。

契约（本文件钉死）：
  1. 正常回答：`provenance` 事件在 `[DONE]` 之前出现，带 outcome/channel/rounds/
     answer_source，且 channel 必须是**实际服务通道**（取自 llm.last_channel）；
  2. 工具循环：rounds=2、tools_used 记录真实工具名、answer_source="model+tools"；
  3. 全通道不可用：先 provenance（outcome="llm_unavailable"、channel=None），
     再 error —— 顺序反了会让客户端把"失败"渲染成"答完了"；
  4. 无文本产出：answer_source="none"（不伪装成 model）；
  5. provenance 里不得出现密钥/端点等敏感字段（白名单外一律不加）。

运行：python -m pytest tests/test_chat_stream_provenance.py -q
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api.chat as chat_api  # noqa: E402
from db.llm_provider import LLMUnavailable  # noqa: E402
from models import ChatSendRequest  # noqa: E402


class _FakeRequest:
    async def is_disconnected(self) -> bool:
        return False


def _chunk(delta: dict, finish=None) -> str:
    return json.dumps({"choices": [{"delta": delta, "finish_reason": finish}]})


class _Provider:
    """可编排的 LLMProvider 替身：按脚本逐轮产出分片。"""

    scripts: list = []
    raise_unavailable: bool = False

    def __init__(self):
        self.last_channel = None

    async def stream_chat(self, messages, temperature=0.7, tools=None, thinking=False, timeout=60):
        if _Provider.raise_unavailable:
            raise LLMUnavailable("所有 LLM 通道流式调用均失败（运行级回退耗尽）")
        script = _Provider.scripts.pop(0)
        for item in script:
            if item == "[DONE]":
                yield "[DONE]"
            else:
                yield item
        self.last_channel = "qwen"     # 模拟运行级回退后**实际**服务通道


def _events(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):].strip()
        if payload == "[DONE]":
            out.append({"type": "[DONE]"})
            continue
        try:
            out.append(json.loads(payload))
        except json.JSONDecodeError:
            out.append({"type": "unparsable", "raw": payload})
    return out


def _run(req: ChatSendRequest, monkeypatch) -> list[dict]:
    monkeypatch.setattr(chat_api, "LLMProvider", _Provider)

    async def _audit(text, tag):
        return [], []

    monkeypatch.setattr(chat_api, "audit_output", _audit)

    async def go():
        resp = await chat_api.chat_stream(req, _FakeRequest(), user={"user_id": "u1"})
        chunks = []
        async for part in resp.body_iterator:
            chunks.append(part if isinstance(part, str) else part.decode())
        return "".join(chunks)

    return _events(asyncio.run(go()))


def _prov(events: list[dict]) -> dict:
    found = [e for e in events if e.get("type") == "provenance"]
    assert found, f"事件流里没有 provenance：{[e.get('type') for e in events]}"
    return found[-1]["provenance"]


def test_plain_answer_declares_channel_and_rounds(monkeypatch):
    _Provider.scripts = [[_chunk({"content": "答案是 42"}), _chunk({}, "stop"), "[DONE]"]]
    _Provider.raise_unavailable = False
    events = _run(ChatSendRequest(message="hi"), monkeypatch)

    prov = _prov(events)
    assert prov["outcome"] == "ok"
    assert prov["channel"] == "qwen", "channel 必须是实际服务通道（last_channel），不是配置里的首选"
    assert prov["rounds"] == 1
    assert prov["tools_used"] == []
    assert prov["answer_source"] == "model"
    # 顺序：provenance 必须在 [DONE] 之前
    types = [e["type"] for e in events]
    assert types.index("provenance") < types.index("[DONE]")


def test_tool_loop_reports_tools_and_two_rounds(monkeypatch):
    _Provider.scripts = [
        [_chunk({"tool_calls": [{"index": 0, "id": "c1", "function": {
            "name": "calculate_crc", "arguments": '{"data":"1011","poly":"11"}'}}]}, "tool_calls")],
        [_chunk({"content": "校验位是 0"}), _chunk({}, "stop"), "[DONE]"],
    ]
    _Provider.raise_unavailable = False
    monkeypatch.setattr(chat_api, "_execute_tool", lambda name, args: f"{name}-ok")

    events = _run(ChatSendRequest(message="算 crc", agent_mode=True), monkeypatch)
    prov = _prov(events)
    assert prov["rounds"] == 2, "工具循环是一次额外的模型往返，轮数必须如实计"
    assert prov["tools_used"] == ["calculate_crc"]
    assert prov["answer_source"] == "model+tools"
    assert prov["agent_mode"] is True


def test_unavailable_channel_is_not_silent(monkeypatch):
    _Provider.scripts = []
    _Provider.raise_unavailable = True
    events = _run(ChatSendRequest(message="hi"), monkeypatch)
    _Provider.raise_unavailable = False

    prov = _prov(events)
    assert prov["outcome"] == "llm_unavailable"
    assert prov["channel"] is None, "一次都没成功时不得编造通道名"
    assert prov["answer_source"] == "none"
    types = [e["type"] for e in events]
    assert "error" in types
    assert types.index("provenance") < types.index("error"), (
        "provenance 必须先于 error：客户端据此区分『失败』与『模型没说话』")


def test_no_text_yields_none_not_model(monkeypatch):
    _Provider.scripts = [[_chunk({}, "stop"), "[DONE]"]]
    _Provider.raise_unavailable = False
    events = _run(ChatSendRequest(message="hi"), monkeypatch)
    prov = _prov(events)
    assert prov["outcome"] == "ok"
    assert prov["answer_source"] == "none", "零文本产出不得标成 model"


def test_provenance_has_no_secret_or_endpoint_fields(monkeypatch):
    _Provider.scripts = [[_chunk({"content": "ok"}), _chunk({}, "stop"), "[DONE]"]]
    _Provider.raise_unavailable = False
    prov = _prov(_run(ChatSendRequest(message="hi"), monkeypatch))
    # 白名单制：字段集固定，新增字段需同时改本断言（防止有人把 headers/url 塞进来）
    assert set(prov) == {"outcome", "channel", "rounds", "tools_used",
                         "agent_mode", "answer_source"}
