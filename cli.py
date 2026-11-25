# -*- coding: utf-8 -*-
"""DStudio合集制种 —— 统一命令行控制中心 (CLI)

遵循 AGENTS.md 与 dev-god 规范：
- 消除外部脆弱的 os.system 调用，全部采用 Python 内部模块直接调用
- 支持手动与自动化双模并存：
  - scan (扫描采集)
  - status (看板状态)
  - verify (完结校验)
  - pull (集中拉取)
  - pack (硬链接制种)
  - publish (手动发布或重试)
  - clean (出种回收)
  - daemon (启动常驻守护服务)
"""

import os
import sys
import argparse
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from database.schema import DatabaseManager
from main import DStudioDaemon
from pt_site.rss import TVSeriesMonitor
from pt_site.publisher import DStudioPublisher
from pt_site.client import DStudioClient
from metadata.tmdb import TMDBValidator
from downloader.qb_client import QBitDStudioClient
from notifier.notify import ReleaseNotifier
from config import HOST_PACKS_DIR, CONTAINER_DOWNLOADS_ROOT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dstudio.cli")


def cmd_scan(args):
    """扫描 Depth Studio 电视剧分类最新种子"""
    monitor = TVSeriesMonitor()
    print(f"正在扫描 Depth Studio 电视剧分类前 {args.pages} 页 ...")
    res = monitor.scan_latest_torrents(pages=args.pages)
    print(f"扫描完成：扫描条目 {res['seen']}，新录入分集 {res['episodes_added']}，检测到站内合集 {res['packs_detected']}")


def cmd_status(args):
    """查看追踪中的电视剧季集看板"""
    db = DatabaseManager()
    with db.get_connection() as conn:
        query = """
        SELECT s.season_key, s.clean_title, s.season, s.resolution, s.release_group, s.status,
               s.total_episodes as target_eps,
               COUNT(e.id) as local_eps
        FROM series_season s
        LEFT JOIN episodes e ON s.season_key = e.season_key AND e.is_superseded = 0
        GROUP BY s.season_key
        ORDER BY s.updated_at DESC
        """
        rows = conn.execute(query).fetchall()

    if not rows:
        print("当前尚无追踪中的剧集数据，请先执行: python cli.py scan")
        return

    print("\n" + "="*115)
    print(f"{'剧集名称':<25} {'季':<4} {'规格/组':<22} {'状态':<18} {'已获集数/目标':<15} {'聚合标识'}")
    print("-" * 115)
    for r in rows:
        title = (r["clean_title"] or "")[:23]
        spec = f"{r['resolution']}-{r['release_group']}"[:20]
        eps_info = f"{r['local_eps']} / {r['target_eps'] or '?'}"
        print(f"{title:<25} S{r['season']:<3} {spec:<22} {r['status']:<18} {eps_info:<15} {r['season_key']}")
    print("="*115 + "\n")


def cmd_verify(args):
    """运行 TMDB 完结状态机校验"""
    db = DatabaseManager()
    validator = TMDBValidator()
    seasons = db.get_seasons_by_status("COLLECTING")

    print(f"开始校验 {len(seasons)} 个采集中剧集的完结状态 ...")
    for s in seasons:
        s_key = s["season_key"]
        episodes = db.get_season_episodes(s_key)
        ep_nums = [e["episode_num"] for e in episodes]

        res = validator.verify_season(
            clean_title=s["clean_title"],
            season_num=s["season"],
            year=s["year"],
            local_episodes=ep_nums,
            subtitle_hint=s["title"]
        )

        print(f"[{s_key}] => {res.reason}")
        if res.is_completed:
            db.update_season_status(s_key, "READY", total_episodes=res.total_episodes)
            print(f"  🎉 恭喜！{s['clean_title']} S{s['season']} 已集齐并完结，状态变更为: READY")


def cmd_pull(args):
    """集中拉取全季分集推入 3018 开始下载"""
    daemon = DStudioDaemon()
    db = DatabaseManager()
    seasons = [s for s in db.get_seasons_by_status("READY") if not args.season_key or s["season_key"] == args.season_key]
    if not seasons:
        print(f"未找到状态为 READY 的待拉取剧季 (或指定 season_key 不存在/未就绪)")
        return

    for s in seasons:
        daemon.start_download_season(s["season_key"])


def cmd_pack(args):
    """执行分集硬链接组包、MediaInfo 体检与 torf 制种"""
    daemon = DStudioDaemon()
    daemon.pack_and_publish_season(season_key=args.season_key, version=args.version)


def cmd_publish(args):
    """手动发布或重试发布合集"""
    daemon = DStudioDaemon()
    db = DatabaseManager()
    s_key = args.season_key
    with db.get_connection() as conn:
        s = conn.execute("SELECT * FROM series_season WHERE season_key = ?", (s_key,)).fetchone()
    if not s:
        print(f"未找到剧季: {s_key}")
        return

    torrent_path = Path(s["pack_torrent_path"]) if s["pack_torrent_path"] else None
    if not torrent_path or not torrent_path.exists():
        print(f"合集种子文件不存在，请先执行: python cli.py pack --season-key \"{s_key}\"")
        return

    bbcode_path = torrent_path.parent / f"{s_key}.v1.bbcode.txt"
    descr = bbcode_path.read_text(encoding="utf-8") if bbcode_path.exists() else ""

    publisher = DStudioPublisher()
    合集主标题 = publisher.build_合集主标题(
        raw_title=s["title"],
        clean_title=s["clean_title"],
        season=s["season"],
        year=s["year"],
        resolution=s["resolution"] or "2160p",
        source=s["source"] or "WEB-DL",
        video_codec=s["video_codec"] or "H.265/HEVC",
        audio_codec=s["audio_codec"] or "DDP5.1",
        release_group=s["release_group"] or "DepWeb"
    )
    合集副标题 = publisher.build_合集副标题(
        cn_title=s["cn_title"] or "",
        season=s["season"],
        total_episodes=s["total_episodes"] or 0
    )

    print(f"正在发布合集 {合集主标题} ...")
    pub_res = publisher.publish_pack(
        torrent_path=torrent_path,
        name=合集主标题,
        small_descr=合集副标题,
        descr=descr,
        resolution=s["resolution"] or "2160p",
        video_codec=s["video_codec"] or "H.265/HEVC",
        audio_codec=s["audio_codec"] or "DDP5.1",
        release_group=s["release_group"] or "DepWeb",
        medium=s["source"] or "WEB-DL"
    )

    if pub_res.success:
        print(f"🎉 发布成功！站点 TID: {pub_res.torrent_id}")
        db.update_season_status(s_key, "PUBLISHED")
    else:
        print(f"❌ 发布未成功: {pub_res.error_msg}")


def cmd_clean(args):
    """出种即删：合集发布做种达标后回收空间"""
    daemon = DStudioDaemon()
    daemon.clean_qualified_season(args.season_key)


def cmd_daemon(args):
    """启动常驻守护服务"""
    daemon = DStudioDaemon()
    daemon.run_scheduler_loop()


def main():
    parser = argparse.ArgumentParser(description="Depth Studio 电视剧合集自动制种控制中枢")
    subparsers = parser.add_subparsers(dest="subcmd")

    p_scan = subparsers.add_parser("scan", help="扫描站点电视剧最新分集")
    p_scan.add_argument("--pages", type=int, default=2, help="扫描页数")

    p_status = subparsers.add_parser("status", help="查看剧集追踪状态看板")

    p_verify = subparsers.add_parser("verify", help="运行 TMDB 完结状态机校验")

    p_pull = subparsers.add_parser("pull", help="集中拉取全季分集进行下载")
    p_pull.add_argument("--season-key", type=str, help="指定剧集聚合键")

    p_pack = subparsers.add_parser("pack", help="执行硬链接制种与生成发布草稿")
    p_pack.add_argument("--season-key", type=str, required=True, help="指定剧集聚合键")
    p_pack.add_argument("--version", type=int, default=1, help="合集版本号 (默认1)")

    p_publish = subparsers.add_parser("publish", help="手动发布或重试发布合集")
    p_publish.add_argument("--season-key", type=str, required=True, help="指定剧集聚合键")

    p_clean = subparsers.add_parser("clean", help="出种后清理回收空间")
    p_clean.add_argument("--season-key", type=str, required=True, help="指定剧集聚合键")

    p_daemon = subparsers.add_parser("daemon", help="启动常驻自动化守护进程")

    args = parser.parse_args()
    if not args.subcmd:
        parser.print_help()
        return

    cmds = {
        "scan": cmd_scan,
        "status": cmd_status,
        "verify": cmd_verify,
        "pull": cmd_pull,
        "pack": cmd_pack,
        "publish": cmd_publish,
        "clean": cmd_clean,
        "daemon": cmd_daemon
    }
    cmds[args.subcmd](args)


if __name__ == "__main__":
    main()
