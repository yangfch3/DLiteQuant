"""物价指数采集：CPI/PPI 月度同比（%）。

源：东财数据中心 RPT_ECONOMY_CPI（2008-01 起）/ RPT_ECONOMY_PPI（2006-01 起）；
核心 CPI（扣除食品和能源）：财经M平方 macromicro.me（2006-01 起，东财无此字段）。
"""
from __future__ import annotations

import logging
import re
import sqlite3

from .. import db, repo
from . import clients
from .base import to_float

log = logging.getLogger("invref.collector.price")

# (metric, reportName, 同比列, 当月指数列, 环比列, 累计列)
SOURCES = [
    ("price:cn:cpi", "RPT_ECONOMY_CPI", "NATIONAL_SAME", "NATIONAL_BASE", "NATIONAL_SEQUENTIAL", "NATIONAL_ACCUMULATE"),
    ("price:cn:ppi", "RPT_ECONOMY_PPI", "BASE_SAME", "BASE", None, "BASE_ACCUMULATE"),
]


def _rows(
    raw: list[dict], yoy_col: str, idx_col: str, mom_col: str | None, acc_col: str
) -> list[tuple[str, float, dict | None]]:
    out: list[tuple[str, float, dict | None]] = []
    for r in raw:
        m = re.match(r"(\d{4})年(\d{2})月", str(r.get("TIME") or ""))
        if not m:
            continue
        d = f"{m.group(1)}-{m.group(2)}-01"
        v = to_float(r.get(yoy_col))
        if v is None:
            continue
        meta = {"index": to_float(r.get(idx_col)), "acc": to_float(r.get(acc_col))}
        if mom_col:
            meta["mom"] = to_float(r.get(mom_col))
        out.append((d, v, meta))
    return out


def _collect_core_cpi(conn: sqlite3.Connection) -> None:
    metric = "price:cn:cpi_core"
    try:
        rows = [(d, v, None) for d, v in clients.macromicro_core_cpi()]
    except Exception as e:  # noqa: BLE001
        repo.log_update(conn, metric, db.utcnow()[:10], 0, "error", str(e))
        log.error("[%s] macromicro 源失败: %s", metric, e)
        return
    if not rows:
        repo.log_update(conn, metric, db.utcnow()[:10], 0, "error", "empty")
        log.error("[%s] macromicro 源返回空", metric)
        return
    n = repo.upsert_series(conn, metric, rows, source="price:macromicro")
    repo.log_update(conn, metric, db.utcnow()[:10], n, "ok", "source=macromicro")
    log.info("[%s] macromicro 源写入 %d 行", metric, n)


def collect(conn: sqlite3.Connection) -> None:
    for metric, report, yoy_col, idx_col, mom_col, acc_col in SOURCES:
        cols = ",".join(x for x in [yoy_col, idx_col, acc_col, mom_col] if x)
        try:
            raw = clients.em_dc(report, f"REPORT_DATE,TIME,{cols}")
        except Exception as e:  # noqa: BLE001
            repo.log_update(conn, metric, db.utcnow()[:10], 0, "error", str(e))
            log.error("[%s] 东财源失败: %s", metric, e)
            continue
        rows = _rows(raw, yoy_col, idx_col, mom_col, acc_col)
        if not rows:
            repo.log_update(conn, metric, db.utcnow()[:10], 0, "error", "empty")
            log.error("[%s] 东财源返回空", metric)
            continue
        n = repo.upsert_series(conn, metric, rows, source="price:em_dc")
        repo.log_update(conn, metric, db.utcnow()[:10], n, "ok", "source=em_dc")
        log.info("[%s] 东财源写入 %d 行", metric, n)
    _collect_core_cpi(conn)
