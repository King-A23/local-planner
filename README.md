# Local Planner（工作名）

本地优先的个人计划软件。目标是同时覆盖：

- **每天**：制定当天要做什么
- **长期**：记录还没做完、需要持续推进的任务

## 仓库状态

| 阶段 | 状态 |
| --- | --- |
| 工作区 | 已建立 |
| 产品需求 | 已冻结（D1–D14） |
| 设计文档 | 已通过审查（0 open issues） |
| 实现 | 脚手架（无产品逻辑） |

已确认决策见 [docs/product/decisions.md](docs/product/decisions.md)。

## 文档

- [v1 需求冻结稿](docs/product/v1-requirements.md) ← 产品范围以这份为准
- [v1 技术设计](docs/design/v1-design.md) ← 实现以这份为准
- [已确认决策](docs/product/decisions.md)
- [产品文档索引](docs/product/README.md)

工作名 `local-planner` 可在需求稳定后改名。

## 开发预告

需要 Python 3.12+。

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m local_planner --help
```

当前 `python -m local_planner` 只打印帮助或「未实现」，不会起服务、不建表、不结转。

后续启动形态（**尚未实现**）：

```bash
python -m local_planner serve
# 只打开启动日志里的 http://127.0.0.1:8787
# 不要用 http://localhost:8787（macOS 可能走到 ::1，本进程不听 IPv6）
```

开发数据目录是仓库内 `.data/`（已 gitignore）。进程只绑定 `127.0.0.1`。日历日固定 `Asia/Shanghai`。
