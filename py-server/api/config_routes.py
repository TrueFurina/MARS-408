# ============================================================
# API — 配置读写
# 从 learning.py 拆分 (D-05)
# ============================================================

import logging

from fastapi import APIRouter, Depends, Request
from db.llm_provider import LLMProvider
from config import load_config, save_config
from models import ConfigResponse
from shared.auth import require_admin
from shared.audit import log_event

logger = logging.getLogger("netlearn.config")

router = APIRouter(prefix="", tags=["config"])


def _mask_key(key: str) -> str:
    """掩码 API 密钥：保留前4位与后4位，中间以 **** 替换（前4 + "****" + 后4）。

    脱敏规则与 db/llm_provider.py:get_provider_info 保持一致，避免密钥经 /api/config
    明文回传（F-002 配置 API 无认证泄露密钥）。长度 <= 8 的短密钥直接整体掩码。
    掩码结果仍包含 "****" 子串，POST /config 据此跳过覆盖真实密钥。
    """
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"


@router.get("/config")
async def config_get(user: dict = Depends(require_admin)):
    """获取配置 — 从深度嵌套结构手动提取到扁平 ConfigResponse"""
    cfg = load_config()
    provider = cfg.get("llm_provider", "deepseek")
    # 从对应 provider 子结构中提取值
    provider_cfg = cfg.get(provider, {})
    # 讯飞配置
    xfyun_cfg = cfg.get("xfyun", {})
    return ConfigResponse(
        llm_api_key=_mask_key(provider_cfg.get("api_key", "")),
        llm_base_url=provider_cfg.get("base_url", "https://api.deepseek.com"),
        llm_model=provider_cfg.get("model", "deepseek-chat"),
        embedding_mode=cfg.get("embedding", {}).get("mode", "local"),
        llm_provider=provider,
        xfyun_api_key=_mask_key(xfyun_cfg.get("api_key", "")),
        xfyun_app_id=_mask_key(xfyun_cfg.get("app_id", "")),
        xfyun_base_url=xfyun_cfg.get("base_url", "https://spark-api-open.xf-yun.com/x2"),
        xfyun_model=xfyun_cfg.get("model", "4.0Ultra"),
    )


@router.post("/config")
async def config_post(config: ConfigResponse, user: dict = Depends(require_admin), request: Request = None):
    """更新配置 — 扁平字段映射到深度嵌套结构后保存"""
    saved = load_config()
    # 映射 LLM provider 对应的子配置
    provider = config.llm_provider or saved.get("llm_provider", "deepseek")
    saved["llm_provider"] = provider
    if provider in saved and isinstance(saved[provider], dict):
        # 跳过掩码密钥（含 ****），避免用掩码值覆盖真实密钥
        if config.llm_api_key and "****" not in config.llm_api_key:
            saved[provider]["api_key"] = config.llm_api_key
        if config.llm_base_url:
            saved[provider]["base_url"] = config.llm_base_url
        if config.llm_model:
            saved[provider]["model"] = config.llm_model
    else:
        saved[provider] = {
            "api_key": config.llm_api_key if config.llm_api_key and "****" not in config.llm_api_key else saved.get(provider, {}).get("api_key", ""),
            "base_url": config.llm_base_url or "https://api.deepseek.com",
            "model": config.llm_model or "deepseek-chat",
        }
    # 讯飞配置映射（同样跳过掩码密钥）
    if (config.xfyun_api_key and "****" not in config.xfyun_api_key) or (config.xfyun_app_id and "****" not in config.xfyun_app_id):
        if "xfyun" not in saved or not isinstance(saved["xfyun"], dict):
            saved["xfyun"] = {}
        if config.xfyun_api_key and "****" not in config.xfyun_api_key:
            saved["xfyun"]["api_key"] = config.xfyun_api_key
        if config.xfyun_app_id and "****" not in config.xfyun_app_id:
            saved["xfyun"]["app_id"] = config.xfyun_app_id
    # Embedding 配置映射
    saved["embedding"]["mode"] = config.embedding_mode
    save_config(saved)
    ip = request.client.host if request and request.client else "unknown"
    log_event("config_change", user_id=user["user_id"], ip=ip, result="success", detail=f"provider={config.llm_provider}")
    return {"status": "ok"}


@router.post("/config/test-llm")
async def config_test_llm(user: dict = Depends(require_admin)):
    """测试 LLM 连接"""
    llm = LLMProvider()
    result = await llm.text_completion(
        "你是一个简单的助手。只需回复'连接正常'即可。",
        "你好",
    )
    if result:
        return {"status": "ok", "message": "LLM 连接正常"}
    return {"status": "error", "message": "LLM 连接失败，请检查 API Key"}
