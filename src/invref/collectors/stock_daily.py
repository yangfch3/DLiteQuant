"""个股前复权日线：多源按需降级（新浪 → 腾讯 → baostock）。

每只股票独立走源链：前一个源报错才降级到下一个，任一源成功即结束（见 `StockSource.__call__`）。
各源返回统一口径 `[(date, close, open, high, low, volume)]`（日期正序、前复权收盘）。

源特性（本机实测，CI 环境需另行确认）：
- 新浪 KLineData：单次最多 6000 根，5 年窗口一次拿完；**不复权**，用同站 qfq.js
  因子表折算前复权（qfq价 = 不复权收盘 ÷ 适用因子，实测校准：600000 除权日 2026-07-16
  折算后涨跌幅 -0.45%，与腾讯 qfq 同量级，未折算则 -4.94%）；
  支持北交所（bj 前缀）。缺点：按累计请求量返回 HTTP 456 封禁。
- 腾讯 fqkline：忽略 start、只返回截至 end 的最近 count(≤640) 根，需从后往前翻页；
  被 stgw/WAF 拦时返回 501 + 挑战页（非 JSON），表现为 HTTPError/JSONDecodeError。
- baostock：前复权长历史，TCP 登录制；**不支持北交所**，且客户端多线程会卡死，
  故默认不启用（--with-baostock 时才作为收尾串行补采源）。
"""
from __future__ import annotations

import bisect
import json
import logging
import re
import threading
from datetime import date

import requests

from .base import RateLimiter, to_float

log = logging.getLogger("invref.collector.stock")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
SINA_REFERER = {"Referer": "https://finance.sina.com.cn/"}

SINA_KLINE = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
SINA_QFQ = "https://finance.sina.com.cn/realstock/company/{sym}/qfq.js"
TENCENT_KLINE = [
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
    "https://ifzq.gtimg.cn/appstock/app/fqkline/get",
]

SINA_MAX_LEN = 6000   # 单次可返回的最大根数（实测 datalen=6000 可用，约 24 年）
TX_PAGE = 640         # 腾讯单页上限
REQ_BUDGET = 6        # 单只股票最多几次 HTTP（1 次日线 + 1 次因子 + 腾讯翻页余量）

_SESSION = requests.Session()
_BS_LOCK = threading.Lock()


def sina_symbol(em_code: str) -> str:
    """东财代码 → 新浪符号：6/5 → sh，0/3 → sz，其余（9 与 920 北交所）→ bj。"""
    if em_code.startswith(("6", "5")):
        return "sh" + em_code
    if em_code.startswith(("0", "3")):
        return "sz" + em_code
    return "bj" + em_code


def _sina_datalen(start: str, end: str) -> int:
    """覆盖区间所需的根数（约 243 交易日/年），上限 SINA_MAX_LEN。"""
    years = (date.fromisoformat(end) - date.fromisoformat(start)).days // 366 + 1
    return min(SINA_MAX_LEN, max(300, years * 244 + 30))


class StockSource:
    """个股日线源：名字 + 取数函数，带单只请求预算计数。"""

    def __init__(self, name: str, fetch, limiter: RateLimiter, budget: int = REQ_BUDGET) -> None:
        self.name = name
        self._fetch = fetch
        self._limiter = limiter
        self._budget = budget

    def __call__(self, em_code: str, start: str, end: str) -> list[tuple]:
        state = {"n": 0}

        def spend() -> None:
            state["n"] += 1
            if state["n"] > self._budget:
                raise RuntimeError(f"{self.name}: 超出单只请求预算({self._budget})")

        return self._fetch(em_code, start, end, self._limiter, spend)


def _get(url: str, params: dict, limiter: RateLimiter, headers: dict | None = None, timeout: int = 20):
    limiter.wait()
    r = _SESSION.get(url, params=params, headers={**UA, **(headers or {})}, timeout=timeout)
    r.raise_for_status()
    return r


def _sina_factors(sym: str, limiter: RateLimiter) -> list[tuple[str, float]]:
    """新浪前复权因子表：[(生效日, 因子)]，含 1900-01-01 兜底项，按日期升序。"""
    r = _get(SINA_QFQ.format(sym=sym), {}, limiter, SINA_REFERER, timeout=15)
    m = re.search(r"\{.*\}", r.text, re.S)
    if not m:
        raise RuntimeError("qfq.js 解析失败")
    data = json.loads(m.group(0)).get("data") or []
    out = [(str(x["d"]), float(x["f"])) for x in data if x.get("d") and x.get("f")]
    if not out:
        raise RuntimeError("qfq.js 无因子")
    out.sort()
    return out


def _apply_qfq(rows: list[dict], factors: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """不复权日线 ÷ 适用因子 → 前复权收盘（分红/送转日不产生假跳空）。

    新浪 qfq.js 的因子是"累计复权系数"：最新日期为 1，越早越大。
    实测校准（600000，除权 2026-07-16，分红 0.42）：不复权 9.310 ÷ 1.04724 = 8.890，
    与腾讯 qfq 的 8.890 一致；因此 qfq价 = 不复权收盘 / 因子。
    """
    days = [f[0] for f in factors]
    out = []
    for r in rows:
        v = to_float(r.get("close"))
        if v is None or not r.get("day"):
            continue
        i = bisect.bisect_right(days, r["day"]) - 1
        f = factors[max(i, 0)][1]
        if f:
            out.append((r["day"], round(v / f, 4)))
    return out


def fetch_sina(em_code: str, start: str, end: str, limiter: RateLimiter, spend) -> list[tuple]:
    """新浪：日线（不复权）+ qfq 因子折算前复权。"""
    sym = sina_symbol(em_code)
    spend()
    r = _get(SINA_KLINE, {"symbol": sym, "scale": "240", "ma": "no",
                          "datalen": str(_sina_datalen(start, end))}, limiter, SINA_REFERER)
    rows = r.json()
    if not rows:
        raise RuntimeError(f"sina {sym}: empty")
    spend()
    factors = _sina_factors(sym, limiter)
    out = [(d, v, None, None, None, None) for d, v in _apply_qfq(rows, factors) if start <= d <= end]
    if not out:
        raise RuntimeError(f"sina {sym}: 区间内无数据")
    return out


def fetch_tencent(em_code: str, start: str, end: str, limiter: RateLimiter, spend) -> list[tuple]:
    """腾讯 fqkline：忽略 start、每页 640 根，从 end 往前翻页取前复权。"""
    code = tencent_code_of(em_code)
    acc: dict[str, tuple] = {}
    e = end
    while True:
        spend()
        kls = _tx_page(code, start, e, limiter)
        if not kls:
            break
        for k in kls:
            try:
                acc[k[0]] = (k[0], float(k[2]), float(k[1]), float(k[3]), float(k[4]), float(k[5]))
            except (ValueError, IndexError):
                continue
        first = str(kls[0][0])
        if len(kls) < TX_PAGE or first <= start:
            break
        nxt = date.fromordinal(date.fromisoformat(first).toordinal() - 1).isoformat()
        if nxt >= e:  # 防死循环
            break
        e = nxt
    rows = [acc[d] for d in sorted(acc) if start <= d <= end]
    if not rows:
        raise RuntimeError(f"tencent {code}: 区间内无数据")
    return rows


def tencent_code_of(em_code: str) -> str:
    """东财代码 → 腾讯代码（腾讯无北交所数据，920 会返回空）。"""
    if em_code.startswith(("6", "5")):
        return "sh" + em_code
    if em_code.startswith(("0", "3")):
        return "sz" + em_code
    return "bj" + em_code


def _tx_page(code: str, start: str, end: str, limiter: RateLimiter) -> list[list]:
    param = f"{code},day,{start},{end},{TX_PAGE},qfq"
    last: Exception | None = None
    for url in TENCENT_KLINE:
        try:
            j = _get(url, {"param": param}, limiter, timeout=15).json()
            d = (j.get("data") or {}).get(code) or {}
            return d.get("qfqday") or d.get("day") or []
        except Exception as ex:  # noqa: BLE001
            last = ex
    raise last if last else RuntimeError("tencent: 无响应")


def fetch_baostock(em_code: str, start: str, end: str, limiter: RateLimiter, spend) -> list[tuple]:
    """baostock 前复权日线（不支持北交所；客户端多线程会卡死，调用方须串行）。"""
    import baostock as bs

    bs_code = _bs_code_of(em_code)
    if bs_code is None:
        raise RuntimeError("baostock 不支持北交所代码")
    spend()
    limiter.wait()
    with _BS_LOCK:
        rs = bs.query_history_k_data_plus(
            bs_code, "date,open,high,low,close,volume",
            start_date=start, end_date=end, frequency="d", adjustflag="2",
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
    if not rows:
        raise RuntimeError(f"baostock {bs_code}: empty")
    return [
        (r[0], to_float(r[4]), to_float(r[1]), to_float(r[2]), to_float(r[3]), to_float(r[5]))
        for r in rows
    ]


def _bs_code_of(em_code: str) -> str | None:
    if em_code.startswith(("6", "5")):
        return "sh." + em_code
    if em_code.startswith(("0", "3")):
        return "sz." + em_code
    return None


def default_chain(limiter: RateLimiter, include_baostock: bool = False) -> list[StockSource]:
    """默认源链：新浪（含因子折算）为主，腾讯兜底，baostock 可选（仅串行补采）。"""
    chain = [
        StockSource("sina_qfq", fetch_sina, limiter),
        StockSource("tencent_qfq", fetch_tencent, limiter),
    ]
    if include_baostock:
        chain.append(StockSource("baostock_qfq", fetch_baostock, limiter))
    return chain
