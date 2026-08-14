"""全A涨跌中位数采集：东财全市场实时列表，计算当日涨跌幅中位数与涨跌家数。

数据源：东财 push2delay clist（沪深京A股，5896 只），每日收盘后运行一次。
"""
from __future__ import annotations

import logging
import sqlite3

from .. import db, repo
from . import clients
from .base import retry, to_float, today_cn

log = logging.getLogger("invref.collector.median")


def collect(conn: sqlite3.Connection) -> None:
    try:
        items = retry(clients.em_clist_all)
    except Exception as e:  # noqa: BLE001
        log.exception("全市场列表拉取失败")
        repo.log_update(conn, "all_a:median_pct", today_cn(), 0, "error", str(e))
        return

    pcts = [p for p in (to_float(x.get("f3")) for x in items) if p is not None]
    if not pcts:
        repo.log_update(conn, "all_a:median_pct", today_cn(), 0, "error", "涨跌幅为空")
        log.error("涨跌幅为空")
        return

    pcts.sort()
    n = len(pcts)
    median = pcts[n // 2] if n % 2 else (pcts[n // 2 - 1] + pcts[n // 2]) / 2
    median = round(median, 2)
    up = sum(1 for p in pcts if p > 0)
    down = sum(1 for p in pcts if p < 0)
    flat = n - up - down
    meta = {"up": up, "down": down, "flat": flat, "total": len(items), "up_ratio": round(up / max(len(items), 1), 4)}
    n_written = repo.upsert_series(conn, "all_a:median_pct", [(today_cn(), median, meta)], source="em_clist")
    repo.log_update(conn, "all_a:median_pct", today_cn(), n_written, "ok", f"样本={n}")
    log.info("[all_a:median_pct] %s 中位数=%.2f%% 上涨%d/下跌%d/平%d (样本%d)", today_cn(), median, up, down, flat, n)
