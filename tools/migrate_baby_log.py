"""一次性迁移工具：logs/baby_log.json → logs/baby_log.db (SQLite)

用法：
    ./venv/bin/python tools/migrate_baby_log.py

行为：
- 检测 logs/baby_log.json 是否存在；不存在则提示无需迁移
- 检测 logs/baby_log.db 是否已有数据；非空时拒绝运行（避免覆盖）
- 历史 JSON 中重复 ts 自动 +1 去重，与 add_entry 规则一致，零数据丢失
- 成功后把原 JSON 改名为 .bak 作为回滚备份
"""

import json
import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

LOG_DIR   = os.path.join(_ROOT, "logs")
DB_FILE   = os.path.join(LOG_DIR, "baby_log.db")
JSON_FILE = os.path.join(LOG_DIR, "baby_log.json")

_CORE_FIELDS = {"ts", "date", "type", "time", "action"}


def main() -> int:
    if not os.path.exists(JSON_FILE):
        print(f"未找到 {JSON_FILE}，无需迁移")
        return 0

    # 触发 app.baby_log 模块加载以确保 DB / schema 已就位
    from app import baby_log  # noqa: F401

    with sqlite3.connect(DB_FILE) as conn:
        existing = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    if existing > 0:
        print(f"❌ {DB_FILE} 已有 {existing} 条数据，拒绝迁移以避免覆盖")
        print(f"   如确需重新导入，请先备份并清空 entries 表")
        return 1

    with open(JSON_FILE, encoding="utf-8") as f:
        data = json.load(f)

    rows: list = []
    used_ts: set = set()
    bumped = 0
    skipped = 0
    for date_key, entries in (data or {}).items():
        if not isinstance(entries, list):
            continue
        for e in entries:
            try:
                ts = int(e.get("ts", 0))
                while ts in used_ts:
                    ts += 1
                    bumped += 1
                used_ts.add(ts)
                payload = {k: v for k, v in e.items() if k not in _CORE_FIELDS}
                rows.append((
                    ts, date_key, e["type"], e.get("time", ""),
                    e.get("action"),
                    json.dumps(payload, ensure_ascii=False) if payload else None,
                ))
            except Exception as ex:
                print(f"  跳过损坏条目: {e} ({ex})")
                skipped += 1

    if not rows:
        print("没有可迁移的数据")
        return 1

    with sqlite3.connect(DB_FILE) as conn:
        conn.executemany(
            "INSERT INTO entries (ts, date, type, time, action, payload) VALUES (?,?,?,?,?,?)",
            rows,
        )
        conn.commit()

    backup = JSON_FILE + ".bak"
    os.replace(JSON_FILE, backup)

    bump_note = f"，{bumped} 条因 ts 重复 +1 去重" if bumped else ""
    skip_note = f"，{skipped} 条损坏跳过" if skipped else ""
    print(f"✓ 已迁移 {len(rows)} 条数据 → {DB_FILE}{bump_note}{skip_note}")
    print(f"✓ 原 JSON 备份至 {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
