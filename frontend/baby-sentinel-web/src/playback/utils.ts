// 录像页公用工具——时间格式 / 时间戳→24h 百分比 / 二分查找最近传感器 / 事件 icon+desc。

import type { EventRow, SensorRow } from "@/playback/types";

export const pad2 = (n: number) => String(n).padStart(2, "0");

/** unix sec → "HH:MM:SS"（本地） */
export function fmtTs(ts: number): string {
  const d = new Date(ts * 1000);
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

/** "YYYY-MM-DD" → unix sec of that local 00:00:00 */
export function dayStart(date: string): number {
  const [y, mo, d] = date.split("-").map(Number);
  return new Date(y, mo - 1, d).getTime() / 1000;
}

/** 把一个 ts（unix 秒）映射到 24h 时间轴的百分比 (0..1)；超出夹紧 */
export function tsToPercent(ts: number, date: string): number {
  const start = dayStart(date);
  const p = (ts - start) / 86400;
  return Math.max(0, Math.min(1, p));
}

/** 二分找 sensors 数组里 ts 最接近 target 的那条。数组需按 ts 升序。
 *  超出 maxGap 秒（默认 30）→ 返 null，让 UI 显示"无传感器记录"，
 *  避免拿距离很远的旧记录冒充当下时刻的数据。 */
export function nearestSensor(rows: SensorRow[], target: number, maxGap = 30): SensorRow | null {
  if (rows.length === 0) return null;
  let lo = 0, hi = rows.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (rows[mid].ts < target) lo = mid + 1;
    else                       hi = mid;
  }
  // lo 指向第一个 ts >= target；和它前一个比哪个更近
  let pick = rows[lo];
  if (lo > 0 && Math.abs(rows[lo - 1].ts - target) < Math.abs(pick.ts - target)) {
    pick = rows[lo - 1];
  }
  return Math.abs(pick.ts - target) > maxGap ? null : pick;
}

/** 育儿日志 entry → 时间轴上展示的 emoji */
export function eventIcon(e: EventRow): string {
  switch (e.type) {
    case "formula":     case "feed":   return "🍼";
    case "bottle_milk":                return "🍶";
    case "breastfeed":                 return "🤱";
    case "diaper": {
      const k = (e as { kind?: string }).kind;
      return k === "wet" ? "💧" : "💩";
    }
    case "sleep": {
      const a = (e as { action?: string }).action;
      return a === "end" ? "☀️" : "😴";
    }
    case "temperature": return "🌡️";
    case "height":      return "📏";
    case "weight":      return "⚖️";
    case "bath":        return "🛁";
    case "pump":        return "🍶";
    default:            return "📝";
  }
}
