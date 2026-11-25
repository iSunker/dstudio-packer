# -*- coding: utf-8 -*-
import sqlite3

conn = sqlite3.connect(r"d:\Projects\PT-Project\DStudio合集制种\data\dstudio.db")
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"数据表清单: {tables}")

for t in ["series_season", "episodes", "pack_releases", "rss_seen"]:
    if t in tables:
        count = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  • 表 `{t}`: 当前记录数 {count}")

remarried_eps = conn.execute("SELECT count(*) FROM episodes WHERE season_key LIKE '%Remarried%'").fetchone()[0]
print(f"《再婚皇后》已录入分集数: {remarried_eps} / 10")
