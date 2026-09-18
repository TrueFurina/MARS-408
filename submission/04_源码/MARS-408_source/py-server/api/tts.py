# ============================================================
# API — 语音合成 TTS（/api/tts/*）
#
# 端点：
#   POST /api/tts/synthesize    — 单段文本合成语音（返回 WAV）
#   POST /api/tts/batch         — 批量文本合成（返回 zip）
#   GET  /api/tts/status        — TTS 引擎状态
# ============================================================

import logging
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from services.tts_service import synthesize, is_melo_available, is_xfyun_configured
from shared.auth import get_current_user
from shared.ratelimit import require_llm_quota

logger = logging.getLogger("netlearn.tts_api")
# F-011：TTS 语音合成端点统一鉴权 + 每用户配额（429，计算较重）
router = APIRouter(prefix="/tts", tags=["tts"], dependencies=[Depends(require_llm_quota)])


# ── 请求/响应模型 ──

class TTSRequest(BaseModel):
    text: str
    language: str = "zh"
    engine: str = "auto"  # auto / melo / xfyun


class BatchTTSRequest(BaseModel):
    items: list[TTSRequest]


class TTSStatusResponse(BaseModel):
    melo_available: bool
    xfyun_configured: bool
    engine: str


# ── 端点 ──

@router.post("/synthesize")
async def synthesize_speech(
    req: TTSRequest,
    user: dict = Depends(get_current_user),
):
    """合成单段文本为语音，返回 WAV 音频

    - text: 要朗读的文本
    - language: 语言代码（zh/en/ja/ko/es/fr）
    - engine: 引擎选择（auto/melo/xfyun）
    """
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="文本不能为空")
    if len(req.text) > 5000:
        raise HTTPException(status_code=400, detail="单次合成文本长度不能超过 5000 字")

    audio = await synthesize(req.text, language=req.language, engine=req.engine)
    if audio is None:
        raise HTTPException(status_code=503, detail="TTS 引擎不可用，请检查配置")

    # L1/L2/L3 三层学情记忆联动（低侵入：语音合成入 L3，供多模态使用轨迹追溯）
    try:
        user_id = user.get("user_id") or user.get("id") or ""
        if user_id:
            from db import memory_store as _ms
            _ms.append_episode(user_id, "tts_synthesize", {
                "text_len": len(req.text),
                "language": req.language,
                "engine": req.engine or "auto",
            })
    except Exception as _me:
        logger.debug(f"TTS 记忆写入失败(忽略): {_me}")

    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "Content-Disposition": f'attachment; filename="tts_{req.language}.wav"',
            "X-TTS-Engine": req.engine if req.engine != "auto" else "melo",
        },
    )


@router.post("/batch")
async def synthesize_batch(
    req: BatchTTSRequest,
    user: dict = Depends(get_current_user),
):
    """批量合成多段文本，返回 zip 压缩包

    每段音频保存为 tts_{index}.wav，附 JSON 索引文件。
    """
    if not req.items:
        raise HTTPException(status_code=400, detail="批量列表不能为空")
    if len(req.items) > 50:
        raise HTTPException(status_code=400, detail="单次批量最多 50 段")

    zip_buffer = tempfile.SpooledTemporaryFile(max_size=100 * 1024 * 1024)
    index = []

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, item in enumerate(req.items):
            audio = await synthesize(item.text, language=item.language, engine=item.engine)
            if audio is None:
                logger.warning(f"批量 TTS 第 {i} 段合成失败，跳过")
                index.append({"index": i, "text": item.text, "language": item.language, "status": "failed"})
                continue
            zf.writestr(f"tts_{i:03d}.wav", audio)
            index.append({"index": i, "text": item.text, "language": item.language, "status": "ok"})

        zf.writestr("index.json", __import__("json").dumps(index, ensure_ascii=False, indent=2))

    zip_buffer.seek(0)
    return Response(
        content=zip_buffer.read(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="tts_batch.zip"'},
    )


@router.get("/status", response_model=TTSStatusResponse)
async def tts_status(user: dict = Depends(get_current_user)):
    """查询 TTS 引擎状态"""
    melo_ok = is_melo_available()
    xfyun_ok = is_xfyun_configured()

    if melo_ok:
        engine = "melo"
    elif xfyun_ok:
        engine = "xfyun"
    else:
        engine = "unavailable"

    return TTSStatusResponse(
        melo_available=melo_ok,
        xfyun_configured=xfyun_ok,
        engine=engine,
    )