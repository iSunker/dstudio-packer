# -*- coding: utf-8 -*-
"""DStudio合集制种 —— 3018 专用 qBittorrent 客户端控制模块

遵循 AGENTS.md 规范：
- 自包含实现，不依赖外部 musichub 目录
- 专用于 3018 客户端 (qbit-dstudio-publish)
- 兼容 qB v4.x / v5.x API，支持 paused, stopped, skip_checking 等参数
- 支持出种达标判定 (seeders > 3 或 ratio >= 1.05) 与安全删种
"""

import urllib.request
import urllib.parse
import json
import logging
from typing import Dict, List, Optional, Any

from config import QB_HOST, QB_PORT, QB_USERNAME, QB_PASSWORD, CONTAINER_EPISODES_DIR

logger = logging.getLogger("dstudio.qb")


class QBitDStudioClient:
    """3018 专属控制器"""

    def __init__(self, host: str = QB_HOST, port: int = QB_PORT, username: str = QB_USERNAME, password: str = QB_PASSWORD):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}/api/v2"
        self.username = username
        self.password = password
        # 内网 LAN 请求显式绕过代理 (ProxyHandler({}))，避免走代理产生 502
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor()
        )

    def login(self) -> bool:
        """登录 qB WebUI"""
        login_url = f"{self.base_url}/auth/login"
        data = urllib.parse.urlencode({
            "username": self.username,
            "password": self.password,
        }).encode("utf-8")

        req = urllib.request.Request(login_url, data=data)
        try:
            with self.opener.open(req, timeout=10) as resp:
                text = resp.read().decode("utf-8").strip()
                return text == "Ok."
        except Exception as e:
            logger.error(f"qB login failed on {self.base_url}: {e}")
            return False

    def get_torrents(
        self,
        filter_status: Optional[str] = None,
        tag: Optional[str] = None,
        hashes: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """获取种子列表"""
        url = f"{self.base_url}/torrents/info"
        params = {}
        if filter_status:
            params["filter"] = filter_status
        if tag:
            params["tag"] = tag
        if hashes:
            params["hashes"] = hashes
        if params:
            url += "?" + urllib.parse.urlencode(params)

        req = urllib.request.Request(url)
        try:
            with self.opener.open(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"Failed to fetch torrents from {self.base_url}: {e}")
            return []

    def add_torrent_bytes(
        self,
        torrent_bytes: bytes,
        filename: str = "upload.torrent",
        save_path: str = "/downloads",
        is_paused: bool = True,
        is_skip_checking: bool = False,
        tags: Optional[str] = None,
        auto_resume: bool = False,
    ) -> bool:
        """向 3018 添加种子任务"""
        paused = not auto_resume if auto_resume else is_paused
        url = f"{self.base_url}/torrents/add"
        boundary = "----WebKitFormBoundaryDStudioPacker202611"

        body = []
        def add_field(name: str, val: str):
            body.append(f"--{boundary}\r\n".encode("utf-8"))
            body.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
            body.append(f"{val}\r\n".encode("utf-8"))

        add_field("savepath", save_path)
        add_field("paused", "true" if paused else "false")
        add_field("stopped", "true" if paused else "false")
        add_field("skip_checking", "true" if is_skip_checking else "false")
        add_field("autoTMM", "false")
        if tags:
            add_field("tags", tags)

        body.append(f"--{boundary}\r\n".encode("utf-8"))
        body.append(f'Content-Disposition: form-data; name="torrents"; filename="{filename}"\r\n'.encode("utf-8"))
        body.append(b"Content-Type: application/x-bittorrent\r\n\r\n")
        body.append(torrent_bytes)
        body.append(b"\r\n")
        body.append(f"--{boundary}--\r\n".encode("utf-8"))

        data = b"".join(body)
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(data)),
            },
        )
        try:
            with self.opener.open(req, timeout=15) as resp:
                # 兼容 200 与 202 异步加种
                return resp.getcode() in (200, 202)
        except Exception as e:
            logger.error(f"Failed to add torrent on {self.base_url}: {e}")
            return False

    def resume_torrent(self, hashes: str) -> bool:
        """唤醒做种/下载任务"""
        for endpoint in ["start", "resume"]:
            url = f"{self.base_url}/torrents/{endpoint}"
            data = urllib.parse.urlencode({"hashes": hashes}).encode("utf-8")
            req = urllib.request.Request(url, data=data)
            try:
                with self.opener.open(req, timeout=10) as resp:
                    if resp.getcode() == 200:
                        return True
            except Exception:
                continue
        logger.error(f"Failed to resume/start torrent {hashes} on 3018")
        return False

    def stop_torrent(self, hashes: str) -> bool:
        """暂停任务"""
        for endpoint in ["stop", "pause"]:
            url = f"{self.base_url}/torrents/{endpoint}"
            data = urllib.parse.urlencode({"hashes": hashes}).encode("utf-8")
            req = urllib.request.Request(url, data=data)
            try:
                with self.opener.open(req, timeout=10) as resp:
                    if resp.getcode() == 200:
                        return True
            except Exception:
                continue
        return False

    def delete_torrents(self, hashes: List[str], delete_files: bool = False) -> bool:
        """删除任务并按需删除实体文件"""
        if not hashes:
            return True
        url = f"{self.base_url}/torrents/delete"
        data = urllib.parse.urlencode({
            "hashes": "|".join(hashes),
            "deleteFiles": "true" if delete_files else "false"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        try:
            with self.opener.open(req, timeout=10) as resp:
                return resp.getcode() == 200
        except Exception as e:
            logger.error(f"Failed to delete torrents {hashes}: {e}")
            return False

    def resume_all_season_episodes(self, season_key: str) -> int:
        """唤醒指定剧季在 3018 上的所有分集任务开始下载"""
        torrents = self.get_torrents()
        matched_hashes = []
        for t in torrents:
            if season_key in t.get("save_path", "") or season_key in t.get("name", ""):
                matched_hashes.append(t["hash"])

        if matched_hashes:
            hashes_str = "|".join(matched_hashes)
            self.resume_torrent(hashes_str)
            logger.info(f"Resumed {len(matched_hashes)} episode torrents for {season_key}")
            return len(matched_hashes)
        return 0

    def get_season_progress(self, season_key: str) -> Dict[str, Any]:
        """获取指定剧季在 3018 上的整体下载进度"""
        torrents = self.get_torrents()
        matched = [t for t in torrents if season_key in t.get("save_path", "") or season_key in t.get("name", "")]
        if not matched:
            return {"total": 0, "completed": 0, "progress": 0.0, "is_all_completed": False, "speed": 0}

        completed = sum(1 for t in matched if t.get("progress", 0) >= 1.0)
        total_speed = sum(t.get("dlspeed", 0) for t in matched)
        avg_progress = sum(t.get("progress", 0) for t in matched) / len(matched)

        return {
            "total": len(matched),
            "completed": completed,
            "progress": avg_progress,
            "is_all_completed": (completed == len(matched) and len(matched) > 0),
            "speed": total_speed
        }

    def check_pack_seeded_qualified(self, info_hash: str, min_seeders: int = 3, min_ratio: float = 1.05) -> bool:
        """检查已发布的合集种子是否达成出种达标指标 (做种人数 > 3 或分享率 >= 1.05)"""
        torrents = self.get_torrents(hashes=info_hash)
        if not torrents:
            return False
        t = torrents[0]
        seeders = t.get("num_complete", 0) or t.get("num_seeds", 0)
        ratio = t.get("ratio", 0.0)
        logger.info(f"[出种检测] info_hash={info_hash[:8]} | seeders={seeders}/{min_seeders} | ratio={ratio:.3f}/{min_ratio}")
        return seeders > min_seeders or ratio >= min_ratio
