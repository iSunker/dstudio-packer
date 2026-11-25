# Depth Studio (dstudio.me) 站点发种与电视剧合集规范备忘录

> **归档时间**：2026-11-25  
> **实测基准源**：Depth Studio 官方电视剧合集 TID 4656（《兄妹》S01）及《再婚皇后》S01 官方分集。

---

## 一、 电视剧合集发种规则与表单字段对照

| 字段 / 属性 | 单集发布规范 | 合集发布规范 | 注意事项与陷阱 |
| :--- | :--- | :--- | :--- |
| **分类 (Type)** | 402 (电视剧-TV Series) | 402 (电视剧-TV Series) | NexusPHP 标准分类 |
| **主标题 (Title)** | `... S01E10 ...` | `... S01 ...` | **合集主标题严禁包含单集集号 E**，保留全季 S 标识 |
| **副标题 (Subtitle)** | `... 第1季 第10集 ...` | `... 第1季 全10集 [杜比视界完整合集] ...` | **绝对不可照抄第1集的副标题**（其写着“第1集”） |
| **标签 (Tags)** | `官方`, `分集`, `中字` | `官方`, `完结`, `中字` | **合集发布时必须勾除“分集”标签**，勾选“完结” |
| **来源 (Source)** | 官方 (WEB-DL / DSNP) | 官方 (WEB-DL / DSNP) | 保持与分集一致 |
| **媒介 (Medium)** | WEB-DL | WEB-DL | 保持一致 |
| **编码 (Codec)** | H.265/HEVC / H.264 | H.265/HEVC / H.264 | 必须全季严格统一 |
| **音频 (Audio)** | DDP5.1 / AAC2.0 | DDP5.1 / AAC2.0 | 抽样填入第 1 集规格 |
| **制作组 (Group)** | DepWeb / DStudio | DepWeb / DStudio | 致谢原制作组 |

---

## 二、 封面与详情页（BBCode）标准结构

Depth Studio 详情页具有统一的排版风格，由以下 7 个区块组成：

```bbcode
[quote]
本站提供的一切影视作品链接均搜集自互联网，仅供网络宽带测试、学习与交流使用，绝对禁止用于任何商业盈利目的。
本站不提供视频文件的存储与录制服务，我们仅作为链接的展示平台，对被传播文件的具体内容及版权归属不承担任何法律责任。
用户的下载行为及后续产生的任何后果将由使用者本人全权承担。请在下载或测试后24小时内彻底删除相关文件。
若您喜欢本作品，强烈建议您通过正规渠道购买和支持正版。如有资源侵犯了您的权益，请联系我们及时清理。
[/quote]

[quote=Depth Studio 合集制种声明]
本合集由 DStudio-Packer 汇集全季各分集制作完整做种。
零删减保留全部分集、多音轨与软字幕。
致谢原分集发布者与制作组：DepWeb。
[/quote]

[center]
[img]https://image.tmdb.org/t/p/w780/海报哈希.jpg[/img]
[/center]

❁ Title:　中文译名
❁ Original Title:　原名（外文名）
❁ Genres:　类型
❁ Languages:　语言
❁ First Air Date:　首播日期
❁ Number of Episodes:　总集数
❁ Number of Seasons:　季数
❁ Rating:　评分
❁ TMDB Link:　https://www.themoviedb.org/tv/xxxx/
❁ Cast:　演职员表
❁ Introduction:　剧情简介

[quote=MediaInfo 抽样媒体参数]
（抽样第 1 集的完整 4K HEVC 杜比视界 / HDR 格式参数）
[/quote]

[quote=全季文件清单 (Filelist)]
  • S01E01.mkv
  • S01E02.mkv
  ...
  • S01E10.mkv
[/quote]
```

---

## 三、 出种生命周期与回收标准

按用户确认的铁律执行：
1. **单任务串行**：全流程一次只处理一部电视剧合集，完成出种回收前不启动下一部。
2. **出种判定标准**：
   - 当任务做种人数 `seeders > 3`，或个人分享率 `ratio >= 1.05` 时，判定为“已成功出种”。
3. **出种即删 (Clean)**：
   - 达成判定后执行 `python cli.py clean --season-key "..."`，自动从 3018 删除任务并删除实体文件，释放 SSD 空间。
