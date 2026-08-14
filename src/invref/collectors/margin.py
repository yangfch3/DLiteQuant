"""两融余额采集：沪深两市融资余额+融券余额合计（亿元）。

主源：金十数据中心（fs_1/fs_2，2010-03-31 至今，当前环境验证可用）；
备源：AKShare 上交所/深交所官网（本机可用时优先走主源金十亦可，口径一致）。
"""
from __future__ import annotations

import logging
import sqlite3

from .. import db, repo
from . import clients
from .base import to_float

log = logging.getLogger("invref.collector.margin")


def _from_sse_szse() -> list[tuple[str, float, float]]:
    """akshare 交易所源，返回 [(date, rz, rq)]，单位元。"""
    import akshare as ak

    def extract(df, date_substr="日期"):
        dcol = next((c for c in df.columns if date_substr in str(c)), df.columns[0])
        rz = next((c for c in df.columns if "融资余额" in str(c)), None)
        rq = next((c for c in df.columns if "融券余额" in str(c)), None)
        if not rz or not rq:
            raise RuntimeError("缺少融资/融券余额列")
        out = []
        for _, r in df.iterrows():
            d = str(r[dcol])[:10]
            rz_v = to_float(r[rz])
            rq_v = to_float(r[rq])
            if d and rz_v is not None:
                out.append((d, rz_v, rq_v if rq_v is not None else 0.0))
        return out

    merged: dict[str, dict] = {}
    for df in [ak.stock_margin_sse(), ak.stock_margin_szse()]:
        for d, rz, rq in extract(df):
            m = merged.setdefault(d, {"rz": 0.0, "rq": 0.0})
            m["rz"] += rz
            m["rq"] += rq
    if not merged:
        raise RuntimeError("sse/szse margin: empty")
    return [(d, m["rz"], m["rq"]) for d, m in sorted(merged.items())]


def collect(conn: sqlite3.Connection) -> None:
    errors = []
    raw: list[tuple[str, float, float]] = []
    src = ""
    for name, fn in [("jin10", clients.jin10_margin), ("sse_szse", _from_sse_szse)]:
        try:
            raw = fn()
            src = name
            break
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
            log.warning("两融 %s 源失败: %s", name, e)

    if not raw:
        repo.log_update(conn, "margin:balance", db.utcnow()[:10], 0, "error", "; ".join(errors))
        log.error("两融全部源失败: %s", errors)
        return

    rows = [
        (
            d,
            round((rz + rq) / 1e8, 2),
            {"rz": round(rz / 1e8, 2), "rq": round(rq / 1e8, 2)},
        )
        for d, rz, rq in raw
    ]
    n = repo.upsert_series(conn, "margin:balance", rows, source=f"margin:{src}")
    repo.log_update(conn, "margin:balance", db.utcnow()[:10], n, "ok", f"source={src}")
    log.info("[margin:balance] %s 源写入 %d 行", src, n)
