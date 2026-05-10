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

from shared.config import BASE_DIR, log
from services.web.config import BABY

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


# ── dict-of-lists 视图（仅 get_stats 需要扫整本日志做跨日 / 长尾统计）──
# 写路径（add/update/delete）已经直接走 SQL 单行事务，不再需要 _save。

def _load() -> dict:
    out: dict = {}
    with _connect() as conn:
        for row in conn.execute("SELECT * FROM entries ORDER BY ts"):
            out.setdefault(row["date"], []).append(_row_to_entry(row))
    return out


# ── 写路径用的 SQL 辅助 ───────────────────────────────────────────────

def _next_free_ts(
    conn: sqlite3.Connection, base_ts: int, exclude_ts: int | None = None
) -> int:
    """从 base_ts 开始找最近一个未占用的 ts（同一分钟多条记录会 +1 错开）。
    exclude_ts 用于 update：把当前正在编辑的行排除在"占用"之外。"""
    ts = base_ts
    while True:
        if exclude_ts is None:
            hit = conn.execute("SELECT 1 FROM entries WHERE ts=?", (ts,)).fetchone()
        else:
            hit = conn.execute(
                "SELECT 1 FROM entries WHERE ts=? AND ts!=?", (ts, exclude_ts)
            ).fetchone()
        if not hit:
            return ts
        ts += 1


def _find_open_sleep_start_db(
    conn: sqlite3.Connection,
    before_ts: int,
    date_pref: tuple[str, ...],
) -> tuple[int, str, dict] | None:
    """语义对齐 _find_open_sleep_start (list 版)：在 date_pref 列出的日期里
    按优先级查找第一个未闭合的 sleep-start（cross_day_wake_ts 未设 → 视为未闭合）。
    返回 (ts, date, payload_dict) 或 None。"""
    for d in date_pref:
        rows = conn.execute(
            "SELECT ts, action, payload FROM entries "
            "WHERE type='sleep' AND date=? AND ts<? "
            "ORDER BY ts",
            (d, before_ts),
        ).fetchall()
        cur: tuple[int, str, dict] | None = None
        for r in rows:
            payload = json.loads(r["payload"]) if r["payload"] else {}
            if r["action"] == "start" and not payload.get("cross_day_wake_ts"):
                cur = (r["ts"], d, payload)
            elif r["action"] == "end" and cur is not None:
                cur = None
        if cur is not None:
            return cur
    return None


def _clear_cross_day_wake_db(conn: sqlite3.Connection, wake_ts: int) -> None:
    """把任何 payload.cross_day_wake_ts == wake_ts 的 sleep-start 标记清掉。
    SQLite < 3.38 没有可靠的 JSON 谓词，这里 SELECT 出来 Python 侧过滤再 UPDATE，
    数量级（一天最多十几条 sleep）无所谓。"""
    rows = conn.execute(
        "SELECT ts, payload FROM entries "
        "WHERE type='sleep' AND action='start' AND payload IS NOT NULL"
    ).fetchall()
    for r in rows:
        try:
            payload = json.loads(r["payload"])
        except Exception:
            continue
        if payload.get("cross_day_wake_ts") != wake_ts:
            continue
        payload.pop("cross_day_wake_ts", None)
        payload.pop("duration_str", None)
        new_pl = json.dumps(payload, ensure_ascii=False) if payload else None
        conn.execute("UPDATE entries SET payload=? WHERE ts=?", (new_pl, r["ts"]))


def _set_payload_field(
    conn: sqlite3.Connection, ts: int, key: str, value
) -> None:
    """读 → 改 → 写一个 payload 字段，同事务内可见。"""
    row = conn.execute("SELECT payload FROM entries WHERE ts=?", (ts,)).fetchone()
    if not row:
        return
    payload = json.loads(row["payload"]) if row["payload"] else {}
    payload[key] = value
    conn.execute(
        "UPDATE entries SET payload=? WHERE ts=?",
        (json.dumps(payload, ensure_ascii=False), ts),
    )


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
    from services.web.i18n import t
    h, m = divmod(abs(seconds), 3600)
    m = m // 60
    return t("duration_h_m", h=h, m=m) if h else t("duration_m", m=m)


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


def add_entry(entry: dict) -> dict:
    # 前端可传 date 字段指定目标日期（日期导航切换到过去时使用）
    target_str = entry.pop("date", None) or _today()
    entry.setdefault("time", datetime.now().strftime("%H:%M"))

    # ts = target date + selected time，同分钟冲突 +1 错开
    try:
        h, m = map(int, entry["time"].split(":"))
        d = date.fromisoformat(target_str)
        base_ts = int(datetime(d.year, d.month, d.day, h, m).timestamp())
    except Exception:
        base_ts = int(time.time())

    with _db_lock, _connect() as conn:
        ts = _next_free_ts(conn, base_ts)
        entry["ts"] = ts

        # Sleep wake-up：找最近一条未闭合的 sleep-start（先今天再昨天），
        # 算 duration；若来自昨天则在 start 行打 cross_day_wake_ts 标记。
        if entry.get("type") == "sleep" and entry.get("action") == "end":
            target_d      = date.fromisoformat(target_str)
            yesterday_str = (target_d - timedelta(days=1)).isoformat()
            found = _find_open_sleep_start_db(
                conn, before_ts=ts, date_pref=(target_str, yesterday_str)
            )
            if found:
                start_ts, start_date, _ = found
                entry["duration_str"] = _fmt_duration(ts - start_ts)
                if start_date == yesterday_str:
                    _set_payload_field(conn, start_ts, "cross_day_wake_ts", ts)

        conn.execute(
            "INSERT INTO entries (ts, date, type, time, action, payload) "
            "VALUES (?,?,?,?,?,?)",
            _entry_to_row(entry, target_str),
        )
        conn.commit()

    log.debug(f"[BabyLog] {entry['type']} @ {target_str} {entry['time']}")
    return entry


def delete_entry(ts: int) -> bool:
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT type, action FROM entries WHERE ts=?", (ts,)
        ).fetchone()
        if not row:
            return False
        # 删掉跨日起床记录 → 把昨天 sleep-start 上的 cross_day_wake_ts 清掉
        if row["type"] == "sleep" and row["action"] == "end":
            _clear_cross_day_wake_db(conn, ts)
        conn.execute("DELETE FROM entries WHERE ts=?", (ts,))
        conn.commit()
    log.debug(f"[BabyLog] deleted ts={ts}")
    return True


def update_entry(ts: int, updates: dict) -> dict | None:
    with _db_lock, _connect() as conn:
        row = conn.execute("SELECT * FROM entries WHERE ts=?", (ts,)).fetchone()
        if not row:
            return None

        old_entry = _row_to_entry(row)
        date_key  = row["date"]

        # 时间编辑 → 重算 ts（排除当前行避免和自己冲突）
        new_ts = ts
        if "time" in updates:
            try:
                h, m = map(int, updates["time"].split(":"))
                d = date.fromisoformat(date_key)
                base_ts = int(datetime(d.year, d.month, d.day, h, m).timestamp())
                new_ts  = _next_free_ts(conn, base_ts, exclude_ts=ts)
            except Exception:
                new_ts = ts

        new_entry = {**old_entry, **updates, "ts": new_ts}

        # Sleep 起床 + 改了时间 → 重算 duration_str + 重置跨日标记
        if (new_entry.get("type") == "sleep"
                and new_entry.get("action") == "end"
                and "time" in updates):
            # 用旧 ts 清掉旧的跨日标记
            _clear_cross_day_wake_db(conn, ts)
            yesterday_str = (date.fromisoformat(date_key) - timedelta(days=1)).isoformat()
            found = _find_open_sleep_start_db(
                conn, before_ts=new_ts, date_pref=(date_key, yesterday_str)
            )
            if found:
                start_ts, start_date, _ = found
                new_entry["duration_str"] = _fmt_duration(new_ts - start_ts)
                if start_date == yesterday_str:
                    _set_payload_field(conn, start_ts, "cross_day_wake_ts", new_ts)
            else:
                new_entry.pop("duration_str", None)

        new_row = _entry_to_row(new_entry, date_key)
        if new_ts != ts:
            # ts 是 PRIMARY KEY，先 DELETE 再 INSERT
            conn.execute("DELETE FROM entries WHERE ts=?", (ts,))
            conn.execute(
                "INSERT INTO entries (ts, date, type, time, action, payload) "
                "VALUES (?,?,?,?,?,?)",
                new_row,
            )
        else:
            conn.execute(
                "UPDATE entries SET date=?, type=?, time=?, action=?, payload=? "
                "WHERE ts=?",
                (new_row[1], new_row[2], new_row[3], new_row[4], new_row[5], ts),
            )
        conn.commit()

    log.debug(f"[BabyLog] updated ts={ts}")
    return new_entry


def get_today() -> list:
    return get_date_entries(_today())


def get_last_feed() -> dict | None:
    """最近一次喂奶条目：今天没有则回退到昨天，用于跨午夜倒计时/提醒。"""
    today_str     = _today()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    for d in (today_str, yesterday_str):
        feeds = [e for e in get_date_entries(d) if e.get("type") in FEED_TYPES]
        if feeds:
            return feeds[-1]
    return None


def _latest_weight_g(data: dict) -> int | None:
    """从已加载的 _load() 数据里找最新一条 weight entry 的 value（克）。

    babies 不会每天称重，所以扫所有日期。耗时 O(n)，n=条目总数，对当前规模可忽略。
    返回 None 表示从未录入过 → 由 caller fallback 到 config.baby.weight_g。
    """
    latest_ts  = -1
    latest_val = None
    for entries in data.values():
        for e in entries:
            if e.get("type") != "weight" or e.get("value") is None:
                continue
            ts = e.get("ts", 0)
            if ts > latest_ts:
                latest_ts  = ts
                latest_val = e["value"]
    if latest_val is None:
        return None
    try:
        return int(latest_val)
    except (TypeError, ValueError):
        return None


def get_stats() -> dict:
    data          = _load()
    today_str     = _today()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()

    entries  = sorted(data.get(today_str, []),    key=lambda e: e.get("ts", 0))
    yentries = sorted(data.get(yesterday_str, []), key=lambda e: e.get("ts", 0))

    feeds    = [e for e in entries if e.get("type") in FEED_TYPES]
    diapers  = [e for e in entries if e.get("type") == "diaper"]
    sleeps   = [e for e in entries if e.get("type") == "sleep"]

    interval_min = int(BABY.get("feed_interval_min", 150))

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
    # 体重优先级：最近一次 /log weight entry > config.baby.weight_g > 无
    # 这样从 Discord / 网页录入体重可立即反映到推荐奶量，无需重启或改 config
    rec_ml     = None
    weight_g   = _latest_weight_g(data) or int(BABY.get("weight_g", 0))
    age_days   = 0
    bd = _parse_birth_date(BABY.get("birth_date", ""))
    if bd:
        try:
            age_days = (date.today() - bd).days
        except Exception:
            pass

    feed_type = BABY.get("feed_type", "formula")
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
