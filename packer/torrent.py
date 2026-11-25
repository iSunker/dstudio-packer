# -*- coding: utf-8 -*-
"""DStudio合集制种 —— torf 种子制作模块

遵循 AGENTS.md 规范：
- 严格开启 private = True (私有种子标配)
- 自动根据总体积梯度适配最优 piece_size (8MB ~ 32MB)
- 生成标准 info_hash (v1 SHA-1) 并注入 Depth Studio 来源标识
"""

import os
import logging
from pathlib import Path
from typing import Tuple, Optional
import torf

logger = logging.getLogger("dstudio.torrent")


class TorrentMaker:
    """标准 PT 种子文件生成器"""

    @staticmethod
    def calculate_piece_size(total_bytes: int) -> int:
        """根据总体积计算分片大小 (2 的幂次)"""
        gb = total_bytes / (1024 ** 3)
        if gb <= 4:
            return 4 * 1024 * 1024       # 4 MB
        elif gb <= 16:
            return 8 * 1024 * 1024       # 8 MB
        elif gb <= 64:
            return 16 * 1024 * 1024      # 16 MB
        else:
            return 32 * 1024 * 1024      # 32 MB

    @classmethod
    def make_pack_torrent(
        cls,
        pack_dir: Path,
        output_torrent_path: Path,
        announce_url: str = "https://dstudio.me/announce.php",
        source: str = "Depth Studio",
        comment: str = "Created by DStudio-Packer"
    ) -> Tuple[Path, str, int]:
        """为合集目录创建 .torrent 文件并返回 (torrent_path, info_hash, total_size)"""
        if not pack_dir.exists():
            raise FileNotFoundError(f"Pack directory not found: {pack_dir}")

        output_torrent_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Hashing pack directory: {pack_dir} ...")
        t = torf.Torrent(path=str(pack_dir))
        total_size = t.size
        piece_size = cls.calculate_piece_size(total_size)
        t.piece_size = piece_size
        t.private = True
        t.source = source
        t.comment = comment
        if announce_url:
            t.trackers = [[announce_url]]

        # 执行分片哈希计算
        t.generate()
        t.write(str(output_torrent_path), overwrite=True)

        info_hash = str(t.infohash)
        logger.info(f"Torrent created successfully: {output_torrent_path} (info_hash={info_hash}, size={total_size}, piece_size={piece_size})")
        return output_torrent_path, info_hash, total_size
