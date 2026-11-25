# -*- coding: utf-8 -*-
"""DStudio合集制种 —— Depth Studio 站点 HTTP 客户端模块

遵循 AGENTS.md 规范：
- CookieCloud 动态获取凭据，不落盘明文 Cookie
- 直连访问，严格频控 (页面请求间隔 >= 2.0s)
- 支持种子列表抓取、详情页解析与 .torrent 文件下载
"""

import time
import urllib.request
import urllib.parse
from typing import Dict, Optional, Tuple
from bs4 import BeautifulSoup
from config import SITE_BASE_URL, HTTP_REQUEST_DELAY_SEC

# 导入本地自内聚 CookieCloud 客户端
from metadata.cookiecloud import CookieCloudClient


class DStudioClient:
    """Depth Studio 站点适配客户端"""

    def __init__(self, domain: str = "dstudio.me"):
        self.domain = domain
        self.cookie_client = CookieCloudClient()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.last_request_time = 0.0

    def get_cookie_header(self) -> str:
        cookies = self.cookie_client.get_domain_cookies(self.domain)
        if not cookies:
            raise RuntimeError(f"No cookies found for domain {self.domain} in CookieCloud")
        return "; ".join([f"{k}={v}" for k, v in cookies.items()])

    def _throttle(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < HTTP_REQUEST_DELAY_SEC:
            time.sleep(HTTP_REQUEST_DELAY_SEC - elapsed)
        self.last_request_time = time.time()

    def request(self, path_or_url: str, data: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None) -> str:
        """执行 HTTP 请求并返回 HTML 字符串"""
        self._throttle()
        url = path_or_url if path_or_url.startswith("http") else f"{SITE_BASE_URL.rstrip('/')}/{path_or_url.lstrip('/')}"
        
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Cookie": self.get_cookie_header()
        }
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, data=data, headers=req_headers)
        with self.opener.open(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="ignore")

    def download_torrent(self, torrent_id: int) -> bytes:
        """从 download.php?id={tid} 下载种子文件原始字节"""
        self._throttle()
        url = f"{SITE_BASE_URL}/download.php?id={torrent_id}"
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Cookie": self.get_cookie_header()
        }
        req = urllib.request.Request(url, headers=req_headers)
        with self.opener.open(req, timeout=25) as resp:
            content = resp.read()
            if not content.startswith(b"d8:announce") and b"announce" not in content[:100]:
                raise ValueError(f"Downloaded content for TID {torrent_id} is not a valid torrent file (length={len(content)})")
            return content

    def fetch_tv_torrents_page(self, page: int = 0) -> str:
        """获取电视剧分类种子列表页"""
        url = f"torrents.php?cat=402&page={page}"
        return self.request(url)

    def fetch_torrent_details(self, torrent_id: int) -> str:
        """获取指定种子详情页 HTML"""
        url = f"details.php?id={torrent_id}"
        return self.request(url)
