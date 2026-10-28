# ============================================================
# WS1 覆盖率补全 — shared/llm_utils.py（LLM 输出 JSON 提取）
#
# 此前在测试套件中零引用（grep shared.<mod> 无命中），却是 LLM 输出解析的
# 关键路径（agent / engine / API 共用）。契约核心：**永远不抛异常**，失败返回 default。
# 纯标准库（json/logging），可脱离 conftest 独立运行：
#   py-server/.venv/Scripts/python.exe -m pytest tests/test_shared_llm_utils.py --noconftest -q
# ================================================================

from shared.llm_utils import extract_json_from_llm_output


def test_pure_json_object():
    assert extract_json_from_llm_output('{"a": 1, "b": [2, 3]}') == {"a": 1, "b": [2, 3]}


def test_markdown_json_code_block():
    text = '说明如下：\n```json\n{"score": 8}\n```\n以上。'
    assert extract_json_from_llm_output(text) == {"score": 8}


def test_mixed_text_with_json():
    assert extract_json_from_llm_output('前缀文字 {"a": 1} 后缀文字') == {"a": 1}


def test_nested_object():
    assert extract_json_from_llm_output('{"a": {"b": 1}}') == {"a": {"b": 1}}


def test_invalid_json_returns_empty_default():
    assert extract_json_from_llm_output("这不是 JSON") == {}


def test_invalid_json_returns_given_default():
    assert extract_json_from_llm_output("这不是 JSON", default={"fallback": True}) == {"fallback": True}


def test_empty_string_returns_default():
    assert extract_json_from_llm_output("", default={"d": 1}) == {"d": 1}


def test_none_returns_default():
    assert extract_json_from_llm_output(None, default={"d": 1}) == {"d": 1}


def test_non_string_input_returns_default():
    assert extract_json_from_llm_output(12345, default={"d": 1}) == {"d": 1}


def test_non_dict_json_returns_default():
    # JSON 数组解析成功但非 dict ⇒ 不属于契约要求的返回类型，回退默认值
    assert extract_json_from_llm_output("[1, 2, 3]", default={"d": 1}) == {"d": 1}


def test_truncated_json_returns_default():
    assert extract_json_from_llm_output('{"a": ', default={"d": 1}) == {"d": 1}


def test_default_none_gives_empty_dict():
    assert extract_json_from_llm_output("bad", default=None) == {}
