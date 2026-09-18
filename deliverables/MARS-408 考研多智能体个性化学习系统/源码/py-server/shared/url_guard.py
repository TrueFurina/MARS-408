# ============================================================
# URL/域名白名单守卫（循环9-P1：防 SSRF，调研结论落地）
#
# 参考 Coze 插件「同插件工具同域名」的域隔离设计，为 Skill 插件
# 工具调用提供域名白名单校验（纵深防御）：
#   - 仅允许 http/https 协议
#   - 仅允许白名单内的域名（默认 = 官方 LLM/讯飞服务域名）
#   - 校验失败抛 URLLimitError，调用方降级处理
# ============================================================

import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("netlearn.url_guard")


class URLLimitError(Exception):
    """URL 不在白名单内 / 协议非法"""


# 默认允许的域名白名单（官方服务域名）
DEFAULT_ALLOWED_DOMAINS = {
    # LLM 通道
    "api.deepseek.com",
    "spark-api-open.xf-yun.com",
    "dashscope.aliyuncs.com",
    # 讯飞开放平台
    "zwapi.xfyun.cn",
    "vms.cn-huadong-1.xf-yun.com",
    "cn-huadong-1.xf-yun.com",
    "search.xfyun.cn",
    # 允许本地开发
    "127.0.0.1",
    "localhost",
}


def validate_url(url: str, allowed_domains: Optional[set] = None) -> str:
    """校验 URL 是否允许访问

    Args:
        url: 待校验 URL
        allowed_domains: 额外允许的域名集合（技能级覆盖，可选）

    Returns:
        规范化后的 URL

    Raises:
        URLLimitError: 协议非法或域名不在白名单内
    """
    if not url:
        raise URLLimitError("URL 为空")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise URLLimitError(f"仅允许 http/https 协议，收到: {parsed.scheme}")

    host = (parsed.hostname or "").lower()
    if not host:
        raise URLLimitError(f"URL 缺少主机名: {url}")

    domains = DEFAULT_ALLOWED_DOMAINS | (allowed_domains or set())
    if host in domains:
        return url

    # 子域名匹配（如 *.xf-yun.com 允许 xxxx.xf-yun.com）
    for d in domains:
        if host.endswith("." + d):
            return url

    logger.warning(f"URL 域名不在白名单，已拦截: {url}")
    raise URLLimitError(f"域名不在白名单内: {host}")


def validate_domain(domain: str, allowed_domains: Optional[set] = None) -> str:
    """校验域名是否在白名单（供 Skill 工具域名白名单校验）"""
    if not domain:
        raise URLLimitError("域名为空")
    d = domain.strip().lower().lstrip(".")
    domains = DEFAULT_ALLOWED_DOMAINS | (allowed_domains or set())
    if d in domains:
        return d
    for base in domains:
        if d.endswith("." + base):
            return d
    raise URLLimitError(f"域名不在白名单内: {domain}")


def is_allowed(url: str, allowed_domains: Optional[set] = None) -> bool:
    """安全检查版：返回布尔（不抛异常，供 try/except 场景）"""
    try:
        validate_url(url, allowed_domains)
        return True
    except URLLimitError:
        return False
