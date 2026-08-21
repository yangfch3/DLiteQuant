"""其他类目采集：Comex 黄金/白银期货日频。

源：Yahoo Finance（GC=F / SI=F，2016-08 起，CI 可达）。
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
    ("misc:comex_gold", clients.yahoo_gold),
    ("misc:comex_silver", clients.yahoo_silver),
]


def collect(conn: sqlite3.Connection) -> None:
    for metric, fn in SOURCES:
        try:
            rows = [(d, v, None) for d, v in fn()]
            n = repo.upsert_series(conn, metric, rows, source="misc:yahoo")
            repo.log_update(conn, metric, db.utcnow()[:10], n, "ok", f"n={n}")
            log.info("[%s] 写入 %d 行", metric, n)
        except Exception as e:  # noqa: BLE001
            repo.log_update(conn, metric, db.utcnow()[:10], 0, "error", str(e))
            log.error("[%s] 失败: %s", metric, e)
