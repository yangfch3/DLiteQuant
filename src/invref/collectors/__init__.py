"""各指标采集器。"""
from . import bond_yield, index_daily, macro, margin, market_median, price, valuation

__all__ = ["index_daily", "margin", "bond_yield", "market_median", "valuation", "macro", "price"]

# 每日更新入口按此顺序执行（valuation 依赖 bond_yield 的 10Y 入库）
COLLECTORS = [
    ("指数历史", index_daily.collect),
    ("两融数据", margin.collect),
    ("国债收益率", bond_yield.collect),
    ("全A涨跌中位数", market_median.collect),
    ("估值与股债性价比", valuation.collect),
    ("货币供应量", macro.collect),
    ("物价指数", price.collect),
]
