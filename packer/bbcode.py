# -*- coding: utf-8 -*-
"""DStudio合集制种 —— 详情页 BBCode 排版生成模块

遵循 AGENTS.md 规范：
- 聚合海报、剧情简介、演职员信息、全季文件列表与 MediaInfo 参数
- 自动生成合集致谢声明，杜绝盗版篡改或粗制滥造
"""

from typing import List, Optional


class BBCodeGenerator:
    """详情页标准 BBCode 渲染引擎"""

    @classmethod
    def generate_pack_bbcode(
        cls,
        clean_title: str,
        season: int,
        year: Optional[int],
        total_episodes: int,
        release_group: str,
        cn_title: str = "",
        poster_url: str = "",
        overview: str = "",
        mediainfo_summary: str = "",
        file_list: Optional[List[str]] = None,
        repack_note: str = ""
    ) -> str:
        parts = []

        # 1. 顶部致谢与免责声明
        notice = f"本合集由 DStudio-Packer 汇集全季各分集制作完整做种。\n零删减保留全部分集、多音轨与软字幕。\n致谢原分集发布者与制作组：{release_group}。"
        if repack_note:
            notice = f"[b][color=red]★ REPACK / 修订说明：[/color][/b]\n{repack_note}\n\n" + notice
        parts.append(f"[quote=Depth Studio 合集制种声明]\n{notice}\n[/quote]\n")

        # 2. 居中海报
        if poster_url:
            parts.append(f"[center][img]{poster_url}[/img][/center]\n")

        # 3. 基础剧集资料
        parts.append(f"◎片　　名　{clean_title}")
        if cn_title:
            parts.append(f"◎译　　名　{cn_title}")
        if year:
            parts.append(f"◎年　　代　{year}")
        parts.append(f"◎季　　数　第 {season} 季")
        parts.append(f"◎集　　数　全 {total_episodes} 集")
        parts.append("")

        # 4. 剧情简介
        if overview:
            parts.append("◎简　　介\n")
            parts.append(overview.strip())
            parts.append("")

        # 5. MediaInfo 媒体参数
        if mediainfo_summary:
            parts.append(f"[quote=MediaInfo 抽样媒体参数]\n{mediainfo_summary.strip()}\n[/quote]\n")

        # 6. 文件列表 (Filelist)
        if file_list:
            files_str = "\n".join([f"  • {Path(f).name}" for f in file_list])
            parts.append(f"[quote=全季文件清单 (共 {len(file_list)} 集)]\n{files_str}\n[/quote]\n")

        return "\n".join(parts)


from pathlib import Path
