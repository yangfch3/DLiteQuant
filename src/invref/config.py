"""集中配置：路径、时区等均可通过环境变量覆盖。"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("INVREF_DATA", str(PROJECT_ROOT / "data")))
DB_PATH = Path(os.getenv("INVREF_DB", str(DATA_DIR / "invref.db")))

TIMEZONE = os.getenv("INVREF_TZ", "Asia/Shanghai")

# API 进程内是否启用 APScheduler 每日定时采集（1 启用）
SCHEDULE_ENABLED = os.getenv("INVREF_SCHEDULE", "0") == "1"
# 每日采集时刻（北京时间）
DAILY_HOUR = int(os.getenv("INVREF_DAILY_HOUR", "19"))
DAILY_MINUTE = int(os.getenv("INVREF_DAILY_MINUTE", "30"))
