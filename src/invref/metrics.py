"""指标注册表：metric 名称 → 展示元信息 与 前端图表布局。"""
from __future__ import annotations

METRIC_META: dict[str, dict] = {
    "index:000985:close": {
        "title": "中证全指",
        "unit": "点",
        "description": "全A走势（中证全指收盘），meta.amount 为全市场成交额（亿元）",
    },
    "index:980080:close": {
        "title": "成长100",
        "unit": "点",
        "description": "中证成长100指数（980080）收盘",
    },
    "index:H30269:close": {
        "title": "红利低波",
        "unit": "点",
        "description": "中证红利低波动指数（H30269）收盘",
    },
    "all_a:turnover": {
        "title": "全A成交额",
        "unit": "亿元",
        "description": "中证全指成分合计成交额，代表全市场成交额",
    },
    "all_a:median_pct": {
        "title": "全A涨跌中位数",
        "unit": "%",
        "description": "全市场个股当日涨跌幅的中位数（东财全市场快照口径，含北交所）",
    },
    "margin:balance": {
        "title": "两融余额",
        "unit": "亿元",
        "description": "沪深两市融资余额与融券余额合计",
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
}

# 前端图表布局（方案 B 静态模式也依赖此顺序）
CHART_LAYOUT: list[dict] = [
    {"id": "market", "title": "全A走势与成交量", "kind": "market", "metrics": ["index:000985:close"]},
    {"id": "median", "title": "全A涨跌中位数", "kind": "median", "metrics": ["all_a:median_pct"]},
    {"id": "index_980080", "title": "成长100指数", "kind": "index", "metrics": ["index:980080:close"]},
    {"id": "index_h30269", "title": "红利低波指数", "kind": "index", "metrics": ["index:H30269:close"]},
    {"id": "margin", "title": "两融数据", "kind": "margin", "metrics": ["margin:balance"]},
    {"id": "yield", "title": "国债收益率", "kind": "yield", "metrics": ["bond:cn:10y", "bond:cn:1y", "bond:cn:30y"]},
]
