"""Calendar days are Asia/Shanghai civil dates, never UTC Date or tzlocal."""

from __future__ import annotations

import inspect

from local_planner import clock as clock_mod
from local_planner.clock import FrozenClock, SHANGHAI, SystemClock, shanghai_date


def test_clock_module_does_not_use_tzlocal_or_os_local() -> None:
    source = inspect.getsource(clock_mod)
    assert "import tzlocal" not in source
    assert "from tzlocal" not in source
    assert "date.today" not in source
    assert "Asia/Shanghai" in source
    assert clock_mod.SHANGHAI.key == "Asia/Shanghai"


def test_utc_instant_and_shanghai_today_can_disagree() -> None:
    """15. 冻结 2026-08-30T16:30:00Z（上海 8-31 00:30）→ today=2026-08-31。"""
    clock = FrozenClock("2026-08-30T16:30:00Z")
    assert clock.today() == "2026-08-31"
    assert clock.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-08-30T16:30:00Z"
    assert shanghai_date("2026-08-30T16:30:00Z") == "2026-08-31"


def test_shanghai_afternoon_stays_on_that_civil_day() -> None:
    clock = FrozenClock("2026-08-30T16:00:00+08:00")
    assert clock.today() == "2026-08-30"
    assert clock.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-08-30T08:00:00Z"


def test_system_clock_today_uses_shanghai_zoneinfo() -> None:
    clock = SystemClock()
    from datetime import datetime

    expected = datetime.now(SHANGHAI).date().isoformat()
    assert clock.today() == expected
    instant = clock.now_utc()
    assert instant.tzinfo is not None
    assert instant.utcoffset().total_seconds() == 0
    assert instant.microsecond == 0
