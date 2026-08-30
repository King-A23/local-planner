# Agent 约定

这是个人本地计划软件的产品仓库。实现以 `docs/design/v1-design.md` 为准，产品范围以冻结需求为准。

## 当前范围

- 允许：产品文档、需求记录、开放问题、工作区脚手架
- 允许：按 `docs/design/v1-design.md` 实现应用代码与测试
- 禁止：扩大冻结非目标（小时表、同步、手机、项目树、提醒、AI 排程等）
- 禁止：在 UI 层复制日界结转或只读规则；领域层是唯一事实来源
- v1 范围以 `docs/product/v1-requirements.md` 和 `docs/product/decisions.md` 为准

## 实现约束

- Python >= 3.12；`pip install -e ".[dev]"` 后跑 `pytest`
- 只绑定 `127.0.0.1`，不听 `0.0.0.0` / `::1`
- 日历日固定 `Asia/Shanghai`，日期用 `YYYY-MM-DD` 字符串

## 文档位置

产品相关文稿只写在 `docs/product/`。

## 决策规则

用户未拍板的产品决策，记录为开放问题，不要自行当作已定需求。
