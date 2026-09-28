"""Discoverable contract for the daily interaction commands exposed to agents."""
from __future__ import annotations


def capabilities_payload() -> dict:
    return {
        "version": 1,
        "commands": [
            {"name": "search", "usage": "search --query TEXT", "description": "搜索待办、今天和已创建未来日期的未完成事项，匹配标题和备注"},
            {"name": "task.edit", "usage": "task edit TASK_ID [--title TEXT] [--notes TEXT | --clear-notes] --expected-title TEXT --expected-notes TEXT", "description": "原子修改标题和备注，省略字段保留原值；必须传入最近读取的原文，冲突不覆盖"},
            {"name": "errand.edit", "usage": "errand edit ERRAND_ID [--title TEXT] [--notes TEXT | --clear-notes] --expected-title TEXT --expected-notes TEXT", "description": "修改当天或未来零碎事项详情，冲突不覆盖"},
            {"name": "task.schedule", "usage": "task schedule TASK_ID --date DATE", "description": "安排待办或移动未完成计划，直接改期保留标题、备注和时钟"},
            {"name": "task.unschedule", "usage": "task unschedule TASK_ID", "description": "移回待办，保留标题和备注，清除当天时钟"},
            {"name": "inventory.complete", "usage": "inventory complete TASK_ID", "description": "直接完成待办，记入服务端今天的完成记录"},
            {"name": "day.todo.complete", "usage": "day todo complete DATE TASK_ID", "description": "完成该日计划"},
            {"name": "day.todo.uncomplete", "usage": "day todo uncomplete DATE TASK_ID", "description": "恢复该日已完成计划"},
            {"name": "errand.complete", "usage": "errand complete ERRAND_ID", "description": "完成零碎事项"},
            {"name": "errand.uncomplete", "usage": "errand uncomplete ERRAND_ID", "description": "恢复已完成零碎事项；已作废不可恢复"},
            {"name": "day.todo.reorder", "usage": "day todo reorder DATE [TASK_ID ...] [--automatic]", "description": "手动排序必须包含该日所有计划 ID（含已完成）；--automatic 不传 ID，恢复按时间排序"},
            {"name": "day.errand.reorder", "usage": "day errand reorder DATE [ERRAND_ID ...] [--automatic]", "description": "手动排序必须包含该日所有零碎事项 ID（含已完成）；--automatic 恢复按时间排序"},
            {"name": "day.todo.move", "usage": "day todo move DATE TASK_ID (--first | --last | --before TASK_ID | --after TASK_ID)", "description": "优先用于单项置顶、置底或相对移动；在同一事务读取当前顺序，只移动未完成项，保留已完成项槽位与其余项相对顺序"},
            {"name": "day.errand.move", "usage": "day errand move DATE ERRAND_ID (--first | --last | --before ERRAND_ID | --after ERRAND_ID)", "description": "移动同日同列的未完成零碎事项，保留已完成项槽位；不能跨日期或跨列"},
        ],
        "dateTokens": ["YYYY-MM-DD", "today", "tomorrow"],
        "timezone": "Asia/Shanghai",
        "limits": {"title": 200, "notes": 10000, "searchQuery": 200, "searchResults": 50},
        "rules": [
            "本清单描述交互扩展；完整命令与参数见 --help。所有操作通过 CLI，禁止直接修改 SQLite。",
            "历史只读；已完成计划不可改期；零碎事项不能跨日移动。",
            "完成区折叠、动画、右键菜单是界面状态，不是数据命令；CLI 读取不隐藏已完成事项。",
            "context.daysAhead 包含已创建未来日的完整列表、完成状态和排序模式，不预生成新的未来日。",
            "重排前 day open DATE 获取完整列表；只调整未完成项时，在原列表槽位替换这些 ID，保留已完成项槽位。",
            "先完成改期、新增、完成等操作，再排序。单项移动优先用 move；全量 reorder 必须在前序操作后重新读取，不能用旧上下文重放顺序。",
            "备注是纯文本；--notes 替换全部备注；追加时基于最近读取的备注拼接，Conflict 后重新读取，不盲目覆盖。",
        ],
    }
