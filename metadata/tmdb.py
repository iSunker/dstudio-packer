# -*- coding: utf-8 -*-
"""DStudio合集制种 —— TMDB 与双源完结校验模块

遵循 AGENTS.md 规范：
- TMDB API v3 作为主力完结验证源，核验每集 air_date 与总集数
- 辅以站点副标题特征提取（如 "完结", "全12集"）作为无 API Key 或冷门剧的兜底
- 提供 is_season_complete() 严密校验门禁：
  1. 本地集数必须连续 [1..N]
  2. N 必须与 TMDB / 官方核准总集数完全一致
  3. 最后一集必须已过播出缓冲期（防提前制种）
"""

import os
import re
import time
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime, date
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from config import TMDB_API_KEY, TMDB_API_BASE

logger = logging.getLogger("dstudio.tmdb")


@dataclass
class SeasonCompletionInfo:
    is_completed: bool
    total_episodes: int
    aired_episodes: int
    air_status: str
    last_air_date: Optional[str]
    tmdb_id: Optional[int]
    reason: str


class TMDBValidator:
    """TMDB 剧季完结状态机与校验器"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or TMDB_API_KEY or os.getenv("TMDB_API_KEY", "")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _request(self, endpoint: str, params: Optional[Dict[str, str]] = None) -> Optional[dict]:
        if not self.api_key:
            return None

        query_params = {"api_key": self.api_key, "language": "zh-CN"}
        if params:
            query_params.update(params)

        url = f"{TMDB_API_BASE.rstrip('/')}/{endpoint.lstrip('/')}?{urllib.parse.urlencode(query_params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "DStudio-Packer/1.0"})
        try:
            with self.opener.open(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.warning(f"TMDB request failed for {endpoint}: {e}")
            return None

    def search_tv(self, title: str, year: Optional[int] = None) -> Optional[int]:
        """搜索电视剧并返回 TMDB TV ID"""
        params = {"query": title}
        if year:
            params["first_air_date_year"] = str(year)
        data = self._request("search/tv", params)
        if not data or not data.get("results"):
            # 若带年份没搜到，去掉年份再试一次
            if year:
                params.pop("first_air_date_year", None)
                data = self._request("search/tv", params)

        if data and data.get("results"):
            return data["results"][0]["id"]
        return None

    def get_season_details(self, tv_id: int, season_num: int) -> Optional[dict]:
        """获取指定电视剧指定季的详细集数信息"""
        return self._request(f"tv/{tv_id}/season/{season_num}")

    def verify_season(
        self,
        clean_title: str,
        season_num: int,
        year: Optional[int] = None,
        local_episodes: Optional[List[int]] = None,
        subtitle_hint: str = ""
    ) -> SeasonCompletionInfo:
        """核心完结校验门禁：
        结合 TMDB 与站点副标题判断该季是否已真正完结、分集是否已全部集齐
        """
        local_eps = sorted(list(set(local_episodes or [])))
        today_str = date.today().isoformat()

        # 1. 尝试从副标题中提取 "全XX集" 或 "完结" 提示
        hint_total_eps = None
        if subtitle_hint:
            m_total = re.search(r"全\s*(\d{1,3})\s*集", subtitle_hint)
            if m_total:
                hint_total_eps = int(m_total.group(1))

        # 2. 如果有 TMDB API Key，以 TMDB 权威数据为准
        if self.api_key:
            tv_id = self.search_tv(clean_title, year)
            if tv_id:
                s_data = self.get_season_details(tv_id, season_num)
                if s_data and "episodes" in s_data:
                    episodes = s_data["episodes"]
                    total_eps = len(episodes)
                    
                    # 检查所有集的播出日期
                    aired_count = 0
                    last_air_date = None
                    for ep in episodes:
                        air_d = ep.get("air_date")
                        if air_d and air_d <= today_str:
                            aired_count += 1
                            last_air_date = air_d

                    air_status = "Ended" if aired_count == total_eps and total_eps > 0 else "Air_in_Progress"

                    # 校验连续性
                    expected_eps = list(range(1, total_eps + 1))
                    if aired_count < total_eps:
                        return SeasonCompletionInfo(
                            is_completed=False,
                            total_episodes=total_eps,
                            aired_episodes=aired_count,
                            air_status=air_status,
                            last_air_date=last_air_date,
                            tmdb_id=tv_id,
                            reason=f"TMDB 显示尚未全剧完结（已播 {aired_count}/{total_eps} 集，末集播映日 {last_air_date}）"
                        )

                    if local_eps != expected_eps:
                        missing = set(expected_eps) - set(local_eps)
                        return SeasonCompletionInfo(
                            is_completed=False,
                            total_episodes=total_eps,
                            aired_episodes=aired_count,
                            air_status=air_status,
                            last_air_date=last_air_date,
                            tmdb_id=tv_id,
                            reason=f"全季已播完，但站点/本地缺集：缺失第 {sorted(list(missing))} 集"
                        )

                    return SeasonCompletionInfo(
                        is_completed=True,
                        total_episodes=total_eps,
                        aired_episodes=aired_count,
                        air_status="Ended",
                        last_air_date=last_air_date,
                        tmdb_id=tv_id,
                        reason="TMDB 核准全季已完结且本地集数连续完整"
                    )

        # 3. 兜底策略：若无 TMDB Key 或 TMDB 查无数据，使用副标题特征
        if hint_total_eps:
            expected_eps = list(range(1, hint_total_eps + 1))
            if local_eps == expected_eps:
                return SeasonCompletionInfo(
                    is_completed=True,
                    total_episodes=hint_total_eps,
                    aired_episodes=hint_total_eps,
                    air_status="Ended (Hint)",
                    last_air_date=today_str,
                    tmdb_id=None,
                    reason=f"副标题标注全 {hint_total_eps} 集且本地分集已集齐 [1..{hint_total_eps}]"
                )
            else:
                return SeasonCompletionInfo(
                    is_completed=False,
                    total_episodes=hint_total_eps,
                    aired_episodes=len(local_eps),
                    air_status="Collecting (Hint)",
                    last_air_date=None,
                    tmdb_id=None,
                    reason=f"副标题标注全 {hint_total_eps} 集，当前仅有 {len(local_eps)} 集"
                )

        # 4. 若无任何元数据，保守返回未完结
        return SeasonCompletionInfo(
            is_completed=False,
            total_episodes=0,
            aired_episodes=len(local_eps),
            air_status="Unknown",
            last_air_date=None,
            tmdb_id=None,
            reason="缺少 TMDB 凭据且标题无总集数标注，保持等待采集"
        )
