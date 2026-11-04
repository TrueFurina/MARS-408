# -*- coding: utf-8 -*-
"""情景库加载缓存（2026-11-02 性能审计）。

`_load_scenario_file()` 原先每次调用都 open + json.load（实测 158µs/次），
而 `list_scenarios()` 每个请求至少调一次、`get_scenario()` 每轮对话调一次。

本文件锁三件事：
1. 同一文件在 mtime+size 未变时**不再解析**；
2. 文件被改写后必须失效（运维改情景库要立即生效，不能永久缓存旧值）；
3. 文件缺失时按旧语义降级为 `{"scenarios": []}`（不抛异常）。
"""
import json
import os

import pytest

import agents.career_nodes as cn

pytestmark = pytest.mark.usefixtures("mock_auth")


class _CountingJson:
    """包装 json 模块，统计 `.load` 次数（其余属性透传）。"""

    def __init__(self, real):
        self._real = real
        self.calls = 0

    def load(self, f):
        self.calls += 1
        return self._real.load(f)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _reset_cache():
    cn._SCENARIO_CACHE.update({"mtime_ns": -1, "size": -1, "data": None})


@pytest.fixture()
def scenario_file(tmp_path, monkeypatch):
    p = tmp_path / "career_scenarios.json"
    p.write_text(
        json.dumps(
            {
                "rubric_version": "9.9",
                "scenarios": [
                    {"id": "s1", "type": "t", "title": "标题一"},
                    {"id": "s2", "type": "t", "title": "标题二"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cn, "_SCENARIO_PATH", str(p))
    _reset_cache()
    yield p
    _reset_cache()


def test_second_call_does_not_reparse(scenario_file, monkeypatch):
    shim = _CountingJson(json)
    monkeypatch.setattr(cn, "json", shim)

    cn._load_scenario_file()
    assert shim.calls == 1, f"首次应解析 1 次，实际 {shim.calls}"

    cn._load_scenario_file()
    assert shim.calls == 1, f"mtime/size 未变却重复解析（{shim.calls} 次）——缓存失效了"


def test_list_scenarios_parses_once_for_two_calls(scenario_file, monkeypatch):
    shim = _CountingJson(json)
    monkeypatch.setattr(cn, "json", shim)

    first = cn.list_scenarios()
    assert [s["id"] for s in first][:2] == ["s1", "s2"]
    after_first = shim.calls

    cn.list_scenarios()
    assert shim.calls == after_first, "list_scenarios 两次调用只应解析一次情景库文件"


def test_change_invalidates_cache(scenario_file):
    assert [s["id"] for s in cn._load_scenario_file()["scenarios"]] == ["s1", "s2"]

    scenario_file.write_text(
        json.dumps(
            {"rubric_version": "9.9", "scenarios": [{"id": "s3", "type": "t", "title": "新"}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    os.utime(scenario_file, (1_700_002_000, 1_700_002_000))

    assert [s["id"] for s in cn._load_scenario_file()["scenarios"]] == ["s3"], (
        "文件改写后必须重新解析，否则运维改情景库不生效"
    )


def test_missing_file_degrades(tmp_path, monkeypatch):
    monkeypatch.setattr(cn, "_SCENARIO_PATH", str(tmp_path / "nope.json"))
    _reset_cache()

    assert cn._load_scenario_file() == {"scenarios": []}
