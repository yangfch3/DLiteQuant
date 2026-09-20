"""采集器公共工具：重试、日期、数值解析、限速。"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Callable, TypeVar

from .. import config

log = logging.getLogger("invref.collector")

T = TypeVar("T")


class RateLimiter:
    """跨线程全局限速：所有调用者合计不超过 per_sec 次/秒。

    行情站点（腾讯/新浪）按累计请求量做 WAF 封禁，突发并发是触发条件之一，
    因此所有出站请求都要经过同一个实例。
    """

    def __init__(self, per_sec: float) -> None:
        self.per_sec = per_sec
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        if self.per_sec <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if now < self._next_at:
                time.sleep(self._next_at - now)
                now = time.monotonic()
            self._next_at = max(now, self._next_at) + 1.0 / self.per_sec


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
