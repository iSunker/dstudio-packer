# DStudio-Packer (Depth Studio 电视剧合集自动制种中枢)

面向 **Depth Studio**（`https://dstudio.me`，NexusPHP 架构）的高性能全自动电视剧分集追踪、完结核验、SSD 零拷贝硬链接合集制种与全生命周期自闭环调度引擎。

---

## 一、 核心特性与架构设计

1. **自建分集监听与聚合**：
   - 严格遵循 `≥ 4 分钟` 频控轮询电视剧分类，杜绝站点风控；
   - 采用六元组聚合键 `(剧名, 季号, 分辨率, 视频编码, 媒介, 制作组)` 严格分组，严禁跨规格混装。
2. **TMDB 双源完结状态机**：
   - 以 **TMDB API v3** 播映计划为主、**站点官方副标题特征**为辅，严格校验全季集数连续且已播映完结；
   - 自动防提前发种，只有集齐且全季播完才进入就绪状态。
3. **空间背压与并行/串行分层治理**：
   - 实时监控 SSD 可用空间（`< 100 GB` 触发红色熔断，自动挂起新剧拉取）；
   - **下载阶段并行**：在存储水位充裕前提下允许多部剧并行拉取分集；
   - **制发种串行单锁**：全局单任务排队，集中 I/O 算力全力主攻单部合集出种闭环。
4. **同卷零拷贝物理硬链接 (Zero-Copy Hardlinks)**：
   - 原生 Python `os.link` 递归建组，**全季组包耗时 < 0.01 秒，占用 0 字节额外磁盘空间**；
   - 内存级预检，自动剔除 `.!qB`, `@eaDir`, `.part`, `.DS_Store` 等临时杂质。
5. **智能抽样 MediaInfo 与标准 BBCode 排版**：
   - 自动提取代表集数的视频、音频（多音轨）、软字幕参数；
   - 渲染符合 Depth Studio 官方合集标准的 BBCode 详情页（含 7 大模块与全季 Filelist）。
6. **NexusPHP 标准发种与双模式平滑降级**：
   - 遵循合集发种铁律（主标题去单集 `E`、副标题全集、标签去“分集”加“完结”）；
   - 若站点权限未开放，系统自动保存草稿并降级挂起，待权限放行后无缝直发。
7. **出种即删 (Auto-Clean)**：
   - 监控 3018 专用客户端做种状态，达成 `seeders > 3` 或 `ratio >= 1.05` 后自动从客户端移除并删除物理文件，彻底释放 SSD 空间。
8. **PT 集群通知中枢集成**：
   - 将事件（存储熔断、制种完成、权限挂起、出种达标回收）原子投递至 `pt-notice` spool 目录，自动汇入每日集群邮件日报。

---

## 二、 服务拓扑与端口规范

| 基础设施 / 服务 | 容器 / 端口 / 挂载路径 | 职责说明 |
| :--- | :--- | :--- |
| **专用 qB 客户端** | `qbit-dstudio-publish` (`3018`, BT `37830`) | 与主保种池、3010 发种端物理隔离，专供单季下载与合集做种 |
| **制种守护容器** | `dstudio-packer` (Docker 常驻) | 24x7 常驻调度守护进程，自动运行全流程状态机 |
| **工作存储** | `/volume2/qb_temp/DSstudio_publish` -> `/downloads` | 全 SSD 运行，分集目录 `episodes/`，合集目录 `packs/` |
| **凭据中枢** | CookieCloud (`3050`) | 动态解密 `dstudio.me` 会话凭据，直连免代理 |
| **通知中枢** | `pt-notice` (`spool/dstudio/`) | 投递标准 spool 事件文本，汇总归集进每日 PT 日报 |

---

## 三、 快速上手与 CLI 常用操作

项目支持通过命令行（`cli.py`）进行单步调试或状态看板查询：

```bash
# 1. 扫描站点最新电视剧分集
python cli.py scan --pages 2

# 2. 查看全季追踪状态看板
python cli.py status

# 3. 运行 TMDB 完结状态机核验
python cli.py verify

# 4. 手动拉取某一已完结剧集的分集至 3018 开始下载
python cli.py pull --season-key "The.Remarried.Empress.S01.2160p.DSNP.WEB-DL.DDP5.1.DV.H.265-DepWeb"

# 5. 手动执行零拷贝硬链接、MediaInfo 体检与 torf 制种
python cli.py pack --season-key "The.Remarried.Empress.S01.2160p.DSNP.WEB-DL.DDP5.1.DV.H.265-DepWeb"

# 6. 手动向 Depth Studio 发布合集 (或重试挂起的合集)
python cli.py publish --season-key "The.Remarried.Empress.S01.2160p.DSNP.WEB-DL.DDP5.1.DV.H.265-DepWeb"

# 7. 出种达标后一键安全回收释放 SSD 空间
python cli.py clean --season-key "The.Remarried.Empress.S01.2160p.DSNP.WEB-DL.DDP5.1.DV.H.265-DepWeb"

# 8. 前台启动常驻自动化守护进程
python cli.py daemon
```

---

## 四、 NAS Docker 化部署

生产端部署于群晖 NAS（`/volume2/docker_ssd/dstudio-packer`）：

```yaml
name: dstudio-packer

services:
  dstudio-packer:
    image: isunker/dstudio-packer:latest
    container_name: dstudio-packer
    restart: unless-stopped
    environment:
      - TZ=Asia/Shanghai
      - PYTHONUNBUFFERED=1
      - QB_HOST=qbit-dstudio-publish
      - QB_PORT=3018
      - COOKIECLOUD_DATA_DIR=/data/cookiecloud
      - TMDB_API_KEY=${TMDB_API_KEY:-}
    volumes:
      - /volume2/docker_ssd/dstudio-packer/src:/app
      - /volume2/docker_ssd/dstudio-packer/data:/app/data
      - /volume2/qb_temp/DSstudio_publish:/downloads
      - /volume2/docker_ssd/cookiecloud/data:/data/cookiecloud:ro
      - /volume2/docker_ssd/pt-notice/data/spool/dstudio:/volume2/docker_ssd/pt-notice/data/spool/dstudio
    networks:
      - qbnet

networks:
  qbnet:
    external: true
```

启动与运维命令：
```bash
# 启动常驻容器
docker compose up -d

# 查看守护实时流水线日志
docker logs -f dstudio-packer
```

---

## 五、 开源与安全协议

- 本项目代码已经过脱敏处理，严禁将私有密钥、Cookie 明文、Passkey 提交至公开仓库。
- 仅供网络技术学习与 PT 社区交流使用。
