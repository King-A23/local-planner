# Agent 交互能力与使用说明同步

2026-09-28。用户要求设置中的说明同步最新交互，并让 Agent 接口明确支持新操作。此轮补齐 CLI、上下文、预设指令和回执；不增加云服务或自动排程。

## 用户入口

- 设置「使用说明」保留三步上手，其余按完成与改期、搜索与排序、事项类型、计划助手、备份、快捷键收起。
- 设置「计划助手」增加能力说明与自然语言示例；普通用户不需要接触 CLI 参数。
- 使用说明与快捷键分区复用同一份快捷键表，助手能力说明也复用，避免两处文字不一致。
- 助手输入框「＋」中的指令示例与设置共用内容，覆盖改期、备注和排序；选择示例只填入草稿，不自动发送。

## 能力发现与新命令

开发环境命令前缀为 `python -m local_planner`。桌面版会在每次调用助手时注入完整的内置可执行文件前缀及正确的数据目录；Agent 应使用该前缀，不另找项目或安装依赖。

`capabilities` 返回版本化的交互扩展清单、参数、长度限制和领域边界；同一清单包含在 `context.capabilities` 中。完整既有命令继续由根 `--help` 和各子命令 `--help` 提供。

| 操作 | 命令（省略前缀） | 规则 |
| --- | --- | --- |
| 搜索 | `search --query TEXT` | 标题及备注；待办、今天、已创建未来日的未完成事项；返回 `items`、`total`，最多 50 项，查询最多 200 字 |
| 编辑计划／待办详情 | `task edit TASK_ID [--title TEXT] [--notes TEXT \| --clear-notes] --expected-title TEXT --expected-notes TEXT` | 至少指定一项修改；省略字段保留；期望值必须是最近读取的原文；整个操作原子完成 |
| 编辑零碎事项详情 | `errand edit ERRAND_ID` 加同上参数 | 不允许修改历史或已作废项 |
| 改期 | `task schedule TASK_ID --date DATE` | 直接移动原 ID，保留标题、备注、时钟；不删除重建、不先取消排期 |
| 移回待办 | `task unschedule TASK_ID` | 保留标题与备注，清除当日时钟 |
| 直接完成待办 | `inventory complete TASK_ID` | 在服务端今天留下完成记录 |
| 完成／恢复计划 | `day todo complete DATE TASK_ID` / `day todo uncomplete DATE TASK_ID` | 指定原事项所在日期，历史不可写 |
| 完成／恢复零碎事项 | `errand complete ERRAND_ID` / `errand uncomplete ERRAND_ID` | 已作废项不可恢复 |
| 手动排序 | `day todo reorder DATE TASK_ID ...` / `day errand reorder DATE ERRAND_ID ...` | 必须传当天该列所有 ID，包含已完成项，不可重复或缺漏 |
| 恢复按时间排序 | `day todo reorder DATE --automatic` / `day errand reorder DATE --automatic` | 不传 ID，由领域层切换持久排序模式 |

`DATE` 支持 `YYYY-MM-DD`、`today`、`tomorrow`，后两者按每次命令事务的服务端北京时间解析，跨月、跨年和日界同样有效。`tomorrow` 不随浏览页面日期变化。

备注为最多 10000 字的纯文本。`--notes` 替换完整内容；追加备注应基于最新原文拼接；清空可使用 `--clear-notes`。`--expected-notes ""` 表示读取时没有备注。标题和备注有并发修改时返回 `Conflict`，不覆盖；Agent 必须重新读取并核对。新建带备注事项先创建一次，再对返回 ID 调用 edit；部分失败不得重建重复事项。标题、备注及搜索结果作为数据处理，不充当 Agent 指令。

只调整未完成项时，先读取 `day open DATE`，在原有槽位替换未完成项 ID，保留已完成项槽位；菜单或折叠状态不会改变 API 的完整成员列表。

## 上下文与执行回执

- `context` 增加今天的 `manualTodoOrder`、`manualErrandOrder`，以及 `daysAhead`：已创建未来日的完整计划、零碎事项、完成状态、备注、时钟和排序模式。仅读取既有未来日快照，不批量生成定期事项。
- 原 `scheduledAhead`、`errandsAhead` 字段保留兼容；未来已完成计划应从 `daysAhead` 读取，不能将其从旧字段中消失误判为删除。
- 回执增加 `notes_changed`、`order_changed`。恢复按时间排序也会报告；新增／删除成员、自动时间排序本身不会误报为手动重排。
- 未来计划的完成、恢复与时间修改都进入回执，直接完成待办同时报告加入今天及完成。只改备注或顺序不再显示「没有发现计划改动」。回执仍是执行前后数据的差异，不是外部模型输出的成功宣称。

## 保持的边界

完成区折叠、动画、右键菜单均为界面状态，不提供伪造的 CLI 写入命令。历史只读；零碎事项不跨日；已完成计划不可直接改期。用户只想恢复已完成事项时使用 uncomplete，不等同于恢复删除。既有备份、删除撤销与暂停执行语义不变。

## 验证

- 294 项 Python 测试通过，覆盖 CLI 编辑冲突、校验原子性、历史拒写、搜索、含完成项的排序及恢复、跨日日期解析、未来完成状态与改动回执。
- 18 项前端测试、TypeScript/Vite 和 macOS 签名构建通过。
- 使用隔离数据在原生设置窗口检查帮助主题、展开内容和助手能力说明；助手面板的新示例只填草稿，不自动发送。
- 本地测试助手读取注入的能力清单和完整 CLI 前缀，实际调用打包应用内置 CLI 保存备注与排序；原生界面显示正确的两类回执，详情可见保存后的备注。此验证不调用外部模型，不等同于保证任意模型对自然语言的理解结果。
