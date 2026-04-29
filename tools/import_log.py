#!/usr/bin/env python3
"""
导入育儿日志文本 → baby_log.json
用法: python tools/import_log.py [logfile.txt]
若不指定文件则使用内置样本数据。
"""

import json
import os
import re
import sys
from datetime import datetime, date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(BASE_DIR, "logs", "baby_log.json")

AMOUNT_MAP = {"通常": "正常", "一点点": "少", "少": "少", "大": "多", "正常": "正常", "多": "多"}
COLOR_MAP  = {
    "黄色": "黄", "黄": "黄", "绿色": "绿", "绿": "绿",
    "红色": "红", "红": "红", "茶色": "茶", "茶": "茶",
    "橙色": "橙", "橙": "橙", "白色": "白", "白": "白",
    "黑色": "黑", "黑": "黑",
}


def ts_from(d: date, time_str: str) -> int:
    dt = datetime.combine(d, datetime.strptime(time_str, "%H:%M").time())
    return int(dt.timestamp())


def parse_breastfeed(rest: str) -> dict:
    rest = rest.strip()
    amount_ml = None
    m = re.search(r"\((\d+)ml\)", rest, re.IGNORECASE)
    if m:
        amount_ml = int(m.group(1))
        rest = rest[: m.start()].strip()

    # "母乳 母乳" or empty → bottle of breast milk (no minute count in app totals)
    if not rest or rest == "母乳":
        return {"type": "bottle_milk", "amount_ml": amount_ml}

    sides = re.findall(r"(左|右)\s*(\d+)\s*分钟?", rest)
    if len(sides) >= 2:
        left_min  = next((int(d) for s, d in sides if s == "左"), None)
        right_min = next((int(d) for s, d in sides if s == "右"), None)
        e = {"type": "breastfeed", "side": "both"}
        if left_min:  e["left_min"]  = left_min
        if right_min: e["right_min"] = right_min
        if amount_ml: e["amount_ml"] = amount_ml
        return e
    elif len(sides) == 1:
        sc, dur = sides[0]
        e = {"type": "breastfeed", "side": "left" if sc == "左" else "right",
             "duration_min": int(dur)}
        if amount_ml: e["amount_ml"] = amount_ml
        return e
    return {"type": "breastfeed", "amount_ml": amount_ml}


def parse_line(line: str) -> tuple | None:
    m = re.match(r"^(\d{2}:\d{2})\s+(.+)", line.strip())
    if not m:
        return None
    time_str, desc = m.group(1), m.group(2).strip()

    if desc.startswith("母乳"):
        e = parse_breastfeed(desc[2:].strip())
        e["time"] = time_str
        return time_str, e

    m2 = re.match(r"配方奶\s+(\d+)ml", desc, re.I)
    if m2:
        return time_str, {"type": "formula", "amount_ml": int(m2.group(1)), "time": time_str}

    m2 = re.match(r"瓶喂母乳\s+(\d+)ml", desc, re.I)
    if m2:
        return time_str, {"type": "bottle_milk", "amount_ml": int(m2.group(1)), "time": time_str}

    if desc == "睡觉":
        return time_str, {"type": "sleep", "action": "start", "time": time_str}

    m2 = re.match(r"起床\s*\((.+)\)", desc)
    if m2:
        return time_str, {"type": "sleep", "action": "end", "duration_str": m2.group(1), "time": time_str}
    if desc == "起床":
        return time_str, {"type": "sleep", "action": "end", "time": time_str}

    if desc == "尿尿":
        return time_str, {"type": "diaper", "kind": "wet", "time": time_str}

    m2 = re.match(r"便便\s*\((.+)\)", desc)
    if m2:
        parts = [p.strip() for p in m2.group(1).split("/")]
        amount = AMOUNT_MAP.get(parts[0], "正常") if parts else "正常"
        cons   = parts[1] if len(parts) > 1 else "正常"
        color  = COLOR_MAP.get(parts[2] if len(parts) > 2 else "黄", "黄")
        return time_str, {"type": "diaper", "kind": "dirty",
                          "amount": amount, "consistency": cons, "color": color, "time": time_str}

    if desc == "洗澡":
        return time_str, {"type": "bath", "time": time_str}

    m2 = re.match(r"体温\s+([\d.]+)[°℃]C?", desc)
    if m2:
        return time_str, {"type": "temperature", "value": float(m2.group(1)), "time": time_str}

    m2 = re.match(r"挤奶\s+(\d+)ml", desc, re.I)
    if m2:
        return time_str, {"type": "pump", "amount_ml": int(m2.group(1)), "time": time_str}

    if "备注" in desc:
        note = re.sub(r"备注\s*", "", desc).strip()
        return time_str, {"type": "note", "text": note, "time": time_str}

    print(f"  [跳过] {time_str}  {desc}", file=sys.stderr)
    return None


SKIP_PREFIXES = (
    "母乳共", "配方奶共", "瓶喂母乳共", "睡觉共", "尿尿共", "便便共",
    "----------", "[日志]", "結葵",
)


def parse_text(text: str) -> dict:
    result: dict = {}
    cur_date: date | None = None

    for line in text.splitlines():
        line = line.strip()
        if not line or any(line.startswith(p) for p in SKIP_PREFIXES):
            continue

        dm = re.match(r"(\d{4})年(\d+)月(\d+)日", line)
        if dm:
            cur_date = date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
            result.setdefault(cur_date.isoformat(), [])
            continue

        if cur_date is None:
            continue

        parsed = parse_line(line)
        if parsed:
            _, entry = parsed
            entry["ts"] = ts_from(cur_date, entry["time"])
            result[cur_date.isoformat()].append(entry)

    return result


# ── 内置样本数据 ────────────────────────────────────────────────────────────
SAMPLE_DATA = """
[日志]2026年4月

----------
2026年4月24日 周五

13:30   母乳 左 5分钟 / 右 5分钟 (40ml)
13:35   尿尿
13:35   配方奶 20ml
13:55   睡觉
14:35   便便 (通常/软/黄色)
14:35   起床 (0小时40分钟)
14:50   母乳 右 5分钟
15:05   母乳 左 10分钟
16:20   尿尿
16:30   洗澡
16:40   睡觉
18:30   起床 (1小时50分钟)
18:35   母乳 母乳 (40ml)
18:50   母乳 左 2分钟 / 右 5分钟
18:50   便便 (少/软/黄色)
19:00   睡觉
21:35   起床 (2小时35分钟)
21:35   尿尿
21:35   便便 (通常/软/黄色)
21:45   母乳 母乳 (40ml)
21:45   配方奶 20ml
21:50   睡觉

----------
2026年4月25日 周六

00:45   起床 (2小时55分钟)
00:50   尿尿
00:55   母乳 左 5分钟 → 右 5分钟
01:05   配方奶 30ml
01:30   便便 (大/软/黄色)
02:10   睡觉
05:00   起床 (2小时50分钟)
05:05   配方奶 60ml
05:10   尿尿
06:30   母乳 左 5分钟
06:35   睡觉
06:55   起床 (0小时20分钟)
07:25   睡觉
10:30   起床 (3小时5分钟)
10:35   尿尿
10:40   母乳 母乳 (20ml)
10:45   配方奶 50ml
11:30   睡觉
14:05   起床 (2小时35分钟)
14:10   配方奶 50ml
14:15   母乳 右 5分钟
14:20   睡觉
15:30   起床 (1小时10分钟)
15:35   尿尿
15:35   便便 (少/软/黄色)
15:40   洗澡
16:00   睡觉
17:35   起床 (1小时35分钟)
17:35   尿尿
17:35   便便 (一点点/软/黄色)
17:40   配方奶 50ml
17:50   母乳 左 10分钟
18:05   睡觉
19:00   便便 (少/软/黄色)
20:25   起床 (2小时20分钟)
20:30   尿尿
20:30   便便 (通常/软/黄色)
20:30   母乳 右 10分钟
20:40   配方奶 30ml
21:15   配方奶 20ml
22:00   尿尿
22:00   便便 (大/软/黄色)
22:30   睡觉

----------
2026年4月26日 周日

00:15   起床 (1小时45分钟)
00:20   母乳 左 10分钟
00:30   配方奶 60ml
00:50   睡觉
02:10   尿尿
02:10   便便 (少/软/黄色)
04:15   起床 (3小时25分钟)
04:25   配方奶 60ml
04:25   尿尿
04:25   便便 (通常/软/黄色)
04:30   睡觉
06:55   起床 (2小时25分钟)
07:00   尿尿
07:10   配方奶 60ml
07:15   睡觉
10:20   体温 37.2°C
10:25   起床 (3小时10分钟)
10:30   尿尿
10:30   便便 (少/软/黄色)
10:35   配方奶 60ml
10:45   母乳 右 5分钟
11:00   尿尿
11:00   便便 (大/软/黄色)
12:00   睡觉
12:15   尿尿
14:45   起床 (2小时45分钟)
14:45   尿尿
14:50   配方奶 60ml
15:05   睡觉
17:45   起床 (2小时40分钟)
17:50   配方奶 60ml
18:00   尿尿
18:10   母乳 左 5分钟 → 右 2分钟
18:25   睡觉
19:05   起床 (0小时40分钟)
19:05   尿尿
19:10   洗澡
19:30   睡觉
21:05   起床 (1小时35分钟)
21:20   瓶喂母乳 50ml
21:25   母乳 左 8分钟
21:30   睡觉

----------
2026年4月27日 周一

00:05   起床 (2小时35分钟)
00:10   尿尿
00:10   便便 (通常/软/黄色)
00:15   配方奶 60ml
00:25   母乳 右 6分钟
01:15   尿尿
01:15   便便 (大/软/黄色)
01:40   母乳 左 10分钟
02:20   体温 37.4°C
02:30   母乳 右 10分钟
02:40   睡觉
05:20   起床 (2小时40分钟)
05:20   尿尿
05:25   配方奶 70ml
05:40   睡觉
08:35   起床 (2小时55分钟)
08:40   母乳 左 4分钟
08:45   配方奶 70ml
08:45   体温 37.4°C
08:50   尿尿
09:00   便便 (通常/软/黄色)
09:10   睡觉
09:55   起床 (0小时45分钟)
10:10   母乳 右 5分钟
10:20   睡觉
13:15   起床 (2小时55分钟)
13:15   尿尿
13:30   配方奶 70ml
13:40   尿尿
13:40   体温 37.0°C
13:40   睡觉
17:10   起床 (3小时30分钟)
17:15   尿尿
17:20   配方奶 70ml
17:30   睡觉
18:00   起床 (0小时30分钟)
18:30   洗澡
18:45   睡觉
20:50   起床 (2小时5分钟)
20:55   配方奶 70ml
21:00   挤奶 40ml
21:10   尿尿
21:10   睡觉

----------
2026年4月28日 周二

00:15   起床 (3小时5分钟)
00:20   瓶喂母乳 40ml
00:30   配方奶 20ml
00:35   母乳 左 8分钟 ← 右 3分钟
01:55   睡觉
02:35   起床 (0小时40分钟)
02:35   母乳 右 3分钟
02:45   配方奶 60ml
03:00   尿尿
03:05   睡觉
06:30   起床 (3小时25分钟)
06:30   母乳 左 5分钟
06:40   配方奶 60ml
06:50   尿尿
06:55   睡觉
10:15   起床 (3小时20分钟)
10:20   尿尿
10:25   配方奶 70ml
11:15   便便 (通常/软/黄色)
11:35   瓶喂母乳 20ml
11:45   睡觉
14:10   起床 (2小时25分钟)
14:15   母乳 右 5分钟
14:15   配方奶 80ml
14:45   尿尿
14:55   睡觉
16:50   起床 (1小时55分钟)
16:55   尿尿
16:55   便便 (少/软/黄色)
17:10   备注   K2シロップ 4回目
17:20   睡觉
"""


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            text = f.read()
    else:
        text = SAMPLE_DATA
        print("使用内置样本数据（可传入文件路径覆盖）")

    imported = parse_text(text)
    print(f"\n解析完成: {len(imported)} 天")
    for d, entries in sorted(imported.items()):
        print(f"  {d}: {len(entries)} 条记录")

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    existing: dict = {}
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, encoding="utf-8") as f:
            existing = json.load(f)

    conflicts = [d for d in imported if d in existing and existing[d]]
    for d, entries in imported.items():
        existing[d] = entries

    if conflicts:
        print(f"\n[!] 以下日期已有数据已覆盖: {', '.join(conflicts)}")

    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 已写入 {LOG_FILE}")


if __name__ == "__main__":
    main()
