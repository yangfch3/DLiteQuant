"""采集器公共工具：重试、日期、数值解析。"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable, TypeVar

from .. import config

log = logging.getLogger("invref.collector")

T = TypeVar("T")


def retry(fn: Callable[[], T], attempts: int = 3, delay: float = 2.0) -> T:
    """带指数退避的重试。"""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < attempts - 1:
                wait = delay * (2**i)
                log.warning("attempt %d/%d failed: %s; retry in %.0fs", i + 1, attempts, e, wait)
                time.sleep(wait)
    assert last is not None
    raise last


def today_cn() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def to_float(v) -> float | None:
    """宽容数值解析：容忍逗号、空值、'--'。"""
    if v is None:
        return None
    s = str(v).replace(",", "").replace("%", "").strip()
    if s in ("", "--", "None", "nan", "NaN"):
        return None
    try:
        return float(s)
    except ValueError:
        return None
