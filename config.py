# -*- coding: utf-8 -*-
"""DStudio合集制种 —— 全局配置模块

遵循 AGENTS.md 规范：
- 凭据不硬编码，动态读取或从 CookieCloud 提取
- 支持 Windows SMB 与 Linux NAS 本地双路径自动适配
"""

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 确保 LAN IP 绕过环境代理 (防止 mihomo 502)
_no_proxy = os.environ.get("no_proxy", "")
if "192.168.0.7" not in _no_proxy:
    os.environ["no_proxy"] = f"{_no_proxy},192.168.0.7,localhost,127.0.0.1".strip(",")
os.environ["NO_PROXY"] = os.environ["no_proxy"]

# SQLite 数据库
DB_PATH = DATA_DIR / "dstudio.db"

# DS 站点配置
SITE_NAME = "Depth Studio"
SITE_DOMAIN = "dstudio.me"
SITE_BASE_URL = "https://dstudio.me"
SITE_TORRENTS_URL = f"{SITE_BASE_URL}/torrents.php"
SITE_RSS_URL = f"{SITE_BASE_URL}/torrentrss.php"

# 分类定义 (NexusPHP)
CAT_TV_SERIES = 402  # 电视剧-TV Series

# 专用 qBittorrent (qbit-dstudio-publish: 3018)
# 容器内 (qbnet 网络) 默认直连容器名 qbit-dstudio-publish，外部开发使用 LAN IP
_default_qb_host = "qbit-dstudio-publish" if os.path.exists("/.dockerenv") else "192.168.0.7"
QB_HOST = os.getenv("QB_HOST", _default_qb_host)
QB_PORT = int(os.getenv("QB_PORT", "3018"))
QB_BASE_URL = f"http://{QB_HOST}:{QB_PORT}"
QB_USERNAME = os.getenv("QB_USER", "admin")
QB_PASSWORD = os.getenv("QB_PASS", "")

# 存储路径适配
# 容器内路径
CONTAINER_DOWNLOADS_ROOT = "/downloads"
CONTAINER_EPISODES_DIR = f"{CONTAINER_DOWNLOADS_ROOT}/episodes"
CONTAINER_PACKS_DIR = f"{CONTAINER_DOWNLOADS_ROOT}/packs"
CONTAINER_INCOMPLETE_DIR = f"{CONTAINER_DOWNLOADS_ROOT}/incomplete"

# 物理路径（自动判断当前运行在 Windows 本地还是 NAS 容器内）
if os.name == "nt":
    HOST_DOWNLOADS_ROOT = Path(r"\\iSunker-DS423\qb_temp\DSstudio_publish")
else:
    HOST_DOWNLOADS_ROOT = Path("/volume2/qb_temp/DSstudio_publish")

HOST_EPISODES_DIR = HOST_DOWNLOADS_ROOT / "episodes"
HOST_PACKS_DIR = HOST_DOWNLOADS_ROOT / "packs"
HOST_INCOMPLETE_DIR = HOST_DOWNLOADS_ROOT / "incomplete"

# 确保物理目录存在
if HOST_DOWNLOADS_ROOT.exists():
    HOST_EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    HOST_PACKS_DIR.mkdir(parents=True, exist_ok=True)
    HOST_INCOMPLETE_DIR.mkdir(parents=True, exist_ok=True)

# 水位监控与安全配额 (GB)
SSD_MIN_FREE_GB = 100.0        # 剩余小于 100GB 触发红色熔断
SEASON_MAX_SIZE_GB = 120.0     # 单部剧一季总大小超过此阈值需人工确认
MAX_CONCURRENT_PULLS = 1       # 全季分集同时拉取并发上限（严格防挤爆 SSD）

# 轮询与频控
RSS_POLL_INTERVAL_SEC = 240    # RSS 轮询间隔 ≥ 4 分钟 (240s)
HTTP_REQUEST_DELAY_SEC = 2.0   # 站点页面抓取间隔 ≥ 2 秒

# TMDB 配置
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_API_BASE = "https://api.themoviedb.org/3"

# CookieCloud 凭据候选目录
COOKIECLOUD_DATA_DIRS = [
    r"\\iSunker-DS423\docker_ssd\cookiecloud\data",
    "/volume2/docker_ssd/cookiecloud/data",
    "/data/cookiecloud",
    os.getenv("COOKIECLOUD_DATA_DIR", "")
]
