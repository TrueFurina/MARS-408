# ============================================================
# 讯飞开放平台 — 统一多能力服务集成
#
# 赛题要求："开发过程中使用的其他AI辅助工具，需选用科大讯飞相关工具"
# 本模块深度集成用户控制台已开通的全部讯飞能力：
#   1. TTI 图片生成        → 教学插图        (xfyun_multimodal 已实现，本模块复用)
#   2. 图片理解            → 多模态问答(上传图片提问)
#   3. 聚合搜索(万搜)      → RAG 联网检索增强
#   4. 智能 PPT 生成       → 演示 PPT 一键生成
#   5. 数字人视频大模型    → 演示视频一键生成
#   6. 文本纠错            → 辅导内容拼写/语法纠错
#   7. 公文校对            → 文档校对(同纠错，不同引擎)
#   8. 文本合规            → 内容安全审核(防幻觉/违规)
#   9. 角色模拟            → 模拟面试官/导师多轮对话
#   10. 智能简历           → 生成可下载考研复试简历(word)
#
# 控制台已开通的全部讯飞能力均已封装（TTI/星火LLM/向量化另见他处）。
#
# 鉴权方式有三种，均已实现：
#   A. HMAC-SHA256(host/date/request-line) — TTI/视频/图片理解/纠错/校对
#   B. Bearer APIPassword                   — 聚合搜索
#   C. appId+timestamp+signature(MD5+HMAC-SHA1) — 智能PPT
#   D. accessKeyId+utc+signature(HMAC-SHA1) — 文本合规
#
# 所有函数带异常兜底，失败时返回结构化错误而非抛异常。
# ============================================================

import os
import time
import json
import base64
import hashlib
import hmac
import logging
import asyncio
import uuid
from datetime import datetime
from urllib.parse import urlencode, quote
from typing import Optional

import httpx

logger = logging.getLogger("netlearn.xfyun_services")


# ── 配置 ──

def _get_cfg() -> dict:
    """从 config.json 读取讯飞统一凭证（所有服务共用同一 APPID/APIKey/APISecret）"""
    try:
        from config import load_config
        x = load_config().get("xfyun", {})
        return {
            "app_id": x.get("app_id", ""),
            "api_key": x.get("api_key", ""),
            "api_secret": x.get("api_secret", ""),
            "api_password": x.get("api_password", ""),
            "search_password": x.get("search_password", ""),
        }
    except Exception:
        return {"app_id": "", "api_key": "", "api_secret": "", "api_password": ""}


def has_credentials() -> bool:
    """是否具备调用讯飞 HMAC 类服务的最小凭证"""
    c = _get_cfg()
    return bool(c["app_id"] and c["api_key"] and c["api_secret"])


# ── 鉴权方式 A：HMAC-SHA256(host/date/request-line) ──

def _assemble_hmac256_url(host_url: str, method: str,
                           api_key: str, api_secret: str) -> str:
    """讯飞标准 WebAPI 签名（TTI/视频/图片理解/纠错/校对 通用）"""
    from urllib.parse import urlparse
    parsed = urlparse(host_url)
    host = parsed.hostname
    path = parsed.path
    date = format_date_time_rfc1123()

    signature_origin = f"host: {host}\ndate: {date}\n{method} {path} HTTP/1.1"
    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")
    auth_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(auth_origin.encode("utf-8")).decode("utf-8")
    return host_url + "?" + urlencode({"host": host, "date": date, "authorization": authorization})


def format_date_time_rfc1123() -> str:
    """RFC1123 格式时间戳（GMT/UTC）"""
    from wsgiref.handlers import format_date_time
    from time import mktime
    return format_date_time(mktime(datetime.now().timetuple()))


# ── 鉴权方式 C：智能PPT(appId+timestamp+signature MD5+HMAC-SHA1) ──

def _ppt_signature(app_id: str, secret: str, ts: int) -> str:
    """PPT 专用签名：md5(appId+ts) → HMAC-SHA1(secret)"""
    md5_val = hashlib.md5((app_id + str(ts)).encode("utf-8")).hexdigest()
    raw = hmac.new(secret.encode("utf-8"), md5_val.encode("utf-8"),
                   digestmod=hashlib.sha1).digest()
    return base64.b64encode(raw).decode("utf-8")


# ── 鉴权方式 D：文本合规(accessKeyId+utc+signature HMAC-SHA1) ──

def _compliance_signature(app_id: str, api_key: str, api_secret: str,
                          utc: str, nonce: str) -> str:
    """文本合规签名：对排序后的参数做 HMAC-SHA1"""
    params = {
        "accessKeyId": api_key,
        "accessKeySecret": api_secret,
        "appId": app_id,
        "utc": utc,
        "uuid": nonce,
    }
    # 按 key ASCII 升序拼接，值为空不参与，value 需 urlencode
    sorted_items = sorted(params.items(), key=lambda kv: kv[0])
    base_string = "&".join(
        f"{k}={quote(str(v), safe='')}" for k, v in sorted_items if v != ""
    )
    raw = hmac.new(api_secret.encode("utf-8"), base_string.encode("utf-8"),
                   digestmod=hashlib.sha1).digest()
    return base64.b64encode(raw).decode("utf-8")


# ── 鉴权方式 E：角色模拟(MD5+HmacSHA1) ──

def _character_signature(app_id: str, secret: str, ts_ms: int) -> str:
    """角色模拟签名：signature = Base64(HmacSHA1(MD5(appId+timestamp), secret))"""
    auth = hashlib.md5((app_id + str(ts_ms)).encode("utf-8")).hexdigest()
    raw = hmac.new(secret.encode("utf-8"), auth.encode("utf-8"),
                   digestmod=hashlib.sha1).digest()
    return base64.b64encode(raw).decode("utf-8")


def _character_headers() -> dict:
    c = _get_cfg()
    ts = int(time.time() * 1000)
    return {
        "appId": c["app_id"],
        "timestamp": str(ts),
        "signature": _character_signature(c["app_id"], c["api_secret"], ts),
        "Content-Type": "application/json",
    }


def _extract_id(resp: dict, *keys: str) -> Optional[str]:
    """角色模拟接口 data 可能是 id 字符串或含 id 字段的对象"""
    d = resp.get("data") if isinstance(resp, dict) else None
    if isinstance(d, str):
        return d
    if isinstance(d, dict):
        for k in keys:
            if d.get(k):
                return d[k]
    return None


# ════════════════════════════════════════════════
# 2. 图片理解（多模态问答，WebSocket）
# ════════════════════════════════════════════════

IMAGE_WS = "wss://spark-api.cn-huabei-1.xf-yun.com/v2.1/image"


from dataclasses import dataclass, field


@dataclass
class ImageUnderstandResult:
    success: bool
    text: str = ""
    error: Optional[str] = None


async def understand_image(image_base64: str, question: str,
                           domain: str = "imagev3") -> ImageUnderstandResult:
    """上传图片 + 提问，返回讯飞图片理解回答（Markdown/文本）"""
    if not has_credentials():
        return ImageUnderstandResult(success=False, error="讯飞凭证未配置")
    c = _get_cfg()
    try:
        import websockets
        auth_url = _assemble_hmac256_url(IMAGE_WS, "GET", c["api_key"], c["api_secret"])
        body = {
            "header": {"app_id": c["app_id"], "uid": "netlearn"},
            "parameter": {"chat": {"domain": domain, "temperature": 0.5,
                                    "top_k": 4, "max_tokens": 2028}},
            "payload": {"message": {"text": [
                {"role": "user", "content": image_base64, "content_type": "image"},
                {"role": "user", "content": question, "content_type": "text"},
            ]}},
        }
        async with websockets.connect(auth_url, max_size=20 * 1024 * 1024) as ws:
            await ws.send(json.dumps(body))
            collected = []
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                data = json.loads(raw)
                code = data.get("header", {}).get("code", -1)
                if code != 0:
                    return ImageUnderstandResult(
                        success=False, error=data.get("header", {}).get("message", "图片理解失败"))
                texts = data.get("payload", {}).get("choices", {}).get("text", [])
                for t in texts:
                    if t.get("content"):
                        collected.append(t["content"])
                if data.get("header", {}).get("status") == 2:
                    break
            return ImageUnderstandResult(success=True, text="".join(collected))
    except ImportError:
        return ImageUnderstandResult(success=False, error="websockets 库未安装")
    except Exception as e:
        logger.warning(f"图片理解异常: {e}")
        return ImageUnderstandResult(success=False, error=str(e))


# ════════════════════════════════════════════════
# 3. 聚合搜索（万搜，Bearer APIPassword）
# ════════════════════════════════════════════════

SEARCH_URL = "https://search-api-open.cn-huabei-1.xf-yun.com/v2/search"


@dataclass
class SearchResultItem:
    title: str = ""
    summary: str = ""
    url: str = ""


@dataclass
class SearchResult:
    success: bool
    items: list = field(default_factory=list)
    error: Optional[str] = None


async def web_search(query: str, limit: int = 10) -> SearchResult:
    """讯飞万搜：联网检索，用于 RAG 检索增强"""
    c = _get_cfg()
    # 万搜(聚合搜索)有独立 PAT，优先用 search_password，回退到通用 api_password
    pw = c.get("search_password") or c.get("api_password")
    if not pw:
        return SearchResult(success=False, error="讯飞搜索 PAT 未配置(请设置 XF_SEARCH_PASSWORD 或 XF_API_PASSWORD)")
    try:
        headers = {
            "Authorization": f"Bearer {pw}",
            "Content-Type": "application/json",
        }
        body = {"search_params": {"query": query, "limit": min(max(limit, 1), 20)}}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(SEARCH_URL, json=body, headers=headers)
            data = resp.json()
        if not data.get("success"):
            return SearchResult(success=False, error=data.get("message", "搜索失败"))
        docs = data.get("data", {}).get("search_results", {}).get("documents", [])
        items = [SearchResultItem(title=d.get("name", ""),
                                  summary=d.get("summary", ""),
                                  url=d.get("url", "")) for d in docs]
        return SearchResult(success=True, items=items)
    except Exception as e:
        logger.warning(f"聚合搜索异常: {e}")
        return SearchResult(success=False, error=str(e))


# ════════════════════════════════════════════════
# 4. 智能 PPT 生成（异步：创建 → 轮询）
# ════════════════════════════════════════════════

PPT_CREATE = "https://zwapi.xfyun.cn/api/ppt/v2/create"
PPT_PROGRESS = "https://zwapi.xfyun.cn/api/ppt/v2/progress"


@dataclass
class PPTResult:
    success: bool
    ppt_url: Optional[str] = None
    title: str = ""
    sid: str = ""
    error: Optional[str] = None


def _ppt_headers() -> dict:
    c = _get_cfg()
    ts = int(time.time())
    sig = _ppt_signature(c["app_id"], c["api_secret"], ts)
    # 注意：不在此设置 Content-Type，multipart 请求由 httpx 自动加 boundary
    return {
        "appId": c["app_id"],
        "timestamp": str(ts),
        "signature": sig,
    }


async def generate_ppt(query: str, is_figure: bool = True,
                       ai_image: str = "normal", template_id: str = "",
                       search: bool = True) -> PPTResult:
    """生成智能 PPT（直接生成，含 AI 配图）。返回可下载 pptx 链接。
    注意：每次直接生成消耗 10 点额度（AI配图另计）。"""
    c = _get_cfg()
    if not (c["app_id"] and c["api_secret"]):
        return PPTResult(success=False, error="讯飞 PPT 凭证未配置")
    try:
        headers = _ppt_headers()
        # /create 端点要求 multipart/form-data
        form = {
            "query": (None, query[:12000]),
            "isFigure": (None, "true" if is_figure else "false"),
            "aiImage": (None, ai_image),
            "search": (None, "true" if search else "false"),
            "language": (None, "cn"),
            "isCardNote": (None, "true"),
        }
        if template_id:
            form["templateId"] = (None, template_id)
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(PPT_CREATE, files=form, headers=headers)
            data = r.json()
        if not data.get("flag") or data.get("code") != 0:
            return PPTResult(success=False, error=data.get("desc", "PPT创建失败"))
        sid = data["data"]["sid"]
        title = data["data"].get("title", "")
        # 轮询进度（限流：3秒一次），progress 端点同样需要鉴权头
        for _ in range(40):  # 最多等 ~120s
            await asyncio.sleep(3)
            async with httpx.AsyncClient(timeout=20) as client:
                pr = await client.get(f"{PPT_PROGRESS}?sid={sid}", headers=_ppt_headers())
                if pr.status_code != 200:
                    continue
                pd = pr.json()
            if pd.get("code") == 0:
                st = pd.get("data", {}).get("pptStatus")
                if st == "done":
                    return PPTResult(
                        success=True,
                        ppt_url=pd["data"].get("pptUrl"),
                        title=title, sid=sid)
                if st == "build_failed":
                    return PPTResult(success=False, error="PPT生成失败")
        return PPTResult(success=False, error="PPT生成超时", sid=sid)
    except Exception as e:
        logger.warning(f"PPT生成异常: {e}")
        return PPTResult(success=False, error=str(e))


# ════════════════════════════════════════════════
# 5. 数字人视频大模型（异步：创建 → 轮询）
# ════════════════════════════════════════════════

VIDEO_GEN = "https://vms.cn-huadong-1.xf-yun.com/v1/private/video/generate"
VIDEO_QUERY = "https://vms.cn-huadong-1.xf-yun.com/v1/private/video/query"


@dataclass
class VideoResult:
    success: bool
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    text: str = ""
    task_id: str = ""
    error: Optional[str] = None


async def generate_video(prompt: str, word_count: int = 120) -> VideoResult:
    """数字人视频生成：输入文本 prompt，自动扩写播报+合成语音+渲染视频。
    返回 mp4 下载链接。注意：额度有限（控制台 300 秒）。"""
    if not has_credentials():
        return VideoResult(success=False, error="讯飞凭证未配置")
    c = _get_cfg()
    try:
        auth_url = _assemble_hmac256_url(VIDEO_GEN, "POST", c["api_key"], c["api_secret"])
        body = {
            "header": {"app_id": c["app_id"]},
            "parameter": {"avatar": {"prompt": prompt[:2000],
                                     "word_count": max(50, min(word_count, 300))}},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(auth_url, json=body)
            data = r.json()
        if data.get("header", {}).get("code", -1) != 0:
            return VideoResult(success=False,
                               error=data.get("header", {}).get("message", "视频创建失败"))
        task_id = data["header"]["task_id"]
        # 轮询
        for _ in range(60):  # 最多等 ~5min
            await asyncio.sleep(5)
            q_url = _assemble_hmac256_url(VIDEO_QUERY, "POST", c["api_key"], c["api_secret"])
            async with httpx.AsyncClient(timeout=20) as client:
                qr = await client.post(q_url, json={"header": {"app_id": c["app_id"],
                                                              "task_id": task_id}})
                qd = qr.json()
            status = qd.get("header", {}).get("task_status", "")
            if status in ("3", "4"):
                payload = qd.get("payload", {})
                return VideoResult(
                    success=True,
                    video_url=payload.get("video"),
                    audio_url=payload.get("audio"),
                    text=payload.get("text", ""),
                    task_id=task_id)
            if qd.get("header", {}).get("code", 0) != 0:
                return VideoResult(success=False,
                                   error=qd.get("header", {}).get("message", "查询失败"),
                                   task_id=task_id)
        return VideoResult(success=False, error="视频生成超时", task_id=task_id)
    except Exception as e:
        logger.warning(f"视频生成异常: {e}")
        return VideoResult(success=False, error=str(e))


# ════════════════════════════════════════════════
# 6. 文本纠错 / 7. 公文校对（共用 HMAC-SHA256，不同 service path）
# ════════════════════════════════════════════════

CORRECT_URL = "https://api.xf-yun.com/v1/private/s9a87e3ec"
GOVPROOF_URL = "https://cn-huadong-1.xf-yun.com/v1/private/s37b42a45"


@dataclass
class ProofreadResult:
    success: bool
    corrections: list = field(default_factory=list)  # [[pos,cur,correct,type],...]
    error: Optional[str] = None


async def _xfyun_correct(text: str, url: str, service_key: str) -> ProofreadResult:
    if not has_credentials():
        return ProofreadResult(success=False, error="讯飞凭证未配置")
    c = _get_cfg()
    try:
        auth_url = _assemble_hmac256_url(url, "POST", c["api_key"], c["api_secret"])
        body = {
            "header": {"app_id": c["app_id"], "status": 3},
            "parameter": {service_key: {"result": {"encoding": "utf8",
                                                    "compress": "raw", "format": "json"}}},
            "payload": {"input": {"encoding": "utf8", "compress": "raw",
                                  "format": "json", "status": 3,
                                  "text": base64.b64encode(text.encode("utf-8")).decode("utf-8")}},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(auth_url, json=body)
            data = r.json()
        if data.get("header", {}).get("code", -1) != 0:
            return ProofreadResult(success=False,
                                   error=data.get("header", {}).get("message", "纠错失败"))
        raw = data.get("payload", {}).get("result", {}).get("text", "")
        if not raw:
            return ProofreadResult(success=True, corrections=[])
        decoded = json.loads(base64.b64decode(raw).decode("utf-8"))
        # 合并所有错误类型
        merged = []
        for corr_type, items in decoded.items():
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, list) and len(it) >= 3:
                        merged.append(it)
        return ProofreadResult(success=True, corrections=merged)
    except Exception as e:
        logger.warning(f"文本纠错异常: {e}")
        return ProofreadResult(success=False, error=str(e))


async def proofread_text(text: str) -> ProofreadResult:
    """文本纠错：拼写/语法/搭配/实体/标点/数字纠错"""
    return await _xfyun_correct(text, CORRECT_URL, "s9a87e3ec")


async def proofread_document(text: str) -> ProofreadResult:
    """公文校对：政务/公文风格校对（midu_correct 引擎，schema 与文本纠错不同）

    讯飞公文校对 API 请求体：
      parameter.midu_correct.output_result + payload.text.text(base64)
    返回 payload.output_result.text = base64(JSON{code, msg, data:{checklist}})
    checklist 项含 word/position/suggest[]/type.name 等。
    """
    if not has_credentials():
        return ProofreadResult(success=False, error="讯飞凭证未配置")
    c = _get_cfg()
    try:
        auth_url = _assemble_hmac256_url(GOVPROOF_URL, "POST", c["api_key"], c["api_secret"])
        body = {
            "header": {"app_id": c["app_id"], "status": 3},
            "parameter": {"midu_correct": {"output_result": {
                "encoding": "utf8", "compress": "raw", "format": "json"}}},
            "payload": {"text": {
                "encoding": "utf8", "compress": "raw", "format": "plain",
                "status": 3,
                "text": base64.b64encode(text.encode("utf-8")).decode("utf-8")}},
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(auth_url, json=body)
            data = r.json()
        if data.get("header", {}).get("code", -1) != 0:
            return ProofreadResult(success=False,
                                   error=data.get("header", {}).get("message", "公文校对失败"))
        raw = data.get("payload", {}).get("output_result", {}).get("text", "")
        if not raw:
            return ProofreadResult(success=True, corrections=[])
        decoded = json.loads(base64.b64decode(raw).decode("utf-8"))
        merged = []
        for it in (decoded.get("data", {}) or {}).get("checklist", []) or []:
            if not isinstance(it, dict):
                continue
            pos = it.get("position", 0)
            cur = it.get("word", "")
            sugg = it.get("suggest") or []
            correct = sugg[0] if isinstance(sugg, list) and sugg else ""
            tname = ""
            t = it.get("type")
            if isinstance(t, dict):
                tname = t.get("name", "")
            merged.append([pos, cur, correct, tname])
        return ProofreadResult(success=True, corrections=merged)
    except Exception as e:
        logger.warning(f"公文校对异常: {e}")
        return ProofreadResult(success=False, error=str(e))


# ════════════════════════════════════════════════
# 8. 文本合规（内容安全审核）
# ════════════════════════════════════════════════

COMPLIANCE_URL = "https://audit.iflyaisol.com/audit/v2/syncText"

# 默认检测分类（赛题系统面向教育，重点防涉政/暴恐/广告/辱骂）
DEFAULT_CATEGORIES = [
    "pornDetection", "violentTerrorism", "political",
    "lowQualityIrrigation", "contraband", "advertisement",
    "uncivilizedLanguage",
]


@dataclass
class ComplianceResult:
    success: bool
    passed: bool = True           # True=合规, False=命中风险
    suggest: str = "pass"         # pass | block
    hits: list = field(default_factory=list)  # [{category, word, confidence}]
    error: Optional[str] = None


async def check_compliance(text: str,
                           categories: list = None) -> ComplianceResult:
    """文本合规审核：识别涉政/违禁/色情/暴恐/辱骂/广告等风险。
    用于辅导链路内容安全（防幻觉 + 防违规输出）。"""
    c = _get_cfg()
    if not (c["app_id"] and c["api_key"] and c["api_secret"]):
        return ComplianceResult(success=False, error="讯飞凭证未配置")
    try:
        utc = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+0000")
        nonce = str(uuid.uuid4())
        sig = _compliance_signature(c["app_id"], c["api_key"], c["api_secret"], utc, nonce)
        # 安全说明（Cody #2）：讯飞文本合规 API 要求 accessKeySecret 随请求传递
        # 以完成服务端验签（实测移除后返回“验签失败”）。故此处必须保留在 URL query 中，
        # 无法移入 body/header。残留风险：URL 含密钥会进入 access log/APM/httpx 异常。
        # 缓解措施（运维侧）：反向代理/uvicorn access log 裁剪 query string；密钥仅存 .env 不入库。
        params = {
            "accessKeyId": c["api_key"],
            "accessKeySecret": c["api_secret"],
            "appId": c["app_id"],
            "utc": utc,
            "uuid": nonce,
            "signature": sig,
        }
        url = COMPLIANCE_URL + "?" + urlencode(params)
        body = {
            "content": text[:5000],
            "categories": categories or DEFAULT_CATEGORIES,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=body)
            data = r.json()
        if data.get("code") != "000000":
            return ComplianceResult(success=False, error=data.get("desc", "审核失败"))
        result = data.get("data", {}).get("result", {})
        suggest = result.get("suggest", "pass")
        hits = []
        for cat in result.get("detail", {}).get("category_list", []):
            for w in cat.get("word_list", []):
                hits.append({
                    "category": cat.get("category"),
                    "word": w,
                    "confidence": cat.get("confidence", 0),
                })
        return ComplianceResult(
            success=True,
            passed=(suggest == "pass"),
            suggest=suggest,
            hits=hits,
        )
    except Exception as e:
        logger.warning(f"文本合规异常: {e}")
        return ComplianceResult(success=False, error=str(e))


# ════════════════════════════════════════════════
# 9. 角色模拟（星火角色模拟：注册玩家→创建人格→新建会话→WS对话）
# ════════════════════════════════════════════════

CHARACTER_HOST = "https://ai-character-v2.xfyun.cn"
CHARACTER_WS = "wss://ai-character-v2.xfyun.cn"

# 默认角色库：一键模拟不同面试/答疑场景（赛题面向408考研）
DEFAULT_PERSONAS = {
    "interviewer_network": "你是严格的计算机网络考研面试官，会针对TCP/IP、拥塞控制、路由算法等考点连续追问，指出回答中的不足。",
    "interviewer_os": "你是操作系统考研面试官，重点考察进程调度、内存管理、死锁、文件系统，要求用专业术语严谨作答。",
    "tutor": "你是耐心的408考研一对一导师，用通俗类比解释数据结构、组成原理等难点，并给出复习建议。",
    "mock_interviewer": "你是通用的计算机考研复试模拟面试官，综合408四科随机提问，评估知识掌握与表达。",
}


@dataclass
class RoleplayResult:
    success: bool
    reply: str = ""
    chat_id: str = ""
    error: Optional[str] = None


# 进程级会话缓存：相同 (user_id, persona) 复用同一对话，支持多轮连续模拟
# 加 TTL + 上限，避免内存泄漏（Cody #3）
_ROLEPLAY_SESSION_TTL = 3600       # 秒
_ROLEPLAY_SESSION_MAX = 1024
_roleplay_sessions: dict = {}


def _prune_roleplay_sessions() -> None:
    """淘汰过期/超限的会话缓存条目"""
    now = time.time()
    expired = [k for k, v in _roleplay_sessions.items()
               if now - v.get("ts", 0) > _ROLEPLAY_SESSION_TTL]
    for k in expired:
        _roleplay_sessions.pop(k, None)
    # 超限时按 ts 升序淘汰最旧
    if len(_roleplay_sessions) > _ROLEPLAY_SESSION_MAX:
        overflow = len(_roleplay_sessions) - _ROLEPLAY_SESSION_MAX
        oldest = sorted(_roleplay_sessions.items(),
                        key=lambda kv: kv[1].get("ts", 0))[:overflow]
        for k, _ in oldest:
            _roleplay_sessions.pop(k, None)


async def _character_post(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(CHARACTER_HOST + path, json=body, headers=_character_headers())
        return r.json()


async def roleplay_interview(persona: str, user_message: str, user_id: str = "",
                             topic: str = "") -> RoleplayResult:
    """星火角色模拟：模拟面试官/导师与用户多轮对话。
    persona: 角色设定描述（或 DEFAULT_PERSONAS 的 key）
    user_message: 用户本轮发言；topic: 可选面试主题
    """
    if not has_credentials():
        return RoleplayResult(success=False, error="讯飞凭证未配置")
    c = _get_cfg()
    persona_desc = DEFAULT_PERSONAS.get(persona, persona)
    try:
        key = f"{user_id}:{persona}"
        sess = _roleplay_sessions.get(key)
        if sess and time.time() - sess.get("ts", 0) > _ROLEPLAY_SESSION_TTL:
            _roleplay_sessions.pop(key, None)
            sess = None
        if not sess:
            # 1. 注册玩家
            pres = await _character_post("/personality/open/player/register",
                                        {"playerName": "netlearn_user",
                                         "playerIdentity": "408考研学习者"})
            pid = _extract_id(pres, "playerId")
            if not pid:
                return RoleplayResult(success=False, error=pres.get("message", "玩家注册失败"))
            # 2. 创建人格（角色设定）
            ares = await _character_post("/personality/open/agent/save",
                                        {"playerId": pid, "agentName": "面试官",
                                         "agentIdentity": persona_desc,
                                         "agentPersonalityDesc": persona_desc})
            aid = _extract_id(ares, "agentId")
            if not aid:
                return RoleplayResult(success=False, error=ares.get("message", "人格创建失败"))
            # 3. 新建会话
            cres = await _character_post("/personality/open/chat/new-chat",
                                        {"playerId": pid, "agentId": aid,
                                         "mission": topic or persona_desc,
                                         "conversationScene": "考研面试/答疑场景"})
            cid = _extract_id(cres, "chatId")
            if not cid:
                return RoleplayResult(success=False, error=cres.get("message", "会话创建失败"))
            sess = {"playerId": pid, "agentId": aid, "chatId": cid, "ts": time.time()}
            _prune_roleplay_sessions()
            _roleplay_sessions[key] = sess

        # 4. WebSocket 对话
        ts = int(time.time() * 1000)
        sig = _character_signature(c["app_id"], c["api_secret"], ts)
        ws_url = (f"{CHARACTER_WS}/personality/open/chat/"
                  f"{sess['chatId']}/{sess['playerId']}/{sess['agentId']}"
                  f"?appId={c['app_id']}&timestamp={ts}&signature={sig}")
        import websockets
        msg = {"header": {"appId": c["app_id"]},
               "parameter": {"type": "chat"},
               "payload": {"content": user_message}}
        async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
            await ws.send(json.dumps(msg))
            collected = []
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                data = json.loads(raw)
                if data.get("header", {}).get("code", -1) != 0:
                    return RoleplayResult(
                        success=False,
                        error=data.get("header", {}).get("message", "对话失败"),
                        chat_id=sess["chatId"])
                for t in data.get("payload", {}).get("choices", {}).get("text", []):
                    if t.get("role") == "assistant" and t.get("content"):
                        collected.append(t["content"])
                if data.get("header", {}).get("status") == 2:
                    break
        return RoleplayResult(success=True, reply="".join(collected), chat_id=sess["chatId"])
    except ImportError:
        return RoleplayResult(success=False, error="websockets 库未安装")
    except Exception as e:
        logger.warning(f"角色模拟异常: {e}")
        _roleplay_sessions.pop(f"{user_id}:{persona}", None)  # 复位，下次重建
        return RoleplayResult(success=False, error=str(e))


# ════════════════════════════════════════════════
# 10. 智能简历生成（HMAC-SHA256，返回可下载 word 简历）
# ════════════════════════════════════════════════

RESUME_URL = "https://cn-huadong-1.xf-yun.com/v1/private/s73f4add9"


@dataclass
class ResumeResult:
    success: bool
    word_url: Optional[str] = None
    raw: str = ""
    error: Optional[str] = None


async def generate_resume(info_text: str) -> ResumeResult:
    """智能简历：输入个人信息文本，返回可下载 word 简历链接 word_url。
    用于生成「408考研复试简历 / 能力档案」。"""
    if not has_credentials():
        return ResumeResult(success=False, error="讯飞凭证未配置")
    c = _get_cfg()
    try:
        auth_url = _assemble_hmac256_url(RESUME_URL, "POST", c["api_key"], c["api_secret"])
        body = {
            "header": {"app_id": c["app_id"], "status": 3},
            "parameter": {"ai_resume": {"resData": {"encoding": "utf8",
                                                    "compress": "raw", "format": "json"}}},
            "payload": {"reqData": {"encoding": "utf8", "compress": "raw", "format": "plain",
                                    "status": 3,
                                    "text": base64.b64encode(info_text.encode("utf-8")).decode("utf-8")}},
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(auth_url, json=body)
            data = r.json()
        if data.get("header", {}).get("code", -1) != 0:
            return ResumeResult(success=False,
                                error=data.get("header", {}).get("message", "简历生成失败"))
        raw = data.get("payload", {}).get("resData", {}).get("text", "")
        if not raw:
            return ResumeResult(success=True, raw="")
        decoded = json.loads(base64.b64decode(raw).decode("utf-8"))
        links = decoded.get("links", [])
        word_url = links[0].get("word_url") if links and isinstance(links[0], dict) else None
        return ResumeResult(success=True, word_url=word_url, raw=decoded.get("raw", ""))
    except Exception as e:
        logger.warning(f"智能简历异常: {e}")
        return ResumeResult(success=False, error=str(e))


# ════════════════════════════════════════════════
# 聚合状态（供前端展示能力全景）
# ════════════════════════════════════════════════

def get_all_status() -> dict:
    """返回所有讯飞能力的可用状态"""
    cred = has_credentials()
    c = _get_cfg()
    return {
        "credentials_configured": cred,
        "services": {
            "image_generation": cred,                       # TTI
            "image_understanding": cred,                   # 图片理解 WS
            "web_search": bool(c.get("search_password") or c["api_password"]),          # 万搜 Bearer
            "ppt_generation": cred,                         # 智能PPT
            "video_generation": cred,                       # 数字人视频
            "text_correction": cred,                        # 文本纠错
            "document_proofread": cred,                     # 公文校对
            "content_compliance": cred,                     # 文本合规
            "role_simulation": cred,                        # 角色模拟
            "resume_generation": cred,                      # 智能简历
        },
    }
