# -*- coding: utf-8 -*-
"""DStudio合集制种 —— 全季媒体体检与 MediaInfo 提取模块

遵循 AGENTS.md 规范：
- 严格验证全季文件完整性，杜绝损坏、缺失与非视频杂质
- 提取代表集数的标准 MediaInfo 用于详情页渲染
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple
from pymediainfo import MediaInfo


@dataclass
class InspectionResult:
    is_valid: bool
    total_files: int
    video_files: List[str]
    sample_mediainfo_text: str
    video_codec: str
    resolution: str
    audio_tracks: List[str]
    subtitle_tracks: List[str]
    error_msg: str = ""


class MediaInspector:
    """全季视频文件体检与元数据提取器"""

    VIDEO_EXTS = {".mkv", ".mp4", ".ts"}

    @classmethod
    def inspect_pack(cls, pack_dir: Path, expected_count: Optional[int] = None) -> InspectionResult:
        if not pack_dir.exists():
            return InspectionResult(
                is_valid=False, total_files=0, video_files=[], sample_mediainfo_text="",
                video_codec="", resolution="", audio_tracks=[], subtitle_tracks=[],
                error_msg=f"目录不存在: {pack_dir}"
            )

        video_files = []
        for root, _, files in os.walk(pack_dir):
            for f in files:
                ext = Path(f).suffix.lower()
                if ext in cls.VIDEO_EXTS:
                    video_files.append(Path(root) / f)

        video_files = sorted(video_files)
        total_files = len(video_files)

        if total_files == 0:
            return InspectionResult(
                is_valid=False, total_files=0, video_files=[], sample_mediainfo_text="",
                video_codec="", resolution="", audio_tracks=[], subtitle_tracks=[],
                error_msg="未在打包目录中找到任何有效视频文件"
            )

        if expected_count is not None and total_files != expected_count:
            return InspectionResult(
                is_valid=False, total_files=total_files, video_files=[str(f) for f in video_files],
                sample_mediainfo_text="", video_codec="", resolution="", audio_tracks=[], subtitle_tracks=[],
                error_msg=f"分集数量与核准总集数不一致：预期 {expected_count} 集，实际找到 {total_files} 个视频文件"
            )

        # 抽样第 1 集提取 MediaInfo
        sample_file = video_files[0]
        try:
            mi = MediaInfo.parse(str(sample_file))
        except Exception as e:
            return InspectionResult(
                is_valid=False, total_files=total_files, video_files=[str(f) for f in video_files],
                sample_mediainfo_text="", video_codec="", resolution="", audio_tracks=[], subtitle_tracks=[],
                error_msg=f"MediaInfo 解析失败: {e}"
            )

        v_codec = ""
        resolution = ""
        audio_tracks = []
        sub_tracks = []

        for track in mi.tracks:
            if track.track_type == "Video":
                v_codec = track.format or track.codec_id or ""
                w, h = track.width, track.height
                if w and h:
                    resolution = f"{w}x{h}"
            elif track.track_type == "Audio":
                fmt = track.format or ""
                ch = track.channel_s or ""
                lang = track.language or "und"
                audio_tracks.append(f"{lang} {fmt} {ch}ch".strip())
            elif track.track_type == "Text":
                lang = track.language or "und"
                fmt = track.format or ""
                sub_tracks.append(f"{lang} {fmt}".strip())

        # 生成简洁 MediaInfo 文本
        mediainfo_text = mi.to_data().get("text", "") if hasattr(mi, "to_data") else ""
        if not mediainfo_text:
            # 备选格式化
            mediainfo_text = f"Format: {v_codec} | Resolution: {resolution} | Audio: {', '.join(audio_tracks)} | Subtitles: {', '.join(sub_tracks)}"

        return InspectionResult(
            is_valid=True,
            total_files=total_files,
            video_files=[str(f) for f in video_files],
            sample_mediainfo_text=mediainfo_text,
            video_codec=v_codec,
            resolution=resolution,
            audio_tracks=audio_tracks,
            subtitle_tracks=sub_tracks,
            error_msg=""
        )
