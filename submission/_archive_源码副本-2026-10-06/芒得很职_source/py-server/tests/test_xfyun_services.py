# ============================================================
# 单元测试骨架：讯飞能力（db/xfyun_services + db/xfyun_multimodal）
#
# 仅用 mock 隔离，不连真实讯飞。覆盖：
#   1. 鉴权签名构造（纯函数，独立重算校验，含 HMAC-SHA256/SHA1/MD5）
#      - _assemble_hmac256_url  (方式 A)
#      - _ppt_signature         (方式 C)
#      - _compliance_signature  (方式 D)
#      - _character_signature   (方式 E)
#   2. 请求/响应解析 + 异常→降级路径
#      - 凭证缺失 → 早返回结构化 error（不抛异常）
#      - respx mock HTTP → 成功/失败/网络异常 三类解析
#   3. G11 回归：xfyun_multimodal._svg_fallback 当 topic 含 <script>
#      时被 html.escape 转义（注入测试，断言转义后不含裸 <script>）
#
# 隔离说明：
#   - 纯签名函数零网络，可直接确定性校验；
#   - HTTP 调用者由 _get_cfg() 网关控制，测试中以 monkeypatch 注入假凭证，
#     再用 respx 拦截 httpx，绝不触达真实讯飞；
#   - respx 当前未列入 pyproject 依赖；respx-only 用例以 skipif 守卫，
#     缺少 respx 时本模块仍可被 pytest 收集且不报错（详见文件底部说明）。
# ============================================================

import base64
import json
import hashlib
import hmac
import httpx
import pytest
from urllib.parse import urlparse, parse_qs

import db.xfyun_services as xs
from db.xfyun_multimodal import _svg_fallback

pytestmark = pytest.mark.unit

try:
    import respx  # noqa: F401
    _HAVE_REPX = True
except ImportError:
    _HAVE_REPX = False


# ───────────────────────────────────────────────────────────
# 1. 鉴权签名构造（纯函数，独立重算校验）
# ───────────────────────────────────────────────────────────

def test_assemble_hmac256_url_structure_and_signature():
    """方式 A：HMAC-SHA256(host/date/request-line)"""
    host_url = "https://spark-api.cn-huabei-1.xf-yun.com/v2.1/image"
    api_key, api_secret = "mykey", "mysecret"
    auth_url = xs._assemble_hmac256_url(host_url, "GET", api_key, api_secret)

    p = urlparse(auth_url)
    assert p.scheme == "https"
    qs = parse_qs(p.query)
    assert qs.get("host") == ["spark-api.cn-huabei-1.xf-yun.com"]
    assert "date" in qs

    auth_b64 = qs["authorization"][0]
    auth_origin = base64.b64decode(auth_b64).decode("utf-8")
    assert f'api_key="{api_key}"' in auth_origin
    assert 'algorithm="hmac-sha256"' in auth_origin
    assert 'headers="host date request-line"' in auth_origin

    # 独立重算签名，验证与讯飞规范一致
    host = "spark-api.cn-huabei-1.xf-yun.com"
    path = "/v2.1/image"
    date = qs["date"][0]
    sig_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
    expected_sig = base64.b64encode(
        hmac.new(api_secret.encode("utf-8"), sig_origin.encode("utf-8"),
                 digestmod=hashlib.sha256).digest()).decode("utf-8")
    assert f'signature="{expected_sig}"' in auth_origin


def test_ppt_signature_matches_reference():
    """方式 C：md5(appId+ts) → HMAC-SHA1(secret)"""
    app_id, secret, ts = "app1", "sec1", 1700000000
    sig = xs._ppt_signature(app_id, secret, ts)
    md5_val = hashlib.md5((app_id + str(ts)).encode("utf-8")).hexdigest()
    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), md5_val.encode("utf-8"),
                 digestmod=hashlib.sha1).digest()).decode("utf-8")
    assert sig == expected


def test_compliance_signature_matches_reference():
    """方式 D：对排序后的参数做 HMAC-SHA1"""
    app_id, api_key, api_secret = "a", "k", "s"
    utc = "2024-01-01T00:00:00+0000"
    nonce = "uuid-123"
    sig = xs._compliance_signature(app_id, api_key, api_secret, utc, nonce)
    from urllib.parse import quote
    params = {"accessKeyId": api_key, "accessKeySecret": api_secret,
              "appId": app_id, "utc": utc, "uuid": nonce}
    base = "&".join(
        f"{k}={quote(str(v), safe='')}" for k, v in sorted(params.items())
        if v != "")
    expected = base64.b64encode(
        hmac.new(api_secret.encode("utf-8"), base.encode("utf-8"),
                 digestmod=hashlib.sha1).digest()).decode("utf-8")
    assert sig == expected


def test_character_signature_matches_reference():
    """方式 E：Base64(HmacSHA1(MD5(appId+timestamp), secret))"""
    app_id, secret, ts_ms = "a", "s", 123456
    sig = xs._character_signature(app_id, secret, ts_ms)
    auth = hashlib.md5((app_id + str(ts_ms)).encode("utf-8")).hexdigest()
    expected = base64.b64encode(
        hmac.new(secret.encode("utf-8"), auth.encode("utf-8"),
                 digestmod=hashlib.sha1).digest()).decode("utf-8")
    assert sig == expected


# ───────────────────────────────────────────────────────────
# 2a. 凭证缺失 → 早返回结构化 error（无网络）
# ───────────────────────────────────────────────────────────

def _empty_cfg():
    return {"app_id": "", "api_key": "", "api_secret": "", "api_password": ""}


def _fake_cfg():
    return {"app_id": "a", "api_key": "k", "api_secret": "s", "api_password": "p"}


def test_has_credentials_false_when_empty(monkeypatch):
    monkeypatch.setattr(xs, "_get_cfg", _empty_cfg)
    assert xs.has_credentials() is False


def test_has_credentials_true_when_present(monkeypatch):
    monkeypatch.setattr(xs, "_get_cfg", _fake_cfg)
    assert xs.has_credentials() is True


async def test_web_search_no_api_password_returns_error(monkeypatch):
    monkeypatch.setattr(xs, "_get_cfg", _empty_cfg)
    r = await xs.web_search("查询")
    assert r.success is False
    assert "API_PASSWORD" in (r.error or "")


async def test_check_compliance_missing_credentials_returns_error(monkeypatch):
    monkeypatch.setattr(xs, "_get_cfg", _empty_cfg)
    r = await xs.check_compliance("内容")
    assert r.success is False
    assert "凭证" in (r.error or "")


async def test_proofread_text_missing_credentials_returns_error(monkeypatch):
    monkeypatch.setattr(xs, "_get_cfg", _empty_cfg)
    r = await xs.proofread_text("文本")
    assert r.success is False


# ───────────────────────────────────────────────────────────
# 2b. respx mock HTTP：成功 / 失败 / 网络异常 解析
#     （respx 缺失时自动跳过，不影响模块收集）
# ───────────────────────────────────────────────────────────

@pytest.mark.skipif(not _HAVE_REPX, reason="respx not installed; 加入 dev/test 依赖以启用 HTTP-mock 用例")
async def test_web_search_success_parses_items(monkeypatch):
    monkeypatch.setattr(xs, "_get_cfg", _fake_cfg)
    payload = {
        "success": True, "message": "ok",
        "data": {"search_results": {"documents": [
            {"name": "Doc1", "summary": "s1", "url": "http://x"},
            {"name": "Doc2", "summary": "s2", "url": "http://y"},
        ]}},
    }
    with respx.mock:
        respx.post(xs.SEARCH_URL).mock(
            return_value=httpx.Response(200, json=payload))
        r = await xs.web_search("量子计算", limit=5)
    assert r.success is True
    assert len(r.items) == 2
    assert r.items[0].title == "Doc1"
    assert r.items[1].url == "http://y"


@pytest.mark.skipif(not _HAVE_REPX, reason="respx not installed")
async def test_web_search_http_failure_returns_error(monkeypatch):
    monkeypatch.setattr(xs, "_get_cfg", _fake_cfg)
    with respx.mock:
        respx.post(xs.SEARCH_URL).mock(
            return_value=httpx.Response(500, json={"success": False, "message": "boom"}))
        r = await xs.web_search("q")
    assert r.success is False
    assert r.error


@pytest.mark.skipif(not _HAVE_REPX, reason="respx not installed")
async def test_web_search_network_exception_downgrades(monkeypatch):
    monkeypatch.setattr(xs, "_get_cfg", _fake_cfg)
    with respx.mock:
        respx.post(xs.SEARCH_URL).mock(side_effect=httpx.ConnectError("network down"))
        r = await xs.web_search("q")
    # 异常→降级路径：不抛异常，返回结构化 error
    assert r.success is False
    assert r.error


# P0-1（Tessa）：直接对应 07-20 事故根因的回归测试。
# 事故：web_search 用 X2 的 api_password 调万搜 → 401。
# 修复：优先用 search_password。本测试断言出站 Authorization 用 search_password 的值。
def _fake_cfg_search():
    return {"app_id": "a", "api_key": "k", "api_secret": "s",
            "api_password": "XPAT", "search_password": "SEARCH_PAT"}


@pytest.mark.skipif(not _HAVE_REPX, reason="respx not installed")
async def test_web_search_uses_search_password_in_authorization(monkeypatch):
    """出站 Authorization 必须是 search_password，而非 api_password（防 07-20 类事故）"""
    monkeypatch.setattr(xs, "_get_cfg", _fake_cfg_search)
    payload = {"success": True, "message": "ok",
               "data": {"search_results": {"documents": [
                   {"name": "D", "summary": "s", "url": "http://z"}]}}}
    with respx.mock:
        respx.post(xs.SEARCH_URL).mock(return_value=httpx.Response(200, json=payload))
        r = await xs.web_search("量子计算", limit=5)
        auth = respx.calls.last.request.headers.get("Authorization")
    assert r.success is True
    assert auth == "Bearer SEARCH_PAT"
    assert auth != "Bearer XPAT"


@pytest.mark.skipif(not _HAVE_REPX, reason="respx not installed")
async def test_web_search_falls_back_to_api_password(monkeypatch):
    """仅配 api_password 时回退用之（事故前的错误路径，现需显式验证回退行为）"""
    monkeypatch.setattr(xs, "_get_cfg", _fake_cfg)  # 只有 api_password="p"
    payload = {"success": True, "message": "ok",
               "data": {"search_results": {"documents": []}}}
    with respx.mock:
        respx.post(xs.SEARCH_URL).mock(return_value=httpx.Response(200, json=payload))
        r = await xs.web_search("q")
        auth = respx.calls.last.request.headers.get("Authorization")
    assert r.success is True
    assert auth == "Bearer p"


@pytest.mark.skipif(not _HAVE_REPX, reason="respx not installed")
async def test_check_compliance_pass_parses(monkeypatch):
    monkeypatch.setattr(xs, "_get_cfg", _fake_cfg)
    payload = {"code": "000000",
               "data": {"result": {"suggest": "pass", "detail": {"category_list": []}}}}
    with respx.mock:
        respx.post(xs.COMPLIANCE_URL).mock(
            return_value=httpx.Response(200, json=payload))
        r = await xs.check_compliance("hello")
    assert r.success is True
    assert r.passed is True
    assert r.suggest == "pass"
    assert r.hits == []


@pytest.mark.skipif(not _HAVE_REPX, reason="respx not installed")
async def test_check_compliance_block_parses_hits(monkeypatch):
    monkeypatch.setattr(xs, "_get_cfg", _fake_cfg)
    payload = {"code": "000000", "data": {"result": {"suggest": "block",
        "detail": {"category_list": [{"category": "political",
                                     "word_list": ["违禁词"], "confidence": 0.95}]}}}}
    with respx.mock:
        respx.post(xs.COMPLIANCE_URL).mock(
            return_value=httpx.Response(200, json=payload))
        r = await xs.check_compliance("敏感内容")
    assert r.success is True
    assert r.passed is False
    assert r.suggest == "block"
    assert r.hits[0]["word"] == "违禁词"


@pytest.mark.skipif(not _HAVE_REPX, reason="respx not installed")
async def test_proofread_text_parses_corrections(monkeypatch):
    monkeypatch.setattr(xs, "_get_cfg", _fake_cfg)
    inner = {"spelling": [["1", "teh", "the", "spell"]]}
    b64 = base64.b64encode(json.dumps(inner).encode("utf-8")).decode("utf-8")
    payload = {"header": {"code": 0, "message": "ok"},
               "payload": {"result": {"text": b64}}}
    with respx.mock:
        respx.post(xs.CORRECT_URL).mock(
            return_value=httpx.Response(200, json=payload))
        r = await xs.proofread_text("I ate teh apple")
    assert r.success is True
    assert len(r.corrections) == 1
    assert r.corrections[0][2] == "the"


@pytest.mark.skipif(not _HAVE_REPX, reason="respx not installed")
async def test_proofread_document_call_path(monkeypatch):
    monkeypatch.setattr(xs, "_get_cfg", _fake_cfg)
    # 公文校对 schema：payload.output_result.text = base64({data:{checklist:[...]}})
    # 每项 checklist: {position, word, suggest[], type:{name}}
    inner = {"data": {"checklist": [
        {"position": 2, "word": "he go", "suggest": ["he goes"], "type": {"name": "grammar"}}
    ]}}
    b64 = base64.b64encode(json.dumps(inner).encode("utf-8")).decode("utf-8")
    payload = {"header": {"code": 0, "message": "ok"},
               "payload": {"output_result": {"text": b64}}}
    with respx.mock:
        respx.post(xs.GOVPROOF_URL).mock(
            return_value=httpx.Response(200, json=payload))
        r = await xs.proofread_document("He go school")
    assert r.success is True
    assert r.corrections[0][2] == "he goes"


# ───────────────────────────────────────────────────────────
# 3. G11 回归：_svg_fallback 对 topic 注入做 html.escape 转义
# ───────────────────────────────────────────────────────────

def test_svg_fallback_escapes_script_tag():
    """G11：topic 含 <script> 时，输出 SVG 不得包含裸 <script> 标签
    （防存储型 XSS / SVG 注入）。"""
    malicious = "<script>alert('xss')</script>"
    r = _svg_fallback(prompt="教学概念", topic=malicious)
    assert r.success is True
    assert r.source == "svg_fallback"
    assert r.image_svg is not None
    # 关键断言：转义后字符串不含裸 <script（任何形式）
    assert "<script" not in r.image_svg
    assert "</script>" not in r.image_svg
    # 转义形态应出现
    assert "&lt;script&gt;" in r.image_svg


def test_svg_fallback_normal_topic_contains_title():
    r = _svg_fallback(prompt="二叉树遍历", topic="二叉树遍历")
    assert r.success is True
    assert "二叉树遍历" in r.image_svg


def test_svg_fallback_falls_back_to_prompt_when_topic_empty():
    r = _svg_fallback(prompt="哈希表冲突", topic="")
    assert r.success is True
    assert "哈希表冲突" in r.image_svg
