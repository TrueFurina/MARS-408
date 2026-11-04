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


# ── 会话元信息缓存（2026-11-02 性能审计） ──
# 此前 session_list 对**每个**会话文件整档 json.load，只为取 title 与消息条数：
# 200 个 28KiB 会话 ≈ 5.6MB 解析（本机实测 198ms/请求），且是 async def 里的同步循环，
# 会阻塞事件循环。现改为：元信息按 (path, mtime_ns, size) 缓存，只解析变更过的文件；
# 扫描本身丢进线程池，不占事件循环。
# 缓存键含 mtime_ns + size：session_save 覆写文件必然改变二者 ⇒ 不会读到旧值。
_META_CACHE: dict[str, tuple[int, int, str, int, bool]] = {}
_META_CACHE_MAX = 4096


def _read_meta(path: str, conv_id: str) -> tuple[str, int, float]:
    """返回 (title, msg_count, updated)。命中缓存时不打开文件。

    `updated` 与 `os.stat` 复合同一次系统调用（Windows 上每文件两次 stat 很贵，
    200 文件即多出约 15ms）。解析失败时按旧语义返回 updated=0。
    """
    try:
        st = os.stat(path)
    except OSError:
        return conv_id[:8], 0, 0

    cached = _META_CACHE.get(path)
    if cached and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
        return cached[2], cached[3], (st.st_mtime if cached[4] else 0)

    ok = True
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        title = data.get("title") or conv_id[:8]
        msg_count = len(data.get("messages") or [])
    except Exception:
        title, msg_count, ok = conv_id[:8], 0, False

    if len(_META_CACHE) >= _META_CACHE_MAX:  # 简单上界：超限整体清空，避免无界增长
        _META_CACHE.clear()
    _META_CACHE[path] = (st.st_mtime_ns, st.st_size, title, msg_count, ok)
    return title, msg_count, (st.st_mtime if ok else 0)


def _scan_sessions(user_dir: str) -> list[dict]:
    """扫描用户会话目录（同步函数；由路由丢进线程池执行）。

    保持与旧实现一致的降级语义：解析失败时 updated 记 0（而不是文件 mtime），
    避免把「读不出来的坏档」排到列表最前。
    """
    try:
        names = os.listdir(user_dir)
    except FileNotFoundError:
        return []

    sessions = []
    for fname in names:
        if not fname.endswith(".json"):
            continue
        conv_id = fname[:-5]
        path = os.path.join(user_dir, fname)
        title, msg_count, updated = _read_meta(path, conv_id)
        sessions.append({
            "conv_id": conv_id,
            "title": title,
            "msg_count": msg_count,
            "updated": updated,
        })
    sessions.sort(key=lambda s: s["updated"], reverse=True)
    return sessions


@router.get("/list")
async def session_list(user: dict = Depends(get_current_user)):
    """列出当前用户的所有存档对话（用户隔离）"""
    from fastapi.concurrency import run_in_threadpool

    uid = user["user_id"]
    user_dir = _ensure_user_dir(uid)
    return {"sessions": await run_in_threadpool(_scan_sessions, user_dir)}


@router.get("/load/{conv_id}", response_model=SessionLoadResponse)
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
