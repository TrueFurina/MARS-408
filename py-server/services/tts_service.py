# ============================================================
# TTS 语音合成服务 — 双引擎架构
#
# 策略：
#   主引擎   MeloTTS（本地离线，免费，无 QPS 限制）
#   备选引擎 讯飞 TTS API（在线，高自然度，展示出题企业能力）
#
# 路由规则：
#   - 批量 / 后台资源配音 → MeloTTS（无配额顾虑）
#   - 用户实时交互朗读 → 讯飞 API（低延迟，更自然）
#   - 离线 / 演示环境     → MeloTTS（不依赖网络）
#   - 多语言（EN/JP/KR）  → MeloTTS（原生支持6种语言）
# ============================================================

import io
import logging
import os
from typing import Optional

logger = logging.getLogger("netlearn.tts")

# ── 语言映射 ──
# MeloTTS 支持的语言代码
MELO_LANGUAGES = {
    "zh": "ZH",
    "zh-cn": "ZH",
    "zh-tw": "ZH",
    "en": "EN",
    "en-us": "EN",
    "en-gb": "EN",
    "ja": "JP",
    "jp": "JP",
    "ko": "KR",
    "kr": "KR",
    "es": "ES",
    "fr": "FR",
}

# 讯飞 TTS API 支持的语言
XFYUN_LANGUAGES = {
    "zh": "zh",
    "zh-cn": "zh",
    "en": "en",
    "en-us": "en",
}

# ── MeloTTS 引擎（单例，延迟加载） ──

_melo_instances: dict[str, "TTS"] = {}  # type: ignore


def _get_melo(language: str):
    """获取 MeloTTS 模型实例（按语言缓存，延迟加载）"""
    lang_code = MELO_LANGUAGES.get(language.lower(), "EN")
    if lang_code not in _melo_instances:
        # 确保离线模式，避免 MeloTTS 的 Japanese BERT tokenizer 下载卡住
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        try:
            from melo.api import TTS
            logger.info(f"正在加载 MeloTTS 模型（language={lang_code}）...")
            _melo_instances[lang_code] = TTS(language=lang_code, device="cpu")
            logger.info(f"MeloTTS 模型加载完成（language={lang_code}）")
        except ImportError:
            logger.warning("MeloTTS 未安装，回退到讯飞 TTS API")
            return None
        except OSError as e:
            logger.warning(f"MeloTTS 模型下载失败（网络不可达），尝试英文模型: {e}")
            # 中文/日文模型需要 HuggingFace 下载，网络不可达时回退英文
            if lang_code != "EN" and "EN" not in _melo_instances:
                try:
                    _melo_instances["EN"] = TTS(language="EN", device="cpu")
                    logger.info("MeloTTS 英文模型加载成功（作为降级）")
                except Exception as e2:
                    logger.warning(f"MeloTTS 英文模型也加载失败: {e2}")
                    return None
            return _melo_instances.get("EN")
        except Exception as e:
            logger.warning(f"MeloTTS 加载失败: {e}")
            return None
    return _melo_instances.get(lang_code)


def melo_synthesize(text: str, language: str = "zh") -> Optional[bytes]:
    """使用 MeloTTS 合成语音，返回 WAV 字节"""
    model = _get_melo(language)
    if model is None:
        return None
    try:
        lang_code = MELO_LANGUAGES.get(language.lower(), "ZH")
        speaker_ids = model.hps.data.spk2id
        speaker_key = list(speaker_ids.keys())[0]
        bio = io.BytesIO()
        model.tts_to_file(text, speaker_ids[speaker_key], bio, format="wav", quiet=True)
        return bio.getvalue()
    except Exception as e:
        logger.error(f"MeloTTS 合成失败: {e}")
        return None


# ── 讯飞 TTS 引擎 ──

async def xfyun_synthesize(text: str, language: str = "zh") -> Optional[bytes]:
    """使用讯飞 TTS API 合成语音，返回音频字节

    需要配置 xfyun.app_id / api_key / api_secret（config.json 或环境变量）
    若凭证未配置或调用失败，返回 None。
    """
    lang_code = XFYUN_LANGUAGES.get(language.lower(), "zh")
    try:
        from config import load_config
        cfg = load_config().get("xfyun", {})
        app_id = cfg.get("app_id", "")
        api_key = cfg.get("api_key", "")
        api_secret = cfg.get("api_secret", "")

        if not (app_id and api_key and api_secret):
            logger.warning("讯飞 TTS 凭证未配置")
            return None

        # 讯飞 TTS WebAPI 端点
        # 参考文档：https://www.xfyun.cn/doc/tts/online_tts/API.html
        import time
        import json
        import base64
        import hashlib
        import hmac
        from urllib.parse import urlencode, urlparse

        host_url = "wss://tts-api.xfyun.cn/v2/tts"
        parsed = urlparse(host_url)
        host = parsed.hostname
        path = parsed.path
        date = _format_date_rfc1123()

        signature_origin = f"host: {host}\ndate: {date}\nGET {path} HTTP/1.1"
        signature = base64.b64encode(
            hmac.new(api_secret.encode("utf-8"), signature_origin.encode("utf-8"),
                     digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
        authorization = base64.b64encode(
            f'api_key="{api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'.encode("utf-8")
        ).decode("utf-8")

        ws_url = f"{host_url}?{urlencode({'host': host, 'date': date, 'authorization': authorization})}"

        import websockets

        body = {
            "common": {"app_id": app_id},
            "business": {
                "aue": "lame",      # MP3 格式
                "auf": "audio/L16;rate=16000",
                "vcn": "x4_zh" if lang_code == "zh" else "x4_en",
                "speed": 50,
                "volume": 50,
                "pitch": 50,
                "tte": "UTF8",
            },
            "data": {
                "text": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
                "status": 2,
            },
        }

        audio_chunks = []
        async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
            await ws.send(json.dumps(body))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                data = json.loads(raw)
                code = data.get("code", -1)
                if code != 0:
                    logger.warning(f"讯飞 TTS 返回错误: {data.get('message', '')}")
                    return None
                audio_data = data.get("data", {}).get("audio", "")
                if audio_data:
                    audio_chunks.append(base64.b64decode(audio_data))
                if data.get("data", {}).get("status") == 2:
                    break

        # MP3 转 WAV（前端 Audio API 更易播放）
        import pydub
        from pydub import AudioSegment

        mp3_data = b"".join(audio_chunks)
        seg = AudioSegment.from_mp3(io.BytesIO(mp3_data))
        wav_bio = io.BytesIO()
        seg.export(wav_bio, format="wav")
        return wav_bio.getvalue()

    except ImportError:
        logger.warning("讯飞 TTS 需要 websockets 和 pydub 库")
        return None
    except Exception as e:
        logger.warning(f"讯飞 TTS 调用失败: {e}")
        return None


def _format_date_rfc1123() -> str:
    """RFC1123 格式时间戳"""
    from wsgiref.handlers import format_date_time
    from time import mktime
    from datetime import datetime
    return format_date_time(mktime(datetime.now().timetuple()))


import asyncio  # noqa: E402 (needed by xfyun_synthesize)


# ════════════════════════════════════════════════
# 统一入口：智能路由
# ════════════════════════════════════════════════

async def synthesize(
    text: str,
    language: str = "zh",
    engine: str = "auto",
) -> Optional[bytes]:
    """统一 TTS 入口，自动选择引擎

    Args:
        text: 要合成的文本
        language: 语言代码（zh / en / ja / ko / es / fr）
        engine: 引擎选择
            - "auto":     交互场景优先讯飞，批量场景优先 MeloTTS
            - "melo":     强制 MeloTTS
            - "xfyun":    强制讯飞 TTS API

    Returns:
        WAV 格式音频字节，失败返回 None
    """
    if not text or not text.strip():
        return None

    if engine == "melo":
        return melo_synthesize(text, language)

    if engine == "xfyun":
        return await xfyun_synthesize(text, language)

    # auto: 优先 MeloTTS（离线可用），失败回退讯飞
    result = melo_synthesize(text, language)
    if result is not None:
        return result

    result = await xfyun_synthesize(text, language)
    if result is not None:
        return result

    logger.error("TTS 所有引擎均失败，返回 None")
    return None


def is_melo_available() -> bool:
    """检查 MeloTTS 是否可用"""
    try:
        import melo  # noqa: F401
        return True
    except ImportError:
        return False


def is_xfyun_configured() -> bool:
    """检查讯飞 TTS 凭证是否已配置"""
    try:
        from config import load_config
        cfg = load_config().get("xfyun", {})
        return bool(cfg.get("app_id") and cfg.get("api_key") and cfg.get("api_secret"))
    except Exception:
        return False