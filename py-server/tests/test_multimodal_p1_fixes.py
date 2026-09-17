# ============================================================
# P1 修复回归测试（2026-09-16）
#
# 覆盖：
#   1. _parse_ppt_slides 的 req_topic NameError（解析为空时抛 NameError → 500）
#   2. P1-2 bg_image 任意文件读（背景图作为 FFmpeg -i 输入，需限制在 BG_DIR 内）
#   3. P1-1 视频生成阻塞事件循环（同步 subprocess.run 必须丢线程池）
# ============================================================

import os
import threading
import tempfile

import pytest


# ------------------------------------------------------------
# 1. _parse_ppt_slides：空解析不得抛 NameError
# ------------------------------------------------------------
def test_parse_ppt_slides_empty_content_uses_topic():
    """LLM 未返回任何标题时，应回落默认标题，而不是抛 NameError。"""
    from api.multimodal import _parse_ppt_slides

    slides = _parse_ppt_slides("没有任何标题的纯文本内容", topic="进程调度")
    assert len(slides) == 1
    assert slides[0]["title"] == "进程调度"
    assert slides[0]["content"] == ["默认内容"]


def test_parse_ppt_slides_empty_content_without_topic():
    """未传 topic 时也不得抛异常（向后兼容默认参数）。"""
    from api.multimodal import _parse_ppt_slides

    slides = _parse_ppt_slides("")
    assert len(slides) == 1
    assert slides[0]["title"] == "默认标题"


def test_parse_ppt_slides_normal_parsing_still_works():
    """正常解析行为不得被修复破坏。"""
    from api.multimodal import _parse_ppt_slides

    md = "## 第一章\n内容 A\n内容 B\n## 第二章\n内容 C\n"
    slides = _parse_ppt_slides(md, topic="X")
    assert len(slides) == 2
    assert slides[0]["title"] == "第一章"
    assert slides[0]["content"] == ["内容 A", "内容 B"]
    assert slides[1]["title"] == "第二章"


# ------------------------------------------------------------
# 2. P1-2：bg_image 路径白名单
# ------------------------------------------------------------
@pytest.mark.parametrize("payload", [
    None,
    "",
    "../../../../py-server/config.json",
    "..\\..\\py-server\\config.json",
    "D:/config.json",
    "/etc/passwd",
    "C:\\Windows\\win.ini",
    "../../.env",
    "subdir/../../secret.png",
])
def test_safe_bg_path_rejects_malicious_paths(payload):
    """各类穿越/绝对路径 payload 一律拒绝（回落默认背景）。"""
    from services.video_dub import _safe_bg_path

    assert _safe_bg_path(payload) is None


def test_safe_bg_path_rejects_file_outside_bg_dir():
    """真实存在于 BG_DIR 之外的文件，即使用绝对路径也不得被引用。"""
    from services.video_dub import _safe_bg_path

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        assert os.path.exists(path)
        # 绝对路径指向 BG_DIR 之外 → 必须拒绝
        assert _safe_bg_path(path) is None
    finally:
        os.unlink(path)


def test_safe_bg_path_accepts_file_inside_bg_dir():
    """位于 BG_DIR 内的合法背景图应被接受。"""
    from services.video_dub import _safe_bg_path, BG_DIR

    name = "_pytest_tmp_bg.png"
    target = BG_DIR / name
    try:
        target.write_bytes(b"\x89PNG\r\n\x1a\n")
        out = _safe_bg_path(name)
        assert out is not None
        assert os.path.realpath(out) == os.path.realpath(str(target))
    finally:
        if target.exists():
            target.unlink()


# ------------------------------------------------------------
# 3. P1-1：视频生成必须在线程池执行（不得阻塞事件循环）
# ------------------------------------------------------------
def test_narrated_video_endpoint_runs_off_main_thread(monkeypatch):
    """生成调用必须发生在非主线程，否则同步 subprocess.run(timeout=300)
    会阻塞整个事件循环，单请求即可造成全站假性宕机。"""
    import asyncio

    import services.video_dub as vd
    import api.multimodal as mm

    fd, video_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    with open(video_path, "wb") as f:
        f.write(b"\x00")

    recorded = {}

    def fake_generate(**kwargs):
        recorded["thread"] = threading.current_thread()
        recorded["kwargs"] = kwargs
        return video_path

    monkeypatch.setattr(vd, "generate_narrated_video", fake_generate)
    monkeypatch.setattr(vd, "is_ffmpeg_available", lambda: True)

    try:
        req = mm.NarratedVideoRequest(text="测试文本", bg_image="../../config.json")
        resp = asyncio.run(mm.generate_narrated_video_endpoint(req, {"user_id": "tester"}))

        assert "thread" in recorded, "生成函数未被调用"
        assert recorded["thread"] is not threading.main_thread(), (
            "generate_narrated_video 仍在主线程执行 —— 会阻塞事件循环（P1-1 未修复）"
        )
        from fastapi.responses import FileResponse
        assert isinstance(resp, FileResponse)
    finally:
        if os.path.exists(video_path):
            os.unlink(video_path)
