"""series / update_log 表的读写。"""
from __future__ import annotations

import json
import sqlite3
from typing import Iterable, Sequence

from . import db

Row = tuple[str, float, dict | None]  # (date, value, meta)


def upsert_series(
    conn: sqlite3.Connection,
    metric: str,
    rows: Sequence[Row],
    source: str = "akshare",
) -> int:
    """幂等写入（按 metric+date 覆盖），返回写入行数。"""
    now = db.utcnow()
    data = [
        (
            metric,
            d,
            float(v),
            json.dumps(m, ensure_ascii=False) if m else None,
            source,
            now,
        )
        for d, v, m in rows
        if d and v is not None
    ]
    if not data:
        return 0
    conn.executemany(
        """INSERT INTO series(metric, date, value, meta, source, updated_at)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(metric, date) DO UPDATE SET
             value=excluded.value, meta=excluded.meta,
             source=excluded.source, updated_at=excluded.updated_at""",
        data,
    )
    return len(data)


def query_series(
    conn: sqlite3.Connection,
    metric: str,
    start: str | None = None,
    end: str | None = None,
) -> list[dict]:
    sql = "SELECT date, value, meta FROM series WHERE metric = ?"
    params: list = [metric]
    if start:
        sql += " AND date >= ?"
        params.append(start)
    if end:
        sql += " AND date <= ?"
        params.append(end)
    sql += " ORDER BY date"
    out = []
    for r in conn.execute(sql, params).fetchall():
        meta = json.loads(r["meta"]) if r["meta"] else None
        out.append({"date": r["date"], "value": r["value"], "meta": meta})
    return out


def latest_date(conn: sqlite3.Connection, metric: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(date) d FROM series WHERE metric = ?", (metric,)
    ).fetchone()
    return row["d"] if row and row["d"] else None


def list_metrics(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT metric, COUNT(*) n, MIN(date) first_date, MAX(date) last_date,
                  MAX(updated_at) updated_at
           FROM series GROUP BY metric ORDER BY metric"""
    ).fetchall()
    return [dict(r) for r in rows]


def log_update(
    conn: sqlite3.Connection,
    metric: str,
    run_date: str,
    rows_written: int,
    status: str,
    message: str = "",
) -> None:
    conn.execute(
        """INSERT INTO update_log(metric, run_date, rows_written, status, message, started_at, finished_at)
           VALUES(?,?,?,?,?,?,?)""",
        (metric, run_date, rows_written, status, message, db.utcnow(), db.utcnow()),
    )


def last_update_log(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM update_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
