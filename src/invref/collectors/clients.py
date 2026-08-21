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

from .base import retry, to_float

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 东财行情主机：push2delay 为延迟行情（当前环境可达）；本机若 push2 可达可改环境变量
EM_HOST = os.getenv("INVREF_EM_HOST", "push2delay.eastmoney.com")
# 沪深京A股
EM_CLIST_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"

EM_DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"

CSINDEX_PERF = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
# 腾讯K线：web.ifzq 可能被 WAF 拦，回退到 ifzq（按序尝试）
TENCENT_KLINE = [
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
    "https://ifzq.gtimg.cn/appstock/app/fqkline/get",
]
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
    """腾讯前复权日K。code 形如 sh600000 / sz159259。返回 [date, open, close, high, low, volume] 行。

    注意：接口忽略 start，只返回截至 end 的最近 count(≤640) 根，调用方需从 end 往前翻页。
    """
    param = f"{code},day,{start},{end},{count},qfq"
    last_err: Exception | None = None
    for url in TENCENT_KLINE:
        try:
            r = requests.get(url, params={"param": param}, headers=UA, timeout=15)
            r.raise_for_status()
            j = r.json()
            d = (j.get("data") or {}).get(code) or {}
            kls = d.get("qfqday") or d.get("day") or []
            if kls:
                return kls
            return []  # 请求成功但无数据（如腾讯不支持的代码），直接返回空
        except Exception as e:  # noqa: BLE001
            last_err = e
    if last_err:
        raise last_err
    return []


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


MACROMICRO_CPI_CHART = 225  # 中国-居民消费价格[CPI]：series[0]=CPI 同比, series[1]=核心 CPI 同比
MACROMICRO_USDCNH_CHART = 153  # 美元/人民幣(離岸) USD/CNH：series[0] 日频


def macromicro_chart(chart_id: int, slug: str, series_idx: int) -> list[tuple[str, float]]:
    """财经M平方图表数据。先 GET 图表页取页面内 stk token，再带 Bearer/Referer 调 /charts/data/{id}。

    返回 [(YYYY-MM-DD, 值), ...]，series 序号按图表配置取（如 0=主序列、1=次级序列）。
    """
    import re

    page_url = f"https://www.macromicro.me/charts/{chart_id}/{slug}"
    s = requests.Session()
    s.headers["User-Agent"] = UA["User-Agent"]
    # 不请求 Brotli 压缩：requests 不解压 br，会得到乱码导致 stk 解析失败；gzip 可自动解压
    s.headers["Accept-Encoding"] = "gzip, deflate"
    page = retry(lambda: s.get(page_url, timeout=20))
    m = re.search(r"stk\s*[:=]\s*[\"']([^\"']+)[\"']", page.text)
    if not m:
        raise RuntimeError(f"macromicro {chart_id}: 页面未找到 stk token")
    stk = m.group(1)
    j = retry(
        lambda: s.get(
            f"https://www.macromicro.me/charts/data/{chart_id}",
            headers={"Authorization": f"Bearer {stk}", "Referer": page_url},
            timeout=20,
        ).json()
    )
    series = (j.get("data") or {}).get(f"c:{chart_id}", {}).get("series")
    if not series or len(series) <= series_idx:
        raise RuntimeError(f"macromicro {chart_id}: 无 series[{series_idx}]")
    rows = []
    for d, v in series[series_idx]:
        v = to_float(v)
        if v is not None:
            rows.append((str(d)[:10], v))
    if not rows:
        raise RuntimeError(f"macromicro {chart_id}: empty")
    return rows


def macromicro_core_cpi() -> list[tuple[str, float]]:
    """财经M平方-中国核心CPI月度同比（扣除食品和能源），2006-01 起。"""
    return macromicro_chart(MACROMICRO_CPI_CHART, "cn-cpi", 1)


def macromicro_usdcnh() -> list[tuple[str, float]]:
    """财经M平方-美元/离岸人民币 USD/CNH 日频，2013-07 起。"""
    return macromicro_chart(MACROMICRO_USDCNH_CHART, "usd-cnh", 0)


YAHOO_DXY = "DX-Y.NYB"  # 美元指数（ICE）
YAHOO_USDCNY = "CNY=X"  # 美元兑在岸人民币
YAHOO_GOLD = "GC=F"  # Comex 黄金期货
YAHOO_SILVER = "SI=F"  # Comex 白银期货


def _yahoo_daily(symbol: str) -> list[tuple[str, float]]:
    """Yahoo Finance 日频历史（range=10y 完整返回，2016-08 起）。"""
    import datetime as dt

    j = retry(
        lambda: requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"range": "10y", "interval": "1d"},
            headers=UA, timeout=25,
        ).json()
    )
    res = j["chart"]["result"][0]
    ts = res["timestamp"]
    close = res["indicators"]["quote"][0]["close"]
    rows = []
    for t, v in zip(ts, close):
        d = dt.date.fromtimestamp(t).isoformat()
        v = to_float(v)
        if v is not None:
            rows.append((d, v))
    if not rows:
        raise RuntimeError(f"yahoo {symbol}: empty")
    return rows


def yahoo_dxy() -> list[tuple[str, float]]:
    """Yahoo Finance-美元指数日频（2016-08 起）。"""
    return _yahoo_daily(YAHOO_DXY)


def yahoo_usdcny() -> list[tuple[str, float]]:
    """Yahoo Finance-美元兑在岸人民币 USD/CNY 日频（2016-08 起）。"""
    return _yahoo_daily(YAHOO_USDCNY)


# 国家统计局-居民消费价格指数分类
# 老 cid：2021-01 起核心CPI；新 cid：2026 年起核心CPI（两个合并覆盖 2021~至今）
NBS_CPI_CID = "809d2522b0fe4be89142650341b19083"
NBS_CORE_CPI_ID = "c2050e97c49a4763a6d0f0f38bf0b4ed"
NBS_CPI_CID_NEW = "5c7452825c7c4dcba391db5ca7f335c5"
NBS_CORE_CPI_ID_NEW = "71be3d43d2fb44188199840272463ae0"
NBS_ROOT_ID = "fc982599aa684be7969d7b90b1bd0e84"
NBS_STREAM = "https://data.stats.gov.cn/dg/website/publicrelease/web/external/stream/esData"


def _nbs_es_data(cid: str, indicator_id: str, dts: list[str]) -> list[tuple[str, float]]:
    """国家统计局 esData：取单指标「上年同月=100」月度序列，转为同比%。"""
    import json

    body = {
        "cid": cid,
        "indicatorIds": [indicator_id],
        "daCatalogId": "",
        "das": [{"text": "全国", "value": "000000000000"}],
        "showType": "1",
        "dts": dts,
        "rootId": NBS_ROOT_ID,
    }
    headers = {
        "User-Agent": UA["User-Agent"],
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://data.stats.gov.cn",
        "Referer": "https://data.stats.gov.cn/dg/website/page.html",
    }
    j = retry(
        lambda: requests.post(NBS_STREAM, data=json.dumps(body), headers=headers, timeout=30).json()
    )
    rows = []
    for month in j.get("data") or []:
        for item in month.get("values") or []:
            if item.get("_id") != indicator_id:
                continue
            try:
                fv = float(item.get("value"))
            except (TypeError, ValueError):
                fv = None
            code = str(month.get("code") or "")
            if fv is not None and len(code) >= 8:
                rows.append((f"{code[:4]}-{code[4:6]}-01", round(fv - 100.0, 2)))
            break
    rows.sort()
    return rows


def nbs_core_cpi() -> list[tuple[str, float]]:
    """国家统计局-核心CPI（不包括食品和能源）月度同比，2021-01 起（官方口径）。

    两个数据源节点合并：老 cid 覆盖 2021-2025，新 cid 覆盖 2026 起（含最新月）。
    """
    merged: dict[str, float] = {}
    for d, v in _nbs_es_data(NBS_CPI_CID, NBS_CORE_CPI_ID, ["202101MM-202612MM"]):
        merged[d] = v
    for d, v in _nbs_es_data(NBS_CPI_CID_NEW, NBS_CORE_CPI_ID_NEW, ["202601MM-202612MM"]):
        merged[d] = v
    if not merged:
        raise RuntimeError("nbs core cpi: empty")
    return sorted(merged.items())


def yahoo_gold() -> list[tuple[str, float]]:
    """Yahoo Finance-Comex 黄金期货日频（2016-08 起）。"""
    return _yahoo_daily(YAHOO_GOLD)


def yahoo_silver() -> list[tuple[str, float]]:
    """Yahoo Finance-Comex 白银期货日频（2016-08 起）。"""
    return _yahoo_daily(YAHOO_SILVER)
