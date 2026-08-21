"""指标注册表：metric 名称 → 展示元信息 与 前端图表布局。"""
from __future__ import annotations

METRIC_META: dict[str, dict] = {
    "index:000985:close": {
        "title": "中证全指(000985)",
        "unit": "点",
        "description": "全A走势（中证全指(000985)收盘），meta.amount 为全市场成交额（亿元）",
    },
    "index:159259:close": {
        "title": "成长100 (ETF 159259)",
        "unit": "元",
        "decimals": 3,
        "description": "易方达成长ETF 前复权收盘价",
    },
    "index:H30269:close": {
        "title": "红利低波(H30269)",
        "unit": "点",
        "description": "中证红利低波动指数（H30269）收盘",
    },
    "all_a:turnover": {
        "title": "全A成交额",
        "unit": "亿元",
        "description": "中证全指(000985)成分合计成交额，代表全市场成交额",
    },
    "all_a:median_pct": {
        "title": "全A涨跌中位数",
        "unit": "%",
        "description": "全市场个股当日涨跌幅的中位数（东财全市场快照口径，含北交所）",
    },
    "margin:balance": {
        "title": "两融余额",
        "unit": "亿元",
        "description": "沪深两融余额",
    },
    "macro:cn:m2": {
        "title": "M2 货币供应量",
        "unit": "亿元",
        "description": "M2 月度余额及 M1/M2 年增率（东财数据中心）",
    },
    "macro:cn:m1": {
        "title": "M1 货币供应量",
        "unit": "亿元",
        "description": "M1 月度余额及年增率（东财数据中心）",
    },
    "macro:us:fed_rate": {
        "title": "美联储基准利率",
        "unit": "%",
        "decimals": 2,
        "description": "美国联邦基金利率目标区间上限（东财数据中心，2008-01 起）",
    },
    "price:us:cpi_core": {
        "title": "美国核心 CPI 同比",
        "unit": "%",
        "decimals": 1,
        "description": "美国核心 CPI（季调）当月同比（东财数据中心，2008-01 起）",
    },
    "price:us:cpi": {
        "title": "美国 CPI 同比",
        "unit": "%",
        "decimals": 1,
        "description": "美国 CPI（非季调）当月同比（东财数据中心，2008-01 起）",
    },
    "bond:us:2y": {
        "title": "美债收益率 2Y",
        "unit": "%",
        "decimals": 4,
        "description": "美国国债收益率（2年）",
    },
    "bond:us:10y": {
        "title": "美债收益率 10Y",
        "unit": "%",
        "decimals": 4,
        "description": "美国国债收益率（10年）",
    },
    "bond:us:30y": {
        "title": "美债收益率 30Y",
        "unit": "%",
        "decimals": 4,
        "description": "美国国债收益率（30年）",
    },
    "price:cn:cpi": {
        "title": "CPI 同比",
        "unit": "%",
        "decimals": 1,
        "description": "CPI 月度同比与 CPI 年度均值（东财数据中心）",
    },
    "price:cn:cpi_core": {
        "title": "核心 CPI 同比",
        "unit": "%",
        "decimals": 1,
        "description": "核心 CPI（扣除食品和能源）月度同比（财经M平方，2006-01 起）",
    },
    "price:cn:ppi": {
        "title": "PPI 同比",
        "unit": "%",
        "decimals": 1,
        "description": "PPI 月度同比（东财数据中心，2006-01 起）",
    },
    "bond:cn:1y": {
        "title": "国债收益率 1Y",
        "unit": "%",
        "decimals": 4,
        "description": "中债国债到期收益率（1年）",
    },
    "bond:cn:10y": {
        "title": "国债收益率 10Y",
        "unit": "%",
        "decimals": 4,
        "description": "中债国债到期收益率（10年）",
    },
    "bond:cn:30y": {
        "title": "国债收益率 30Y",
        "unit": "%",
        "decimals": 4,
        "description": "中债国债到期收益率（30年）",
    },
    "valuation:all_a:pe": {
        "title": "全A等权PE",
        "unit": "倍",
        "decimals": 2,
        "description": "全A等权滚动市盈率（乐咕乐股，TTM）",
    },
    "valuation:all_a:pb": {
        "title": "全A等权PB",
        "unit": "倍",
        "decimals": 2,
        "description": "全A等权市净率（乐咕乐股）",
    },
    "valuation:all_a:pe_pct": {
        "title": "全A PE 分位",
        "unit": "%",
        "decimals": 1,
        "description": "全A等权PE 全历史滚动分位（0-100，截至当日含当日）",
    },
    "valuation:all_a:pb_pct": {
        "title": "全A PB 分位",
        "unit": "%",
        "decimals": 1,
        "description": "全A等权PB 全历史滚动分位（0-100，截至当日含当日）",
    },
    "erp:csi800": {
        "title": "股债性价比 ERP",
        "unit": "%",
        "decimals": 2,
        "description": "中证800(000906)加权EP(100/PE) − 10Y国债；meta 含 ep/y10 分量",
    },
}

# 前端图表布局（方案 B 静态模式也依赖此顺序）
CHART_LAYOUT: list[dict] = [
    {"id": "market", "title": "全A走势与成交量", "kind": "market", "metrics": ["index:000985:close"]},
    {"id": "median", "title": "全A涨跌中位数", "kind": "median", "metrics": ["all_a:median_pct"]},
    {"id": "index_159259", "title": "成长100 ETF", "kind": "index", "metrics": ["index:159259:close"]},
    {"id": "index_h30269", "title": "红利低波指数", "kind": "index", "metrics": ["index:H30269:close"]},
    {"id": "margin", "title": "两融数据", "kind": "margin", "metrics": ["margin:balance"]},
    {"id": "macro", "title": "货币供应量 M1/M2", "kind": "macro", "metrics": ["macro:cn:m2", "macro:cn:m1"]},
    {"id": "price", "title": "CPI、核心CPI与PPI", "kind": "price", "metrics": ["price:cn:cpi", "price:cn:cpi_core", "price:cn:ppi"]},
    {"id": "us_yield", "title": "美联储利率与美债", "kind": "us_yield", "metrics": ["macro:us:fed_rate", "bond:us:2y", "bond:us:10y", "bond:us:30y"]},
    {"id": "us_price", "title": "美国 CPI 与核心 CPI", "kind": "us_price", "metrics": ["price:us:cpi", "price:us:cpi_core"]},
    {"id": "yield", "title": "国债收益率", "kind": "yield", "metrics": ["bond:cn:10y", "bond:cn:1y", "bond:cn:30y"]},
    {"id": "erp", "title": "股债性价比", "kind": "erp", "metrics": ["erp:csi800"]},
    {"id": "valuation", "title": "全A估值分位", "kind": "valuation", "metrics": ["valuation:all_a:pe_pct", "valuation:all_a:pb_pct"]},
]
