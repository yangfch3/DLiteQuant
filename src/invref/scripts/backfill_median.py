"""全A涨跌中位数历史回填：invref-backfill [--years 2] [--threads 8] [--dry-run]

逐只股票取前复权日线（**多源按需降级**，见 collectors/stock_daily.py），
由前复权收盘价计算每日涨跌幅，按日期分组求中位数，写入 all_a:median_pct；
同时把个股日线落库 stock_kline（备用数据，当前图表未使用）。

说明：
- 源链：新浪（日线 + qfq 因子折算前复权，5 年窗口 1 次拿完，覆盖北交所）
  → 腾讯 fqkline（640/页翻页）
  → baostock（仅收尾串行补采用，其客户端多线程会卡死）；
  任一只股票只要有一个源成功即算完成，单只失败不影响其他股票；
- 行情站点按累计请求量做 WAF 封禁（腾讯 501、新浪 456），因此全部出站请求
  走同一个全局限速器（默认 3.5 请求/秒）；单只总请求数有硬上限；
- 代码列表来自东财 clist（沪深京A），带重试；失败时回退到上次成功保存的缓存
  （data/a_share_codes.json，缺新上市股票几天可接受）；
- 收尾核对 stock_kline 覆盖度：最新日期落后 A 股交易日历的券码会被列出，
  占比超阈值则返回 1（可用 --coverage-tolerance 调阈值，或 --no-coverage-check 关闭）；
- 不含"今天"（当日数据由每日实时快照采集，避免盘中/收盘口径冲突）。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from .. import config, db, repo
from ..collectors import clients, stock_daily
from ..collectors.base import RateLimiter, retry

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"

log = logging.getLogger("invref.backfill")

CODES_CACHE = config.DATA_DIR / "a_share_codes.json"

MAX_REQ_PER_SEC = 3.5   # 全局限速：所有线程合计请求/秒（12/s 实测会触发 WAF 封禁）
FETCH_ATTEMPTS = 3      # 单只股票尝试轮数（源内已有 host 级降级）
FETCH_DELAY = 5.0       # 轮间隔基数秒（5/10）；WAF 封禁通常持续数十秒
RETRY_THREADS = 1       # 收尾补采并发（baostock 客户端多线程会卡死，故串行）
RETRY_SLEEP = 0.5       # 补采时每次提交之间的间隔秒

COVERAGE_TOLERANCE = 0.10  # 落后券码占比超过它即判失败
CAL_GAP_DAYS = 4           # 相邻交易日最大间隔（跨长假）；超过则视为数据缺口

KLine = tuple[str, float, float, float, float, float]  # (date, close, open, high, low, volume)

_KLINE_SQL = """INSERT INTO stock_kline(code, date, open, close, high, low, volume, source, fetched_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(code, date) DO UPDATE SET
                  open=excluded.open, close=excluded.close, high=excluded.high,
                  low=excluded.low, volume=excluded.volume,
                  source=excluded.source, fetched_at=excluded.fetched_at"""


def _load_codes(log) -> list[str]:
    try:
        items = retry(clients.em_clist_all, attempts=3, delay=2.0)
        codes = [x["f12"] for x in items if x.get("f12")]
        if codes:
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            CODES_CACHE.write_text(json.dumps(codes), encoding="utf-8")
            return codes
    except Exception as e:  # noqa: BLE001
        log.warning("代码列表拉取失败: %s", e)
    if CODES_CACHE.exists():
        cached = json.loads(CODES_CACHE.read_text(encoding="utf-8"))
        log.warning("使用缓存代码列表 %d 只（数据源 %s 不可达）", len(cached), clients.EM_HOST)
        return cached
    raise RuntimeError("代码列表获取失败且无缓存可用")


def _fetch_stock(code: str, start_s: str, end_s: str, chain) -> tuple[list[KLine], str, bool]:
    """按源链取单只股票日线，返回 (rows, 数据源名, 是否零数据)。

    源内已做「host / 页面级降级」，这里只做「源级降级 + 轮级退避：
    某源报错（WAF 封禁、超时）时换下一个源；全部源报错则退避后重试下一轮；
    某源明确返回空（代码不存在）视为永久失败，不重试。
    """
    last = ""
    for attempt in range(FETCH_ATTEMPTS):
        errors = []
        for src in chain:
            try:
                rows = src(code, start_s, end_s)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{src.name}: {str(e)[:60]}")
                log.debug("[%s] %s 失败: %s", code, src.name, e)
                continue
            if not rows:
                last = f"{src.name}: empty"
                break
            return rows, src.name, False
        last = "; ".join(errors) or last
        if attempt < FETCH_ATTEMPTS - 1:
            time.sleep(FETCH_DELAY * (2**attempt))
    log.debug("[%s] 全部源失败: %s", code, last)
    return [], "", True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="全A涨跌中位数历史回填（多源按需降级）")
    parser.add_argument("--years", type=int, default=2, help="回填年数（默认2年）")
    parser.add_argument("--threads", type=int, default=8, help="并发线程数")
    parser.add_argument("--max-rps", type=float, default=MAX_REQ_PER_SEC, help="全局限速：请求/秒上限")
    parser.add_argument("--retry-threads", type=int, default=RETRY_THREADS, help="收尾补采并发数")
    parser.add_argument("--with-baostock", action="store_true", help="补采轮追加 baostock 源（仅串行）")
    parser.add_argument("--coverage-tolerance", type=float, default=COVERAGE_TOLERANCE,
                        help="覆盖度核对：落后券码占比超过它即返回 1")
    parser.add_argument("--no-coverage-check", action="store_true", help="跳过覆盖度核对")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=args.years * 366)
    log.info("获取全市场代码列表…")
    codes = _load_codes(log)

    limiter = RateLimiter(args.max_rps)
    chain = stock_daily.default_chain(limiter)
    retry_chain = stock_daily.default_chain(limiter, include_baostock=args.with_baostock)
    log.info("共 %d 只股票，%d 线程，源链 %s（%s ~ %s，限速 %.1f 请求/秒）…",
             len(codes), args.threads, " → ".join(s.name for s in retry_chain),
             start, end, args.max_rps)

    agg: dict[str, list[float]] = {}
    kline_total = 0
    done = empty = 0
    retry_codes: list[str] = []
    src_stat: Counter = Counter()
    with db.session() as conn:
        now = db.utcnow()

        def handle(code: str, kls: list[KLine], src_name: str, zero: bool) -> None:
            nonlocal kline_total, done, empty
            done += 1
            if zero:
                empty += 1
                retry_codes.append(code)
                if done % 500 == 0:
                    log.info("进度 %d/%d（零数据 %d，待补采 %d）", done, len(codes), empty, len(retry_codes))
                return
            src_stat[src_name] += 1
            if not args.dry_run:
                conn.executemany(_KLINE_SQL, [(code, k[0], *k[1:6], src_name, now) for k in kls])
                kline_total += len(kls)
            prev: float | None = None
            for k in kls:
                if prev is not None and prev > 0:
                    agg.setdefault(k[0], []).append(round((k[1] - prev) / prev * 100, 4))
                prev = k[1]
            if done % 500 == 0:
                log.info("进度 %d/%d（零数据 %d，待补采 %d）", done, len(codes), empty, len(retry_codes))

        with ThreadPoolExecutor(max_workers=args.threads) as ex:
            futs = {
                ex.submit(_fetch_stock, c, start.isoformat(), end.isoformat(), chain): c
                for c in codes
            }
            for fut in as_completed(futs):
                code = futs[fut]
                try:
                    kls, src_name, zero = fut.result()
                except Exception as e:  # noqa: BLE001
                    log.debug("单股异常: %s: %s", code, e)
                    kls, src_name, zero = [], "", True
                handle(code, kls, src_name, zero)

        log.info("首轮完成：%d/%d 只，零数据 %d 只；源分布 %s",
                 done, len(codes), empty, dict(src_stat))

        # 收尾补采：串行 + 退避，救回被 WAF 封禁的券码（dry-run 也补，便于核对数据质量）
        if retry_codes:
            log.info("补采 %d 只（%d 线程，间隔 %.1fs，源链含 baostock=%s）…",
                     len(retry_codes), args.retry_threads, RETRY_SLEEP, args.with_baostock)
            left = list(retry_codes)
            still: list[str] = []
            recovered = 0
            with ThreadPoolExecutor(max_workers=max(1, args.retry_threads)) as ex:
                for code in left:
                    fut = ex.submit(_fetch_stock, code, start.isoformat(), end.isoformat(), retry_chain)
                    time.sleep(RETRY_SLEEP)
                    try:
                        kls, src_name, zero = fut.result()
                    except Exception as e:  # noqa: BLE001
                        log.debug("补采异常: %s: %s", code, e)
                        kls, src_name, zero = [], "", True
                    if zero:
                        still.append(code)
                        continue
                    recovered += 1
                    src_stat[src_name] += 1
                    if kls and not args.dry_run:
                        conn.executemany(_KLINE_SQL, [(code, k[0], *k[1:6], src_name, now) for k in kls])
                        kline_total += len(kls)
                    prev: float | None = None
                    for k in kls:
                        if prev is not None and prev > 0:
                            agg.setdefault(k[0], []).append(round((k[1] - prev) / prev * 100, 4))
                        prev = k[1]
            log.info("补采完成：救回 %d 只，仍零数据 %d 只", recovered, len(still))
            if still:
                log.warning("以下券码本轮无数据（腾讯/新浪均不支持或已被封）共 %d 只，样例：%s",
                            len(still), ", ".join(still[:10]))
            retry_codes = still

        log.info("拉取完成，共 %d 个交易日，个股K线 %d 行，源分布 %s，开始聚合…",
                 len(agg), kline_total, dict(src_stat))

        if len(agg) < 50:
            log.error("有效交易日太少（%d），可能行情源在当前网络不可达，不写入", len(agg))
            return 1

        rows = []
        for d in sorted(agg):
            vals = sorted(agg[d])
            n = len(vals)
            med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
            up = sum(1 for v in vals if v > 0)
            down = sum(1 for v in vals if v < 0)
            rows.append(
                (
                    d,
                    round(med, 2),
                    {"up": up, "down": down, "flat": n - up - down, "total": n, "up_ratio": round(up / max(n, 1), 4)},
                )
            )

        if args.dry_run:
            print("最近 5 个交易日：")
            for r in rows[-5:]:
                print("  ", r)
        else:
            n = repo.upsert_series(conn, "all_a:median_pct", rows, source="backfill")
            repo.log_update(conn, "all_a:median_pct", end.isoformat(), n, "ok", "backfill:multi-source")
            repo.log_update(conn, "stock_kline", end.isoformat(), kline_total, "ok",
                            f"codes={done},empty={empty},failed={len(retry_codes)},src={dict(src_stat)}")
            log.info("已写入 all_a:median_pct %d 行，stock_kline %d 行", n, kline_total)

        incomplete = _report_coverage(conn, codes, start.isoformat(), end.isoformat(), log)
        if args.no_coverage_check:
            return 0
        if incomplete is None:
            log.warning("覆盖度核对跳过（窗口内无任何K线数据）")
            return 1 if not args.dry_run else 0
        ratio = incomplete / max(len(codes), 1)
        if ratio > args.coverage_tolerance:
            log.error("覆盖度核对未通过：%d/%d 只（%.1f%%）落后最新交易日，超过阈值 %.1f%%",
                      incomplete, len(codes), ratio * 100, args.coverage_tolerance * 100)
            return 1
        log.info("覆盖度核对通过：落后券码 %d/%d（%.1f%%）", incomplete, len(codes), ratio * 100)
    return 0


def _report_coverage(conn, codes: list[str], start_s: str, end_s: str, log) -> int | None:
    """核对 stock_kline 覆盖度：列出最新日期落后 A 股交易日历的券码，返回其数量。

    "最新交易日"由库内全部券码的日期并集自行校准（不依赖外部节假日表）：
    取最近的相邻两个交易日，倒数第二个即视为"上一交易日"。某券码的最新日期早于它，
    说明其 end 之前的数据缺失（被封禁或长期停牌/退市）。
    """
    dates = [r[0] for r in conn.execute(
        "select distinct date from stock_kline where date between ? and ? order by date", (start_s, end_s)
    )]
    if not dates:
        return None
    ref = dates[-1]
    prev = dates[-2] if len(dates) > 1 else ref
    gap = (date.fromisoformat(ref) - date.fromisoformat(prev)).days
    if gap > CAL_GAP_DAYS:
        log.warning("交易日历可疑：最新两个交易日 %s / %s 相隔 %d 天", prev, ref, gap)
    latest = {r[0]: r[1] for r in conn.execute(
        "select code, max(date) from stock_kline where date between ? and ? group by code",
        (start_s, end_s),
    )}
    behind = [c for c in codes if latest.get(c, "") < prev]
    missing = [c for c in behind if c not in latest]
    log.info("覆盖度：上一交易日 %s（窗口最新 %s）｜落后 %d 只，其中窗口内完全无数据 %d 只",
             prev, ref, len(behind), len(missing))
    if behind:
        log.info("落后样例：%s", ", ".join(behind[:10]))
    return len(behind)


if __name__ == "__main__":
    sys.exit(main())
