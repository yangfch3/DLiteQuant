"""方案B口子：把 SQLite 全量导出为 JSON 快照（web/public/data/）。

invref-export [--out web/public/data]
前端在静态模式下直接读取这些 JSON 文件，可配合 GitHub Actions + Pages 零服务器部署。
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .. import config, db, repo
from ..metrics import METRIC_META

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def _safe_name(metric: str) -> str:
    return metric.replace(":", "_")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出 SQLite 到 JSON 静态快照")
    parser.add_argument("--out", default=str(Path(config.PROJECT_ROOT) / "web" / "public" / "data"))
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with db.session() as conn:
        metrics = repo.list_metrics(conn)
        for m in metrics:
            points = repo.query_series(conn, m["metric"])
            path = out_dir / f"{_safe_name(m['metric'])}.json"
            path.write_text(
                json.dumps(
                    [{"date": p["date"], "value": p["value"], "meta": p["meta"]} for p in points],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        meta_out = [
            {
                "metric": m["metric"],
                "title": METRIC_META.get(m["metric"], {}).get("title", m["metric"]),
                "unit": METRIC_META.get(m["metric"], {}).get("unit", ""),
                "description": METRIC_META.get(m["metric"], {}).get("description", ""),
                "n": m["n"],
                "first_date": m["first_date"],
                "last_date": m["last_date"],
                "updated_at": m["updated_at"],
            }
            for m in metrics
        ]
        (out_dir / "meta.json").write_text(
            json.dumps(meta_out, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    log = logging.getLogger("invref.export")
    log.info("导出完成：%d 个指标 → %s", len(metrics), out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
