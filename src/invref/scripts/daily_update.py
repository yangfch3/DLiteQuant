"""每日数据更新入口：invref-collect。

运行全部采集器，把结果写入 SQLite；每个采集器独立记录 update_log。
"""
from __future__ import annotations

import argparse
import logging
import sys

from .. import db
from ..collectors import COLLECTORS

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="InvRef 每日数据采集")
    parser.add_argument("--verbose", "-v", action="store_true", help="DEBUG 日志")
    parser.add_argument("--skip", default="", help="跳过的采集器名称（逗号分隔，如：全A涨跌中位数）")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format=LOG_FORMAT,
        stream=sys.stdout,
    )
    log = logging.getLogger("invref.collect")

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    ok, fail = 0, 0
    with db.session() as conn:
        for name, fn in COLLECTORS:
            if name in skip:
                log.info("== 跳过：%s ==", name)
                continue
            log.info("== 开始：%s ==", name)
            try:
                fn(conn)
                ok += 1
            except Exception as e:  # noqa: BLE001
                log.exception("== %s 异常 ==", name)
                fail += 1

    log.info("采集完成：成功 %d / 失败 %d", ok, fail)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
