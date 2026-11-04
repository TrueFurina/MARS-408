# -*- coding: utf-8 -*-
"""`GET /api/sessions/list` 的元信息缓存与降级语义（2026-11-02 性能审计）。

背景：旧实现对每个会话文件整档 `json.load`，只为取 title 与消息条数。
200 个 28KiB 会话 ≈ 5.6MB 解析（本机实测 198ms/请求），且发生在 async def 里的
同步循环中，会阻塞事件循环。

本文件锁三件事：
1. 列表的形状 / 排序 / 字段语义不变；
2. 同一文件在 mtime+size 未变时**不再解析**（缓存生效）；
3. 文件变了要能失效；坏档按旧语义降级（title=id 前 8 位、msg_count=0、updated=0）。
"""
import json
import os

import pytest

import api.sessions as S

pytestmark = pytest.mark.usefixtures("mock_auth")


class _CountingJson:
    """包装 json 模块，统计 `.load` 调用次数（其余属性透传）。"""

    def __init__(self, real):
        self._real = real
        self.calls = 0

    def load(self, f):
        self.calls += 1
        return self._real.load(f)

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture()
def user_dir(tmp_path, monkeypatch):
    """把用户目录指到临时目录，并清空缓存（避免跨用例污染）。"""
    d = tmp_path / "sessions" / "u1"
    d.mkdir(parents=True)
    monkeypatch.setattr(S, "_ensure_user_dir", lambda uid: str(d))
    S._META_CACHE.clear()
    yield d
    S._META_CACHE.clear()


def _write(d, conv_id, title, messages, mtime=None):
    path = d / f"{conv_id}.json"
    path.write_text(
        json.dumps({"title": title, "messages": messages}, ensure_ascii=False),
        encoding="utf-8",
    )
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_list_shape_and_sorting(client, user_dir):
    _write(user_dir, "old", "旧对话", [{"role": "user", "content": "a"}], mtime=1_700_000_000)
    _write(
        user_dir,
        "new",
        "新对话",
        [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
        mtime=1_700_000_500,
    )

    r = client.get("/api/sessions/list")
    assert r.status_code == 200
    rows = r.json()["sessions"]

    assert [x["conv_id"] for x in rows] == ["new", "old"], "必须按 updated 倒序"
    assert rows[0]["title"] == "新对话"
    assert rows[0]["msg_count"] == 2
    assert set(rows[0]) == {"conv_id", "title", "msg_count", "updated"}


def test_second_call_does_not_reparse(client, user_dir, monkeypatch):
    for i in range(5):
        _write(user_dir, f"c{i}", f"T{i}", [{"role": "user", "content": "x"}])

    shim = _CountingJson(json)
    monkeypatch.setattr(S, "json", shim)

    client.get("/api/sessions/list")
    first = shim.calls
    assert first == 5, f"首次应解析 5 个文件，实际 {first}"

    client.get("/api/sessions/list")
    assert shim.calls == first, (
        f"mtime/size 未变时不得重复解析（多解析了 {shim.calls - first} 次）"
        "——缓存失效或用错了键"
    )


def test_changed_file_invalidates_cache(client, user_dir):
    path = _write(user_dir, "c1", "旧标题", [{"role": "user", "content": "x"}])

    assert client.get("/api/sessions/list").json()["sessions"][0]["title"] == "旧标题"

    # 改写内容并推进 mtime（模拟 session_save 覆写）
    path.write_text(
        json.dumps(
            {"title": "新标题", "messages": [{"role": "user", "content": "x"}] * 3},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    os.utime(path, (1_700_001_000, 1_700_001_000))

    row = client.get("/api/sessions/list").json()["sessions"][0]
    assert row["title"] == "新标题"
    assert row["msg_count"] == 3


def test_broken_file_degrades_like_before(client, user_dir):
    (user_dir / "broken.json").write_text("{not json", encoding="utf-8")

    rows = client.get("/api/sessions/list").json()["sessions"]
    assert len(rows) == 1
    row = rows[0]
    assert row["conv_id"] == "broken"
    assert row["title"] == "broken"[:8]
    assert row["msg_count"] == 0
    assert row["updated"] == 0, "坏档按旧语义记 updated=0，不得排到列表最前"
