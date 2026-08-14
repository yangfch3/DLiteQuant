"""FastAPI 应用：只读查询接口 + 可选内嵌定时采集 + 静态前端托管。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import config, db, repo
from ..metrics import METRIC_META

log = logging.getLogger("invref.api")

WEB_DIST = Path(config.PROJECT_ROOT) / "web" / "dist"


def _metric_meta(metric: str) -> dict:
    return METRIC_META.get(metric, {})


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    scheduler = None
    if config.SCHEDULE_ENABLED:
        from apscheduler.schedulers.background import BackgroundScheduler
        from ..scripts import daily_update

        scheduler = BackgroundScheduler(timezone=config.TIMEZONE)
        scheduler.add_job(
            daily_update.main,
            "cron",
            hour=config.DAILY_HOUR,
            minute=config.DAILY_MINUTE,
            id="daily_collect",
            misfire_grace_time=3600,
            coalesce=True,
        )
        scheduler.start()
        log.info("APScheduler 已启动：每日 %02d:%02d 采集", config.DAILY_HOUR, config.DAILY_MINUTE)
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)


app = FastAPI(title="InvRef 投资参考数据", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "db": str(config.DB_PATH)}


@app.get("/api/meta")
def meta() -> list[dict]:
    with db.session() as conn:
        metrics = repo.list_metrics(conn)
    out = []
    for m in metrics:
        info = _metric_meta(m["metric"])
        out.append(
            {
                "metric": m["metric"],
                "title": info.get("title", m["metric"]),
                "unit": info.get("unit", ""),
                "description": info.get("description", ""),
                "n": m["n"],
                "first_date": m["first_date"],
                "last_date": m["last_date"],
                "updated_at": m["updated_at"],
            }
        )
    return out


@app.get("/api/series/{metric}")
def series(metric: str, start: str | None = None, end: str | None = None) -> dict:
    with db.session() as conn:
        rows = repo.query_series(conn, metric, start, end)
    if not rows:
        # 若指标从未入库，也返回空序列而非 404（前端统一处理）
        info = _metric_meta(metric)
        return {
            "metric": metric,
            "title": info.get("title", metric),
            "unit": info.get("unit", ""),
            "points": [],
        }
    info = _metric_meta(metric)
    return {
        "metric": metric,
        "title": info.get("title", metric),
        "unit": info.get("unit", ""),
        "points": rows,
    }


@app.get("/api/status")
def status() -> dict:
    with db.session() as conn:
        metrics = repo.list_metrics(conn)
        logs = repo.last_update_log(conn, 30)
    return {"metrics": metrics, "last_updates": logs}


# 托管前端构建产物（若存在）
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")


def main() -> None:
    import os

    import uvicorn

    host = os.getenv("INVREF_HOST", "0.0.0.0")
    port = int(os.getenv("INVREF_PORT", "8000"))
    uvicorn.run("invref.api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
