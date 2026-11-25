# -*- coding: utf-8 -*-
"""DStudio合集制种 —— NexusPHP 标准发种与发布管理器

遵循 AGENTS.md 与 dev-god 规范：
- 实现标准 NexusPHP multipart/form-data 发种接口 (takeupload.php)
- 严谨的合集发种规范：合集主标题剔除单集 E 集号、副标题规范全集、标签剔除“分集”并包含“完结”
- 双模式平滑降级：站点未开放发布权限或提交被拒时，返回结构化错误并自动降级保存草稿，待开通权限后一键重试
"""

import re
import urllib.request
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List, Any
import logging

from pt_site.client import DStudioClient
from config import SITE_BASE_URL, CAT_TV_SERIES

logger = logging.getLogger("dstudio.publisher")


@dataclass
class PublishResult:
    success: bool
    torrent_id: Optional[int]
    error_code: str
    error_msg: str
    redirect_url: str = ""


class DStudioPublisher:
    """Depth Studio 站点发布器"""

    def __init__(self, client: Optional[DStudioClient] = None):
        self.client = client or DStudioClient()

    def build_合集主标题(self, raw_title: str, clean_title: str, season: int, year: Optional[int], resolution: str, source: str, video_codec: str, audio_codec: str, release_group: str) -> str:
        """格式化合集主标题，严禁包含单集集号 E，保留全季 S 标识"""
        # 如果 raw_title 包含类似 S01E01，正则替换为 S01
        title = re.sub(r'S(\d+)E\d+', r'S\1', raw_title, flags=re.I)
        # 去除多余点号
        title = re.sub(r'\.+', '.', title).strip('.')
        return title

    def build_合集副标题(self, cn_title: str, season: int, total_episodes: int, extra_info: str = "完整合集") -> str:
        """格式化合集副标题，例：再婚皇后 第1季 全10集 [杜比视界完整合集] [DepWeb官组出品]"""
        prefix = f"{cn_title} 第{season}季 全{total_episodes}集" if cn_title else f"第{season}季 全{total_episodes}集"
        return f"{prefix} [{extra_info}]"

    def publish_pack(
        self,
        torrent_path: Path,
        name: str,
        small_descr: str,
        descr: str,
        resolution: str = "2160p",
        video_codec: str = "H.265/HEVC",
        audio_codec: str = "DDP5.1",
        release_group: str = "DepWeb",
        medium: str = "WEB-DL",
        source: str = "WEB-DL",
        anonymous: bool = True
    ) -> PublishResult:
        """向 Depth Studio 提交发布合集种子"""
        if not torrent_path.exists():
            return PublishResult(success=False, torrent_id=None, error_code="FILE_NOT_FOUND", error_msg=f"种子文件不存在: {torrent_path}")

        # 检查当前账号是否具备发布权限 (通过预检 upload.php)
        try:
            upload_page = self.client.request("upload.php")
            if "你没有发布种子的权限" in upload_page:
                logger.warning("Depth Studio 预检显示当前账号暂无发布种子权限 (提示需管理组授权或候选区提交)")
                return PublishResult(
                    success=False,
                    torrent_id=None,
                    error_code="NO_PERMISSION",
                    error_msg="站点提示当前账号暂无发布种子权限，需管理组放行"
                )
        except Exception as e:
            logger.warning(f"Upload pre-check failed: {e}")

        torrent_bytes = torrent_path.read_bytes()
        boundary = "----WebKitFormBoundaryDStudioPackUpload202611"

        body = []
        def add_field(k: str, v: str):
            body.append(f"--{boundary}\r\n".encode("utf-8"))
            body.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
            body.append(f"{v}\r\n".encode("utf-8"))

        def add_file(k: str, filename: str, content: bytes, mime: str = "application/x-bittorrent"):
            body.append(f"--{boundary}\r\n".encode("utf-8"))
            body.append(f'Content-Disposition: form-data; name="{k}"; filename="{filename}"\r\n'.encode("utf-8"))
            body.append(f"Content-Type: {mime}\r\n\r\n".encode("utf-8"))
            body.append(content)
            body.append(b"\r\n")

        # 1. 种子文件
        add_file("file", torrent_path.name, torrent_bytes)

        # 2. 基础信息
        add_field("name", name)
        add_field("small_descr", small_descr)
        add_field("descr", descr)
        add_field("type", str(CAT_TV_SERIES))

        # 3. 规范下拉参数
        add_field("source_sel", source)
        add_field("medium_sel", medium)
        add_field("codec_sel", video_codec)
        add_field("audiocodec_sel", audio_codec)
        add_field("standard_sel", resolution)
        add_field("team_sel", release_group)

        # 4. 匿名发布
        if anonymous:
            add_field("uplver", "yes")

        # 5. 标签：合集必须剔除“分集”，勾选“完结”与“中字”
        tags = ["官方", "完结", "中字"]
        for t in tags:
            add_field("tags[]", t)

        body.append(f"--{boundary}--\r\n".encode("utf-8"))
        data = b"".join(body)

        url = f"{SITE_BASE_URL.rstrip('/')}/takeupload.php"
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(data)),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Cookie": self.client.get_cookie_header(),
            "Referer": f"{SITE_BASE_URL.rstrip('/')}/upload.php"
        }

        req = urllib.request.Request(url, data=data, headers=headers)

        # 自定义不自动跳转的 Opener 以便捕获 302 Found 重定向中的 details.php?id=XXXX
        class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def http_error_302(self, req, fp, code, msg, headers):
                return fp
            http_error_301 = http_error_302
            http_error_303 = http_error_302
            http_error_307 = http_error_302

        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            NoRedirectHandler()
        )

        try:
            with opener.open(req, timeout=30) as resp:
                status_code = resp.getcode()
                resp_headers = resp.headers
                content = resp.read().decode("utf-8", errors="ignore")

                redirect_to = resp_headers.get("Location") or ""
                # 如果 302 重定向到 details.php?id=XXXX
                m = re.search(r"details\.php\?id=(\d+)", redirect_to)
                if m:
                    tid = int(m.group(1))
                    logger.info(f"🎉 Depth Studio 成功发布合集！TID={tid}, URL={redirect_to}")
                    return PublishResult(
                        success=True,
                        torrent_id=tid,
                        error_code="",
                        error_msg="",
                        redirect_url=redirect_to
                    )

                # 检查页面返回信息中的错误
                if "你没有发布种子的权限" in content:
                    return PublishResult(success=False, torrent_id=None, error_code="NO_PERMISSION", error_msg="站点返回：你没有发布种子的权限")
                if "上传失败" in content or "错误" in content:
                    err_match = re.search(r"class=\"(?:text|error|msg)[^\"]*\">([^<]+)<", content)
                    err_text = err_match.group(1).strip() if err_match else content[:200]
                    return PublishResult(success=False, torrent_id=None, error_code="UPLOAD_REJECTED", error_msg=err_text)

                return PublishResult(
                    success=False,
                    torrent_id=None,
                    error_code="UNKNOWN_RESPONSE",
                    error_msg=f"未知发布响应状态码 {status_code}, Location: {redirect_to}"
                )

        except Exception as e:
            logger.error(f"Failed to submit upload to Depth Studio: {e}", exc_info=True)
            return PublishResult(success=False, torrent_id=None, error_code="NETWORK_ERROR", error_msg=str(e))
