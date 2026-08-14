"""估值与股债性价比采集：全A PE/PB + 分位（乐咕乐股）、ERP（中证800(000906)加权 − 10Y国债）。

口径说明：
- 全A PE/PB 取乐咕乐股「全A等权」序列（TTM PE / 等权PB），历史自 2005；
  分位为本地全历史滚动分位（截至当日、含当日，值<=当日值的交易日占比）。
- ERP（股债性价比）= 中证800(000906) 加权滚动EP(100/PE) − 10Y国债（取自本库 bond:cn:10y，
  须在国债采集之后运行）。加权口径与市场通行定义一致；中证800 为全A 的免费加权代理。
"""
from __future__ import annotations

import bisect
import logging
import sqlite3

from .. import db, repo
from .base import retry, to_float

log = logging.getLogger("invref.collector.valuation")

PE = "valuation:all_a:pe"
PB = "valuation:all_a:pb"
PE_PCT = "valuation:all_a:pe_pct"
PB_PCT = "valuation:all_a:pb_pct"
ERP = "erp:csi800"


def _percentile(rows: list[tuple[str, float, None]]) -> list[tuple[str, float, None]]:
    """全历史滚动分位（0-100）：截至当日，值<=当日值的交易日占比。"""
    rows = sorted(rows, key=lambda r: r[0])
    out: list[tuple[str, float, None]] = []
    seen: list[float] = []
    for i, (d, v, _) in enumerate(rows):
        pos = bisect.bisect_right(seen, v)
        seen.insert(pos, v)
        out.append((d, round(pos / (i + 1) * 100, 2), None))
    return out


def _fetch_legulegu_pe() -> list[tuple[str, float, None]]:
    import akshare as ak

    df = retry(lambda: ak.stock_a_ttm_lyr())
    if df is None or df.empty:
        raise RuntimeError("stock_a_ttm_lyr empty")
    rows = []
    for _, r in df.iterrows():
        d = str(r["date"])[:10]
        v = to_float(r["averagePETTM"])
        if d and v is not None:
            rows.append((d, v, None))
    if not rows:
        raise RuntimeError("全A等权PE empty")
    return rows


def _fetch_legulegu_pb() -> list[tuple[str, float, None]]:
    import akshare as ak

    df = retry(lambda: ak.stock_a_all_pb())
    if df is None or df.empty:
        raise RuntimeError("stock_a_all_pb empty")
    rows = []
    for _, r in df.iterrows():
        d = str(r["date"])[:10]
        v = to_float(r["equalWeightAveragePB"])
        if d and v is not None:
            rows.append((d, v, None))
    if not rows:
        raise RuntimeError("全A等权PB empty")
    return rows


def _fetch_csi800_pe() -> list[tuple[str, float, None]]:
    """中证800(000906) 加权滚动市盈率（乐咕乐股，全历史）。"""
    import akshare as ak

    df = retry(lambda: ak.stock_index_pe_lg(symbol="中证800"))
    if df is None or df.empty:
        raise RuntimeError("中证800(000906) PE empty")
    rows = []
    for _, r in df.iterrows():
        d = str(r["日期"])[:10]
        v = to_float(r["滚动市盈率"])
        if d and v is not None:
            rows.append((d, v, None))
    if not rows:
        raise RuntimeError("中证800(000906) 加权PE empty")
    return rows


def _load_y10(conn: sqlite3.Connection) -> dict[str, float]:
    rows = conn.execute(
        "SELECT date, value FROM series WHERE metric='bond:cn:10y'"
    ).fetchall()
    return {r["date"]: r["value"] for r in rows}


def _write(
    conn: sqlite3.Connection, metric: str, rows, source: str
) -> None:
    n = repo.upsert_series(conn, metric, rows, source=source)
    repo.log_update(conn, metric, db.utcnow()[:10], n, "ok", f"source={source}")
    log.info("[%s] 写入 %d 行 (source=%s)", metric, n, source)


def collect(conn: sqlite3.Connection) -> None:
    # 1) 全A PE/PB + 分位（乐咕乐股）
    try:
        pe = _fetch_legulegu_pe()
        pb = _fetch_legulegu_pb()
        _write(conn, PE, pe, "legulegu")
        _write(conn, PB, pb, "legulegu")
        _write(conn, PE_PCT, _percentile(pe), "legulegu:calc")
        _write(conn, PB_PCT, _percentile(pb), "legulegu:calc")
    except Exception as e:  # noqa: BLE001
        log.error("全A估值采集失败: %s", e)
        repo.log_update(conn, PE, db.utcnow()[:10], 0, "error", str(e))

    # 2) ERP（依赖本库 10Y 国债，须在国债采集之后运行）
    y10 = _load_y10(conn)
    if not y10:
        log.error("缺少 10Y 国债数据，跳过 ERP")
        return

    try:
        csi800 = _fetch_csi800_pe()
        erp_rows = []
        for d, v, _ in csi800:
            if v > 0 and d in y10:
                ep = 100.0 / v
                erp_rows.append(
                    (d, round(ep - y10[d], 4), {"ep": round(ep, 4), "y10": y10[d]})
                )
        _write(conn, ERP, erp_rows, "legulegu800+10y")
    except Exception as e:  # noqa: BLE001
        log.error("ERP 采集/计算失败: %s", e)
        repo.log_update(conn, ERP, db.utcnow()[:10], 0, "error", str(e))
