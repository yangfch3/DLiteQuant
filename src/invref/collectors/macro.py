"""货币供应量采集：M1/M2 月度余额（亿元）+ 同比/环比。

源：东财数据中心 RPT_ECONOMY_CURRENCY_SUPPLY（2008-01 至今，当前环境验证可用）。
金十仅提供 M2 同比年率（1998 起，无绝对量）且含 NaN 行，不作备源。
"""
from __future__ import annotations

import logging
import re
import sqlite3

from .. import db, repo
from . import clients
from .base import to_float

log = logging.getLogger("invref.collector.macro")

# (metric, 余额列, 同比列, 环比列)
METRICS = [
    ("macro:cn:m2", "BASIC_CURRENCY", "BASIC_CURRENCY_SAME", "BASIC_CURRENCY_SEQUENTIAL"),
    ("macro:cn:m1", "CURRENCY", "CURRENCY_SAME", "CURRENCY_SEQUENTIAL"),
]


def _rows(raw: list[dict]) -> dict[str, list[tuple[str, float, dict | None]]]:
    """按 metric 分组：date=YYYY-MM-01, value=余额(亿元), meta={yoy,mom}。"""
    out: dict[str, list[tuple[str, float, dict | None]]] = {m: [] for m, *_ in METRICS}
    for r in raw:
        m = re.match(r"(\d{4})年(\d{2})月", str(r.get("TIME") or ""))
        if not m:
            continue
        d = f"{m.group(1)}-{m.group(2)}-01"
        for metric, col, yoy_col, mom_col in METRICS:
            v = to_float(r.get(col))
            if v is None:
                continue
            out[metric].append(
                (d, v, {"yoy": to_float(r.get(yoy_col)), "mom": to_float(r.get(mom_col))})
            )
    return out


def collect(conn: sqlite3.Connection) -> None:
    try:
        raw = clients.em_money_supply()
    except Exception as e:  # noqa: BLE001
        for metric, *_ in METRICS:
            repo.log_update(conn, metric, db.utcnow()[:10], 0, "error", str(e))
        log.error("[macro] 东财货币供应源失败: %s", e)
        return

    for metric, rows in _rows(raw).items():
        if not rows:
            repo.log_update(conn, metric, db.utcnow()[:10], 0, "error", "empty")
            log.error("[%s] 东财源返回空", metric)
            continue
        n = repo.upsert_series(conn, metric, rows, source="macro:em_dc")
        repo.log_update(conn, metric, db.utcnow()[:10], n, "ok", "source=em_dc")
        log.info("[%s] 东财源写入 %d 行", metric, n)
