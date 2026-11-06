import itertools

import pytest

from plugin import receipts

TODAY = "2026-11-05"


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch):
    """Today is 2026-11-05 in every test, and the clock ticks one second per reading, so receipts' times are
    known and increasing."""
    ticks = itertools.count()

    def now() -> str:
        second = next(ticks)
        return f"{TODAY} 12:{second // 60 % 60:02d}:{second % 60:02d}.000000"

    monkeypatch.setattr(receipts, "CLOCK", now)
    return now
