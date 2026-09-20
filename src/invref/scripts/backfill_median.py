"""全A涨跌中位数历史回填：invref-backfill [--years 2] [--threads 12] [--dry-run]

用腾讯前复权日K按股拉取（当前环境验证可用，替代此环境不可用的 baostock），
由前复权收盘价计算每日涨跌幅，按日期分组求中位数，写入 all_a:median_pct；
同时把个股前复权日K线原样落库 stock_kline（备用数据，当前图表未使用）。

说明：
- 前复权收盘价计算的涨跌幅≈交易所口径（已做除权调整）；
- 代码列表来自东财 clist（沪深京A），带重试；失败时回退到上次成功保存的缓存
  （data/a_share_codes.json，缺新上市股票几天可接受）；
- 腾讯 fqkline 由 stgw/WAF 托管，突发并发会返回 501（waf.tencent.com 挑战页）：
  整体限速（默认 ≤8 请求/秒）+ 单股 4 次退避重试（3/6/12s）；本轮仍失败的券码，
  收尾以低并发（默认 2 线程）慢速补采一轮；
- 腾讯不支持的代码（920 开头北交所等）返回空、不写入、不计失败；
- 收尾核对 stock_kline 覆盖度：最新日期落后 A 股交易日历的券码会被列出，
  占比超阈值则返回 1（可用 --coverage-tolerance 调阈值，或 --no-coverage-check 关闭）；
- 不含"今天"（当日数据由每日实时快照采集，避免盘中/收盘口径冲突）。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from .. import config, db, repo
from ..collectors import clients
from ..collectors.base import retry

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"

CODES_CACHE = config.DATA_DIR / "a_share_codes.json"

# 腾讯 WAF 相关参数
FETCH_ATTEMPTS = 4   # 单次请求总尝试次数（含首次）
FETCH_DELAY = 3.0    # 退避基数秒，retry() 内为 delay * 2**i → 3/6/12s
MAX_REQ_PER_SEC = 12.0  # 全局限速：所有线程合计的请求/秒上限（5年窗口下 CI 90min 超时的折中）
RETRY_THREADS = 2      # 收尾补采并发
RETRY_SLEEP = 0.6      # 补采时每次提交之间的间隔秒

# 覆盖度核对阈值
COVERAGE_TOLERANCE = 0.10  # 落后券码占比超过它即判失败
CAL_GAP_DAYS = 4           # 相邻交易日最大间隔（跨长假）；超过则视为数据缺口

KLine = tuple[str, float, float, float, float, float]  # (date, open, close, high, low, volume)

_KLINE_SQL = """INSERT INTO stock_kline(code, date, open, close, high, low, volume, source, fetched_at)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(code, date) DO UPDATE SET
                  open=excluded.open, close=excluded.close, high=excluded.high,
                  low=excluded.low, volume=excluded.volume,
                  source=excluded.source, fetched_at=excluded.fetched_at"""


def _rate_limiter(per_sec: float):
    """返回一个全局节流函数：所有调用者合计不超过 per_sec 次/秒。"""
    lock = threading.Lock()
    next_at = 0.0

    def wait() -> None:
        nonlocal next_at
        if per_sec <= 0:
            return
        with lock:
            now = time.monotonic()
            if now < next_at:
                time.sleep(next_at - now)
                now = time.monotonic()
            next_at = max(now, next_at) + 1.0 / per_sec

    return wait


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


def _fetch_stock(code: str, start_s: str, end_s: str, wait) -> tuple[list[KLine], bool]:
    """按股从 end 往前翻页拉取前复权日K，返回 (rows, 是否取全)（日期正序）。

    腾讯 fqkline 接口忽略 start、只返回截至 end 的最近 count(≤640) 根，
    因此必须从 end 往前翻页：每批取最近 640 根，下一批以本批第一根的前一天为 end。
    任一批次在被 WAF 拦截（501）且退避重试耗尽后，返回已拿到的部分数据并标记未取全，
    由调用方收尾补采——避免静默丢数据。
    """
    tx_code = clients.tencent_code_of(code)
    rows: dict[str, tuple[float, float, float, float, float]] = {}
    complete = True
    e = end_s
    while True:
        try:
            kls = retry(
                lambda: clients.tencent_kline(tx_code, start_s, e, count=640),
                attempts=FETCH_ATTEMPTS,
                delay=FETCH_DELAY,
            )
        except Exception:  # noqa: BLE001
            complete = False
            break
        if not kls:
            break
        for k in kls:
            try:
                rows[k[0]] = (float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]))
            except (ValueError, IndexError):
                continue
        first = kls[0][0]
        if len(kls) < 640 or first <= start_s:
            break
        nd = date.fromisoformat(first) - timedelta(days=1)
        if nd.isoformat() >= e:  # 防死循环
            break
        e = nd.isoformat()
        wait()  # 翻页也计入限速
    return [(d, *rows[d]) for d in sorted(rows)], complete


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="全A涨跌中位数历史回填（腾讯K线并发）")
    parser.add_argument("--years", type=int, default=2, help="回填年数（默认2年）")
    parser.add_argument("--threads", type=int, default=12, help="并发线程数")
    parser.add_argument("--max-rps", type=float, default=MAX_REQ_PER_SEC, help="全局限速：请求/秒上限")
    parser.add_argument("--retry-threads", type=int, default=RETRY_THREADS, help="收尾补采并发数")
    parser.add_argument("--coverage-tolerance", type=float, default=COVERAGE_TOLERANCE,
                        help="覆盖度核对：落后券码占比超过它即返回 1")
    parser.add_argument("--no-coverage-check", action="store_true", help="跳过覆盖度核对")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
    log = logging.getLogger("invref.backfill")

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=args.years * 366)
    log.info("获取全市场代码列表…")
    codes = _load_codes(log)
    log.info("共 %d 只股票，%d 线程拉取腾讯日K（%s ~ %s，限速 %.1f 请求/秒）…",
             len(codes), args.threads, start, end, args.max_rps)

    wait = _rate_limiter(args.max_rps)
    agg: dict[str, list[float]] = {}
    kline_total = 0
    done = empty = 0
    retry_codes: list[str] = []
    with db.session() as conn:
        now = db.utcnow()

        def handle(code: str, kls: list[KLine], complete: bool) -> None:
            nonlocal kline_total, done, empty
            done += 1
            if not complete:
                retry_codes.append(code)
            if not kls:
                empty += 1
                return
            if not args.dry_run:
                conn.executemany(_KLINE_SQL, [(code, k[0], *k[1:6], "tencent", now) for k in kls])
                kline_total += len(kls)
            prev: float | None = None
            for k in kls:
                if prev is not None and prev > 0:
                    agg.setdefault(k[0], []).append(round((k[2] - prev) / prev * 100, 4))
                prev = k[2]
            if done % 500 == 0:
                log.info("进度 %d/%d", done, len(codes))

        with ThreadPoolExecutor(max_workers=args.threads) as ex:
            futs = {
                ex.submit(_fetch_stock, c, start.isoformat(), end.isoformat(), wait): c
                for c in codes
            }
            for fut in as_completed(futs):
                code = futs[fut]
                try:
                    kls, complete = fut.result()
                except Exception as e:  # noqa: BLE001
                    log.debug("单股失败: %s: %s", code, e)
                    handle(code, [], False)
                    continue
                handle(code, kls, complete)

        log.info("首轮完成：%d/%d 只，其中空数据 %d 只，需补采 %d 只",
                 done, len(codes), empty, len(retry_codes))

        # 收尾补采：低并发 + 慢速，救回被 WAF 突发拦截的券码（dry-run 也补，便于核对数据质量）
        if retry_codes:
            left = len(retry_codes)
            log.info("补采 %d 只（%d 线程，间隔 %.1fs）…", left, args.retry_threads, RETRY_SLEEP)
            still = 0
            with ThreadPoolExecutor(max_workers=max(1, args.retry_threads)) as ex:
                for code in retry_codes:
                    fut = ex.submit(_fetch_stock, code, start.isoformat(), end.isoformat(), wait)
                    time.sleep(RETRY_SLEEP)
                    try:
                        kls, complete = fut.result()
                    except Exception as e:  # noqa: BLE001
                        log.debug("补采失败: %s: %s", code, e)
                        kls, complete = [], False
                    if not complete:
                        still += 1
                    if kls:
                        conn.executemany(
                            _KLINE_SQL, [(code, k[0], *k[1:6], "tencent", now) for k in kls]
                        )
                        kline_total += len(kls)
                        prev: float | None = None
                        for k in kls:
                            if prev is not None and prev > 0:
                                agg.setdefault(k[0], []).append(round((k[2] - prev) / prev * 100, 4))
                            prev = k[2]
            if still:
                log.warning("补采后仍失败 %d 只（这些券码本次数据可能不全）", still)
            else:
                log.info("补采全部成功")

        log.info("拉取完成，共 %d 个交易日，个股K线 %d 行，开始聚合…", len(agg), kline_total)

        if len(agg) < 50:
            log.error("有效交易日太少（%d），可能腾讯K线在当前网络不可达，不写入", len(agg))
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
            n = repo.upsert_series(conn, "all_a:median_pct", rows, source="tencent")
            repo.log_update(conn, "all_a:median_pct", end.isoformat(), n, "ok", "backfill:tencent")
            repo.log_update(conn, "stock_kline", end.isoformat(), kline_total, "ok",
                            f"codes={done},empty={empty},failed={len(retry_codes)}")
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
    说明其 end 之前的数据缺失（WAF 拦截或长期停牌/退市）。
    """
    dates = [r[0] for r in conn.execute(
        "select distinct date from stock_kline where date between ? and ? order by date", (start_s, end_s)
    )]
    if not dates:
        return None
    ref = dates[-1]
    prev = dates[-2] if len(dates) > 1 else ref
    gap = (date.fromisoformat(ref) - date.fromisoformat(prev)).days
    if gap > CAL_GAP_DAYS:  # 参考交易日历本身疑似缺档（如整段被拦），以更早一天为基准
        log.warning("交易日历可疑：最新两个交易日 %s / %s 相隔 %d 天", prev, ref, gap)
    latest = {r[0]: r[1] for r in conn.execute(
        "select code, max(date) from stock_kline where date between ? and ? group by code",
        (start_s, end_s),
    )}
    behind = [c for c in codes if latest.get(c, "") < prev and not c.startswith("920")]
    missing = [c for c in behind if c not in latest]
    log.info("覆盖度：上一交易日 %s（窗口最新 %s）｜落后 %d 只，其中窗口内完全无数据 %d 只",
             prev, ref, len(behind), len(missing))
    if behind:
        log.info("落后样例：%s", ", ".join(behind[:10]))
    return len(behind)


if __name__ == "__main__":
    sys.exit(main())
