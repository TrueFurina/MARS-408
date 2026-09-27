# -*- coding: utf-8 -*-
"""SSRF 防护守卫单测 —— shared/url_guard.py（此前 0% 覆盖）

为什么值得测：这是防 SSRF 的**安全边界**，此前完全没有测试。
重点不是覆盖率数字，而是把"哪些 URL 必须被拒绝"固化成回归断言 ——
尤其是子域名伪装这类真实攻击手法（`api.deepseek.com.evil.com`）。
"""

import pytest

from shared.url_guard import (
    DEFAULT_ALLOWED_DOMAINS,
    URLLimitError,
    is_allowed,
    validate_domain,
    validate_url,
)


class TestValidateUrlRejects:
    """必须被拒绝的输入（安全负例）。"""

    @pytest.mark.parametrize("url", ["", None])
    def test_empty_url_rejected(self, url):
        with pytest.raises(URLLimitError):
            validate_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://api.deepseek.com/x",
            "javascript:alert(1)",
            "data:text/html,<script>",
            "gopher://127.0.0.1:6379/_INFO",
        ],
    )
    def test_non_http_scheme_rejected(self, url):
        """只允许 http/https —— 其余协议一律拒绝（file/gopher 是经典 SSRF 跳板）。"""
        with pytest.raises(URLLimitError):
            validate_url(url, {"api.deepseek.com"})

    def test_missing_hostname_rejected(self):
        with pytest.raises(URLLimitError):
            validate_url("http://")

    @pytest.mark.parametrize(
        "url",
        [
            "http://evil.com/steal",
            "https://internal-service.local/admin",
            "http://169.254.169.254/latest/meta-data/",   # 云元数据地址（SSRF 典型目标）
            "http://10.0.0.5:8080/",
        ],
    )
    def test_non_whitelisted_host_rejected(self, url):
        with pytest.raises(URLLimitError):
            validate_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "http://api.deepseek.com.evil.com/v1",   # 把白名单域当子域名前缀
            "http://evil.com/api.deepseek.com",
            "http://notapi.deepseek.com.evil.tld",
        ],
    )
    def test_subdomain_spoofing_rejected(self, url):
        """伪装攻击：域名里"包含"白名单域，但真实主机并非白名单域的后代。"""
        with pytest.raises(URLLimitError):
            validate_url(url)


class TestValidateUrlAccepts:
    """必须放行的输入（正常路径）。"""

    @pytest.mark.parametrize(
        "url",
        [
            "https://api.deepseek.com/v1/chat/completions",
            "https://spark-api-open.xf-yun.com/v1/chat",
            "http://127.0.0.1:8002/api/status",
            "http://localhost:5173/",
        ],
    )
    def test_whitelisted_host_accepted(self, url):
        assert validate_url(url) == url

    def test_subdomain_of_whitelisted_accepted(self):
        """白名单域的子域名放行（设计意图，见源码第 67-70 行注释）。"""
        url = "https://cn-huadong-1.xf-yun.com/tts"
        assert validate_url(url) == url

    def test_case_insensitive_host(self):
        assert validate_url("HTTPS://API.DeepSeek.COM/v1") is not None

    def test_extra_allowed_domains_extends_whitelist(self):
        """技能级覆盖：调用方可临时扩展白名单。"""
        url = "https://my-plugin.example.org/tool"
        with pytest.raises(URLLimitError):
            validate_url(url)
        assert validate_url(url, {"my-plugin.example.org"}) == url

    def test_default_whitelist_not_mutated_by_extra_domains(self):
        """扩展白名单不得污染全局默认集合（否则一次调用永久放行）。"""
        validate_url("https://temp.example.org/", {"temp.example.org"})
        assert "temp.example.org" not in DEFAULT_ALLOWED_DOMAINS


class TestValidateDomain:
    def test_empty_domain_rejected(self):
        with pytest.raises(URLLimitError):
            validate_domain("")

    def test_exact_domain_accepted_and_normalized(self):
        assert validate_domain("API.DeepSeek.com") == "api.deepseek.com"

    def test_leading_dot_and_whitespace_stripped(self):
        """`.api.deepseek.com` 这类前导点写法应归一后通过。"""
        assert validate_domain("  .api.deepseek.com  ") == "api.deepseek.com"

    def test_subdomain_accepted(self):
        assert validate_domain("vms.cn-huadong-1.xf-yun.com") == "vms.cn-huadong-1.xf-yun.com"

    @pytest.mark.parametrize("domain", ["evil.com", "api.deepseek.com.evil.com"])
    def test_unlisted_domain_rejected(self, domain):
        with pytest.raises(URLLimitError):
            validate_domain(domain)

    def test_extra_domains_honored(self):
        assert validate_domain("plug.example.org", {"plug.example.org"}) == "plug.example.org"


class TestIsAllowed:
    """布尔版：不抛异常，供 try/except 场景使用。"""

    def test_allowed_returns_true(self):
        assert is_allowed("https://api.deepseek.com/v1") is True

    @pytest.mark.parametrize(
        "url",
        ["https://evil.com", "file:///etc/passwd", "", "http://api.deepseek.com.evil.com"],
    )
    def test_blocked_returns_false(self, url):
        assert is_allowed(url) is False

    def test_never_raises(self):
        """契约：任何输入都不得把异常抛给调用方。"""
        for url in ("", ":::", "http://", "not a url at all", "https://"):
            assert is_allowed(url) in (True, False)
