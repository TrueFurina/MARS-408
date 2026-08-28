# ============================================================
# 视频配音服务 — MeloTTS + FFmpeg 自动生成教学短视频
#
# 流程：
#   1. 接收文本/视频脚本
#   2. MeloTTS 合成语音（WAV）
#   3. 生成字幕文件（SRT）
#   4. FFmpeg 合成视频（背景图 + 语音 + 字幕）
#
# 适用于赛题要求：多模态教学视频/动画生成
# ============================================================

import io
import os
import json
import logging
import tempfile
import subprocess
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("netlearn.video_dub")

# 背景图目录（内置几张默认背景）
BG_DIR = Path(__file__).parent.parent / "assets" / "video_bg"
os.makedirs(BG_DIR, exist_ok=True)

# 输出目录
OUTPUT_DIR = Path(__file__).parent.parent / "media" / "videos"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _create_default_bg():
    """如果背景图不存在，用 Python 生成一张默认背景（纯色 + 渐变）"""
    bg_path = BG_DIR / "default_bg.png"
    if bg_path.exists():
        return str(bg_path)
    try:
        import matplotlib.pyplot as plt
        import numpy as np

        fig, ax = plt.subplots(figsize=(16, 9), facecolor="#0f0f1a")
        ax.set_facecolor("#0f0f1a")
        # 添加渐变效果
        gradient = np.linspace(0, 1, 256).reshape(1, -1)
        gradient = np.vstack((gradient, gradient))
        ax.imshow(gradient, aspect="auto", cmap="viridis", alpha=0.15,
                  extent=[0, 16, 0, 9])
        ax.text(8, 5.5, "MARS-408", fontsize=48, color="white",
                ha="center", va="center", fontweight="bold", alpha=0.3)
        ax.text(8, 4.2, "考研个性化学习系统", fontsize=20, color="white",
                ha="center", va="center", alpha=0.2)
        ax.set_xlim(0, 16)
        ax.set_ylim(0, 9)
        ax.axis("off")
        plt.savefig(bg_path, dpi=72, bbox_inches="tight", pad_inches=0,
                    facecolor="#0f0f1a")
        plt.close()
        logger.info(f"已生成默认背景图: {bg_path}")
        return str(bg_path)
    except Exception as e:
        logger.warning(f"生成背景图失败: {e}")
        return None


def _generate_srt(text: str, language: str = "zh") -> str:
    """生成简单的 SRT 字幕（按句子分段，每句约 2-5 秒）"""
    import re

    # 按中文句号、问号、感叹号、换行拆分
    sentences = re.split(r"[。！？\n]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    srt_lines = []
    start_time = 0.0
    for i, sentence in enumerate(sentences):
        # 估算时长：中文字数 * 0.25 秒/字，英文单词数 * 0.3 秒/词
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", sentence))
        en_words = len(re.findall(r"[a-zA-Z]+", sentence))
        duration = max(1.5, cn_chars * 0.25 + en_words * 0.3)

        # 格式化时间戳
        def _fmt(sec):
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = int(sec % 60)
            ms = int((sec - int(sec)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        srt_lines.append(str(i + 1))
        srt_lines.append(f"{_fmt(start_time)} --> {_fmt(start_time + duration)}")
        srt_lines.append(sentence)
        srt_lines.append("")

        start_time += duration

    return "\n".join(srt_lines)


def generate_narrated_video(
    text: str,
    language: str = "zh",
    bg_image: Optional[str] = None,
    speed: float = 1.0,
) -> Optional[str]:
    """生成配音教学视频

    Args:
        text: 旁白文本
        language: 语言代码（zh/en/ja/ko/es/fr）
        bg_image: 背景图路径，None 则使用默认背景
        speed: 语速（0.5–2.0）

    Returns:
        视频文件路径，失败返回 None
    """
    try:
        # 1. 生成音频
        from services.tts_service import melo_synthesize

        audio_data = melo_synthesize(text, language)
        if audio_data is None:
            logger.error("MeloTTS 合成失败，无法生成配音视频")
            return None

        # 2. 写入临时文件
        task_id = uuid.uuid4().hex[:12]
        tmp_dir = Path(tempfile.gettempdir()) / f"mars408_video_{task_id}"
        os.makedirs(tmp_dir, exist_ok=True)

        audio_path = tmp_dir / "narration.wav"
        with open(audio_path, "wb") as f:
            f.write(audio_data)

        # 3. 生成字幕
        srt_content = _generate_srt(text, language)
        srt_path = tmp_dir / "subtitle.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        # 4. 准备背景图
        bg = bg_image or str(BG_DIR / "default_bg.png")
        if not os.path.exists(bg):
            bg = _create_default_bg()
        if bg is None or not os.path.exists(bg):
            logger.error("无可用背景图")
            return None

        # 5. FFmpeg 合成视频
        output_path = OUTPUT_DIR / f"{task_id}.mp4"
        # 获取音频时长
        probe_cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=15)
        audio_duration = float(result.stdout.strip() or 10)

        # FFmpeg 命令：背景图 + 音频 + 字幕
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(bg),
            "-i", str(audio_path),
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-vf", f"subtitles={srt_path}:force_style='FontName=Microsoft YaHei,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,Outline=1,Shadow=0,MarginV=40'",
            "-t", str(audio_duration),
            "-shortest",
            str(output_path),
        ]

        logger.info(f"正在合成视频: {' '.join(cmd)}")
        subprocess.run(cmd, capture_output=True, timeout=300, check=True)

        # 清理临时文件
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

        if output_path.exists():
            logger.info(f"视频合成完成: {output_path} ({output_path.stat().st_size / 1024:.0f} KB)")
            return str(output_path)
        return None

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg 合成超时（300s）")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg 合成失败: {e.stderr.decode()[:500]}")
        return None
    except Exception as e:
        logger.error(f"视频生成异常: {e}")
        return None


def is_ffmpeg_available() -> bool:
    """检查 FFmpeg 是否可用"""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False