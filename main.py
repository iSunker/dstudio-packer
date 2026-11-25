# -*- coding: utf-8 -*-
"""DStudio合集制种 —— 主调度守护进程 (Daemon)

遵循 AGENTS.md、dev-god 与 nas-ops 铁律：
- 严格 >= 4 分钟 (240s) 轮询周期，杜绝站点风控
- 实时监控 SSD 可用空间 (< 100GB 红色熔断)
- 下载并行 + 制发种单锁串行：全力主攻单部合集出种达标后流水线式轮转
- 优雅启停信号捕获 (SIGINT / SIGTERM)
- 闭环全生命周期：采集 -> 完结核验 -> 集中拉取 -> 零拷贝硬链接 -> MediaInfo体检 -> torf制种 -> 自动发布/降级 -> 出种达标自动回收
"""

import os
import sys
import time
import signal
import shutil
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database.schema import DatabaseManager
from pt_site.rss import TVSeriesMonitor
from pt_site.client import DStudioClient
from pt_site.publisher import DStudioPublisher
from metadata.tmdb import TMDBValidator
from downloader.qb_client import QBitDStudioClient
from packer.hardlink import HardlinkPacker
from packer.inspector import MediaInspector
from packer.torrent import TorrentMaker
from packer.bbcode import BBCodeGenerator
from notifier.notify import ReleaseNotifier
from config import (
    RSS_POLL_INTERVAL_SEC, SSD_MIN_FREE_GB, HOST_DOWNLOADS_ROOT,
    CONTAINER_DOWNLOADS_ROOT, CONTAINER_EPISODES_DIR, HOST_PACKS_DIR
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dstudio.daemon")


class DStudioDaemon:
    """电视剧合集自动制种常驻中枢"""

    def __init__(self):
        self.running = True
        self.db = DatabaseManager()
        self.client = DStudioClient()
        self.monitor = TVSeriesMonitor(db=self.db, client=self.client)
        self.validator = TMDBValidator()
        self.qb = QBitDStudioClient()
        self.publisher = DStudioPublisher(client=self.client)
        self.packer = HardlinkPacker()

        # 注册信号捕获以实现优雅停机
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        logger.info(f"Received exit signal ({signum}), gracefully shutting down...")
        self.running = False

    def get_ssd_free_gb(self) -> float:
        """获取工作 SSD 卷剩余可用空间 (GB)"""
        target_dir = CONTAINER_DOWNLOADS_ROOT if os.path.exists(CONTAINER_DOWNLOADS_ROOT) else str(HOST_DOWNLOADS_ROOT)
        try:
            total, used, free = shutil.disk_usage(target_dir)
            return free / (1024 ** 3)
        except Exception as e:
            logger.warning(f"Failed to check disk usage on {target_dir}: {e}")
            return 999.0

    def start_download_season(self, season_key: str) -> bool:
        """集中拉取指定全季分集推入 3018 开始下载"""
        episodes = self.db.get_season_episodes(season_key)
        if not episodes:
            logger.warning(f"No episodes found in DB for season: {season_key}")
            return False

        logger.info(f"开始拉取 {season_key} 的全部 {len(episodes)} 个分集种子到 3018 ...")
        target_save_path = f"{CONTAINER_EPISODES_DIR}/{season_key}"
        added = 0
        for ep in episodes:
            try:
                torrent_bytes = self.client.download_torrent(ep["torrent_id"])
                filename = f"{ep['torrent_id']}.torrent"
                success = self.qb.add_torrent_bytes(
                    torrent_bytes=torrent_bytes,
                    filename=filename,
                    save_path=target_save_path,
                    tags="dstudio-pack",
                    auto_resume=True
                )
                if success:
                    added += 1
            except Exception as e:
                logger.error(f"Failed to add episode {ep['episode_num']} (TID={ep['torrent_id']}): {e}")

        logger.info(f"已将 {added}/{len(episodes)} 个分集推入 3018，状态更新为 DOWNLOADING")
        self.db.update_season_status(season_key, "DOWNLOADING")
        return added > 0

    def pack_and_publish_season(self, season_key: str, version: int = 1) -> bool:
        """纯 Python 驱动：执行硬链接组包、抽样体检、制种、生成详情页与自动发布/降级"""
        with self.db.get_connection() as conn:
            s = conn.execute("SELECT * FROM series_season WHERE season_key = ?", (season_key,)).fetchone()
        if not s:
            logger.error(f"Season not found in DB: {season_key}")
            return False

        # 1. 创建同卷物理硬链接
        logger.info(f"[流水线-1] 正在为 {season_key} 创建同卷零拷贝硬链接组包 ...")
        pack_dir = self.packer.create_pack_hardlinks(season_key, version=version)

        # 2. 抽样媒体体检
        logger.info(f"[流水线-2] 正在执行全季文件完整性与 MediaInfo 抽样体验 ...")
        insp = MediaInspector.inspect_pack(pack_dir, expected_count=s["total_episodes"] or None)
        if not insp.is_valid:
            logger.error(f"媒体体检未通过，中止制种: {insp.error_msg}")
            return False

        # 3. 生成 .torrent 种子文件
        logger.info(f"[流水线-3] 正在计算分片哈希生成合集种子 ...")
        out_torrent = pack_dir.parent / f"{season_key}.v{version}.torrent"
        torrent_path, info_hash, total_size = TorrentMaker.make_pack_torrent(
            pack_dir=pack_dir,
            output_torrent_path=out_torrent,
            comment=f"DStudio Complete Pack by iSunker (v{version})"
        )

        # 4. 生成 BBCode 详情页草稿
        logger.info(f"[流水线-4] 正在生成 BBCode 详情页排版草稿 ...")
        bbcode = BBCodeGenerator.generate_pack_bbcode(
            clean_title=s["clean_title"],
            season=s["season"],
            year=s["year"],
            total_episodes=s["total_episodes"] or insp.total_files,
            release_group=s["release_group"] or "DepWeb",
            cn_title=s["cn_title"] or "",
            mediainfo_summary=insp.sample_mediainfo_text,
            file_list=insp.video_files
        )
        bbcode_file = pack_dir.parent / f"{season_key}.v{version}.bbcode.txt"
        bbcode_file.write_text(bbcode, encoding="utf-8")

        self.db.update_season_status(
            season_key, "PACKED",
            pack_torrent_path=str(out_torrent),
            pack_info_hash=info_hash,
            total_size_bytes=total_size
        )

        ReleaseNotifier.notify_pack_ready(
            season_key=season_key,
            clean_title=s["clean_title"],
            season=s["season"],
            total_episodes=s["total_episodes"] or insp.total_files,
            total_size_bytes=total_size,
            torrent_path=str(out_torrent),
            bbcode_path=str(bbcode_file),
            cn_title=s["cn_title"] or ""
        )

        # 5. 自动发布到 Depth Studio (带权限平滑降级)
        logger.info(f"[流水线-5] 正在向 Depth Studio 提交发布合集 ...")
        合集主标题 = self.publisher.build_合集主标题(
            raw_title=s["title"],
            clean_title=s["clean_title"],
            season=s["season"],
            year=s["year"],
            resolution=s["resolution"] or insp.resolution,
            source=s["source"] or "WEB-DL",
            video_codec=s["video_codec"] or insp.video_codec,
            audio_codec=s["audio_codec"] or "DDP5.1",
            release_group=s["release_group"] or "DepWeb"
        )
        合集副标题 = self.publisher.build_合集副标题(
            cn_title=s["cn_title"] or "",
            season=s["season"],
            total_episodes=s["total_episodes"] or insp.total_files
        )

        pub_res = self.publisher.publish_pack(
            torrent_path=out_torrent,
            name=合集主标题,
            small_descr=合集副标题,
            descr=bbcode,
            resolution=s["resolution"] or "2160p",
            video_codec=s["video_codec"] or "H.265/HEVC",
            audio_codec=s["audio_codec"] or "DDP5.1",
            release_group=s["release_group"] or "DepWeb",
            medium=s["source"] or "WEB-DL",
            anonymous=True
        )

        if pub_res.success and pub_res.torrent_id:
            logger.info(f"🎉 合集发布成功！TID={pub_res.torrent_id}，正在回加 3018 客户端做种 ...")
            # 回加 3018 做种 (指到 packs 目录)
            save_path = f"{CONTAINER_DOWNLOADS_ROOT}/packs" if os.path.exists(CONTAINER_DOWNLOADS_ROOT) else str(HOST_PACKS_DIR)
            self.qb.add_torrent_bytes(
                torrent_bytes=out_torrent.read_bytes(),
                filename=out_torrent.name,
                save_path=save_path,
                is_skip_checking=True,
                auto_resume=True,
                tags="dstudio-pack"
            )
            self.db.update_season_status(season_key, "PUBLISHED")
            ReleaseNotifier.notify_publish_success(
                season_key=season_key,
                clean_title=s["clean_title"],
                season=s["season"],
                torrent_id=pub_res.torrent_id
            )
            return True
        else:
            logger.warning(f"发布未能直接完成: {pub_res.error_msg}，状态更新为 PACKED_PENDING_APPROVAL")
            self.db.update_season_status(season_key, "PACKED_PENDING_APPROVAL")
            ReleaseNotifier.notify_publish_failed(
                season_key=season_key,
                clean_title=s["clean_title"],
                season=s["season"],
                error_msg=pub_res.error_msg
            )
            return False

    def clean_qualified_season(self, season_key: str) -> bool:
        """出种达标后安全回收：从 3018 删除做种任务并删除物理文件"""
        logger.info(f"正在执行出种达标回收: {season_key} ...")
        with self.db.get_connection() as conn:
            s = conn.execute("SELECT * FROM series_season WHERE season_key = ?", (season_key,)).fetchone()

        torrents = self.qb.get_torrents(tag="dstudio-pack")
        target_hashes = [t["hash"] for t in torrents if season_key in t.get("name", "") or season_key in t.get("save_path", "")]
        if target_hashes:
            self.qb.delete_torrents(target_hashes, delete_files=True)
            logger.info(f"已从 3018 移除 {len(target_hashes)} 个任务并清理关联物理文件。")

        # 清除分集与打包目录
        root = Path(CONTAINER_DOWNLOADS_ROOT) if os.path.exists(CONTAINER_DOWNLOADS_ROOT) else HOST_DOWNLOADS_ROOT
        episodes_dir = root / "episodes" / season_key
        packs_dir = root / "packs" / f"{season_key}.v1"

        freed_gb = (s["total_size_bytes"] or 0) / (1024 ** 3)
        if episodes_dir.exists():
            shutil.rmtree(episodes_dir, ignore_errors=True)
        if packs_dir.exists():
            shutil.rmtree(packs_dir, ignore_errors=True)

        self.db.update_season_status(season_key, "ARCHIVED")
        ReleaseNotifier.notify_seed_qualified_and_cleaned(
            season_key=season_key,
            clean_title=s["clean_title"] if s else season_key,
            freed_gb=freed_gb
        )
        return True

    def run_cycle(self):
        """执行单次全流程调度巡检"""
        # 1. 检查 SSD 存储水位
        free_gb = self.get_ssd_free_gb()
        logger.info(f"[水位监测] 当前 SSD 可用空间: {free_gb:.2f} GB (熔断警戒线: {SSD_MIN_FREE_GB} GB)")
        allow_new_download = (free_gb >= SSD_MIN_FREE_GB)
        if not allow_new_download:
            ReleaseNotifier.notify_storage_alert(free_gb, SSD_MIN_FREE_GB)

        # 2. 轮询电视剧列表 / RSS
        logger.info("[RSS 轮询] 正在抓取最新电视剧分集 ...")
        stats = self.monitor.scan_latest_torrents(pages=2)
        logger.info(f"[RSS 轮询] 条目 {stats['seen']}，新分集 {stats['episodes_added']}，站内合集 {stats['packs_detected']}")

        # 3. 校验采集中剧集的完结状态
        collecting = self.db.get_seasons_by_status("COLLECTING")
        for s in collecting:
            s_key = s["season_key"]
            episodes = self.db.get_season_episodes(s_key)
            ep_nums = [e["episode_num"] for e in episodes]
            res = self.validator.verify_season(
                clean_title=s["clean_title"],
                season_num=s["season"],
                year=s["year"],
                local_episodes=ep_nums,
                subtitle_hint=s["title"]
            )
            if res.is_completed:
                self.db.update_season_status(s_key, "READY", total_episodes=res.total_episodes)
                logger.info(f"🎉 剧集 {s_key} 已核准全季完结且分集集齐！状态变更为 READY")

        # 4. 下载阶段（支持并行拉取，受 SSD 水位门禁约束）
        if allow_new_download:
            ready_seasons = self.db.get_seasons_by_status("READY")
            for s in ready_seasons:
                s_key = s["season_key"]
                logger.info(f"启动已集齐剧集下载: {s_key}")
                self.start_download_season(s_key)

        # 5. 检查正在下载的剧集是否全部 100% 下载完毕
        downloading = self.db.get_seasons_by_status("DOWNLOADING")
        if downloading:
            torrents = self.qb.get_torrents(tag="dstudio-pack")
            for s in downloading:
                s_key = s["season_key"]
                episodes = self.db.get_season_episodes(s_key)
                all_done = True
                for ep in episodes:
                    matched = [t for t in torrents if str(ep["torrent_id"]) in t.get("name", "") or s_key in t.get("save_path", "")]
                    if not matched or any(t.get("progress", 0) < 1.0 for t in matched):
                        all_done = False
                        break

                if all_done and episodes:
                    logger.info(f"全季分集已 100% 下载完毕: {s_key}，状态变更为 DOWNLOADED")
                    self.db.update_season_status(s_key, "DOWNLOADED")

        # 6. 制种与发种阶段（严格单锁串行：全力主攻出一个种子）
        active_pack_seasons = self.db.get_seasons_by_status("PACKED") + self.db.get_seasons_by_status("PUBLISHED")
        if not active_pack_seasons:
            downloaded_seasons = self.db.get_seasons_by_status("DOWNLOADED")
            if downloaded_seasons:
                target_season = downloaded_seasons[0]["season_key"]
                logger.info(f"当前流水线空闲，挑选首个就绪剧集全力制发种: {target_season}")
                self.pack_and_publish_season(target_season)
        else:
            logger.info(f"当前已有正在制发种/做种中的剧集，串行等待出种回收: {[s['season_key'] for s in active_pack_seasons]}")

        # 7. 监控已发布合集的做种达标回收 (seeders > 3 或 ratio >= 1.05)
        published_seasons = self.db.get_seasons_by_status("PUBLISHED")
        for s in published_seasons:
            s_key = s["season_key"]
            info_hash = s["pack_info_hash"]
            if info_hash and self.qb.check_pack_seeded_qualified(info_hash):
                logger.info(f"🎉 剧集 {s_key} 已达成出种指标，启动自动清理释放 SSD 空间！")
                self.clean_qualified_season(s_key)

    def run_scheduler_loop(self):
        """常驻守护进程主循环"""
        logger.info("==================================================================")
        logger.info("🚀 DStudio-Packer 自动化守护进程已启动 (常驻 NAS 模式)")
        logger.info(f"   轮询周期: {RSS_POLL_INTERVAL_SEC} 秒 | 熔断水位: {SSD_MIN_FREE_GB} GB")
        logger.info("==================================================================")

        while self.running:
            try:
                self.run_cycle()
            except Exception as e:
                logger.error(f"Scheduler loop iteration failed: {e}", exc_info=True)

            logger.info(f"等待下一次调度轮询 ({RSS_POLL_INTERVAL_SEC} 秒) ...")
            # 步进睡眠以响应中断信号
            for _ in range(RSS_POLL_INTERVAL_SEC // 5):
                if not self.running:
                    break
                time.sleep(5)

        logger.info("DStudio-Packer 服务已安全停止。")


if __name__ == "__main__":
    daemon = DStudioDaemon()
    daemon.run_scheduler_loop()
