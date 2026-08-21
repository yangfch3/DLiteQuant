"""国债收益率采集：中债国债到期收益率 1Y / 10Y / 30Y。

主源：AKShare bond_china_yield（中国债券信息网，全期限；本机可达时使用）；
1Y 备源：新浪 bond_gb_zh_sina（中国1年期国债 CN1YT，2022-09 起）；
10Y/30Y 备源：东财数据中心 RPTA_WEB_TREASURYYIELD（中国国债 2Y/5Y/10Y/30Y）。
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date

from .. import db, repo
from . import clients
from .base import retry, to_float

log = logging.getLogger("invref.collector.bond")

MATURITIES = ["1Y", "10Y", "30Y"]
HIST_START = "20020101"

# 新浪国债行情 symbol 映射（1Y 备源）
SINA_SYMBOL_MAP = {"1Y": "中国1年期国债"}

# 东财数据中心列的期限映射（仅 10Y/30Y 有）
EM_COL_MAP = {"10Y": "中国国债收益率10年", "30Y": "中国国债收益率30年"}


def _from_chinabond(maturity: str) -> list[tuple[str, float, None]]:
    import akshare as ak

    end = date.today().strftime("%Y%m%d")
    df = retry(lambda: ak.bond_china_yield(start_date=HIST_START, end_date=end))
    if df is None or df.empty:
        raise RuntimeError("bond_china_yield empty")
    dcol = next((c for c in df.columns if "日期" in str(c)), df.columns[0])
    col = next((c for c in df.columns if maturity in str(c) and "日期" not in str(c)), None)
    if col is None:
        raise RuntimeError(f"缺少期限列 {maturity}，实际列: {list(df.columns)[:12]}")
    rows = []
    for _, r in df.iterrows():
        d = str(r[dcol])[:10]
        v = to_float(r[col])
        if d and v is not None:
            rows.append((d, v, None))
    if not rows:
        raise RuntimeError(f"{maturity} empty")
    return rows


def _from_sina(maturity: str) -> list[tuple[str, float, None]]:
    import akshare as ak

    df = retry(lambda: ak.bond_gb_zh_sina(symbol=SINA_SYMBOL_MAP[maturity]))
    rows = []
    for _, r in df.iterrows():
        d = str(r["date"])[:10]
        v = to_float(r["close"])
        if d and v is not None:
            rows.append((d, v, None))
    if not rows:
        raise RuntimeError(f"{maturity} empty")
    return rows


def _from_em_dc(maturity: str) -> list[tuple[str, float, None]]:
    df = retry(lambda: clients.em_treasury_cn(start_date="20080101"))
    col = EM_COL_MAP[maturity]
    if col not in df.columns:
        raise RuntimeError(f"东财数据中心缺少 {maturity} 列")
    rows = []
    for _, r in df.iterrows():
        d = str(r["日期"])[:10]
        v = to_float(r[col])
        if d and v is not None:
            rows.append((d, v, None))
    if not rows:
        raise RuntimeError(f"{maturity} empty")
    return rows


def _collect_one(conn: sqlite3.Connection, metric: str, maturity: str) -> None:
    errors = []
    for name, fn in [("chinabond", lambda: _from_chinabond(maturity))]:
        try:
            rows = fn()
            n = repo.upsert_series(conn, metric, rows, source=f"bond:{name}")
            repo.log_update(conn, metric, db.utcnow()[:10], n, "ok", f"source={name}")
            log.info("[%s] %s 源写入 %d 行", metric, name, n)
            return
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
            log.warning("[%s] %s 源失败: %s", metric, name, e)

    if maturity in SINA_SYMBOL_MAP:
        try:
            rows = _from_sina(maturity)
            n = repo.upsert_series(conn, metric, rows, source="bond:sina")
            repo.log_update(conn, metric, db.utcnow()[:10], n, "ok", "source=sina (备源)")
            log.info("[%s] sina 备源写入 %d 行", metric, n)
            return
        except Exception as e:  # noqa: BLE001
            errors.append(f"sina: {e}")

    if maturity in EM_COL_MAP:
        try:
            rows = _from_em_dc(maturity)
            n = repo.upsert_series(conn, metric, rows, source="bond:em_dc")
            repo.log_update(conn, metric, db.utcnow()[:10], n, "ok", "source=em_dc (备源)")
            log.info("[%s] em_dc 备源写入 %d 行", metric, n)
            return
        except Exception as e:  # noqa: BLE001
            errors.append(f"em_dc: {e}")

    repo.log_update(conn, metric, db.utcnow()[:10], 0, "error", "; ".join(errors))
    log.error("[%s] 全部源失败: %s", metric, errors)


def collect(conn: sqlite3.Connection) -> None:
    for m in MATURITIES:
        _collect_one(conn, f"bond:cn:{m.lower()}", m)
