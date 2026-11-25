# -*- coding: utf-8 -*-
"""一键拉取《再婚皇后》S01 DV 全10集至 3018 下载器"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, r"d:\Projects\PT-Project\DStudio合集制种")
from database.schema import DatabaseManager
from pt_site.client import DStudioClient
from downloader.qb_client import QBitDStudioClient
from config import CONTAINER_EPISODES_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dstudio.pull_remarried")

# 10 个 DV 分集的精确 TID 与文件名
DV_EPISODES = [
    (1, 5257, "The Remarried Empress 2026 S01E01 2160p DSNP WEB-DL DDP5.1 DV H.265-DepWeb", 6034417254),
    (2, 5259, "The Remarried Empress 2026 S01E02 2160p DSNP WEB-DL DDP5.1 DV H.265-DepWeb", 7118939750),
    (3, 5261, "The Remarried Empress 2026 S01E03 2160p DSNP WEB-DL DDP5.1 DV H.265-DepWeb", 6571299962),
    (4, 5263, "The Remarried Empress 2026 S01E04 2160p DSNP WEB-DL DDP5.1 DV H.265-DepWeb", 6335076761),
    (5, 5533, "The Remarried Empress 2026 S01E05 2160p DSNP WEB-DL DDP5.1 DV H.265-DepWeb", 6260024524),
    (6, 5535, "The Remarried Empress 2026 S01E06 2160p DSNP WEB-DL DDP5.1 DV H.265-DepWeb", 5465345228),
    (7, 5802, "The Remarried Empress 2026 S01E07 2160p DSNP WEB-DL DDP5.1 DV H.265-DepWeb", 5991471513),
    (8, 5804, "The Remarried Empress 2026 S01E08 2160p DSNP WEB-DL DDP5.1 DV H.265-DepWeb", 6743124869),
    (9, 6019, "The Remarried Empress 2026 S01E09 2160p DSNP WEB-DL DDP5.1 DV H.265-DepWeb", 6141870694),
    (10, 6022, "The Remarried Empress 2026 S01E10 2160p DSNP WEB-DL DDP5.1 DV H.265-DepWeb", 6979321856),
]

SEASON_KEY = "The.Remarried.Empress.S01.2160p.DSNP.WEB-DL.DDP5.1.DV.H.265-DepWeb"

db = DatabaseManager()
client = DStudioClient()
qb = QBitDStudioClient()

# 1. 确保 series_season 在数据库中
db.get_or_create_season(
    season_key=SEASON_KEY,
    title="The Remarried Empress 2026 S01 2160p DSNP WEB-DL DDP5.1 DV H.265-DepWeb",
    clean_title="The Remarried Empress",
    season=1,
    year=2026,
    cn_title="再婚皇后",
    resolution="2160p",
    source="WEB-DL",
    video_codec="H.265",
    audio_codec="DDP5.1",
    release_group="DepWeb"
)
db.update_season_status(SEASON_KEY, "READY", total_episodes=10)

# 2. 写入分集数据
for ep_num, tid, title, size in DV_EPISODES:
    db.add_or_update_episode(
        season_key=SEASON_KEY,
        episode_num=ep_num,
        raw_title=title,
        torrent_id=tid,
        download_url=f"download.php?id={tid}",
        size_bytes=size
    )

print(f"已同步《再婚皇后》S01 DV 全 10 集元数据至数据库。")

# 3. 逐一下载 .torrent 种子文件并推入 3018
save_path = f"{CONTAINER_EPISODES_DIR}/{SEASON_KEY}"
print(f"目标下载路径: {save_path}")

success_count = 0
for ep_num, tid, title, size in DV_EPISODES:
    try:
        torrent_bytes = client.download_torrent(tid)
        ok = qb.add_torrent_bytes(
            torrent_bytes=torrent_bytes,
            filename=f"{tid}.torrent",
            save_path=save_path,
            tags="dstudio-pack",
            auto_resume=True
        )
        if ok:
            success_count += 1
            print(f"  [E{ep_num:02d} | TID={tid}] 种子成功添加至 3018")
        else:
            print(f"  [E{ep_num:02d} | TID={tid}] 添加失败: {ok}")
    except Exception as e:
        print(f"  [E{ep_num:02d} | TID={tid}] 异常: {e}")

print(f"\n全部推送完成！共成功添加 {success_count} / {len(DV_EPISODES)} 个分集到 3018。")
db.update_season_status(SEASON_KEY, "DOWNLOADING")
