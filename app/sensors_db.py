"""传感器时序数据 — SQLite 存储

存储后端：SQLite (logs/sensors.db)
表：sensor_readings —— 一行 = 一次成功的 BLE 轮询。

启动时自动把旧 recordings/{date}/sensors.jsonl 导入到 SQLite，
导入成功的文件改名为 sensors.jsonl.imported 防止重复导入。
"""

import json
import os
import sqlite3
import threading
import time
from datetime import datetime

from app.config import BASE_DIR, REC_DIR, log

LOG_DIR = os.path.join(BASE_DIR, "logs")
DB_FILE = os.path.join(LOG_DIR, "sensors.db")

_db_lock = threading.Lock()


# ── 连接 / Schema ─────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                ts          INTEGER PRIMARY KEY,
                date        TEXT    NOT NULL,
                time        TEXT    NOT NULL,
                breath_rate REAL,
                temperature REAL,
                posture     TEXT,
                battery     INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_sensor_readings_date ON sensor_readings(date);
        """)
        conn.commit()


# ── 公共 API ──────────────────────────────────────────────────────────

def add_reading(
    breath_rate: float | None,
    temperature: float | None,
    posture:     str   | None,
    battery:     int   | None,
    ts: int | None = None,
) -> None:
    """写入一条传感器读数。同一秒重复写入会被忽略。"""
    if ts is None:
        ts = int(time.time())
    d = datetime.fromtimestamp(ts)
    with _db_lock, _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sensor_readings "
            "(ts, date, time, breath_rate, temperature, posture, battery) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ts, d.date().isoformat(), d.strftime("%H:%M:%S"),
             breath_rate, temperature, posture, battery),
        )
        conn.commit()


def get_by_date(date_str: str) -> list[dict]:
    """按 ts 升序返回指定日期的所有读数。键名与原 jsonl 格式一致，
    方便回放页面 _sensors 数组直接消费。"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT ts, time, breath_rate, temperature, posture, battery "
            "FROM sensor_readings WHERE date = ? ORDER BY ts",
            (date_str,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── 旧 jsonl 一次性导入 ───────────────────────────────────────────────

def _import_jsonl_files() -> None:
    if not os.path.isdir(REC_DIR):
        return
    for d in sorted(os.listdir(REC_DIR)):
        sub = os.path.join(REC_DIR, d)
        # 仅扫 YYYY-MM-DD 命名的目录
        if not (os.path.isdir(sub) and len(d) == 10):
            continue
        jsonl = os.path.join(sub, "sensors.jsonl")
        if not os.path.isfile(jsonl):
            continue

        rows: list[tuple] = []
        try:
            with open(jsonl, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    ts = e.get("ts")
                    if not isinstance(ts, (int, float)):
                        continue
                    ts = int(ts)
                    dt = datetime.fromtimestamp(ts)
                    rows.append((
                        ts,
                        dt.date().isoformat(),
                        e.get("time") or dt.strftime("%H:%M:%S"),
                        e.get("breath_rate"),
                        e.get("temperature"),
                        e.get("posture"),
                        e.get("battery"),
                    ))
        except Exception as ex:
            log.warning(f"[SensorsDB] 读取 {jsonl} 失败: {ex}")
            continue

        try:
            if rows:
                with _db_lock, _connect() as conn:
                    conn.executemany(
                        "INSERT OR IGNORE INTO sensor_readings "
                        "(ts, date, time, breath_rate, temperature, posture, battery) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        rows,
                    )
                    conn.commit()
            os.rename(jsonl, jsonl + ".imported")
            log.info(f"[SensorsDB] 已导入 {jsonl} ({len(rows)} 行)")
        except Exception as ex:
            log.warning(f"[SensorsDB] 写入失败 {jsonl}: {ex}")


# 模块加载时初始化 schema + 一次性导入旧 jsonl（幂等：已导入文件已改名）
_init_db()
_import_jsonl_files()
