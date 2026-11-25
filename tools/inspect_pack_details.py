# -*- coding: utf-8 -*-
import sys
from bs4 import BeautifulSoup

sys.path.insert(0, r"d:\Projects\PT-Project\DStudio合集制种")
from pt_site.client import DStudioClient

client = DStudioClient()
html = client.fetch_torrent_details(4656)
soup = BeautifulSoup(html, "html.parser")

h1 = soup.find("h1")
print("=== H1 标题 ===")
print(h1.text.strip() if h1 else "None")

print("\n=== 表单属性 (rowhead) ===")
for td in soup.find_all("td", class_="rowhead"):
    val_td = td.find_next_sibling("td")
    val_text = val_td.text.strip() if val_td else ""
    print(f"{td.text.strip()}: {val_text[:120]}")

desc = soup.find("div", id="kdescr")
if desc:
    print("\n=== 正文简介 (BBCode 渲染后) ===")
    print(desc.text[:1500])
    print("\n=== 正文包含的图片 (img) ===")
    for img in desc.find_all("img"):
        print("  IMG:", img.get("src"))
