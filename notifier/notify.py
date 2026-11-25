# -*- coding: utf-8 -*-
"""DStudio合集制种 —— pt-notice 事件归档与告警通知器

遵循 AGENTS.md 规范：
- 将生命周期事件（存储熔断、合集打包就绪、发种降级、出种达标回收）原子落盘至 pt-notice 的 spool 目录
- 兼容无 spool 目录环境（本地开发直接标准日志输出）
- 支持格式对齐 pt-notice 日报生成器
"""

import os
import time
import socket
from pathlib import Path
from datetime import datetime
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("dstudio.notify")

# 候选 spool 目录
DEFAULT_SPOOL_CANDIDATES = [
    Path("/volume2/docker_ssd/pt-notice/data/spool/dstudio"),
    Path(r"\\iSunker-DS423\docker_ssd\pt-notice\data\spool\dstudio"),
    Path(__file__).resolve().parent.parent / "data" / "spool"
]


class ReleaseNotifier:
    """PT-Project 标准通知投递器"""

    @classmethod
    def _get_spool_dir(cls) -> Path:
        env_dir = os.getenv("NOTIFY_SPOOL_DIR", "")
        if env_dir:
            p = Path(env_dir)
            p.mkdir(parents=True, exist_ok=True)
            return p

        for cand in DEFAULT_SPOOL_CANDIDATES:
            if cand.parent.exists():
                cand.mkdir(parents=True, exist_ok=True)
                return cand

        fallback = DEFAULT_SPOOL_CANDIDATES[-1]
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    @classmethod
    def _emit_spool_event(cls, kind: str, title: str, body: str, severity: str = "P2"):
        """写入标准原子 spool 事件文本"""
        spool_dir = cls._get_spool_dir()
        now = time.time()
        ts_str = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
        ts_slug = int(now * 1000)
        hostname = socket.gethostname() if hasattr(socket, "gethostname") else "nas"

        content = f"""# dstudio-notify 1.0
kind: {kind}
level: {'alert' if kind == 'alert' else 'info'}
severity: {severity}
title: {title}
timestamp: {ts_str}
host: {hostname}

{body}
"""
        filename = f"{ts_slug}_{kind}.txt"
        target_path = spool_dir / filename
        tmp_path = spool_dir / f".{filename}.tmp"

        try:
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(target_path)
            logger.info(f"Notification spool event emitted: {target_path.name}")
        except Exception as e:
            logger.warning(f"Failed to write spool event file: {e}")

    @classmethod
    def notify_storage_alert(cls, current_free_gb: float, min_free_gb: float):
        title = f"[DStudio存储告警] SSD可用空间不足 ({current_free_gb:.1f}GB < {min_free_gb}GB)"
        body = (
            f"SSD 当前可用空间仅剩 {current_free_gb:.2f} GB，已触发 {min_free_gb} GB 红色熔断线！\n"
            f"系统已自动挂起新增剧集下载队列，制发种流水线保持监控运行。"
        )
        print(f"\n⚠️  {title}\n{body}\n")
        logger.warning(title)
        cls._emit_spool_event(kind="alert", title=title, body=body, severity="P1")

    @classmethod
    def notify_pack_ready(
        cls,
        season_key: str,
        clean_title: str,
        season: int,
        total_episodes: int,
        total_size_bytes: int,
        torrent_path: str,
        bbcode_path: str,
        cn_title: str = ""
    ):
        gb = total_size_bytes / (1024 ** 3)
        title = f"[DStudio制种完成] {clean_title} S{season:02d} 全{total_episodes}集合集已生成 ({gb:.1f}GB)"
        body = (
            f"剧集: {clean_title} {f'({cn_title})' if cn_title else ''}\n"
            f"季集: 第 {season} 季 (全 {total_episodes} 集)\n"
            f"体积: {gb:.2f} GB\n"
            f"标识: {season_key}\n"
            f"种子: {torrent_path}\n"
            f"草稿: {bbcode_path}"
        )
        print(f"\n📦  {title}\n{body}\n")
        logger.info(title)
        cls._emit_spool_event(kind="info", title=title, body=body, severity="P2")

    @classmethod
    def notify_publish_success(cls, season_key: str, clean_title: str, season: int, torrent_id: int):
        title = f"[DStudio自动发布成功] {clean_title} S{season:02d} (TID={torrent_id})"
        body = (
            f"剧集 {clean_title} S{season:02d} 已成功全自动发布至 Depth Studio！\n"
            f"站点 TID: {torrent_id}\n"
            f"已回加 3018 客户端做种，正在监控出种达标回收。"
        )
        print(f"\n🎉  {title}\n{body}\n")
        logger.info(title)
        cls._emit_spool_event(kind="batch", title=title, body=body, severity="P2")

    @classmethod
    def notify_publish_failed(cls, season_key: str, clean_title: str, season: int, error_msg: str):
        title = f"[DStudio发布权限挂起] {clean_title} S{season:02d} 等待权限放行"
        body = (
            f"合集 {season_key} 制种已完成，向 Depth Studio 提交发布时返回：\n"
            f"错误原因: {error_msg}\n"
            f"系统已安全挂起并保留已打包种子与详情页草稿。\n"
            f"权限就绪后可执行: python cli.py publish --season-key \"{season_key}\""
        )
        print(f"\n⏸️  {title}\n{body}\n")
        logger.warning(title)
        cls._emit_spool_event(kind="alert", title=title, body=body, severity="P2")

    @classmethod
    def notify_seed_qualified_and_cleaned(cls, season_key: str, clean_title: str, freed_gb: float):
        title = f"[DStudio出种达标] {clean_title} 已达标并安全回收空间 (+{freed_gb:.1f}GB)"
        body = (
            f"剧集合集 {season_key} 达成出种指标 (seeders > 3 或 ratio >= 1.05)！\n"
            f"已从 3018 移除做种任务并安全删除实体文件，为后续剧集释放 {freed_gb:.2f} GB 空间。"
        )
        print(f"\n🧹  {title}\n{body}\n")
        logger.info(title)
        cls._emit_spool_event(kind="info", title=title, body=body, severity="P2")
