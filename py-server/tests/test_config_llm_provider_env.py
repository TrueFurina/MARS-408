"""守护：LLM 主通道可由环境变量 LLM_PROVIDER 覆盖（配置级改造 2026-09-15）。

背景：db/llm_provider.py 与 config.get_llm_config 均读 config["llm_provider"] 决定
主通道（auto|deepseek|xfyun|qwen），但 config._apply_env_overrides 的 env_map 原先
缺 LLM_PROVIDER 映射，导致"主通道"无法用环境变量切换（只能改 config.json）。
本次补上顶层键映射；本测试锁定该能力，防止回退。
"""
from config import _apply_env_overrides


def test_llm_provider_env_overrides_top_level(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    cfg = {"llm_provider": "auto", "deepseek": {"api_key": ""}, "xfyun": {"api_key": ""}}
    _apply_env_overrides(cfg)
    assert cfg["llm_provider"] == "deepseek"


def test_llm_provider_unset_keeps_default(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    cfg = {"llm_provider": "auto"}
    _apply_env_overrides(cfg)
    assert cfg["llm_provider"] == "auto"


def test_llm_provider_env_does_not_touch_other_sections(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    # 隔离其他通道凭证类 env（.env 会把真实 XF_API_KEY 等注入 os.environ，
    # 否则本用例会因真实凭证覆盖 xfyun.api_key 而误判）
    for k in (
        "XF_API_KEY", "XF_APP_ID", "XF_APPID", "XF_API_SECRET",
        "XF_API_PASSWORD", "XF_SEARCH_PASSWORD", "XF_MODEL", "XF_ACTIVE_PRESET",
        "DEEPSEEK_API_KEY", "QWEN_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    cfg = {"llm_provider": "auto", "xfyun": {"api_key": "k"}, "qwen": {"api_key": ""}}
    _apply_env_overrides(cfg)
    assert cfg["llm_provider"] == "qwen"
    assert cfg["xfyun"]["api_key"] == "k"


def test_llm_provider_env_accepts_all_known_values(monkeypatch):
    for val in ("auto", "deepseek", "xfyun", "qwen"):
        monkeypatch.setenv("LLM_PROVIDER", val)
        cfg = {"llm_provider": "auto"}
        _apply_env_overrides(cfg)
        assert cfg["llm_provider"] == val
