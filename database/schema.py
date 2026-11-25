# -*- coding: utf-8 -*-
"""DStudio合集制种 —— SQLite WAL 数据库架构与管理模块

遵循 AGENTS.md 规范：
- 严格开启 PRAGMA journal_mode = WAL
- 维护剧季(series_season)、分集(episodes)、发布归档(pack_releases)、RSS去重(rss_seen)
"""

import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from config import DB_PATH


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    target = db_path or DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: Optional[Path] = None):
    """初始化数据库表结构与索引"""
    with get_connection(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS series_season (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_key TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            clean_title TEXT,
            cn_title TEXT,
            year INTEGER,
            season INTEGER NOT NULL DEFAULT 1,
            resolution TEXT,
            source TEXT,
            video_codec TEXT,
            audio_codec TEXT,
            release_group TEXT,
            tmdb_id INTEGER,
            douban_id TEXT,
            total_episodes INTEGER DEFAULT 0,
            air_status TEXT,
            last_air_date TEXT,
            status TEXT NOT NULL DEFAULT 'COLLECTING',
            total_size_bytes INTEGER DEFAULT 0,
            pack_torrent_path TEXT,
            pack_info_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_season_status ON series_season(status);
        CREATE INDEX IF NOT EXISTS idx_season_title_season ON series_season(clean_title, season);

        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_key TEXT NOT NULL,
            episode_num INTEGER NOT NULL,
            raw_title TEXT NOT NULL,
            torrent_id INTEGER NOT NULL,
            download_url TEXT,
            info_hash TEXT,
            size_bytes INTEGER DEFAULT 0,
            local_filename TEXT,
            local_path TEXT,
            download_status TEXT NOT NULL DEFAULT 'PENDING',
            is_superseded INTEGER NOT NULL DEFAULT 0,
            superseded_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(season_key) REFERENCES series_season(season_key) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_episodes_season ON episodes(season_key, episode_num);
        CREATE INDEX IF NOT EXISTS idx_episodes_tid ON episodes(torrent_id);
        CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(download_status);

        CREATE TABLE IF NOT EXISTS pack_releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_key TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            target_torrent_id INTEGER,
            pack_info_hash TEXT,
            release_title TEXT NOT NULL,
            subtitle TEXT,
            bbcode_body TEXT,
            mediainfo_summary TEXT,
            cover_url TEXT,
            published_at TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'DRAFT',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(season_key) REFERENCES series_season(season_key) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_releases_season_ver ON pack_releases(season_key, version);
        CREATE INDEX IF NOT EXISTS idx_releases_target_tid ON pack_releases(target_torrent_id);

        CREATE TABLE IF NOT EXISTS rss_seen (
            torrent_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            published_date TEXT,
            is_our_pack INTEGER NOT NULL DEFAULT 0,
            seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()


class DatabaseManager:
    """数据库便捷访问封装"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        init_db(self.db_path)

    def get_connection(self):
        return get_connection(self.db_path)

    def is_rss_seen(self, torrent_id: int) -> bool:
        with get_connection(self.db_path) as conn:
            cur = conn.execute("SELECT 1 FROM rss_seen WHERE torrent_id = ?", (torrent_id,))
            return cur.fetchone() is not None

    def mark_rss_seen(self, torrent_id: int, title: str, published_date: str = "", is_our_pack: bool = False):
        with get_connection(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO rss_seen (torrent_id, title, published_date, is_our_pack) VALUES (?, ?, ?, ?)",
                (torrent_id, title, published_date, 1 if is_our_pack else 0)
            )
            conn.commit()

    def get_or_create_season(
        self,
        season_key: str,
        title: str,
        clean_title: str,
        season: int,
        year: Optional[int] = None,
        cn_title: str = "",
        resolution: str = "",
        source: str = "",
        video_codec: str = "",
        audio_codec: str = "",
        release_group: str = ""
    ) -> sqlite3.Row:
        with get_connection(self.db_path) as conn:
            cur = conn.execute("SELECT * FROM series_season WHERE season_key = ?", (season_key,))
            row = cur.fetchone()
            if row:
                return row

            conn.execute("""
            INSERT INTO series_season (
                season_key, title, clean_title, cn_title, year, season,
                resolution, source, video_codec, audio_codec, release_group
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                season_key, title, clean_title, cn_title, year, season,
                resolution, source, video_codec, audio_codec, release_group
            ))
            conn.commit()
            cur = conn.execute("SELECT * FROM series_season WHERE season_key = ?", (season_key,))
            return cur.fetchone()

    def add_or_update_episode(
        self,
        season_key: str,
        episode_num: int,
        raw_title: str,
        torrent_id: int,
        download_url: str = "",
        info_hash: str = "",
        size_bytes: int = 0
    ) -> int:
        with get_connection(self.db_path) as conn:
            # 查该季该集是否已有未废弃记录
            cur = conn.execute("""
            SELECT id, raw_title FROM episodes 
            WHERE season_key = ? AND episode_num = ? AND is_superseded = 0
            """, (season_key, episode_num))
            existing = cur.fetchone()

            is_proper = any(k in raw_title.upper() for k in ["PROPER", "REPACK", "RERIP"])
            if existing:
                exist_id = existing["id"]
                if is_proper and not any(k in existing["raw_title"].upper() for k in ["PROPER", "REPACK", "RERIP"]):
                    # 标记旧版已被废弃，插入新版 PROPER/REPACK
                    conn.execute("UPDATE episodes SET is_superseded = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (exist_id,))
                    cur = conn.execute("""
                    INSERT INTO episodes (
                        season_key, episode_num, raw_title, torrent_id, download_url, info_hash, size_bytes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (season_key, episode_num, raw_title, torrent_id, download_url, info_hash, size_bytes))
                    new_id = cur.lastrowid
                    conn.execute("UPDATE episodes SET superseded_by = ? WHERE id = ?", (new_id, exist_id))
                    conn.commit()
                    return new_id
                else:
                    # 保持既有记录
                    return exist_id

            cur = conn.execute("""
            INSERT INTO episodes (
                season_key, episode_num, raw_title, torrent_id, download_url, info_hash, size_bytes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (season_key, episode_num, raw_title, torrent_id, download_url, info_hash, size_bytes))
            conn.commit()
            return cur.lastrowid

    def get_season_episodes(self, season_key: str, active_only: bool = True) -> List[sqlite3.Row]:
        with get_connection(self.db_path) as conn:
            query = "SELECT * FROM episodes WHERE season_key = ?"
            if active_only:
                query += " AND is_superseded = 0"
            query += " ORDER BY episode_num ASC"
            return conn.execute(query, (season_key,)).fetchall()

    def update_season_status(self, season_key: str, status: str, **kwargs):
        with get_connection(self.db_path) as conn:
            fields = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
            params = [status]
            for k, v in kwargs.items():
                fields.append(f"{k} = ?")
                params.append(v)
            params.append(season_key)
            conn.execute(f"UPDATE series_season SET {', '.join(fields)} WHERE season_key = ?", params)
            conn.commit()

    def update_season_metadata(
        self,
        season_key: str,
        tmdb_id: int,
        total_episodes: int,
        air_status: str,
        last_air_date: str = ""
    ):
        with get_connection(self.db_path) as conn:
            conn.execute("""
            UPDATE series_season SET
                tmdb_id = ?,
                total_episodes = ?,
                air_status = ?,
                last_air_date = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE season_key = ?
            """, (tmdb_id, total_episodes, air_status, last_air_date, season_key))
            conn.commit()

    def get_seasons_by_status(self, status: str) -> List[sqlite3.Row]:
        with get_connection(self.db_path) as conn:
            return conn.execute("SELECT * FROM series_season WHERE status = ? ORDER BY id ASC", (status,)).fetchall()
