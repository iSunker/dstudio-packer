# -*- coding: utf-8 -*-
"""DStudio合集制种 —— 种子标题解析与规格分组模块

遵循 AGENTS.md 规范：
- 严格按 (clean_title, season, resolution, video_codec, source, release_group) 提取六元组
- 精确区分单集 (Single Episode) 与合集 (Complete / Pack)
- 识别 PROPER / REPACK 洗版标记
"""

import re
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class ParsedTitle:
    raw_title: str
    clean_title: str
    year: Optional[int]
    season: int
    episode: Optional[int]          # 若为整季合集则为 None
    end_episode: Optional[int]      # 若为多集如 E01-E02 则包含结束集
    resolution: str                # 如 1080p, 2160p, 720p
    source: str                    # 如 WEB-DL, Blu-ray, HDTV
    video_codec: str               # 如 H.264, H.265, HEVC, AVC
    audio_codec: str               # 如 DDP5.1, AAC, TrueHD
    release_group: str             # 如 DepWeb, DStudio, DSWeb
    is_pack: bool                  # 是否为合集
    is_proper: bool                # 是否为 PROPER/REPACK
    season_key: str                # 聚合规格键


class TitleParser:
    """电视剧种子标题解析引擎"""

    # 分辨率匹配
    RES_RE = re.compile(r"\b(2160p|1080p|720p|4320p|4k|8k)\b", re.I)
    # 媒介/来源匹配
    SOURCE_RE = re.compile(r"\b(WEB-DL|WEBRip|Blu-ray|BluRay|HDTV|Remux|DVD)\b", re.I)
    # 视频编码
    VCODEC_RE = re.compile(r"\b(H\.?265|HEVC|H\.?264|AVC|AV1|X265|X264)\b", re.I)
    # 音频编码
    ACODEC_RE = re.compile(r"\b(DDP\s?5\.1|DDP|Atmos|AAC|TrueHD(?:\s?5\.1|\s?7\.1)?|LPCM|AC3|FLAC|DTS(?:-HD)?)\b", re.I)
    # 洗版标记
    PROPER_RE = re.compile(r"\b(PROPER|REPACK|RERIP)\b", re.I)

    # 季集匹配正则
    # 支持 S01E02, S01E01-E02, S01EP02, S01 等格式
    SEASON_EP_RE = re.compile(r"\bS(\d{1,2})(?:[E|EP](\d{1,3})(?:-[E|EP]?(\d{1,3}))?)?\b", re.I)

    @classmethod
    def parse(cls, title: str) -> Optional[ParsedTitle]:
        clean = title.strip()
        if not clean:
            return None

        # 1. 查找 SxxExx
        se_match = cls.SEASON_EP_RE.search(clean)
        if not se_match:
            # 尝试匹配 "第X季" 或 "第X集"
            cn_se = re.search(r"第(\d+)季(?:第(\d+)集)?", clean)
            if cn_se:
                season = int(cn_se.group(1))
                ep = int(cn_se.group(2)) if cn_se.group(2) else None
                end_ep = None
            else:
                return None
        else:
            season = int(se_match.group(1))
            ep = int(se_match.group(2)) if se_match.group(2) else None
            end_ep = int(se_match.group(3)) if se_match.group(3) else None

        # 判断是否为合集
        # 若无单集号，或包含 Complete / 全xx集 / S01(且无E) 则判定为合集
        is_pack = False
        if ep is None:
            is_pack = True
        elif any(k in clean.lower() for k in ["complete", "全集", "disc"]):
            is_pack = True

        # 2. 提取年份
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", clean[:se_match.start() if se_match else len(clean)])
        year = int(year_match.group(1)) if year_match else None

        # 3. 提取剧名 (Sxx 前面的部分)
        title_part = clean[:se_match.start()].strip() if se_match else clean
        # 清除年份
        if year:
            title_part = re.sub(rf"\b{year}\b", "", title_part).strip()
        # 清理多余点号或空格
        clean_title = re.sub(r"[\._]+", " ", title_part).strip()

        # 4. 提取分辨率
        res_m = cls.RES_RE.search(clean)
        resolution = res_m.group(1).lower() if res_m else "unknown"
        if resolution == "4k":
            resolution = "2160p"

        # 5. 提取来源
        src_m = cls.SOURCE_RE.search(clean)
        source = src_m.group(1).upper() if src_m else "WEB-DL"

        # 6. 提取视频编码
        vc_m = cls.VCODEC_RE.search(clean)
        video_codec = vc_m.group(1).upper() if vc_m else "H.265"
        if video_codec in ["X265", "HEVC"]:
            video_codec = "H.265"
        elif video_codec in ["X264", "AVC"]:
            video_codec = "H.264"

        # 7. 提取音频编码
        ac_m = cls.ACODEC_RE.search(clean)
        audio_codec = ac_m.group(1).upper() if ac_m else "DDP5.1"

        # 8. 提取制作组 (最末尾的 -Group)
        grp_m = re.search(r"-([A-Za-z0-9_]+)$", clean)
        release_group = grp_m.group(1) if grp_m else "DStudio"

        # 9. 洗版标记
        is_proper = bool(cls.PROPER_RE.search(clean))

        # 10. 生成规格聚合键 (六元组标准化)
        norm_title = re.sub(r"[^A-Za-z0-9]+", ".", clean_title).strip(".")
        season_key = f"{norm_title}.S{season:02d}.{resolution}.{source}.{video_codec}-{release_group}"

        return ParsedTitle(
            raw_title=clean,
            clean_title=clean_title,
            year=year,
            season=season,
            episode=ep,
            end_episode=end_ep,
            resolution=resolution,
            source=source,
            video_codec=video_codec,
            audio_codec=audio_codec,
            release_group=release_group,
            is_pack=is_pack,
            is_proper=is_proper,
            season_key=season_key
        )
