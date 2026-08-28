# ============================================================
# 讯飞多模态服务集成 — TTI图片生成 + TTS语音合成
#
# 赛题合规：赛题要求"开发过程中使用的其他AI辅助工具，需选用科大讯飞相关工具"
# 本模块深度集成讯飞多模态能力：
#   1. TTI (Text-to-Image) — 知识点→教学插图
#   2. TTS (Text-to-Speech) — 视频脚本→语音旁白
#
# 降级策略：
#   - 有讯飞API key → 调用讯飞TTI/TTS生成真图真音
#   - 无讯飞API key → SVG编程绘图 + 浏览器Web Speech API
# ============================================================

import os
import time
import json
import base64
import hashlib
import hmac
import html
import logging
import asyncio
from datetime import datetime
from wsgiref.handlers import format_date_time
from time import mktime
from urllib.parse import urlencode, quote
from typing import Optional
from dataclasses import dataclass

import httpx

logger = logging.getLogger("netlearn.xfyun_multimodal")


# ── 配置 ──

def _get_xfyun_config() -> dict:
    """从 config 获取讯飞多模态配置"""
    try:
        from config import load_config
        cfg = load_config()
        xfyun = cfg.get("xfyun", {})
        # 只有 tti_enabled=True 且有完整鉴权三要素时才认为可用
        tti_enabled = xfyun.get("tti_enabled", False)
        tts_enabled = xfyun.get("tts_enabled", False)
        has_auth = bool(xfyun.get("app_id") and xfyun.get("api_key") and xfyun.get("api_secret"))
        return {
            "app_id": xfyun.get("app_id", ""),
            "api_key": xfyun.get("api_key", ""),
            "api_secret": xfyun.get("api_secret", ""),
            "api_password": xfyun.get("api_password", ""),
            "tti_enabled": tti_enabled and has_auth,
            "tts_enabled": tts_enabled and has_auth,
        }
    except Exception:
        return {"app_id": "", "api_key": "", "api_secret": "", "api_password": "",
                "tti_enabled": False, "tts_enabled": False}


def is_tti_available() -> bool:
    """检查讯飞TTI是否可用（需要app_id + api_key + api_secret + tti_enabled）"""
    cfg = _get_xfyun_config()
    return cfg.get("tti_enabled", False)


def is_tts_available() -> bool:
    """检查讯飞TTS是否可用"""
    cfg = _get_xfyun_config()
    return cfg.get("tts_enabled", False)


# ── 讯飞鉴权 ──

def _assemble_auth_url(request_url: str, method: str = "GET",
                        api_key: str = "", api_secret: str = "") -> str:
    """生成讯飞鉴权URL（HMAC-SHA256签名）"""
    from urllib.parse import urlparse

    parsed = urlparse(request_url)
    host = parsed.hostname
    path = parsed.path

    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))

    signature_origin = f"host: {host}\ndate: {date}\n{method} {path} HTTP/1.1"
    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")

    auth_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    auth = base64.b64encode(auth_origin.encode("utf-8")).decode("utf-8")

    params = {"host": host, "date": date, "authorization": auth}
    return request_url + "?" + urlencode(params)


# ── TTI: 讯飞图片生成 ──

TTI_HOST = "https://spark-api.cn-huabei-1.xf-yun.com/v2.1/tti"


@dataclass
class TTIResult:
    """图片生成结果"""
    success: bool
    image_base64: Optional[str] = None  # base64编码的JPEG
    image_svg: Optional[str] = None     # 降级SVG
    error: Optional[str] = None
    source: str = "xfyun"  # xfyun | svg_fallback


async def generate_image(prompt: str, topic: str = "") -> TTIResult:
    """生成教学插图

    有讯飞TTI key → 调用讯飞生成真实图片(512x512 JPEG)
    无key → 生成SVG教学图（概念图/流程图风格）
    """
    if is_tti_available():
        return await _xfyun_tti(prompt, topic)
    else:
        return _svg_fallback(prompt, topic)


async def _xfyun_tti(prompt: str, topic: str) -> TTIResult:
    """调用讯飞TTI生成图片"""
    cfg = _get_xfyun_config()

    # 构造请求体
    body = {
        "header": {
            "app_id": cfg["app_id"],
            "uid": "netlearn_user"
        },
        "parameter": {
            "chat": {
                "domain": "general",
                "temperature": 0.5,
                "max_tokens": 4096
            }
        },
        "payload": {
            "message": {
                "text": [
                    {
                        "role": "user",
                        "content": f"生成一张教学插图：{prompt}。风格：简洁清晰的计算机科学教学示意图，适合大学生学习使用。"
                    }
                ]
            }
        }
    }

    try:
        authed_url = _assemble_auth_url(
            TTI_HOST, method="POST",
            api_key=cfg["api_key"], api_secret=cfg["api_secret"]
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(authed_url, json=body,
                                     headers={"Content-Type": "application/json"})
            data = resp.json()

            code = data.get("header", {}).get("code", -1)
            if code != 0:
                err_msg = data.get("header", {}).get("message", "未知错误")
                logger.warning(f"讯飞TTI失败 code={code}: {err_msg}，降级SVG")
                return _svg_fallback(prompt, topic)

            text_list = data.get("payload", {}).get("choices", {}).get("text", [])
            if text_list and text_list[0].get("content"):
                img_b64 = text_list[0]["content"]
                logger.info(f"讯飞TTI成功: {prompt[:50]}...")
                return TTIResult(success=True, image_base64=img_b64, source="xfyun")

            return _svg_fallback(prompt, topic)

    except Exception as e:
        logger.warning(f"讯飞TTI异常: {e}，降级SVG")
        return _svg_fallback(prompt, topic)


def _svg_fallback(prompt: str, topic: str) -> TTIResult:
    """SVG降级：生成教学概念图（无外部API依赖）"""

    # 根据主题生成不同类型的SVG
    title = html.escape(topic or prompt[:20] or "教学概念图")
    colors = ["#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#06b6d4"]

    # 生成概念图风格的SVG
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#1e1b4b;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#312e81;stop-opacity:1" />
    </linearGradient>
    <filter id="glow">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <rect width="512" height="512" fill="url(#bg)" rx="16"/>

  <!-- 标题 -->
  <text x="256" y="50" text-anchor="middle" fill="#e0e7ff"
        font-size="22" font-weight="bold" font-family="sans-serif">{title[:30]}</text>
  <line x1="100" y1="70" x2="412" y2="70" stroke="#6366f1" stroke-width="2" opacity="0.5"/>

  <!-- 中心节点 -->
  <circle cx="256" cy="256" r="60" fill="#6366f1" opacity="0.9" filter="url(#glow)"/>
  <text x="256" y="262" text-anchor="middle" fill="white"
        font-size="16" font-weight="bold" font-family="sans-serif">{title[:12]}</text>

  <!-- 卫星节点 -->
  '''

    # 生成6个卫星节点
    import math
    labels = ["概念", "原理", "应用", "示例", "要点", "拓展"]
    for i, label in enumerate(labels):
        angle = i * 60 - 90  # 从顶部开始
        rad = math.radians(angle)
        x = 256 + 150 * math.cos(rad)
        y = 256 + 150 * math.sin(rad)
        color = colors[i % len(colors)]
        svg += f'''
  <line x1="256" y1="256" x2="{x:.0f}" y2="{y:.0f}" stroke="{color}" stroke-width="2" opacity="0.4"/>
  <circle cx="{x:.0f}" cy="{y:.0f}" r="35" fill="{color}" opacity="0.8" filter="url(#glow)"/>
  <text x="{x:.0f}" y="{y+5:.0f}" text-anchor="middle" fill="white"
        font-size="13" font-family="sans-serif">{label}</text>'''

    svg += f'''
  <!-- 底部水印 -->
  <text x="256" y="490" text-anchor="middle" fill="#a5b4fc"
        font-size="11" font-family="sans-serif" opacity="0.6">MARS-408 AI 教学插图 · 讯飞星火</text>
</svg>'''

    logger.info(f"SVG降级教学图生成: {title[:20]}")
    return TTIResult(success=True, image_svg=svg, source="svg_fallback")


# ── TTS: 讯飞语音合成 ──

TTS_HOST = "wss://tts-api.xfyun.cn/v2/tts"


@dataclass
class TTSResult:
    """语音合成结果"""
    success: bool
    audio_base64: Optional[str] = None  # base64编码的音频
    audio_format: str = "mp3"
    fallback_text: Optional[str] = None  # 降级时返回原文（前端用浏览器TTS）
    error: Optional[str] = None
    source: str = "xfyun"  # xfyun | browser_fallback


async def generate_speech(text: str, voice: str = "xiaoyan") -> TTSResult:
    """文本转语音

    有讯飞TTS key → 调用讯飞生成音频
    无key → 返回原文，前端用浏览器Web Speech API朗读
    """
    if is_tts_available():
        return await _xfyun_tts(text, voice)
    else:
        return TTSResult(
            success=True,
            fallback_text=text,
            source="browser_fallback"
        )


async def _xfyun_tts(text: str, voice: str) -> TTSResult:
    """调用讯飞TTS WebSocket API生成语音"""
    cfg = _get_xfyun_config()

    # 讯飞TTS WebSocket请求体
    body = {
        "common": {"app_id": cfg["app_id"]},
        "business": {
            "aue": "lame",  # mp3格式
            "auf": "audio/L16;rate=16000",
            "vcn": voice,  # 发音人
            "speed": 50,
            "volume": 50,
            "pitch": 50,
            "tte": "utf8"
        },
        "data": {
            "status": 2,  # 最后一次请求
            "text": base64.b64encode(text.encode("utf-8")).decode("utf-8")
        }
    }

    try:
        authed_url = _assemble_auth_url(
            TTS_HOST, method="GET",
            api_key=cfg["api_key"], api_secret=cfg["api_secret"]
        )

        # 使用 websockets 库连接
        import websockets
        async with websockets.connect(authed_url) as ws:
            await ws.send(json.dumps(body))

            audio_chunks = []
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                data = json.loads(msg)
                code = data.get("code", -1)
                if code != 0:
                    err = data.get("message", "TTS错误")
                    logger.warning(f"讯飞TTS失败: {err}，降级浏览器TTS")
                    return TTSResult(
                        success=True, fallback_text=text,
                        source="browser_fallback"
                    )

                audio_b64 = data.get("data", {}).get("audio", "")
                if audio_b64:
                    audio_chunks.append(audio_b64)

                if data.get("data", {}).get("status", 0) == 2:
                    break

        if audio_chunks:
            combined = "".join(audio_chunks)
            logger.info(f"讯飞TTS成功: {len(text)}字 → {len(combined)}字节音频")
            return TTSResult(
                success=True, audio_base64=combined,
                audio_format="mp3", source="xfyun"
            )

        return TTSResult(success=True, fallback_text=text, source="browser_fallback")

    except ImportError:
        logger.warning("websockets库未安装，TTS降级为浏览器Web Speech API")
        return TTSResult(success=True, fallback_text=text, source="browser_fallback")
    except Exception as e:
        logger.warning(f"讯飞TTS异常: {e}，降级浏览器TTS")
        return TTSResult(success=True, fallback_text=text, source="browser_fallback")


# ── 多模态资源生成（组合 TTI + TTS） ──

@dataclass
class MultimodalResource:
    """多模态资源（图+文+音）"""
    text: str = ""
    image_base64: Optional[str] = None
    image_svg: Optional[str] = None
    audio_base64: Optional[str] = None
    audio_fallback_text: Optional[str] = None
    image_source: str = "none"
    audio_source: str = "none"


async def generate_multimodal_resource(
    topic: str,
    text_content: str,
    generate_image: bool = True,
    generate_audio: bool = True,
) -> MultimodalResource:
    """生成多模态资源：文本 + 教学插图 + 语音旁白

    Args:
        topic: 知识点主题
        text_content: 文本内容（讲解/视频脚本）
        generate_image: 是否生成插图
        generate_audio: 是否生成语音

    Returns:
        MultimodalResource: 包含文本、图片(base64或SVG)、音频(base64或降级文本)
    """
    resource = MultimodalResource(text=text_content)

    tasks = []
    if generate_image:
        tasks.append(("image", _generate_image_task(topic)))
    if generate_audio:
        # TTS只处理前500字（避免超时）
        tts_text = text_content[:500] if len(text_content) > 500 else text_content
        tasks.append(("audio", _generate_audio_task(tts_text)))

    # 并行生成
    results = await asyncio.gather(
        *[task for _, task in tasks],
        return_exceptions=True
    )

    for (name, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            logger.warning(f"多模态生成[{name}]异常: {result}")
            continue
        if name == "image":
            if result.image_base64:
                resource.image_base64 = result.image_base64
                resource.image_source = result.source
            elif result.image_svg:
                resource.image_svg = result.image_svg
                resource.image_source = result.source
        elif name == "audio":
            if result.audio_base64:
                resource.audio_base64 = result.audio_base64
                resource.audio_source = result.source
            elif result.fallback_text:
                resource.audio_fallback_text = result.fallback_text
                resource.audio_source = result.source

    return resource


async def _generate_image_task(topic: str) -> TTIResult:
    """图片生成子任务"""
    return await generate_image(f"计算机科学教学图：{topic}", topic)


async def _generate_audio_task(text: str) -> TTSResult:
    """语音合成子任务"""
    return await generate_speech(text)


def get_multimodal_status() -> dict:
    """获取多模态服务状态（供前端展示）"""
    return {
        "tti_available": is_tti_available(),
        "tts_available": is_tts_available(),
        "tti_source": "讯飞星火TTI" if is_tti_available() else "SVG编程绘图(降级)",
        "tts_source": "讯飞TTS语音合成" if is_tts_available() else "浏览器Web Speech API(降级)",
    }
