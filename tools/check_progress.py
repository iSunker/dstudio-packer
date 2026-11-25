# -*- coding: utf-8 -*-
import urllib.request
import json
import time

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
resp = opener.open("http://192.168.0.7:3018/api/v2/torrents/info")
torrents = json.loads(resp.read().decode("utf-8"))

total_speed = 0
total_downloaded = 0
total_size = 0

print("="*105)
print(f"{'分集名称':<42} {'状态':<12} {'速度':<12} {'做种连接':<10} {'当前进度':<10} {'已下/总大小'}")
print("-" * 105)

for t in sorted(torrents, key=lambda x: x["name"]):
    name = t["name"][:40]
    state = t["state"]
    speed = t["dlspeed"] / (1024 * 1024)
    total_speed += speed
    seeds = f"{t['num_seeds']}/{t['num_complete']}"
    prog = f"{t['progress'] * 100:.2f}%"
    dl_mb = t["downloaded"] / (1024 * 1024)
    sz_mb = t["total_size"] / (1024 * 1024)
    total_downloaded += t["downloaded"]
    total_size += t["total_size"]
    print(f"{name:<42} {state:<12} {speed:>7.2f} MB/s {seeds:<10} {prog:<10} {dl_mb:.1f} / {sz_mb:.1f} MB")

print("="*105)
print(f"3018 全局下行总带宽: {total_speed:.2f} MB/s | 总进度: {total_downloaded/(1024**3):.2f} / {total_size/(1024**3):.2f} GB ({total_downloaded/total_size*100:.2f}%)")
