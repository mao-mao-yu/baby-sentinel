// 按 viewingDate 当天 entries 计算 4 项统计，对应旧 index.html renderDateStats()。
//
// 关键：跨天睡眠的"今日份额"分摊
//  - 起床有匹配的入睡 → 直接 end - start
//  - 没匹配的起床（入睡在前一天）→ 从本日 00:00 起算
//  - 没匹配的入睡（起床在后一天 / 还没起）→ 算到本日 24:00（今天封顶到 now）

import type { LogEntry } from "@/baby-log/types";

export interface DateStats {
  bottleCount: number;
  bottleMl:    number;
  breastCount: number;       // 母乳次数（包括左/右/双侧任意一种 entry）
  bfL:         number;       // 母乳左侧分钟
  bfR:         number;       // 母乳右侧分钟
  wet:         number;
  dirty:       number;
  sleepMs:     number;
}

export function computeDateStats(
  entries: LogEntry[],
  viewingDate: string,
  sysToday:    string,
): DateStats {
  const dayStartTs = new Date(viewingDate + "T00:00:00").getTime() / 1000;
  const dayEndTs   = dayStartTs + 86400;
  const sleepUpper = viewingDate === sysToday
    ? Math.min(Date.now() / 1000, dayEndTs)
    : dayEndTs;

  let bottleCount = 0, bottleMl = 0;
  let breastCount = 0;
  let bfL = 0, bfR = 0;
  let wet = 0, dirty = 0;
  let sleepMs = 0;
  let sleepStart: number | null = null;

  // 假定 entries 已按 ts 升序传入；若没序，先排
  const sorted = [...entries].sort((a, b) => a.ts - b.ts);

  for (const e of sorted) {
    if (e.type === "formula" || e.type === "bottle_milk") {
      bottleCount++;
      bottleMl += (e as { amount_ml?: number }).amount_ml ?? 0;
    }
    if (e.type === "breastfeed") {
      breastCount++;
      const r = e as { side?: string; duration_min?: number; left_min?: number; right_min?: number };
      bfL += r.left_min  ?? (r.side === "left"  ? r.duration_min ?? 0 : 0);
      bfR += r.right_min ?? (r.side === "right" ? r.duration_min ?? 0 : 0);
    }
    if (e.type === "diaper") {
      const k = (e as { kind?: string }).kind;
      if (k === "wet") wet++;
      else dirty++;
    }
    if (e.type === "sleep") {
      const a = (e as { action?: string }).action;
      if (a === "start") sleepStart = e.ts;
      else if (a === "end") {
        // 没匹配上的 end → 入睡在前一天，本日份额从 00:00 起算
        const startTs = sleepStart ?? dayStartTs;
        sleepMs += Math.max(0, e.ts - startTs) * 1000;
        sleepStart = null;
      }
    }
  }
  // 没匹配上的 start → 起床在后一天 / 还在睡，本日份额算到 24:00（今天封顶 now）
  if (sleepStart != null) {
    sleepMs += Math.max(0, sleepUpper - sleepStart) * 1000;
  }

  return { bottleCount, bottleMl, breastCount, bfL, bfR, wet, dirty, sleepMs };
}

/** "1h23m" / "23m" 格式，给 stats / wake picker 用。
 *  四舍五入到最近分钟（跟 backend baby_log._fmt_duration 行为对齐）：避免
 *  ts 同分钟碰撞被 +1 秒后 floor 截掉一分钟，看上去比预期少一分钟。 */
export function formatHm(ms: number, T: { cdHour: string; cdMin: string }): string {
  const totalMin = Math.round(ms / 60000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (h > 0) return `${h}${T.cdHour}${m}${T.cdMin}`;
  return `${m}${T.cdMin}`;
}
