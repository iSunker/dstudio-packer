# -*- coding: utf-8 -*-
"""DStudio合集制种 —— 站点分集监控与采集器 (RSS / 列表轮询)

遵循 AGENTS.md 规范：
- 严格 >= 4 分钟 (240s) 轮询周期，防站点风控
- 解析单集并归集至六元组聚合键
- 自动检测站内既有合集防撞车
"""

import re
import time
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from database.schema import DatabaseManager
from pt_site.client import DStudioClient
from pt_site.parser import TitleParser, ParsedTitle
from config import RSS_POLL_INTERVAL_SEC

logger = logging.getLogger("dstudio.rss")


def parse_size_bytes(size_str: str) -> int:
    """将人类可读大小转换为字节数"""
    m = re.search(r"([\d\.]+)\s*([KMGT]?B)", size_str, re.I)
    if not m:
        return 0
    val, unit = float(m.group(1)), m.group(2).upper()
    factors = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return int(val * factors.get(unit, 1))


class TVSeriesMonitor:
    """电视剧分集监听与归集器"""

    def __init__(self, db: Optional[DatabaseManager] = None, client: Optional[DStudioClient] = None):
        self.db = db or DatabaseManager()
        self.client = client or DStudioClient()

    def scan_latest_torrents(self, pages: int = 2) -> Dict[str, int]:
        """扫描电视剧分类前 N 页，提取分集与合集状态"""
        stats = {"seen": 0, "episodes_added": 0, "packs_detected": 0}

        for page in range(pages):
            try:
                html = self.client.fetch_tv_torrents_page(page=page)
            except Exception as e:
                logger.error(f"Failed to fetch TV torrents page {page}: {e}")
                break

            soup = BeautifulSoup(html, "html.parser")
            torrent_tables = soup.find_all("table", class_="torrentname")

            for t_table in torrent_tables:
                link = t_table.find("a", href=re.compile(r"details\.php\?id=\d+"))
                if not link:
                    continue

                m_id = re.search(r"id=(\d+)", link.get("href"))
                if not m_id:
                    continue
                tid = int(m_id.group(1))

                # 提取完整主标题
                raw_title = link.get("title") or link.text.strip()
                if not raw_title:
                    continue

                # 提取中文副标题（如存在）
                sub_tag = t_table.find(["span", "font"], class_=re.compile(r"sub|desc|gray"))
                sub_text = sub_tag.text.strip() if sub_tag else ""
                cn_title = ""
                if sub_text:
                    cn_match = re.search(r"^([^/|]+)", sub_text)
                    if cn_match:
                        cn_title = cn_match.group(1).strip()

                # 提取体积
                tr = t_table.find_parent("tr")
                size_bytes = 0
                if tr:
                    tds = tr.find_all("td")
                    for td in tds:
                        txt = td.text.strip()
                        if re.search(r"^\d+(?:\.\d+)?\s*[KMGT]B$", txt, re.I):
                            size_bytes = parse_size_bytes(txt)
                            break

                # 解析标题
                parsed = TitleParser.parse(raw_title)
                if not parsed:
                    continue

                stats["seen"] += 1

                if parsed.is_pack:
                    # 站内已发布全季合集
                    stats["packs_detected"] += 1
                    # 检查本地是否在追该季，若在追则标记站内已有合集避免重复撞车
                    self.db.mark_rss_seen(tid, raw_title, is_our_pack=False)
                    cur_season = self.db.get_or_create_season(
                        season_key=parsed.season_key,
                        title=parsed.raw_title,
                        clean_title=parsed.clean_title,
                        season=parsed.season,
                        year=parsed.year,
                        cn_title=cn_title,
                        resolution=parsed.resolution,
                        source=parsed.source,
                        video_codec=parsed.video_codec,
                        audio_codec=parsed.audio_codec,
                        release_group=parsed.release_group
                    )
                    if cur_season["status"] in ["COLLECTING", "READY"]:
                        self.db.update_season_status(parsed.season_key, "EXISTING_ON_SITE")
                    continue

                # 单集处理 (parsed.episode is not None)
                if parsed.episode is not None:
                    # 确保 series_season 存在
                    self.db.get_or_create_season(
                        season_key=parsed.season_key,
                        title=parsed.raw_title,
                        clean_title=parsed.clean_title,
                        season=parsed.season,
                        year=parsed.year,
                        cn_title=cn_title,
                        resolution=parsed.resolution,
                        source=parsed.source,
                        video_codec=parsed.video_codec,
                        audio_codec=parsed.audio_codec,
                        release_group=parsed.release_group
                    )

                    # 录入分集明细
                    download_url = f"download.php?id={tid}"
                    self.db.add_or_update_episode(
                        season_key=parsed.season_key,
                        episode_num=parsed.episode,
                        raw_title=raw_title,
                        torrent_id=tid,
                        download_url=download_url,
                        size_bytes=size_bytes
                    )
                    self.db.mark_rss_seen(tid, raw_title, is_our_pack=False)
                    stats["episodes_added"] += 1

        return stats
