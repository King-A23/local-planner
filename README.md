# Local Planner

本机个人日计划。打开即是今天：正经待办与零碎差事两列清单，长期任务住在库存里。数据只在这台 Mac 上。

日历日固定 `Asia/Shanghai`（`YYYY-MM-DD`）。进程只绑定 `127.0.0.1`。

## 如何运行

### macOS 桌面应用

双击 `~/Applications/Local Planner.app` 打开独立桌面窗口。待办数据沿用原目录，退出窗口会自动停止桌面服务。已构建的应用包含 Python 与前端，日常使用无需终端。

从源码构建安装：

```bash
.venv/bin/python -m pip install -e '.[dev]' -r desktop/macos/requirements-build.txt
.venv/bin/python scripts/build_macos.py --install
```

需要 Xcode Command Line Tools、Python 3.12+ 和 Node.js。产物在 `dist/macos/`；已有同名应用时不会覆盖。[桌面版说明](docs/product/macos-desktop.md)包含更新方式、菜单快捷键、日志和分发限制。

### 网页与命令行

需要 Python 3.12+ 与 Node.js（构建前端）。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cd web && npm ci && npm run build && cd ..
local-todo
```

日常使用直接运行 `local-todo`：如果服务尚未启动，它会在后台启动服务，等待就绪后打开网页；如果已经启动，则直接打开，不会重复启动。`local-todo open` 与无参数形式等价。后台日志写入数据目录的 `server.log`。

需要让服务留在当前终端查看实时日志时，使用 `local-todo serve`；原有的 `python -m local_planner serve` 与 `local-planner` 命令继续兼容。

浏览器**只**打开启动日志里的地址：

```
http://127.0.0.1:8787
```

不要用 `http://localhost:8787`。macOS 上 `localhost` 常解析到 `::1`，本进程不听 IPv6，会连不上。

生产 `serve` 同时提供 JSON API 与 `web/dist` SPA。缺 `web/dist/index.html` 时拒绝启动，并提示 `run npm run build`。

换端口：`local-todo --port 9000`、`LOCAL_PLANNER_PORT`，或 `python -m local_planner serve --port 9000`。

默认数据文件：`~/Library/Application Support/local-planner/planner.sqlite`。覆盖目录：`LOCAL_PLANNER_DATA_DIR`（文件名仍是 `planner.sqlite`）。

开发：`LOCAL_PLANNER_DEV=1 python -m local_planner serve` 可无 dist（只开 API）；另开终端 `cd web && npm i && npm run dev`，Vite 把 `/api` 代理到 `8787`。`LOCAL_PLANNER_DEV=1` 时数据目录是仓库内 `.data/`（已 gitignore），并允许 Vite `5173` Origin。

## 备份

WAL 模式下不要只拷贝 `planner.sqlite`（会漏掉 `-wal`）。用 SQLite backup API：

```bash
python -m local_planner backup
# 默认写到 $DATA_DIR/backups/planner-YYYYMMDD-HHMMSS.sqlite

python -m local_planner backup ~/Desktop/planner-copy.sqlite
python -m local_planner backup /path/to/dir
```

进程运行时也可以备份。v1 不自动定时备份、不同步网盘。备份 = 复制这个 sqlite 文件。

## 重置

停进程，删除 `planner.sqlite`、`planner.sqlite-wal`、`planner.sqlite-shm`，再 `python -m local_planner serve`。得到空今天。

回滚一次坏迁移：停进程，把 `backups/pre-migrate-….sqlite` 拷回 `planner.sqlite`，删 `-wal`/`-shm`，用旧代码启动。

## GET /api/debug

仅本机 loopback 可读（进程绑 `127.0.0.1`）。响应含 `dbPath`，不要把 bind 改成 `0.0.0.0`。

```bash
curl http://127.0.0.1:8787/api/debug
```

字段：`today`、`timezone`（`Asia/Shanghai`）、`lastSettledDate`（水位）、`dbPath`、`schemaVersion`（`MAX(schema_migrations.version)`）、`integrityCheck`、`counts`。日界异常时先看日志里的 `settled …`，再看这个水位。

## 文档

- [v1 需求冻结稿](docs/product/v1-requirements.md) ← 产品范围以这份为准
- [v1 技术设计](docs/design/v1-design.md) ← 实现以这份为准
- [已确认决策](docs/product/decisions.md)
- [产品文档索引](docs/product/README.md)

壳上显示名是 **Local Planner**。v1 不做搜索、标签、同步、小时表。
