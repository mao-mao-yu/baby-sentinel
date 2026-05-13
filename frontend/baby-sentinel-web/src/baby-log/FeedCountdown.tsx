// 喂奶倒计时 — 1Hz 自更新，跟旧 index.html tickCountdown() 行为一致。
// 数据来自 babyStats.next_feed_ts (unix sec)，超时显示"已超过 X 分 Y 秒"。

import { useEffect, useState } from "react";
import { useT } from "@/i18n";
import { useBabyStats } from "@/api/ws";
import { cn } from "@/lib/utils";

export function FeedCountdown() {
  const T = useT();
  const stats = useBabyStats() as null | {
    next_feed_ts?: number | null;
    last_feed_time?: string | null;
    last_feed_ml?: number | null;
    recommended_ml?: number | null;
  };

  // 1Hz tick — 用 nowMs state 强制重渲染倒计时数字
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const target = stats?.next_feed_ts ?? null;
  const remainSec = target == null ? null : target - Math.floor(now / 1000);

  const overdue   = remainSec != null && remainSec < 0;
  const soonish   = remainSec != null && remainSec >= 0 && remainSec <= 20 * 60;

  const timeStr = target == null
    ? "--:--"
    : new Date(target * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });

  const durationStr = remainSec == null
    ? T.feedNone
    : overdue
      ? `${T.cdOverdue} ${formatDuration(-remainSec, T)}`
      : `${T.cdRemain} ${formatDuration(remainSec, T)}`;

  const subText = stats?.last_feed_time
    ? `${T.lastFeed} ${stats.last_feed_time}${stats.last_feed_ml ? ` · ${stats.last_feed_ml}mL` : ""}`
    : (stats?.recommended_ml ? `${T.feedRecMl} ${stats.recommended_ml}mL` : "");

  return (
    <div className={cn(
      "rounded-md border px-3 py-2",
      overdue ? "border-destructive/60 bg-destructive/10"
              : soonish ? "border-amber-500/60 bg-amber-500/10"
                        : "border-border/40 bg-card/40",
    )}>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{T.labelNextFeed}</span>
        <span>{subText}</span>
      </div>
      <div className="mt-0.5 flex items-baseline justify-between gap-2">
        <span className="text-2xl font-semibold">{timeStr}</span>
        <span className={cn(
          "text-sm font-medium",
          overdue ? "text-destructive"
                  : soonish ? "text-amber-700 dark:text-amber-300"
                            : "text-foreground",
        )}>
          {durationStr}
        </span>
      </div>
    </div>
  );
}

function formatDuration(sec: number, T: ReturnType<typeof useT>): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}${T.cdHour} ${m}${T.cdMin} ${s}${T.cdSec}`;
  if (m > 0) return `${m}${T.cdMin} ${s}${T.cdSec}`;
  return `${s}${T.cdSec}`;
}
