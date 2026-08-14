"""多数据源客户端：东财行情(push2delay)、中证官网、腾讯K线、金十、东财数据中心。

选型背景：部分环境（如本开发机）无法直连东财 push2/push2his、交易所官网与中债官网，
本模块统一封装当前环境验证可用的链路，采集器按优先级组合使用。
"""
from __future__ import annotations

import os
import time
from datetime import date

import pandas as pd
import requests

from .base import retry

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 东财行情主机：push2delay 为延迟行情（当前环境可达）；本机若 push2 可达可改环境变量
EM_HOST = os.getenv("INVREF_EM_HOST", "push2delay.eastmoney.com")
# 沪深京A股
EM_CLIST_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"

EM_DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"

CSINDEX_PERF = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
TENCENT_KLINE = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
JIN10_MARGIN = {
    "sh": "https://cdn.jin10.com/data_center/reports/fs_1.json",
    "sz": "https://cdn.jin10.com/data_center/reports/fs_2.json",
}


def em_clist_all() -> list[dict]:
    """东财全市场A股实时行情列表（分页），字段含 f2 最新价 / f3 涨跌幅% / f12 代码 / f14 名称。

    每页请求都带重试（GHA/Azure 等网络对东财偶发超时），超时 20s。
    """
    out: list[dict] = []
    page = 1
    while True:

        def _fetch():
            r = requests.get(
                f"https://{EM_HOST}/api/qt/clist/get",
                params={
                    "pn": page, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                    "fid": "f3", "fs": EM_CLIST_FS, "fields": "f2,f3,f12,f14",
                },
                headers=UA, timeout=20,
            )
            r.raise_for_status()
            return r.json()

        d = retry(_fetch, attempts=3, delay=1.5).get("data") or {}
        diff = d.get("diff") or []
        out.extend(diff)
        total = int(d.get("total") or 0)
        if not diff or len(out) >= total or page >= 200:
            break
        page += 1
        time.sleep(0.05)
    return out


def csindex_perf(code: str, start: str = "19900101", end: str | None = None) -> list[dict]:
    """中证指数官网-指数历史行情（官方源）。

    返回字段：tradeDate(YYYYMMDD), open, high, low, close, tradingVol(股), tradingValue(亿元)。
    """
    end = end or date.today().strftime("%Y%m%d")
    r = requests.get(
        CSINDEX_PERF,
        params={"indexCode": code, "startDate": start, "endDate": end},
        headers=UA, timeout=20,
    )
    r.raise_for_status()
    j = r.json()
    if str(j.get("code")) != "200":
        raise RuntimeError(f"csindex {code}: {j.get('msg')}")
    return j.get("data") or []


def em_money_supply() -> list[dict]:
    """东财数据中心-货币供应量（月度 M0/M1/M2 余额亿元 + 同比/环比）。

    返回原始行：REPORT_DATE/TIME/BASIC_CURRENCY(M2)/CURRENCY(M1)/FREE_CASH(M0) 及 *_SAME/*_SEQUENTIAL。
    历史 2008-01 至今（该表不提供更早数据）。
    """
    return em_dc(
        "RPT_ECONOMY_CURRENCY_SUPPLY",
        "REPORT_DATE,TIME,BASIC_CURRENCY,BASIC_CURRENCY_SAME,BASIC_CURRENCY_SEQUENTIAL,"
        "CURRENCY,CURRENCY_SAME,CURRENCY_SEQUENTIAL",
    )


def em_dc(report: str, columns: str) -> list[dict]:
    """东财数据中心通用直连。返回原始行 dict 列表（倒序，最新在前）。"""
    r = requests.get(
        EM_DC,
        params={
            "columns": columns,
            "pageNumber": "1",
            "pageSize": "2000",
            "sortColumns": "REPORT_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
            "reportName": report,
        },
        headers=UA, timeout=20,
    )
    r.raise_for_status()
    j = r.json()
    data = (j.get("result") or {}).get("data") or []
    if not data:
        raise RuntimeError(f"em_dc {report}: empty")
    return data


def tencent_kline(code: str, start: str, end: str, count: int = 640) -> list[list]:
    """腾讯前复权日K。code 形如 sh600000 / sz159259。返回 [date, open, close, high, low, volume] 行。"""
    param = f"{code},day,{start},{end},{count},qfq"
    r = requests.get(TENCENT_KLINE, params={"param": param}, headers=UA, timeout=15)
    r.raise_for_status()
    j = r.json()
    d = (j.get("data") or {}).get(code) or {}
    return d.get("qfqday") or d.get("day") or []


def tencent_code_of(em_code: str) -> str:
    """东财代码 → 腾讯行情代码（6开头沪市，0/3开头深市，其余按北交所尝试）。"""
    if em_code.startswith(("6", "5", "9")):
        return "sh" + em_code
    if em_code.startswith(("0", "3", "1")):
        return "sz" + em_code
    return "bj" + em_code


def jin10_margin() -> list[tuple[str, float, float]]:
    """金十数据中心 沪深两融余额。返回 [(date, 融资余额, 融券余额)]，单位：元。"""
    merged: dict[str, dict] = {}
    for kind, url in JIN10_MARGIN.items():
        j = retry(lambda u=url: requests.get(u, params={"_": time.time()}, headers=UA, timeout=20).json())
        values = j.get("values") or {}
        for d, v in values.items():
            # v = [融资买入额, 融资余额, 融券卖出量, 融券余量, 融券余额, 融资融券余额]
            try:
                rz, rq = float(v[1]), float(v[4])
            except (TypeError, ValueError, IndexError):
                continue
            m = merged.setdefault(str(d)[:10], {"rz": 0.0, "rq": 0.0})
            m["rz"] += rz
            m["rq"] += rq
    if not merged:
        raise RuntimeError("jin10 margin: empty")
    # 单位自适应：数值量级若 < 1e10 视为万元
    maxv = max(max(m["rz"], m["rq"]) for m in merged.values())
    scale = 1e4 if maxv < 1e10 else 1.0  # → 元
    return [(d, m["rz"] * scale, m["rq"] * scale) for d, m in sorted(merged.items())]


def em_treasury_cn(start_date: str = "20080101") -> pd.DataFrame:
    """东财数据中心-中美国债收益率（含中国国债 2Y/5Y/10Y/30Y）。"""
    import akshare as ak

    return ak.bond_zh_us_rate(start_date=start_date)
