"""育儿日志模块 — 喂奶 / 尿布 / 睡眠 / 体温 / 身高体重 记录 + 统计

存储后端：SQLite (logs/baby_log.db)

如有旧 logs/baby_log.json 需要导入，运行：
    ./venv/bin/python tools/migrate_baby_log.py
"""

import json
import os
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta

from app.config import BASE_DIR, CFG, log

LOG_DIR = os.path.join(BASE_DIR, "logs")
DB_FILE = os.path.join(LOG_DIR, "baby_log.db")

# 所有喂奶类型（含旧的 "feed" 兼容）
FEED_TYPES = {"feed", "formula", "breastfeed", "bottle_milk"}

# 独立列对应的字段；其余字段塞进 payload JSON
_CORE_FIELDS = {"ts", "date", "type", "time", "action"}

_db_lock = threading.Lock()


# ── SQLite 连接 / Schema ──────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    with _connect() as conn:
        # WAL 模式：读写并发更友好（写入元信息一次永久生效）
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS entries (
                ts          INTEGER PRIMARY KEY,
                date        TEXT    NOT NULL,
                type        TEXT    NOT NULL,
                time        TEXT    NOT NULL,
                action      TEXT,
                payload     TEXT,
                created_at  INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
            );
            CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(date);
            CREATE INDEX IF NOT EXISTS idx_entries_type ON entries(type);
        """)
        conn.commit()


# ── 行 ↔ dict 转换 ───────────────────────────────────────────────────

def _row_to_entry(row: sqlite3.Row) -> dict:
    payload = json.loads(row["payload"]) if row["payload"] else {}
    out: dict = {"ts": row["ts"], "type": row["type"], "time": row["time"]}
    if row["action"]:
        out["action"] = row["action"]
    out.update(payload)
    return out


def _entry_to_row(entry: dict, date_key: str) -> tuple:
    payload = {k: v for k, v in entry.items() if k not in _CORE_FIELDS}
    return (
        int(entry["ts"]),
        date_key,
        entry["type"],
        entry.get("time", ""),
        entry.get("action"),
        json.dumps(payload, ensure_ascii=False) if payload else None,
    )


# 模块加载时初始化 schema
_init_db()


# ── 公共查询 API ──────────────────────────────────────────────────────

def list_dates() -> list:
    """有日志的日期列表（降序）。"""
    with _connect() as conn:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT date FROM entries ORDER BY date DESC"
        )]


def get_date_entries(date_str: str) -> list:
    """指定日期的所有条目，按 ts 升序。"""
    with _connect() as conn:
        return [_row_to_entry(r) for r in conn.execute(
            "SELECT * FROM entries WHERE date=? ORDER BY ts", (date_str,)
        )]


# ── dict-of-lists 桥接 ───────────────────────────────────────────────
# 业务函数（add_entry/update_entry/delete_entry/get_stats）需要遍历整本日志
# 来处理跨日睡眠等场景，这里保留 _load/_save 提供 dict-of-lists 视图。
# _save 走全量重写：当前数据规模（百~千条）性能足够。

def _load() -> dict:
    out: dict = {}
    with _connect() as conn:
        for row in conn.execute("SELECT * FROM entries ORDER BY ts"):
            out.setdefault(row["date"], []).append(_row_to_entry(row))
    return out


def _save(data: dict) -> None:
    rows: list = []
    for date_key, entries in data.items():
        for e in entries:
            rows.append(_entry_to_row(e, date_key))
    with _db_lock, _connect() as conn:
        conn.execute("DELETE FROM entries")
        if rows:
            conn.executemany(
                "INSERT INTO entries (ts, date, type, time, action, payload) VALUES (?,?,?,?,?,?)",
                rows,
            )
        conn.commit()


# ── 业务逻辑 ──────────────────────────────────────────────────────────

def _today() -> str:
    return date.today().isoformat()


def _parse_birth_date(s: str):
    """Accept YYYY-MM-DD or YYYYMMDD."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _fmt_duration(seconds: int) -> str:
    h, m = divmod(abs(seconds), 3600)
    m = m // 60
    return f"{h}時間{m}分" if h else f"{m}分"


def _find_open_sleep_start(entries: list, before_ts: int | None = None) -> dict | None:
    """Return the last sleep-start entry that has no paired sleep-end.

    An entry tagged with cross_day_wake_ts is already resolved and is skipped.
    """
    cur: dict | None = None
    for e in sorted(entries, key=lambda e: e.get("ts", 0)):
        if e.get("type") != "sleep":
            continue
        if before_ts is not None and e.get("ts", 0) >= before_ts:
            continue
        if e.get("action") == "start" and not e.get("cross_day_wake_ts"):
            cur = e
        elif e.get("action") == "end" and cur:
            cur = None
    return cur


def _clear_cross_day_wake(data: dict, wake_ts: int) -> None:
    """Remove cross_day_wake_ts from any sleep-start that points to wake_ts."""
    for entries in data.values():
        for e in entries:
            if e.get("cross_day_wake_ts") == wake_ts:
                e.pop("cross_day_wake_ts", None)
                e.pop("duration_str", None)


def add_entry(entry: dict) -> dict:
    # 前端可传 date 字段指定目标日期（日期导航切换到过去时使用）
    target_str = entry.pop("date", None) or _today()
    entry.setdefault("time", datetime.now().strftime("%H:%M"))

    data = _load()

    # ts = target date + selected time
    try:
        h, m = map(int, entry["time"].split(":"))
        d = date.fromisoformat(target_str)
        base_ts = int(datetime(d.year, d.month, d.day, h, m).timestamp())
        existing_ts = {e.get("ts") for e in data.get(target_str, [])}
        ts = base_ts
        while ts in existing_ts:
            ts += 1
        entry["ts"] = ts
    except Exception:
        entry["ts"] = int(time.time())

    # Auto-compute sleep duration when recording wake-up
    if entry.get("type") == "sleep" and entry.get("action") == "end":
        target_d      = date.fromisoformat(target_str)
        yesterday_str = (target_d - timedelta(days=1)).isoformat()
        start_entry: dict | None = None
        start_date:  str  | None = None
        for dk in (target_str, yesterday_str):
            found = _find_open_sleep_start(data.get(dk, []), before_ts=entry["ts"])
            if found:
                start_entry = found
                start_date  = dk
                break
        if start_entry:
            entry["duration_str"] = _fmt_duration(entry["ts"] - start_entry["ts"])
            if start_date == yesterday_str:
                start_entry["cross_day_wake_ts"] = entry["ts"]

    data.setdefault(target_str, []).append(entry)
    data[target_str].sort(key=lambda e: e.get("ts", 0))
    _save(data)
    log.debug(f"[BabyLog] {entry['type']} @ {target_str} {entry['time']}")
    return entry


def delete_entry(ts: int) -> bool:
    data = _load()
    for date_key, entries in data.items():
        for i, e in enumerate(entries):
            if e.get("ts") == ts:
                entries.pop(i)
                # 若删除的是跨日起床记录，清除昨天入睡条目上的 cross_day_wake_ts
                if e.get("type") == "sleep" and e.get("action") == "end":
                    _clear_cross_day_wake(data, ts)
                _save(data)
                log.debug(f"[BabyLog] deleted ts={ts}")
                return True
    return False


def update_entry(ts: int, updates: dict) -> dict | None:
    data = _load()
    for date_key, entries in data.items():
        for i, e in enumerate(entries):
            if e.get("ts") == ts:
                new_ts = ts
                if "time" in updates:
                    try:
                        h, m = map(int, updates["time"].split(":"))
                        d = date.fromisoformat(date_key)
                        base_ts = int(datetime(d.year, d.month, d.day, h, m).timestamp())
                        other_ts = {e2.get("ts") for j, e2 in enumerate(entries) if j != i}
                        new_ts = base_ts
                        while new_ts in other_ts:
                            new_ts += 1
                    except Exception:
                        new_ts = ts
                entry = {**e, **updates, "ts": new_ts}
                # Recompute sleep duration if this is a wake-up entry and time changed
                if entry.get("type") == "sleep" and entry.get("action") == "end" and "time" in updates:
                    yesterday_str = (date.fromisoformat(date_key) - timedelta(days=1)).isoformat()
                    # 先清除旧的跨日标记（用旧 ts 定位）
                    _clear_cross_day_wake(data, ts)
                    start_entry2: dict | None = None
                    start_date2:  str  | None = None
                    for dk in (date_key, yesterday_str):
                        found = _find_open_sleep_start(data.get(dk, []), before_ts=new_ts)
                        if found:
                            start_entry2 = found
                            start_date2  = dk
                            break
                    if start_entry2:
                        entry["duration_str"] = _fmt_duration(new_ts - start_entry2["ts"])
                        if start_date2 == yesterday_str:
                            start_entry2["cross_day_wake_ts"] = new_ts
                    else:
                        entry.pop("duration_str", None)
                entries[i] = entry
                data[date_key].sort(key=lambda e: e.get("ts", 0))
                _save(data)
                log.debug(f"[BabyLog] updated ts={ts}")
                return entry
    return None


def get_today() -> list:
    return get_date_entries(_today())


def get_stats() -> dict:
    data          = _load()
    today_str     = _today()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()

    entries  = sorted(data.get(today_str, []),    key=lambda e: e.get("ts", 0))
    yentries = sorted(data.get(yesterday_str, []), key=lambda e: e.get("ts", 0))

    feeds    = [e for e in entries if e.get("type") in FEED_TYPES]
    diapers  = [e for e in entries if e.get("type") == "diaper"]
    sleeps   = [e for e in entries if e.get("type") == "sleep"]

    baby_cfg     = CFG.get("baby", {})
    interval_min = int(baby_cfg.get("feed_interval_min", 150))

    # ── 所有喂奶（倒计时用，跨日连续）────
    last_feed = feeds[-1] if feeds else None
    if not last_feed:
        yesterday_feeds = [e for e in yentries if e.get("type") in FEED_TYPES]
        if yesterday_feeds:
            last_feed = max(yesterday_feeds, key=lambda e: e.get("ts", 0))
    next_feed_ts = (last_feed["ts"] + interval_min * 60) if last_feed else None
    mins_until   = round((next_feed_ts - time.time()) / 60) if next_feed_ts else None
    total_ml     = sum(e.get("amount_ml", 0) or 0 for e in feeds)
    avg_ml       = round(total_ml / len(feeds)) if feeds else 0

    # ── 配方奶单独统计 ─────────────────────
    formulas   = [e for e in entries if e["type"] == "formula"]
    formula_ml = sum(e.get("amount_ml", 0) or 0 for e in formulas)
    formula_avg = round(formula_ml / len(formulas)) if formulas else 0

    # ── 母乳单独统计 ───────────────────────
    breastfeeds      = [e for e in entries if e["type"] == "breastfeed"]
    breast_left_min  = sum(
        e.get("left_min") or (e.get("duration_min", 0) if e.get("side") == "left" else 0)
        for e in breastfeeds
    )
    breast_right_min = sum(
        e.get("right_min") or (e.get("duration_min", 0) if e.get("side") == "right" else 0)
        for e in breastfeeds
    )

    # ── 瓶喂母乳单独统计 ───────────────────
    bottles   = [e for e in entries if e["type"] == "bottle_milk"]
    bottle_ml = sum(e.get("amount_ml", 0) or 0 for e in bottles)

    # ── 推荐喂奶量 ────────────────────────
    rec_ml     = None
    weight_g   = int(baby_cfg.get("weight_g", 0))
    age_days   = 0
    bd = _parse_birth_date(baby_cfg.get("birth_date", ""))
    if bd:
        try:
            age_days = (date.today() - bd).days
        except Exception:
            pass

    feed_type = baby_cfg.get("feed_type", "formula")
    if feed_type == "formula":
        if weight_g and interval_min:
            feeds_per_day = round(24 * 60 / interval_min)
            rec_ml = max(10, round(weight_g * 0.15 / feeds_per_day))
        elif age_days:
            rec_ml = min(90, 30 + age_days * 3)

    # ── 尿布 ──────────────────────────────
    wet   = sum(1 for e in diapers if e.get("kind") in ("wet",   "both"))
    dirty = sum(1 for e in diapers if e.get("kind") in ("dirty", "both"))

    # ── 睡眠（跨日分段计算）─────────────────
    today_d        = date.today()
    today_midnight = int(datetime(today_d.year, today_d.month, today_d.day).timestamp())

    total_sleep_s  = 0
    longest_s      = 0
    sleeping_since = None

    # 找昨天未闭合的 sleep-start（跨日入睡）
    _y_open_entry = _find_open_sleep_start(yentries)
    y_open_start  = _y_open_entry["ts"] if _y_open_entry else None

    # 处理今天的睡眠记录
    cur_start = None
    for e in sleeps:
        if e.get("action") == "start":
            cur_start = e["ts"]
        elif e.get("action") == "end":
            if cur_start is not None:
                # 同日完整睡眠段
                dur            = e["ts"] - cur_start
                total_sleep_s += dur
                longest_s      = max(longest_s, dur)
                cur_start      = None
            elif y_open_start is not None:
                # 跨日睡眠：今天的份额 = 午夜 → 起床
                dur            = e["ts"] - today_midnight
                total_sleep_s += dur
                longest_s      = max(longest_s, dur)
                y_open_start   = None  # 已消费

    # 当前睡眠状态（用于前端显示"已睡 X 小时"）
    if cur_start is not None:
        sleeping_since = cur_start
    elif y_open_start is not None:
        # 昨天入睡、今天还没有起床记录
        sleeping_since = y_open_start

    return {
        # 所有喂奶（倒计时 / 提醒）
        "feed_count":        len(feeds),
        "total_ml":          total_ml,
        "avg_ml":             avg_ml,
        "last_feed_time":    last_feed["time"] if last_feed else None,
        "last_feed_ml":      last_feed.get("amount_ml") if last_feed else None,
        "next_feed_ts":      next_feed_ts,
        "mins_until_next":   mins_until,
        "recommended_ml":    rec_ml,
        "interval_min":      interval_min,
        "age_days":          age_days,
        # 配方奶单独
        "formula_count":     len(formulas),
        "formula_ml":        formula_ml,
        "formula_avg_ml":    formula_avg,
        # 母乳单独
        "breastfeed_count":  len(breastfeeds),
        "breast_left_min":   breast_left_min,
        "breast_right_min":  breast_right_min,
        # 瓶喂母乳单独
        "bottle_count":      len(bottles),
        "bottle_ml":         bottle_ml,
        # 尿布
        "diaper_wet":        wet,
        "diaper_dirty":      dirty,
        # 睡眠
        "sleep_total_min":   total_sleep_s // 60,
        "sleep_longest_min": longest_s // 60,
        "sleeping_since":    sleeping_since,
    }
