# InvRef — 自用投资参考数据查询站点

一个自用的 A 股投资参考数据站：自动采集公开免费数据源，SQLite 本地存储，网页图表展示。

## 指标与数据源

| 指标 | metric | 当前环境已验证源 | 本机直连备源 |
|---|---|---|---|
| 全A走势 | `index:000985:close` | 中证指数官网 API ✅ | 东财 `index_zh_a_hist` |
| 全A成交额 | `all_a:turnover` | 中证指数官网（tradingValue，亿元）✅ | 东财成交额 |
| 全A涨跌中位数 | `all_a:median_pct` | 东财 push2delay 全市场快照 ✅ + 腾讯K线历史回填 ✅ | 东财 `stock_zh_a_spot_em` |
| 红利低波 | `index:H30269:close` | 中证指数官网 API ✅ | 东财 |
| 成长100 | `index:159259:close` | 腾讯 成长ETF(159259) 前复权K线 ✅（口径即 ETF 净值，仅1年历史） | —（不再用指数直连） |
| 两融余额 | `margin:balance` | 金十数据中心 fs_1/fs_2 ✅ | 上交所/深交所官网 |
| 货币供应量 | `macro:cn:m1/m2`（2008-01 起；图：M2余额 + M2/M1年增率） | 东财数据中心 RPT_ECONOMY_CURRENCY_SUPPLY ✅（月度） | —（金十仅 M2 同比无绝对量） |
| 物价指数 | `price:cn:cpi`（2008-01 起）/ `price:cn:ppi`（2006-01 起）；图：同比双线 | 东财数据中心 RPT_ECONOMY_CPI / RPT_ECONOMY_PPI ✅（月度） | —（金十仅增速且滞后） |
| 国债 1Y | `bond:cn:1y` | ⚠️ 中债官网（当前环境不可达，本机可用） | 中债 `bond_china_yield` |
| 国债 10Y/30Y | `bond:cn:10y/30y` | 东财数据中心 RPTA_WEB_TREASURYYIELD ✅ | 中债（同源，含全期限） |

> ✅ = 已在当前开发环境实测跑通。采集器均为多源回退，接口漂移/单源不可达时自动切备源。

## 架构

方案 A（默认，本机/服务器常开）：

```
多数据源（中证官网/东财行情/东财数据中心/腾讯/金十）
   │  每日定时采集（幂等 upsert，重试+update_log 审计）
   ▼
SQLite (data/invref.db)
   │  FastAPI 只读 API（/api/meta /api/series/{metric} /api/status）
   ▼
Vue3 + ECharts 深色主题图表页（http://127.0.0.1:8000）
```

方案 B（可选，零服务器）：`.github/workflows/daily.yml` 每天在 GitHub Actions 上
采集 → `invref-export` 导出 JSON → 构建 → 部署 GitHub Pages；前端自动降级到静态 JSON 模式。

## 快速开始

```bash
# Python 依赖（Python 3.11+）
python -m pip install -e .

# 首次：全量采集（指数历史/两融/国债/今日涨跌中位数）
python -m invref.scripts.daily_update

# 涨跌中位数历史回填（腾讯K线并发拉取，默认近2年；可 --years 调整）
python -m invref.scripts.backfill_median --years 2 --threads 16

# 启动站点（API + 静态页面）→ http://127.0.0.1:8000
python -m invref.api.main

# 前端开发模式（可选）→ http://127.0.0.1:5173（/api 已代理到 8000）
cd web && npm install && npm run dev

# 导出静态 JSON（方案B 用）→ web/public/data/
python -m invref.scripts.export_static
```

## 每日定时更新

- 方式一（推荐，进程内调度）：启动 API 前设置环境变量后直接跑：
  ```bash
  set INVREF_SCHEDULE=1
  python -m invref.api.main   # 内置 APScheduler，每天 19:30 自动采集
  ```
- 方式二：Windows 任务计划程序每天 19:30 执行 `python -m invref.scripts.daily_update`。
- 失败审计：`update_log` 表记录每次采集的 metric/状态/行数/错误信息。

## 目录结构

```
src/invref/
  config.py            # 配置（DB 路径、调度、东财主机可覆盖）
  db.py / repo.py      # SQLite 连接、幂等读写
  metrics.py           # 指标注册表 + 图表布局
  collectors/
    clients.py         # 多数据源客户端（东财/中证官网/腾讯/金十）
    index_daily.py     # 指数历史 + 全A成交额（多源回退）
    margin.py          # 两融余额（金十/交易所）
    bond_yield.py      # 国债 1Y/10Y/30Y（中债/东财数据中心）
    market_median.py   # 全A涨跌中位数（每日快照）
    macro.py           # 货币供应量 M1/M2（东财数据中心）
    price.py           # 物价指数 CPI/PPI 同比（东财数据中心）
  api/main.py          # FastAPI（含可选 APScheduler 调度）
  scripts/             # daily_update / backfill_median / export_static
web/                   # Vue3 + Vite + ECharts
.github/workflows/     # 方案B：GitHub Actions 每日构建 + Pages
data/invref.db         # 运行时数据库（gitignore）
```

## 数据口径与已知 TODO

- 全A涨跌中位数：每日快照口径为东财沪深京A 全体个股涨跌幅中位数（含北交所、剔除停牌）；
  历史回填用腾讯前复权收盘价计算涨跌幅（≈交易所口径），**仅覆盖当前存续股票（幸存者偏差）**。
- 成长100：口径即为**易方达成长ETF(159259) 前复权价**（跟踪中证成长100指数(980080)），非指数点位；
  腾讯源仅约 1 年历史。
- 国债 1Y：中债官网在本开发环境不可达，当前只有 10Y/30Y（东财数据中心）；本机部署后自动补全。
- 历史回填默认 2 年（约 485 个交易日），需要更长历史可调 `--years`（耗时约 每2年 17 分钟/16线程）。
- 免费数据源接口可能漂移：采集器带重试与多源回退，更新失败会记录在 `update_log`，不会写脏数据。

## 免责声明

数据来自公开免费源，仅供个人研究参考，不构成投资建议。
