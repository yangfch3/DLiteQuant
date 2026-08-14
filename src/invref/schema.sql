-- 指标时间序列：每指标每日一行，value 为数值，meta 存附加字段（JSON）
CREATE TABLE IF NOT EXISTS series (
    metric     TEXT    NOT NULL,
    date       TEXT    NOT NULL,                -- YYYY-MM-DD
    value      REAL    NOT NULL,
    meta       TEXT,                            -- JSON 附加字段
    source     TEXT    NOT NULL DEFAULT 'akshare',
    updated_at TEXT    NOT NULL,
    PRIMARY KEY (metric, date)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_series_date ON series(date);

-- 采集运行日志
CREATE TABLE IF NOT EXISTS update_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    metric       TEXT    NOT NULL,
    run_date     TEXT    NOT NULL,
    rows_written INTEGER NOT NULL DEFAULT 0,
    status       TEXT    NOT NULL,              -- ok | error
    message      TEXT,
    started_at   TEXT    NOT NULL,
    finished_at  TEXT
);
