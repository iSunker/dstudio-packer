# DStudio 合集制种 —— AI Agent 与开发者总规约 (AGENTS.md)

> **文档定位**：本文件是 `D:\Projects\PT-Project\DStudio合集制种` 子项目的智能体与开发者规约，遵循根目录 [`AGENTS.md`](../AGENTS.md) 规范。
> **生产部署形态**：NAS 常驻容器 `dstudio-packer`（工作目录 `/volume2/docker_ssd/dstudio-packer`，数据持久化位于 `./data/`，代码动态挂载于 `./src/`）。

---

## 0. 项目定位与核心职责

`DStudio合集制种` 是面向 **Depth Studio**（`https://dstudio.me`，**NexusPHP** 架构）的电视剧分集自动追踪、全季完结校验、零拷贝合集打包、自动发布与生命周期自闭环调度引擎：

1. **分集采集（自建 RSS/列表监听）**：独立轮询 DS 站点电视剧列表（严格 ≥ 4 分钟间隔），按六元组规格键 `(剧名, 季号, 分辨率, 视频编码, 媒介, 制作组)` 归集分集元数据，严禁跨规格混装。
2. **空间背压与并发治理**：
   - 实时监控 SSD 可用空间（`< 100 GB` 触发红色熔断，禁止新增分集下载）；
   - **下载阶段并行**：在存储水位充裕前提下允许多部剧并行拉取分集；
   - **制发种串行单锁**：全局单任务排队，集中 I/O 算力全力主攻单部合集出种闭环。
3. **双源完结状态机**：以 **TMDB API v3** 播映时间线为主、**官方副标题特征**为辅，交叉确认全季集数连续且全季完结播映。
4. **同卷零拷贝硬链接组包**：通过原生 Python `os.link` 进行同卷物理硬链接，耗时 < 0.01 秒，占用 0 额外磁盘空间；制种前强制过滤 `.!qB`、`@eaDir`、`.part` 等垃圾文件。
5. **NexusPHP 发种与双模式平滑降级**：
   - 遵循合集发种铁律：主标题去单集 `E` 标识、副标题标明全集、标签剔除“分集”并勾选“完结”；
   - 若站点权限未开放（如无发布权限），自动降级为保存草稿并投递告警，保留 CLI 一键重发接口。
6. **出种即删 (Auto-Clean)**：合集做种达成 `seeders > 3` 或 `ratio >= 1.05` 后自动从 3018 客户端移除并删除物理文件，彻底释放 SSD 空间。
7. **PT 集群通知联动**：生命周期事件原子落盘至 `/volume2/docker_ssd/pt-notice/data/spool/dstudio`，自动汇入每日集群邮件日报。

---

## 1. 基础设施与存储拓扑

- **专用 qBittorrent 实例**：
  - 容器名：`qbit-dstudio-publish`
  - WebUI 端口：`3018`，BT 端口：`37830`
  - 网络：`qbnet` 桥接网络，容器间直连主机名 `qbit-dstudio-publish:3018`
  - 隔离策略：不纳入 `qbit_manage` 与 `iyuu` 托管，与 `publish`（3010）、`vertex`（3005）彻底隔离；出种后直接清理，不分发至其他长期保种池。
  - **限速铁律**：全局上行限速锁定为 **6 MB/s**，单种连接数上限为 3，内存配额 1GB，缓存 128MB。
- **工作存储目录**：
  - 宿主机数据根：`/volume2/qb_temp/DSstudio_publish`（全 SSD 运行）-> 容器内 `/downloads`。
  - 目录分层：
    - `/downloads/episodes/<season_key>/`：分集下载目录
    - `/downloads/packs/<season_key>.v<N>/`：合集硬链接组包目录
    - `/downloads/incomplete/`：未完成下载临时目录
- **外部依赖与凭据**：
  - **CookieCloud**：动态解密获取 `dstudio.me` Cookie，直连访问免代理；`config.py` 内置 `no_proxy` 自动规避本地回环 502。
  - **TMDB API v3**：支持环境变量 `TMDB_API_KEY` 注入。

---

## 2. 核心运行铁律

1. **SSD 水位红色熔断线**：
   - 当 `/volume2` 剩余可用空间 `< 100 GB` 时，**严禁新增新剧分集下载**，仅记录元数据并发送告警。
2. **RSS 轮询与站点风控**：
   - RSS / 列表轮询周期**必须 ≥ 4 分钟**；页面抓取间隔 **≥ 2 秒**，严禁高频并发扫站。
3. **同规格聚合与 Pre-pack QA 红线**：
   - 聚合键必须包含 `(剧名/TMDB_ID, 季号, 分辨率, 视频编码, 片源, 制作组)`，严禁跨规格混装。
   - 制种前必须校验全季无 `.!qB` 临时文件、无 `@eaDir`/`.DS_Store` 垃圾文件、全季集数连续无缺档且媒体规格一致。
4. **防自抓回环与延迟回加**：
   - 每次成功发布合集后，立即将合集 TID 写入本地 `publish_blocklist`（防 RSS 自抓回环）。
   - 发种提交后回加 3018 客户端保持 `skip_checking=True, paused=False` 秒做种。
5. **非破坏性清理与硬链接安全**：
   - 物理文件删除操作严格只针对本项目的 `episodes/<season_key>` 与 `packs/<season_key>.v*` 目录，绝对禁止删除系统目录或根目录。
6. **凭据与 Git 隔离**：
   - 严禁将 Cookie、Passkey、TMDB API Key 提交仓库；本地数据库 `data/dstudio.db` 与临时制种产物严格写入 `.gitignore`。

---

## 3. 数据模型契约（SQLite WAL）

持久化状态统一落盘于 `data/dstudio.db`（开启 `PRAGMA journal_mode=WAL;`）：

- `series_season`：剧季主表，维护聚合规格键、TMDB 总集数、完结状态与生命周期状态机（`COLLECTING -> READY -> DOWNLOADING -> DOWNLOADED -> PACKED / PACKED_PENDING_APPROVAL -> PUBLISHED -> ARCHIVED`）。
- `episodes`：分集明细表，记录集号、DS 原种 TID、`info_hash`、本地路径、下载状态及 `is_superseded`。
- `pack_releases`：合集发布归档表，记录版本号（`v1`/`v2`）、合集 TID、`info_hash`、发布标题与 MediaInfo。
- `rss_seen`：RSS 已扫描条目与自发合集防环账本。

---

## 4. 改动与验证闸门

每次修改代码或配置后，上线前必须完成：

```bash
# 1. 语法与导入自检
python -m py_compile <改动文件>

# 2. 状态与看板核对
python cli.py status

# 3. 生产端变更后核验容器与日志
ssh -p 36688 iSunker@192.168.0.7 'docker ps -a --filter name=dstudio-packer'
ssh -p 36688 iSunker@192.168.0.7 'docker logs --tail 30 dstudio-packer'
```
