# -*- coding: utf-8 -*-
import sys
import re
import urllib.parse
from bs4 import BeautifulSoup

sys.path.insert(0, r"d:\Projects\PT-Project\DStudio合集制种")
from pt_site.client import DStudioClient
from pt_site.rss import parse_size_bytes

client = DStudioClient()
html = client.request("torrents.php?cat=402&search=" + urllib.parse.quote("The Remarried Empress"))
soup = BeautifulSoup(html, "html.parser")

torrent_tables = soup.find_all("table", class_="torrentname")
print(f"找到 {len(torrent_tables)} 个相关种子结果:")

dv_episodes = {}
hdr_episodes = {}

for t_table in torrent_tables:
    link = t_table.find("a", href=re.compile(r"details\.php\?id=\d+"))
    if not link:
        continue
    tid = int(re.search(r"id=(\d+)", link.get("href")).group(1))
    title = link.get("title") or link.text.strip()
    
    # 提取体积与做种数
    tr = t_table.find_parent("tr")
    size_str = ""
    seeders = 0
    if tr:
        tds = tr.find_all("td")
        for td in tds:
            txt = td.text.strip()
            if re.search(r"^\d+(?:\.\d+)?\s*[KMGT]B$", txt, re.I):
                size_str = txt
            elif re.search(r"^\d+$", txt) and not seeders and td.find("a", href=re.compile(r"viewpeerlist")):
                seeders = int(txt)
                
    m_ep = re.search(r"S01E(\d+)", title, re.I)
    if not m_ep:
        continue
    ep_num = int(m_ep.group(1))
    
    item = {
        "tid": tid,
        "title": title,
        "size_str": size_str,
        "size_bytes": parse_size_bytes(size_str),
        "seeders": seeders
    }
    
    if "DV" in title.upper():
        dv_episodes[ep_num] = item
    elif "HDR" in title.upper():
        hdr_episodes[ep_num] = item

print("\n--- DV 版本分集 (Dolby Vision) ---")
total_dv_bytes = sum(x["size_bytes"] for x in dv_episodes.values())
for ep in sorted(dv_episodes.keys()):
    x = dv_episodes[ep]
    print(f"  E{ep:02d}: TID={x['tid']} | 体积={x['size_str']} | 做种={x['seeders']} | {x['title']}")
print(f"DV 版本集数: {len(dv_episodes)} / 10 | 总体积: {total_dv_bytes / (1024**3):.2f} GB")

print("\n--- HDR 版本分集 (HDR10) ---")
total_hdr_bytes = sum(x["size_bytes"] for x in hdr_episodes.values())
for ep in sorted(hdr_episodes.keys()):
    x = hdr_episodes[ep]
    print(f"  E{ep:02d}: TID={x['tid']} | 体积={x['size_str']} | 做种={x['seeders']} | {x['title']}")
print(f"HDR 版本集数: {len(hdr_episodes)} / 10 | 总体积: {total_hdr_bytes / (1024**3):.2f} GB")
