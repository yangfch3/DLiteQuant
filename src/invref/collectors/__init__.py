"""各指标采集器。"""
from . import bond_yield, index_daily, margin, market_median

__all__ = ["index_daily", "margin", "bond_yield", "market_median"]

# 每日更新入口按此顺序执行
COLLECTORS = [
    ("指数历史", index_daily.collect),
    ("两融数据", margin.collect),
    ("国债收益率", bond_yield.collect),
    ("全A涨跌中位数", market_median.collect),
]
