"""全A涨跌中位数历史回填：invref-backfill [--years 2] [--threads 12] [--dry-run]

用腾讯前复权日K按股拉取（当前环境验证可用，替代此环境不可用的 baostock），
由前复权收盘价计算每日涨跌幅，按日期分组求中位数，写入 all_a:median_pct。

说明：
- 前复权收盘价计算的涨跌幅≈交易所口径（已做除权调整）；
- 代码列表来自东财 clist（沪深京A），带重试；失败时回退到上次成功保存的缓存
  （data/a_share_codes.json，缺新上市股票几天可接受）；
- 腾讯不支持的代码自动跳过（含部分北交所）；
- 不含"今天"（当日数据由每日实时快照采集，避免盘中/收盘口径冲突）。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from .. import config, db, repo
from ..collectors import clients
from ..collectors.base import retry

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"

CODES_CACHE = config.DATA_DIR / "a_share_codes.json"


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


def _fetch_stock(code: str, start_s: str, end_s: str) -> list[tuple[str, float]]:
    """按股拉取前复权日K（自动翻页），返回 [(date, pct)]。"""
    tx_code = clients.tencent_code_of(code)
    out: list[tuple[str, float]] = []
    s = start_s
    while s < end_s:
        try:
            kls = retry(lambda: clients.tencent_kline(tx_code, s, end_s, count=640), attempts=2, delay=1.0)
        except Exception:  # noqa: BLE001
            break
        if not kls:
            break
        prev: float | None = None
        for k in kls:
            try:
                close = float(k[2])
            except (ValueError, IndexError):
                continue
            if prev is not None and prev > 0:
                out.append((k[0], round((close - prev) / prev * 100, 4)))
            prev = close
        if len(kls) < 640:
            break
        last = kls[-1][0]
        nd = date.fromisoformat(last) + timedelta(days=1)
        if nd >= date.fromisoformat(end_s):
            break
        s = nd.isoformat()
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="全A涨跌中位数历史回填（腾讯K线并发）")
    parser.add_argument("--years", type=int, default=2, help="回填年数（默认2年）")
    parser.add_argument("--threads", type=int, default=12, help="并发线程数")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写入")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
    log = logging.getLogger("invref.backfill")

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=args.years * 366)
    log.info("获取全市场代码列表…")
    codes = _load_codes(log)
    log.info("共 %d 只股票，%d 线程拉取腾讯日K（%s ~ %s）…", len(codes), args.threads, start, end)

    agg: dict[str, list[float]] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futs = {ex.submit(_fetch_stock, c, start.isoformat(), end.isoformat()): c for c in codes}
        for fut in as_completed(futs):
            try:
                for d, p in fut.result():
                    agg.setdefault(d, []).append(p)
            except Exception as e:  # noqa: BLE001
                log.debug("单股失败: %s", e)
            done += 1
            if done % 500 == 0:
                log.info("进度 %d/%d", done, len(codes))
    log.info("拉取完成，共 %d 个交易日，开始聚合…", len(agg))

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
        return 0

    with db.session() as conn:
        n = repo.upsert_series(conn, "all_a:median_pct", rows, source="tencent")
        repo.log_update(conn, "all_a:median_pct", end.isoformat(), n, "ok", "backfill:tencent")
    log.info("已写入 all_a:median_pct %d 行", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
