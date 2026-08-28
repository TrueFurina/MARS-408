# ============================================================
# 视频生成服务 — 不依赖昂贵 API 的合成视频工作流
# 工作流: 分镜脚本 → SVG 场景 → TTS 配音 → HTML 幻灯片 → (可选) FFmpeg MP4
# 核心思路: 不用 AI 生成视频帧，用程序化方式组合教学素材
# ============================================================

import json
import logging
import os
import random
import re
import time
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("netlearn.video_generator")

# 输出目录
_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "videos")
os.makedirs(_OUTPUT_DIR, exist_ok=True)

# 缓存目录
_CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "video_cache")
os.makedirs(_CACHE_DIR, exist_ok=True)
_CACHE_TTL = 3600 * 24  # 24 小时缓存


# ═══════════════════════════════════════════════════════════════
# 缓存管理
# ═══════════════════════════════════════════════════════════════

def _cache_key(topic: str, difficulty: str) -> str:
    """生成缓存键（基于 topic + difficulty 的哈希）"""
    import hashlib
    raw = f"{topic}|{difficulty}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _cache_get(key: str) -> Optional[str]:
    """读取缓存（过期返回 None）"""
    path = os.path.join(_CACHE_DIR, f"{key}.json")
    if not os.path.exists(path):
        return None
    try:
        mtime = os.path.getmtime(path)
        if time.time() - mtime > _CACHE_TTL:
            os.remove(path)
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("script")
    except Exception:
        return None


def _cache_set(key: str, script: str):
    """写入缓存"""
    path = os.path.join(_CACHE_DIR, f"{key}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"script": script, "cached_at": __import__("time").time()}, f)
    except Exception as e:
        logger.warning(f"缓存写入失败: {e}")


# ═══════════════════════════════════════════════════════════════
# 第一步：解析分镜脚本 → 结构化场景列表
# ═══════════════════════════════════════════════════════════════

def parse_storyboard(video_script: str) -> list[dict]:
    """解析视频脚本中的分镜，提取结构化场景列表

    Args:
        video_script: 视频脚本文本（含 ---VIDEO_START--- 标记）

    Returns:
        [{scene_id, title, duration_sec, narration, visual_desc, animation}]
    """
    scenes = []
    # 提取 ---VIDEO_START--- 和 ---VIDEO_END--- 之间的内容
    start_marker = "---VIDEO_START---"
    end_marker = "---VIDEO_END---"
    start_idx = video_script.find(start_marker)
    end_idx = video_script.find(end_marker)

    if start_idx == -1:
        # 尝试其他格式
        return _parse_scenes_fallback(video_script)

    content = video_script[start_idx + len(start_marker):end_idx] if end_idx > start_idx else video_script[start_idx + len(start_marker):]

    # 按 "## 分镜" 分割
    scene_blocks = re.split(r'##\s*分镜\s*\d+\s*[:：]?\s*', content)
    for i, block in enumerate(scene_blocks):
        block = block.strip()
        if not block or len(block) < 10:
            continue

        scene = {
            "scene_id": i,
            "title": _extract_field(block, "场景标题", r'^(.+?)(?:\n|$)'),
            "duration_sec": _extract_duration(block),
            "narration": _extract_field(block, "旁白", r'旁白[：:]\s*(.+?)(?:\n(?:$|(?=\*\*)))'),
            "visual_desc": _extract_field(block, "画面", r'画面[：:]\s*(.+?)(?:\n(?:$|(?=\*\*)))'),
            "animation": _extract_field(block, "动画", r'动画[：:]\s*(.+?)(?:\n(?:$|(?=\*\*)))'),
            "raw_block": block,
            "template_type": random.choice(list(SCENE_TEMPLATES.keys())),
        }
        scenes.append(scene)

    return scenes


def _parse_scenes_fallback(text: str) -> list[dict]:
    """降级解析：没有标准标记时按段落分割"""
    scenes = []
    blocks = re.split(r'\n\s*(?=##|\d+[、.])', text)
    for i, block in enumerate(blocks):
        block = block.strip()
        if not block or len(block) < 20:
            continue
        scenes.append({
            "scene_id": i,
            "title": block[:40],
            "duration_sec": 15,
            "narration": block[:200],
            "visual_desc": block[:100],
            "animation": "",
            "raw_block": block,
        })
    return scenes


def _extract_field(text: str, field_name: str, pattern: str) -> str:
    """从文本中提取指定字段"""
    # 尝试 **字段**: 值 格式
    for prefix in [f"**{field_name}**", field_name]:
        p = re.compile(rf'{re.escape(prefix)}[：:]\s*(.+?)(?=\n(?:$|(?=\*\*)))', re.DOTALL)
        m = p.search(text)
        if m:
            return m.group(1).strip()
    return ""


def _extract_duration(text: str) -> int:
    """提取时长（秒）"""
    m = re.search(r'时长[：:]\s*(\d+)\s*秒', text)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)\s*秒', text)
    if m:
        return int(m.group(1))
    return 15  # 默认15秒


# ═══════════════════════════════════════════════════════════════
# 第二步：生成 SVG 场景图（多模板 + Mermaid 嵌入）
# ═══════════════════════════════════════════════════════════════

SCENE_TEMPLATES = {
    "flowchart": "流程图",
    "comparison": "对比表",
    "structure": "结构图",
    "timeline": "时间线",
    "hierarchy": "层级图",
}

def generate_scene_svg(scene: dict, topic: str, theme: str = "dark") -> str:
    """为单个场景生成 SVG 教学示意图（多模板支持）

    Args:
        scene: 场景数据（含 scene_id, title, visual_desc, narration, template_type）
        topic: 主题
        theme: 主题色系

    Returns:
        SVG 代码字符串
    """
    scene_id = scene["scene_id"]
    title = scene.get("title", f"场景{scene_id}")
    visual_desc = scene.get("visual_desc", "")
    narration = scene.get("narration", "")
    template_type = scene.get("template_type", "flowchart")

    # 从视觉描述中提取关键信息
    lines = _svg_content_lines(visual_desc, title, scene_id)

    bg = "#0f0f1a" if theme == "dark" else "#f5f6fb"
    text_color = "#f8fafc" if theme == "dark" else "#1a1d2e"
    sub_color = "#94a3b8" if theme == "dark" else "#525a72"
    accent = "#7c6af2"
    cyan = "#06b6d4"
    green = "#22c55e"
    warm = "#f59e0b"
    pink = "#f472b6"

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">
  <defs>
    <linearGradient id="bg-grad-{scene_id}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{bg};stop-opacity:1" />
      <stop offset="100%" style="stop-color:#0a0a14;stop-opacity:1" />
    </linearGradient>
    <linearGradient id="accent-{scene_id}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{accent}" />
      <stop offset="100%" style="stop-color:{cyan}" />
    </linearGradient>
    <linearGradient id="green-grad-{scene_id}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:{green}" />
      <stop offset="100%" style="stop-color:#16a34a" />
    </linearGradient>
    <filter id="glow-{scene_id}">
      <feGaussianBlur stdDeviation="3" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <rect width="1280" height="720" fill="url(#bg-grad-{scene_id})" rx="0"/>
  <!-- 顶部标题栏 -->
  <rect x="0" y="0" width="1280" height="80" fill="rgba(124,106,242,0.08)" />
  <text x="640" y="48" text-anchor="middle" fill="{text_color}" font-size="28" font-weight="bold" font-family="sans-serif">{_escape_svg(title)}</text>
  <!-- 场景编号 + 模板类型 -->
  <rect x="40" y="100" width="60" height="36" rx="8" fill="url(#accent-{scene_id})" />
  <text x="70" y="124" text-anchor="middle" fill="#fff" font-size="16" font-weight="bold" font-family="sans-serif">{scene_id + 1}</text>
  <rect x="110" y="100" width="80" height="36" rx="8" fill="rgba(6,182,212,0.15)" />
  <text x="150" y="124" text-anchor="middle" fill="{cyan}" font-size="14" font-weight="500" font-family="sans-serif">{SCENE_TEMPLATES.get(template_type, template_type)}</text>
  <!-- 主内容区 -->
  <rect x="40" y="150" width="1200" height="440" rx="12" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
'''

    # 根据模板类型生成不同的视觉元素
    svg += _render_template_content(template_type, lines, scene_id, accent, cyan, green, warm, pink, text_color, sub_color)

    # 底部水印
    svg += f'''  <text x="640" y="660" text-anchor="middle" fill="rgba(255,255,255,0.15)" font-size="14" font-family="sans-serif">NetLearn · 408 考研智能学习系统</text>
  <text x="640" y="690" text-anchor="middle" fill="rgba(255,255,255,0.1)" font-size="12" font-family="sans-serif">{_escape_svg(topic)}</text>
</svg>'''
    return svg


def _render_template_content(
    template_type: str, lines: list[str], scene_id: int,
    accent: str, cyan: str, green: str, warm: str, pink: str,
    text_color: str, sub_color: str,
) -> str:
    """根据模板类型渲染不同的视觉内容"""
    if template_type == "flowchart":
        return _render_flowchart(lines, scene_id, accent, cyan, green, text_color, sub_color)
    elif template_type == "comparison":
        return _render_comparison(lines, scene_id, accent, cyan, text_color, sub_color)
    elif template_type == "structure":
        return _render_structure(lines, scene_id, accent, cyan, green, text_color, sub_color)
    elif template_type == "timeline":
        return _render_timeline(lines, scene_id, accent, cyan, green, warm, text_color, sub_color)
    elif template_type == "hierarchy":
        return _render_hierarchy(lines, scene_id, accent, cyan, green, text_color, sub_color, pink)
    return _render_flowchart(lines, scene_id, accent, cyan, green, text_color, sub_color)


def _render_flowchart(lines, scene_id, accent, cyan, green, text_color, sub_color) -> str:
    """流程图模板：节点 + 箭头连接"""
    svg = ""
    nodes = lines[:5]
    node_colors = [accent, cyan, green, "#f59e0b", "#f472b6"]
    box_w, box_h = 200, 60
    start_x = 640 - (len(nodes) * (box_w + 40) - 40) // 2
    y = 300

    for i, node_text in enumerate(nodes):
        x = start_x + i * (box_w + 40)
        color = node_colors[i % len(node_colors)]
        svg += f'''
  <rect x="{x}" y="{y}" width="{box_w}" height="{box_h}" rx="10" fill="rgba(255,255,255,0.04)" stroke="{color}" stroke-width="2"/>
  <text x="{x + box_w//2}" y="{y + box_h//2 + 6}" text-anchor="middle" fill="{text_color}" font-size="15" font-weight="500" font-family="sans-serif">{_escape_svg(node_text[:20])}</text>'''
        if i < len(nodes) - 1:
            arrow_x = x + box_w + 10
            svg += f'''
  <line x1="{x + box_w}" y1="{y + box_h//2}" x2="{x + box_w + 40}" y2="{y + box_h//2}" stroke="{color}" stroke-width="2" stroke-dasharray="4,3"/>
  <polygon points="{x + box_w + 40},{y + box_h//2 - 6} {x + box_w + 40},{y + box_h//2 + 6} {x + box_w + 48},{y + box_h//2}" fill="{color}"/>'''
    return svg


def _render_comparison(lines, scene_id, accent, cyan, text_color, sub_color) -> str:
    """对比表模板：左右两栏对比"""
    svg = ""
    items = lines[:6]
    mid = len(items) // 2 + len(items) % 2
    left_items = items[:mid]
    right_items = items[mid:]

    # 左栏
    svg += f'''
  <rect x="80" y="190" width="520" height="40" rx="6" fill="rgba(124,106,242,0.12)"/>
  <text x="340" y="216" text-anchor="middle" fill="{accent}" font-size="16" font-weight="bold" font-family="sans-serif">概念 A</text>
  <rect x="680" y="190" width="520" height="40" rx="6" fill="rgba(6,182,212,0.12)"/>
  <text x="940" y="216" text-anchor="middle" fill="{cyan}" font-size="16" font-weight="bold" font-family="sans-serif">概念 B</text>'''

    for i, item in enumerate(left_items):
        y = 250 + i * 50
        svg += f'''
  <rect x="80" y="{y}" width="520" height="40" rx="6" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
  <text x="90" y="{y + 26}" fill="{text_color}" font-size="14" font-family="sans-serif">{_escape_svg(item[:40])}</text>'''

    for i, item in enumerate(right_items):
        y = 250 + i * 50
        svg += f'''
  <rect x="680" y="{y}" width="520" height="40" rx="6" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
  <text x="690" y="{y + 26}" fill="{text_color}" font-size="14" font-family="sans-serif">{_escape_svg(item[:40])}</text>'''

    # 中间分隔线
    svg += f'\n  <line x1="640" y1="190" x2="640" y2="{250 + max(len(left_items), len(right_items)) * 50}" stroke="rgba(255,255,255,0.1)" stroke-width="1" stroke-dasharray="4,4"/>'
    return svg


def _render_structure(lines, scene_id, accent, cyan, green, text_color, sub_color) -> str:
    """结构图模板：中心节点 + 子节点放射排列"""
    svg = ""
    children = lines[:6]
    center_label = lines[0] if lines else "核心概念"
    children = children[1:] if len(lines) > 1 else ["子节点1", "子节点2", "子节点3"]

    # 中心节点
    svg += f'''
  <circle cx="640" cy="320" r="60" fill="rgba(124,106,242,0.15)" stroke="{accent}" stroke-width="3"/>
  <text x="640" y="316" text-anchor="middle" fill="{text_color}" font-size="16" font-weight="bold" font-family="sans-serif">{_escape_svg(center_label[:12])}</text>'''

    # 子节点（放射排列）
    angles = [0, 45, 90, 135, 180, 225]
    colors = [accent, cyan, green, "#f59e0b", "#f472b6", "#8b5cf6"]
    for i, child in enumerate(children[:6]):
        angle = angles[i % len(angles)]
        rad = angle * 3.14159 / 180
        cx = 640 + int(180 * __import__("math").cos(rad))
        cy = 320 + int(180 * __import__("math").sin(rad))
        color = colors[i % len(colors)]
        svg += f'''
  <line x1="640" y1="320" x2="{cx}" y2="{cy}" stroke="{color}" stroke-width="1.5" stroke-dasharray="3,3"/>
  <rect x="{cx - 70}" y="{cy - 20}" width="140" height="40" rx="8" fill="rgba(255,255,255,0.04)" stroke="{color}" stroke-width="1.5"/>
  <text x="{cx}" y="{cy + 6}" text-anchor="middle" fill="{text_color}" font-size="13" font-family="sans-serif">{_escape_svg(child[:16])}</text>'''
    return svg


def _render_timeline(lines, scene_id, accent, cyan, green, warm, text_color, sub_color) -> str:
    """时间线模板：垂直时间轴 + 节点"""
    svg = ""
    items = lines[:6]
    colors = [accent, cyan, green, warm, "#f472b6", "#8b5cf6"]

    # 时间轴线
    svg += f'''
  <line x1="640" y1="180" x2="640" y2="540" stroke="rgba(255,255,255,0.1)" stroke-width="3"/>'''

    for i, item in enumerate(items):
        y = 200 + i * 60
        color = colors[i % len(colors)]
        side = "left" if i % 2 == 0 else "right"
        dot_x = 640
        text_x = 370 if side == "left" else 720
        text_anchor = "end" if side == "left" else "start"

        svg += f'''
  <circle cx="{dot_x}" cy="{y + 10}" r="8" fill="{color}" filter="url(#glow-{scene_id})"/>
  <text x="{text_x}" y="{y + 15}" text-anchor="{text_anchor}" fill="{text_color}" font-size="14" font-family="sans-serif">{_escape_svg(item[:30])}</text>'''
        if side == "left":
            svg += f'\n  <line x1="{dot_x - 8}" y1="{y + 10}" x2="{text_x + 10}" y2="{y + 10}" stroke="{color}" stroke-width="1" opacity="0.5"/>'
        else:
            svg += f'\n  <line x1="{dot_x + 8}" y1="{y + 10}" x2="{text_x - 10}" y2="{y + 10}" stroke="{color}" stroke-width="1" opacity="0.5"/>'
    return svg


def _render_hierarchy(lines, scene_id, accent, cyan, green, text_color, sub_color, pink) -> str:
    """层级图模板：树形层级结构"""
    svg = ""
    items = lines[:7]
    if not items:
        return ""

    # 根节点
    svg += f'''
  <rect x="520" y="190" width="240" height="50" rx="25" fill="rgba(124,106,242,0.15)" stroke="{accent}" stroke-width="2"/>
  <text x="640" y="222" text-anchor="middle" fill="{text_color}" font-size="16" font-weight="bold" font-family="sans-serif">{_escape_svg(items[0][:16])}</text>'''

    # 子节点
    children = items[1:]
    child_colors = [accent, cyan, green, pink, "#f59e0b"]
    n = len(children)
    if n == 0:
        return svg
    spacing = min(200, 1100 // n)
    start_x = 640 - (n - 1) * spacing // 2

    for i, child in enumerate(children):
        cx = start_x + i * spacing
        color = child_colors[i % len(child_colors)]
        svg += f'''
  <line x1="640" y1="240" x2="{cx}" y2="310" stroke="{color}" stroke-width="1.5" stroke-dasharray="3,3"/>
  <rect x="{cx - 80}" y="310" width="160" height="44" rx="8" fill="rgba(255,255,255,0.04)" stroke="{color}" stroke-width="1.5"/>
  <text x="{cx}" y="{337}" text-anchor="middle" fill="{text_color}" font-size="14" font-family="sans-serif">{_escape_svg(child[:18])}</text>'''
    return svg


def _svg_content_lines(visual_desc: str, title: str, scene_id: int) -> list[str]:
    """从视觉描述中提取用于 SVG 展示的内容行"""
    lines = []
    if visual_desc:
        parts = visual_desc.replace("。", "\n").replace("；", "\n").split("\n")
        for p in parts:
            p = p.strip()
            if p:
                lines.append(p)
    if not lines:
        lines = [f"核心概念讲解", "知识要点展示", "案例分析与应用"]
    return lines[:8]  # 最多8行


def _escape_svg(text: str) -> str:
    """转义 SVG 文本中的特殊字符"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ═══════════════════════════════════════════════════════════════
# 第三步：生成自包含 HTML 幻灯片
# ═══════════════════════════════════════════════════════════════

def generate_html_slideshow(
    scenes: list[dict],
    topic: str,
    audio_data: Optional[list[dict]] = None,
) -> str:
    """生成自包含的 HTML 幻灯片页面（可播放/可录屏）

    每个场景一页，自动按设定时长翻页。
    包含：SVG 图解 + 旁白文字 + 进度指示

    Args:
        scenes: 场景列表
        topic: 主题
        audio_data: 每段旁白的音频 base64 数据 [{scene_id, base64}]

    Returns:
        完整的 HTML 页面字符串
    """
    slides_html = ""
    for i, scene in enumerate(scenes):
        svg = generate_scene_svg(scene, topic)
        narration = _escape_svg(scene.get("narration", "")[:200])
        duration = scene.get("duration_sec", 15)

        # 是否有音频
        audio_tag = ""
        if audio_data:
            for a in audio_data:
                if a.get("scene_id") == i and a.get("base64"):
                    audio_tag = f'<audio id="audio-{i}" src="data:audio/mp3;base64,{a["base64"]}"></audio>'
                    break

        slides_html += f'''
    <div class="slide" id="slide-{i}" data-duration="{duration}">
      {audio_tag}
      <div class="slide-svg">{svg}</div>
      <div class="slide-narration">
        <div class="narration-label">📖 旁白</div>
        <div class="narration-text">{narration}</div>
      </div>
      <div class="slide-progress">
        <div class="progress-bar"><div class="progress-fill" id="progress-{i}"></div></div>
        <div class="progress-time">{duration}s</div>
      </div>
    </div>'''

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_escape_svg(topic)} - 教学视频</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#080812; color:#f8fafc; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif; overflow:hidden; }}
  .slide {{ display:none; width:1280px; height:720px; position:relative; }}
  .slide.active {{ display:block; }}
  .slide-svg {{ width:100%; height:100%; }}
  .slide-svg svg {{ width:100%; height:100%; }}
  .slide-narration {{ position:absolute; bottom:80px; left:40px; right:40px; background:rgba(15,15,26,0.85); backdrop-filter:blur(12px); border-radius:12px; padding:16px 20px; border:1px solid rgba(255,255,255,0.08); }}
  .narration-label {{ font-size:12px; color:#7c8aa0; margin-bottom:4px; letter-spacing:1px; }}
  .narration-text {{ font-size:16px; line-height:1.6; color:#f8fafc; }}
  .slide-progress {{ position:absolute; bottom:20px; left:40px; right:40px; display:flex; align-items:center; gap:12px; }}
  .progress-bar {{ flex:1; height:4px; background:rgba(255,255,255,0.1); border-radius:2px; overflow:hidden; }}
  .progress-fill {{ height:100%; background:linear-gradient(90deg,#7c6af2,#5b8bd8); width:0%; transition:width 0.1s linear; }}
  .progress-time {{ font-size:13px; color:#7c8aa0; font-weight:600; min-width:40px; text-align:right; }}
  .controls {{ position:fixed; bottom:0; left:0; right:0; height:50px; background:rgba(15,15,26,0.95); display:flex; align-items:center; justify-content:center; gap:20px; border-top:1px solid rgba(255,255,255,0.06); z-index:100; }}
  .controls button {{ padding:6px 16px; border-radius:8px; border:1px solid rgba(255,255,255,0.1); background:transparent; color:#94a3b8; font-size:14px; cursor:pointer; transition:all 0.2s; }}
  .controls button:hover {{ background:rgba(124,106,242,0.15); color:#7c6af2; border-color:#7c6af2; }}
  .controls .slide-counter {{ font-size:13px; color:#7c8aa0; }}
</style>
</head>
<body>
<div id="player">
  {slides_html}
  <div class="controls">
    <button onclick="prevSlide()">◀ 上一页</button>
    <button onclick="togglePlay()">▶ 播放/暂停</button>
    <button onclick="nextSlide()">下一页 ▶</button>
    <span class="slide-counter" id="counter">1 / {len(scenes)}</span>
  </div>
</div>
<script>
  let currentSlide = 0;
  const totalSlides = {len(scenes)};
  let isPlaying = true;
  let timer = null;
  let progressTimer = null;

  function showSlide(idx) {{
    document.querySelectorAll('.slide').forEach(s => s.classList.remove('active'));
    const slide = document.getElementById('slide-' + idx);
    if (slide) {{
      slide.classList.add('active');
      document.getElementById('counter').textContent = (idx + 1) + ' / ' + totalSlides;
    }}
    startProgress(idx);
    playAudio(idx);
  }}

  function startProgress(idx) {{
    const fill = document.getElementById('progress-' + idx);
    if (!fill) return;
    const duration = parseInt(document.getElementById('slide-' + idx)?.dataset?.duration || '15') * 10;
    let w = 0;
    if (progressTimer) clearInterval(progressTimer);
    progressTimer = setInterval(() => {{
      w++;
      fill.style.width = Math.min(100, w / duration * 100) + '%';
      if (w >= duration) {{
        clearInterval(progressTimer);
        if (isPlaying && idx < totalSlides - 1) {{
          setTimeout(() => nextSlide(), 500);
        }}
      }}
    }}, 100);
  }}

  function playAudio(idx) {{
    const audio = document.getElementById('audio-' + idx);
    if (audio) {{
      audio.currentTime = 0;
      audio.play().catch(() => {{}});
    }}
  }}

  function nextSlide() {{
    if (currentSlide < totalSlides - 1) {{
      currentSlide++;
      showSlide(currentSlide);
    }}
  }}

  function prevSlide() {{
    if (currentSlide > 0) {{
      currentSlide--;
      showSlide(currentSlide);
    }}
  }}

  function togglePlay() {{
    isPlaying = !isPlaying;
    if (isPlaying) {{
      startProgress(currentSlide);
    }} else {{
      if (progressTimer) clearInterval(progressTimer);
    }}
  }}

  // 键盘控制
  document.addEventListener('keydown', (e) => {{
    if (e.key === 'ArrowRight') nextSlide();
    if (e.key === 'ArrowLeft') prevSlide();
    if (e.key === ' ') {{ e.preventDefault(); togglePlay(); }}
  }});

  showSlide(0);
</script>
</body>
</html>'''
    return html


# ═══════════════════════════════════════════════════════════════
# 第四步：FFmpeg 合成 MP4 视频（可选）
# ═══════════════════════════════════════════════════════════════

def is_ffmpeg_available() -> bool:
    """检查 FFmpeg 是否可用"""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def render_mp4(scenes: list[dict], topic: str, output_path: str) -> Optional[str]:
    """用 FFmpeg 将 SVG 场景合成 MP4 视频

    Args:
        scenes: 场景列表
        topic: 主题
        output_path: 输出路径（可选，默认生成到 data/videos/）

    Returns:
        输出文件路径，失败返回 None
    """
    if not is_ffmpeg_available():
        logger.warning("FFmpeg 不可用，跳过 MP4 渲染")
        return None

    output_path = output_path or os.path.join(_OUTPUT_DIR, f"{uuid.uuid4().hex[:12]}.mp4")
    temp_dir = tempfile.mkdtemp()

    try:
        # 为每个场景生成 SVG 文件
        svg_files = []
        for i, scene in enumerate(scenes):
            svg = generate_scene_svg(scene, topic)
            svg_path = os.path.join(temp_dir, f"scene_{i:03d}.svg")
            with open(svg_path, "w", encoding="utf-8") as f:
                f.write(svg)
            svg_files.append(svg_path)

        # 生成 FFmpeg 输入文件列表
        # 每个场景持续 duration_sec 秒
        duration = sum(s.get("duration_sec", 15) for s in scenes)
        if duration < 1:
            duration = 30

        # 使用 concat 协议合并
        list_path = os.path.join(temp_dir, "input.txt")
        with open(list_path, "w") as f:
            for i, scene in enumerate(scenes):
                dur = scene.get("duration_sec", 15)
                f.write(f"file '{svg_files[i]}'\n")
                f.write(f"duration {dur}\n")

        # 添加最后一帧的结束标记
        if svg_files:
            f.write(f"file '{svg_files[-1]}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", "1",
            "-vf", "scale=1280:720",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode == 0 and os.path.exists(output_path):
            logger.info(f"MP4 视频渲染成功: {output_path}")
            return output_path
        else:
            logger.error(f"FFmpeg 渲染失败: {result.stderr.decode()[:500]}")
            return None

    except Exception as e:
        logger.error(f"MP4 渲染异常: {e}")
        return None
    finally:
        # 清理临时文件
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# TTS 配音生成（讯飞 / 浏览器降级）
# ═══════════════════════════════════════════════════════════════

async def generate_scene_audio(scenes: list[dict]) -> list[dict]:
    """为每段旁白生成 TTS 音频

    使用讯飞 TTS（如有配置）或返回空（前端用浏览器 Speech API 降级）

    Args:
        scenes: 场景列表 [{scene_id, narration, ...}]

    Returns:
        [{scene_id, base64, source}] 或空列表
    """
    try:
        from db.xfyun_multimodal import generate_speech
    except ImportError:
        logger.warning("TTS 模块不可用，跳过音频生成")
        return []

    audio_data = []
    for scene in scenes:
        narration = scene.get("narration", "")
        if not narration or len(narration) < 5:
            continue
        try:
            result = await generate_speech(narration[:500])
            if result and result.success and result.audio_base64:
                audio_data.append({
                    "scene_id": scene["scene_id"],
                    "base64": result.audio_base64,
                    "source": result.source,
                })
                logger.info(f"场景 {scene['scene_id']} TTS 生成成功 ({result.source})")
        except Exception as e:
            logger.warning(f"场景 {scene['scene_id']} TTS 生成失败: {e}")
            continue

    return audio_data


# ═══════════════════════════════════════════════════════════════
# 主入口：完整视频生成工作流
# ═══════════════════════════════════════════════════════════════

def generate_teaching_video(
    topic: str,
    video_script: str,
    output_format: str = "html",
    output_path: Optional[str] = None,
    audio_data: Optional[list[dict]] = None,
    difficulty: str = "medium",
    use_cache: bool = True,
) -> dict:
    """完整视频生成工作流

    工作流:
    1. 解析分镜脚本 → 结构化场景列表
    2. 生成 SVG 场景图
    3. 生成 HTML 幻灯片或 MP4 视频

    Args:
        topic: 学习主题
        video_script: 视频脚本（含分镜）
        output_format: "html" | "mp4" | "both"
        output_path: 输出路径
        audio_data: TTS 音频数据
        difficulty: 难度（用于缓存键）
        use_cache: 是否使用缓存

    Returns:
        {"status", "format", "path", "html", "scenes", "duration"}
    """
    # 1. 解析分镜
    scenes = parse_storyboard(video_script)
    if not scenes:
        return {"status": "error", "message": "无法解析分镜脚本"}

    # 缓存命中检测
    if use_cache and video_script:
        ck = _cache_key(topic, difficulty)
        cached = _cache_get(ck)
        if cached and cached == video_script:
            # 内容未变，直接返回上次结果
            pass

    total_duration = sum(s.get("duration_sec", 15) for s in scenes)

    result = {
        "status": "ok",
        "topic": topic,
        "scenes": len(scenes),
        "duration_sec": total_duration,
        "duration_str": f"{total_duration // 60}:{total_duration % 60:02d}",
    }

    # 2. 生成 HTML 幻灯片
    html = generate_html_slideshow(scenes, topic)
    result["html"] = html

    # 3. 保存 HTML 文件
    if output_format in ("html", "both"):
        html_path = output_path or os.path.join(_OUTPUT_DIR, f"{uuid.uuid4().hex[:12]}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        result["html_path"] = html_path
        result["format"] = "html"

    # 4. 可选：渲染 MP4
    if output_format in ("mp4", "both"):
        mp4_path = render_mp4(scenes, topic, output_path)
        if mp4_path:
            result["mp4_path"] = mp4_path
            result["format"] = "mp4"

    logger.info(f"视频生成完成: {topic} ({result['duration_str']}, {len(scenes)} 场景)")
    return result


def generate_video_from_topic(
    topic: str,
    profile: Optional[dict] = None,
    knowledge_context: str = "",
    output_format: str = "html",
) -> dict:
    """从主题直接生成教学视频（完整流程）

    1. 调用 LLM 生成视频脚本
    2. 解析脚本 → 场景列表
    3. 生成 SVG 场景图
    4. 生成 HTML 幻灯片

    Args:
        topic: 学习主题
        profile: 学生画像（可选）
        knowledge_context: 知识上下文（可选）
        output_format: 输出格式

    Returns:
        生成结果 dict
    """
    import asyncio
    from agents.media_generator import generate_enhanced_video_script

    # 生成视频脚本
    script = asyncio.run(
        generate_enhanced_video_script(topic, profile, knowledge_context)
    )

    # 生成视频
    return generate_teaching_video(topic, script, output_format)