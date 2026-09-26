# Now 技术设计

状态：实现基线（2026-08-31）  
产品依据：`docs/product/v3-now-requirements.md`、`docs/product/v3-now-decisions.md`。

## 1. 核心模型

### recurrence_series

系列保存 `kind(plan|errand)`、标题、`frequency(daily|weekly)`、每周星期集合、用户开始日、当前规则生效日、默认起止时钟、`active|paused|stopped` 状态与可空的 `deleted_at` 软删除时间。daily 的星期集合等价于七天。

### recurrence_occurrences

以 `(series_id, occurrence_date)` 为主键记录生成账本，并指向该期独立的 task 或 errand id。实体被用户删除后账本仍保留，避免同一期再次生成。实体继续走原有 Plan / Errand 命令与日界状态机。

### day_planning

以日期为主键；没有行表示 `unplanned`，有 `planned_at` 表示 `ready`。“规划中”是页面临时态，不入库。历史日的 planning 行与当天条目一样受封印保护。

## 2. 事务与日界顺序

所有入口仍先进入现有 `planner_txn`。事务内顺序固定为：

1. 读取上海日历日与结转水位；
2. 对水位到昨天的每一天，先幂等生成该日命中的周期实例；
3. 再执行该日既有封印：未完成 Plan 回 To Do，未完成 Errand 作废；
4. 推进水位到今天；
5. 幂等生成今天实例；
6. 执行当前领域命令并提交。

未来日被打开或写入前同样调用统一的 `prepare_day(date)`；HTTP 与前端不得自行判断周期。

## 3. 系列变更

- 创建：从开始日生效；如果今天命中，在同一事务生成今天。
- 编辑：新规则从明天或更晚的新开始日起生效；任何已生成实例不变。
- 暂停：今天已经生成的实例保留；暂停区间不记欠账、不在恢复时补发。
- 恢复：从恢复当天重新生效；若当天命中可生成当天。
- 停止：不可恢复的终态；停止后允许软删除。
- 删除：仅 `stopped` 可执行，写入 `deleted_at`。管理列表、周期物化和 Agent 上下文过滤软删除系列；按 id 的底层读取仍保留，以支持 occurrence 外键与历史来源解析。既有实例和账本不变。

## 4. 每日规划读模型

`GET /api/planning/today` 在领域层组装：完整当天计划、昨日回库、到期 / 逾期 To Do、其余库存及未来七日计数。任务分组按 task id 去重；未来摘要对未生成周期做规则投影，不为展示而提前写入未来实例。

`POST /api/planning/today/complete` 只允许服务器今天，确保当天 day 行存在并写 `planned_at`。它不封印、不锁定计划，之后仍可手工编辑。

## 5. Agent 回执

前端只挂载一个 Agent 侧边栏实例，由应用根组件统一管理。顶部导航的常驻入口和每日规划页的快捷入口都记录各自实际触发按钮，关闭后将焦点还给该按钮。请求上下文按当前路由映射为 `today`、`todo` 或 `day + date`；执行完成后统一触发当前页面读模型刷新。

启动器执行前后各在独立、已结转事务中读取规范化计划状态。外部脚本运行期间不持有进程锁或 SQLite 事务，以免其 CLI 自锁死。结构化 diff 使用实体 id，不根据 stdout 猜测：

- 创建 Plan / Errand / To Do；
- To Do 加入今天、移回 To Do、改排；
- 完成 / 取消完成、改名、改时钟、改目标日、删除。

非零退出也计算 diff；若已有变化，响应必须表达“失败且有部分改动”。stdout/stderr 仅用于技术诊断并做长度上限。后续若需要跨刷新精确审计，可引入 run id 并由每条 CLI 写入审计表；Now 不用整库恢复伪装撤销。

## 6. 不变量

1. 同一系列同一日期最多生成一次。
2. 先生成、后封印；二者与水位推进在同一事务。
3. 完成一期不改变系列。
4. 模板变更不改任何既有实例或封印快照。
5. 所有日期来自服务端上海日历日，仍受十年上限。
6. 前端只渲染 API 读模型，不复制日界、周期或历史只读判断。
7. 删除系列只能从 `stopped` 状态发生，且不能级联删除 occurrence 或实例。

## 7. 日常命令入口

安装包额外暴露 `local-todo` console script，内部代码仍使用 `local_planner` 包：

- 无参数与 `open`：先请求无锁、无数据访问的 `/api/health`，并校验 Local Planner 专属身份；未运行时以独立会话在后台启动 `python -m local_planner serve --port N`，轮询至健康后才调用 macOS `open`。
- `serve`：转交既有前台 `serve` 入口，不打开浏览器。
- 端口只使用 `127.0.0.1`；CLI 参数优先于 `LOCAL_PLANNER_PORT`，默认 `8787`。
- 独立的 `launch-{port}.lock` 只覆盖探测、启动和就绪等待，不能复用或持有数据库 `planner.lock`。锁内必须再次探测，以保证两个并发入口最多启动一个服务。
- 健康身份不匹配但端口已经监听时，视为其他程序占用，不启动、不打开也不接管该进程。
- 后台 stdout/stderr 追加到数据目录 `server.log`。启动超时只结束本次创建的子进程；成功后的服务不随启动命令退出。
