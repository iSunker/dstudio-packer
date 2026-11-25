# -*- coding: utf-8 -*-
"""DStudio合集制种 —— 同卷零拷贝硬链接组包模块

遵循 AGENTS.md 与 dev-god 规范：
- 采用原生 Python os.link 实现同卷零拷贝物理硬链接，耗时 < 1 秒，占用 0 额外磁盘空间
- 内存级预检过滤：严禁 .!qB, @eaDir, .part, .DS_Store, Thumbs.db 等垃圾文件
- 幂等性保障：若目标已存在且 inode 一致则跳过，防止重复创建
- 自动适配运行环境（NAS 容器内本地路径 vs Windows 远程/本地路径）
"""

import os
import shutil
import logging
from pathlib import Path
from typing import List, Set, Optional
from config import HOST_DOWNLOADS_ROOT, CONTAINER_DOWNLOADS_ROOT

logger = logging.getLogger("dstudio.hardlink")


class HardlinkPacker:
    """分集零拷贝硬链接组包引擎"""

    IGNORE_PATTERNS = {
        "@eadir", ".!qb", ".part", ".ds_store", "thumbs.db", ".tmp"
    }
    IGNORE_EXTS = {
        ".!qb", ".part", ".tmp"
    }

    def __init__(self, downloads_root: Optional[Path] = None):
        # 容器内默认为 /downloads，本机开发时为 HOST_DOWNLOADS_ROOT
        if downloads_root:
            self.root = downloads_root
        elif os.path.exists(CONTAINER_DOWNLOADS_ROOT):
            self.root = Path(CONTAINER_DOWNLOADS_ROOT)
        else:
            self.root = HOST_DOWNLOADS_ROOT

    def is_ignored(self, filename: str) -> bool:
        """判定文件是否属于应剔除的临时/系统杂质"""
        lower = filename.lower()
        if any(ign in lower for ign in self.IGNORE_PATTERNS):
            return True
        ext = Path(filename).suffix.lower()
        if ext in self.IGNORE_EXTS:
            return True
        return False

    def create_pack_hardlinks(self, season_key: str, version: int = 1) -> Path:
        """为已下载分集创建合集硬链接目录，返回合集绝对路径"""
        src_dir = self.root / "episodes" / season_key
        dst_dir = self.root / "packs" / f"{season_key}.v{version}"

        if not src_dir.exists():
            raise FileNotFoundError(f"Source episode directory not found: {src_dir}")

        dst_dir.mkdir(parents=True, exist_ok=True)
        linked_count = 0

        # 遍历源目录下的所有文件并建立硬链接
        for root_path, dirs, files in os.walk(src_dir):
            # 过滤垃圾子目录 (如 @eaDir)
            dirs[:] = [d for d in dirs if not self.is_ignored(d)]

            rel_root = Path(root_path).relative_to(src_dir)
            target_sub_dir = dst_dir / rel_root
            target_sub_dir.mkdir(parents=True, exist_ok=True)

            for f in files:
                if self.is_ignored(f):
                    logger.debug(f"Ignoring junk/temp file: {f}")
                    continue

                src_file = Path(root_path) / f
                dst_file = target_sub_dir / f

                if dst_file.exists():
                    # 检查是否已是相同 inode
                    try:
                        if src_file.stat().st_ino == dst_file.stat().st_ino:
                            linked_count += 1
                            continue
                        else:
                            dst_file.unlink()
                    except OSError:
                        pass

                try:
                    os.link(src_file, dst_file)
                    linked_count += 1
                except Exception as e:
                    logger.error(f"Failed to hardlink {src_file} -> {dst_file}: {e}")
                    raise RuntimeError(f"Hardlink failed (ensure same volume): {e}")

        logger.info(f"Successfully created hardlink pack with {linked_count} files at: {dst_dir}")
        return dst_dir

    def remove_pack_hardlinks(self, season_key: str, version: int = 1) -> bool:
        """安全移除合集硬链接目录 (不影响源分集文件)"""
        pack_dir = self.root / "packs" / f"{season_key}.v{version}"
        if pack_dir.exists():
            shutil.rmtree(pack_dir, ignore_errors=True)
            logger.info(f"Removed pack directory: {pack_dir}")
            return True
        return False
