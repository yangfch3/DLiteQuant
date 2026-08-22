"""美国宏观数据采集：Fed 利率、美债收益率、CPI 系列。

源：Fed/CPI 来自东财数据中心 RPT_ECONOMICVALUE_USA（本机可达）；
美债 10Y/30Y 来自 Yahoo Finance（^TNX/^TYX，2016-08 起，可回填新浪缺失的更早历史），
失败回退新浪 bond_gb_us_sina（2022-10 起）；2Y 仍走新浪（Yahoo 无 2Y 收益率指数，FRED 当前环境不可达）；
美元兑人民币支持 Yahoo 失败后的国内备源，美元指数暂无完整历史备源。
美国 PPI（同比）各源（FRED/东财/金十/英为财情）当前环境均不可得，暂不采集。
"""
from __future__ import annotations

import logging
import sqlite3

from .. import db, repo
from . import clients
from .base import retry, to_float

log = logging.getLogger("invref.collector.us")

# (metric, INDICATOR_ID) — 东财 RPT_ECONOMICVALUE_USA
EM_INDICATORS = [
    ("macro:us:fed_rate", "EMG00342250", "美国:联邦基金利率目标:上限"),
    ("price:us:cpi_core", "EMG00000746", "美国:核心CPI:季调:当月同比"),
    ("price:us:cpi", "EMG00000733", "美国:CPI:非季调:当月同比"),
]

# (metric, 新浪 symbol)；10Y 改由 Yahoo 主源提供，见 collect()
SINA_BONDS = [
    ("bond:us:2y", "美国2年期国债"),
    ("bond:us:10y", "美国10年期国债"),
    ("bond:us:30y", "美国30年期国债"),
]

# (metric, 数据函数)
FX = [
    ("fx:us:dxy", clients.dxy_daily),
    ("fx:us:usdcny", clients.usdcny_daily),
]


def _from_em(indicator_id: str) -> list[tuple[str, float, None]]:
    import requests

    r = retry(
        lambda: requests.get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "reportName": "RPT_ECONOMICVALUE_USA",
                "columns": "ALL",
                "filter": f'(INDICATOR_ID="{indicator_id}")',
                "pageNumber": "1",
                "pageSize": "2000",
                "sortColumns": "REPORT_DATE",
                "sortTypes": "1",
                "source": "WEB",
                "client": "WEB",
            },
            headers=clients.UA, timeout=20,
        ).json()
    )
    rows = []
    for r_ in (j := r)["result"]["data"] or []:
        d = str(r_.get("REPORT_DATE") or "")[:10]
        v = to_float(r_.get("VALUE"))
        if d and v is not None:
            rows.append((d, v, None))
    if not rows:
        raise RuntimeError(f"em us {indicator_id}: empty")
    return rows


def _from_sina(symbol: str) -> list[tuple[str, float, None]]:
    import akshare as ak

    df = retry(lambda: ak.bond_gb_us_sina(symbol=symbol))
    rows = []
    for _, r_ in df.iterrows():
        d = str(r_["date"])[:10]
        v = to_float(r_["close"])
        if d and v is not None:
            rows.append((d, v, None))
    if not rows:
        raise RuntimeError(f"sina {symbol}: empty")
    return rows


def _collect_one(conn: sqlite3.Connection, metric: str, source: str, fn) -> None:
    try:
        rows = fn()
        n = repo.upsert_series(conn, metric, rows, source=source)
        repo.log_update(conn, metric, db.utcnow()[:10], n, "ok", f"n={n}")
        log.info("[%s] 写入 %d 行", metric, n)
    except Exception as e:  # noqa: BLE001
        repo.log_update(conn, metric, db.utcnow()[:10], 0, "error", str(e))
        log.error("[%s] 失败: %s", metric, e)


def _collect_with_source(conn: sqlite3.Connection, metric: str, fn) -> None:
    try:
        rows, source = fn()
        rows = [(d, v, None) for d, v in rows]
        n = repo.upsert_series(conn, metric, rows, source=source)
        repo.log_update(conn, metric, db.utcnow()[:10], n, "ok", f"n={n},source={source}")
        log.info("[%s] 写入 %d 行（source=%s）", metric, n, source)
    except Exception as e:  # noqa: BLE001
        repo.log_update(conn, metric, db.utcnow()[:10], 0, "error", str(e))
        log.error("[%s] 失败: %s", metric, e)


def collect(conn: sqlite3.Connection) -> None:
    for metric, iid, _ in EM_INDICATORS:
        _collect_one(conn, metric, "us:em_dc", lambda iid=iid: _from_em(iid))
    for metric, symbol in SINA_BONDS:
        if metric == "bond:us:10y":
            _collect_with_source(conn, metric, _us10y_daily)
        elif metric == "bond:us:30y":
            _collect_with_source(conn, metric, _us30y_daily)
        else:
            _collect_one(conn, metric, "us:sina", lambda symbol=symbol: _from_sina(symbol))
    for metric, fn in FX:
        _collect_with_source(conn, metric, fn)


def _us10y_daily() -> tuple[list[tuple[str, float]], str]:
    """美债 10Y：Yahoo ^TNX 主源（2016-08 起），失败回退新浪（2022-10 起）。"""
    return clients._first_success([
        ("us:yahoo_tnx", clients.yahoo_us10y),
        ("us:sina", lambda: _from_sina("美国10年期国债")),
    ])


def _us30y_daily() -> tuple[list[tuple[str, float]], str]:
    """美债 30Y：Yahoo ^TYX 主源（2016-08 起），失败回退新浪（2022-10 起）。"""
    return clients._first_success([
        ("us:yahoo_tyx", clients.yahoo_us30y),
        ("us:sina", lambda: _from_sina("美国30年期国债")),
    ])
