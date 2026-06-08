"""
存储模块 — SQLite 记录价格快照与当日提醒状态。
"""

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "alerts.db"


def get_conn() -> sqlite3.Connection:
    """获取数据库连接，自动创建目录。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化表结构。"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS price_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT,
            fund_type TEXT NOT NULL,
            price REAL NOT NULL,
            price_date TEXT,
            fetched_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            name TEXT,
            alert_date TEXT NOT NULL,
            triggered_at TEXT NOT NULL,
            reasons TEXT NOT NULL,
            UNIQUE(code, alert_date)
        );

        CREATE INDEX IF NOT EXISTS idx_price_code ON price_snapshots(code, fetched_at);
        CREATE INDEX IF NOT EXISTS idx_alert_code_date ON alert_log(code, alert_date);
    """)
    conn.commit()
    conn.close()
    logger.info("数据库初始化完成: %s", DB_PATH)


# ---- 价格快照 ----


def save_price_snapshot(code: str, name: str, fund_type: str, price: float, price_date: str) -> None:
    """保存一次价格抓取记录。"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO price_snapshots (code, name, fund_type, price, price_date, fetched_at) VALUES (?,?,?,?,?,?)",
        (code, name, fund_type, price, price_date, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


# ---- 当天是否已提醒 ----


def already_alerted_today(code: str) -> bool:
    """检查某基金今天是否已经成功提醒过。"""
    today = date.today().isoformat()
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM alert_log WHERE code=? AND alert_date=?",
        (code, today),
    ).fetchone()
    conn.close()
    return row is not None


def mark_alerted(code: str, name: str, reasons: str) -> None:
    """记录一次提醒。"""
    today = date.today().isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO alert_log (code, name, alert_date, triggered_at, reasons) VALUES (?,?,?,?,?)",
        (code, name, today, datetime.now().isoformat(timespec="seconds"), reasons),
    )
    conn.commit()
    conn.close()


# ---- 辅助：获取最近快照 ----


def get_last_snapshot_price(code: str) -> Optional[float]:
    """获取最近一次快照价格，可用于比较变化。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT price FROM price_snapshots WHERE code=? ORDER BY fetched_at DESC LIMIT 1",
        (code,),
    ).fetchone()
    conn.close()
    if row:
        return row["price"]
    return None
