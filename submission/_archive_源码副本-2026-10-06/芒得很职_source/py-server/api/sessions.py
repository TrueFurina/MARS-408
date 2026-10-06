# ============================================================
# API — 对话存档（/api/sessions/*）
# 用户隔离：每个用户的会话按 user_id 分目录存储
# ============================================================

import os
import json
import logging
from fastapi import APIRouter, HTTPException, Depends
from shared.auth import get_current_user
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger("netlearn.sessions")
router = APIRouter(prefix="/sessions", tags=["sessions"])

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions")


def _ensure_user_dir(user_id: str) -> str:
    """确保用户会话目录存在，返回路径"""
    path = os.path.join(SESSIONS_DIR, user_id)
    os.makedirs(path, exist_ok=True)
    return path


class SessionMessage(BaseModel):
    role: str
    content: str
    segments: list[dict] = []
    reasoningDuration: Optional[float] = None

class SessionSaveRequest(BaseModel):
    conv_id: str
    title: str = ""
    messages: list[SessionMessage] = []

class SessionLoadResponse(BaseModel):
    conv_id: str
    title: str = ""
    messages: list[dict] = []
    created_at: str = ""


def _session_path(user_id: str, conv_id: str) -> str:
    """构建用户隔离的会话文件路径，防止路径穿越攻击。"""
    import re
    # 1) 去除路径分隔符 / 父目录片段（防 ../ 穿越）
    conv_id = os.path.basename(conv_id or "")
    user_id = os.path.basename(user_id or "")
    # 2) 严格白名单
    if not re.match(r'^[a-zA-Z0-9_\-]+$', conv_id):
        raise HTTPException(400, "无效的会话 ID")
    if not re.match(r'^[a-zA-Z0-9_\-]+$', user_id):
        raise HTTPException(400, "无效的用户 ID")
    user_dir = _ensure_user_dir(user_id)
    path = os.path.join(user_dir, f"{conv_id}.json")
    # 3) realpath 二次校验：解析符号链接与 .. 后，必须严格位于 SESSIONS_DIR 内
    real_path = os.path.realpath(path)
    real_base = os.path.realpath(SESSIONS_DIR)
    if not real_path.startswith(real_base + os.sep):
        raise HTTPException(400, "无效的会话 ID")
    return real_path


@router.post("/save")
async def session_save(req: SessionSaveRequest, user: dict = Depends(get_current_user)):
    """保存对话（仅当前用户可访问自己的会话）"""
    uid = user["user_id"]
    path = _session_path(uid, req.conv_id)
    data = {
        "user_id": uid,
        "title": req.title or f"对话 {req.conv_id[:8]}",
        "messages": [{"role": m.role, "content": m.content} for m in req.messages],
    }
    try:
        prev_title = data["title"]
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                prev = json.load(f)
                prev_title = prev.get("title", data["title"])
        data["title"] = prev_title
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"status": "ok", "conv_id": req.conv_id}
    except Exception as e:
        logger.warning("会话保存失败: %s", e)
        raise HTTPException(500, "会话保存失败，请稍后重试")


@router.get("/list")
async def session_list(user: dict = Depends(get_current_user)):
    """列出当前用户的所有存档对话（用户隔离）"""
    uid = user["user_id"]
    user_dir = _ensure_user_dir(uid)
    sessions = []
    try:
        for fname in os.listdir(user_dir):
            if fname.endswith(".json"):
                conv_id = fname[:-5]
                path = os.path.join(user_dir, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    sessions.append({
                        "conv_id": conv_id,
                        "title": data.get("title", conv_id[:8]),
                        "msg_count": len(data.get("messages", [])),
                        "updated": os.path.getmtime(path),
                    })
                except Exception:
                    sessions.append({"conv_id": conv_id, "title": conv_id[:8], "msg_count": 0, "updated": 0})
        sessions.sort(key=lambda s: s.get("updated", 0), reverse=True)
    except FileNotFoundError:
        pass
    return {"sessions": sessions}


@router.get("/load/{conv_id}")
async def session_load(conv_id: str, user: dict = Depends(get_current_user)):
    """加载当前用户的单个对话（用户隔离）"""
    uid = user["user_id"]
    path = _session_path(uid, conv_id)
    if not os.path.exists(path):
        raise HTTPException(404, f"对话 {conv_id} 不存在")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SessionLoadResponse(
            conv_id=conv_id,
            title=data.get("title", ""),
            messages=data.get("messages", []),
            created_at="",
        )
    except Exception as e:
        logger.warning("会话加载失败: %s", e)
        raise HTTPException(500, "会话加载失败，请稍后重试")


@router.delete("/delete/{conv_id}")
async def session_delete(conv_id: str, user: dict = Depends(get_current_user)):
    """删除当前用户的对话（用户隔离）"""
    uid = user["user_id"]
    path = _session_path(uid, conv_id)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            logger.warning("会话文件删除失败（已忽略）: %s — %s", path, e)
        return {"status": "ok"}
    raise HTTPException(404, f"对话 {conv_id} 不存在")
