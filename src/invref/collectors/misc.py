"""其他类目采集：Comex 黄金/白银期货日频。

源：Yahoo Finance（GC=F / SI=F，2016-08 起，支持新浪备源）。
美元指数/Fed利率/10Y美债 由 us 采集器提供，此处不再重复。
"""
from __future__ import annotations

import logging
import sqlite3

from .. import db, repo
from . import clients

log = logging.getLogger("invref.collector.misc")

# (metric, 数据函数)
SOURCES = [
    ("misc:comex_gold", clients.gold_daily),
    ("misc:comex_silver", clients.silver_daily),
]


def collect(conn: sqlite3.Connection) -> None:
    for metric, fn in SOURCES:
        try:
            rows, source = fn()
            rows = [(d, v, None) for d, v in rows]
            n = repo.upsert_series(conn, metric, rows, source=source)
            repo.log_update(conn, metric, db.utcnow()[:10], n, "ok", f"n={n},source={source}")
            log.info("[%s] 写入 %d 行（source=%s）", metric, n, source)
        except Exception as e:  # noqa: BLE001
            repo.log_update(conn, metric, db.utcnow()[:10], 0, "error", str(e))
            log.error("[%s] 失败: %s", metric, e)
