"""指数历史采集：中证全指(000985)、成长100(ETF 159259)、红利低波(H30269)。

数据源优先级（按当前环境验证可用性排列）：
- 000985 / H30269：中证指数官网 API（官方源，含成交额）→ 东财行情（本机）→ 腾讯K线
- 成长100：腾讯成长ETF(159259) 前复权K线（ETF 代理，口径即 ETF 净值，非指数点位）

同时由 000985 的成交额派生全市场成交额指标 all_a:turnover（亿元）。
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import date

from .. import db, repo
from . import clients
from .base import retry, to_float

log = logging.getLogger("invref.collector.index")

HIST_START = "19900101"


# ---------------- 各源取数函数：返回 [(date, close, meta)]，meta.amount 单位亿元 ----------------

def _from_csindex(code: str):
    def fn():
        data = retry(lambda: clients.csindex_perf(code))
        if not data:
            raise RuntimeError(f"csindex {code}: empty")
        rows = []
        for r in data:
            d = str(r["tradeDate"])
            d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            # 跳过占位行：open 为空且无成交（官方 API 会回补基准日前的合成行）
            if r.get("open") is None:
                continue
            close = to_float(r.get("close"))
            if close is None:
                continue
            meta = {
                "open": to_float(r.get("open")),
                "high": to_float(r.get("high")),
                "low": to_float(r.get("low")),
                "volume": to_float(r.get("tradingVol")),
                "amount": to_float(r.get("tradingValue")),  # 亿元
            }
            rows.append((d, close, meta))
        return rows

    return fn


def _from_em_index(secid: str):
    """东财K线（本机可用；当前环境 push2his 不可达时会失败，自动跳过）。"""

    def fn():
        import akshare as ak

        code = secid.split(".")[1]
        df = retry(lambda: ak.index_zh_a_hist(symbol=code, period="daily", start_date=HIST_START, end_date=date.today().strftime("%Y%m%d")))
        if df is None or df.empty:
            raise RuntimeError(f"em index {secid}: empty")
        rows = []
        for _, r in df.iterrows():
            d = str(r["日期"])[:10]
            close = to_float(r["收盘"])
            if close is None:
                continue
            amount = to_float(r["成交额"])
            meta = {
                "open": to_float(r.get("开盘")),
                "high": to_float(r.get("最高")),
                "low": to_float(r.get("最低")),
                "volume": to_float(r.get("成交量")),
                "amount": round(amount / 1e8, 2) if amount is not None else None,
            }
            rows.append((d, close, meta))
        return rows

    return fn


def _from_tx_kline(code: str):
    def fn():
        rows_all: list[tuple[str, float, dict | None]] = []
        # 腾讯对上市前的区间可能返回空，逐级回退起点（注意腾讯需要 YYYY-MM-DD 格式）
        for start in ("1990-01-01", "2015-01-01", "2020-01-01"):
            rows_all = []
            s = start
            try:
                while True:
                    kls = retry(lambda: clients.tencent_kline(code, s, date.today().strftime("%Y-%m-%d"), count=640))
                    if not kls:
                        break
                    for k in kls:
                        d = k[0]
                        close = to_float(k[2])
                        if close is None:
                            continue
                        rows_all.append((d, close, {"open": to_float(k[1]), "high": to_float(k[3]), "low": to_float(k[4]), "volume": to_float(k[5]), "amount": None}))
                    if len(kls) < 640:
                        break
                    from datetime import date as _d, timedelta

                    last = kls[-1][0]
                    nd = _d.fromisoformat(last) + timedelta(days=1)
                    if nd >= _d.today():
                        break
                    s = nd.strftime("%Y-%m-%d")
            except Exception:  # noqa: BLE001
                rows_all = []
                continue
            if rows_all:
                break
        if not rows_all:
            raise RuntimeError(f"tx kline {code}: empty")
        return rows_all

    return fn


# metric → [(源名, 取数函数)]
INDEX_SOURCES: dict[str, list[tuple[str, callable]]] = {
    "index:000985:close": [
        ("csindex", _from_csindex("000985")),
        ("em", _from_em_index("1.000985")),
        ("tx", _from_tx_kline("sh000985")),
    ],
    "index:H30269:close": [
        ("csindex", _from_csindex("H30269")),
        ("em", _from_em_index("2.H30269")),
    ],
    "index:159259:close": [
        ("tx", _from_tx_kline("sz159259")),  # 成长ETF易方达（跟踪中证成长100(980080)），口径即 ETF 净值
    ],
}

# 中证官网回补合成行的截止日：早于该日期的数据为占位行，写入后清理
CSINDEX_CLEANUP: dict[str, str] = {
    "index:000985:close": "2004-01-01",
    "index:H30269:close": "2004-01-01",
    "all_a:turnover": "2004-01-01",
}


def _collect_one(conn: sqlite3.Connection, metric: str) -> None:
    errors = []
    for src_name, fn in INDEX_SOURCES[metric]:
        try:
            rows = fn()
            if not rows:
                raise RuntimeError("empty")
            n = repo.upsert_series(conn, metric, rows, source=f"index:{src_name}")
            repo.log_update(conn, metric, db.utcnow()[:10], n, "ok", f"source={src_name}")
            log.info("[%s] %s 源写入 %d 行", metric, src_name, n)

            # 中证官网回补的基准日前合成行清理（仅 csindex 源需要）
            if src_name == "csindex" and metric in CSINDEX_CLEANUP:
                cur = conn.execute(
                    "DELETE FROM series WHERE metric=? AND date < ?",
                    (metric, CSINDEX_CLEANUP[metric]),
                )
                if cur.rowcount:
                    log.info("[%s] 清理基准日前占位行 %d 行", metric, cur.rowcount)

            # 派生全市场成交额（亿元），来自中证全指成交额
            if metric == "index:000985:close":
                turnover = [
                    (d, v, None)
                    for d, v, m in rows
                    if m and m.get("amount") is not None
                ]
                if turnover:
                    repo.upsert_series(conn, "all_a:turnover", turnover, source=f"index:{src_name}")
                    log.info("[all_a:turnover] %s 源写入 %d 行", src_name, len(turnover))
                conn.execute(
                    "DELETE FROM series WHERE metric='all_a:turnover' AND date < ?",
                    ("2004-01-01",),
                )
            return
        except Exception as e:  # noqa: BLE001
            errors.append(f"{src_name}: {e}")
            log.warning("[%s] %s 源失败: %s", metric, src_name, e)
    repo.log_update(conn, metric, db.utcnow()[:10], 0, "error", "; ".join(errors))
    log.error("[%s] 全部源失败: %s", metric, errors)


def collect(conn: sqlite3.Connection) -> None:
    for metric in INDEX_SOURCES:
        _collect_one(conn, metric)
