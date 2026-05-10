// 日期切换条 — ‹ M月D日 [今日] › 三段式，跟旧 .log-date-nav-bar 对齐。
// 未来日期 next 按钮 disabled。

import { useLang } from "@/i18n";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useShiftViewingDate, useSysToday, useViewingDate } from "@/baby-log/scope";
import { cn } from "@/lib/utils";

export function DateNav() {
  const lang = useLang();
  const viewing = useViewingDate();
  const sysToday = useSysToday();
  const shift = useShiftViewingDate();

  const d = new Date(viewing + "T00:00:00");
  const isToday = viewing === sysToday;

  // ja: M月D日; zh: 同 (中日字面接近，简化共用一种格式)
  const label = lang === "ja"
    ? `${d.getMonth() + 1}月${d.getDate()}日`
    : `${d.getMonth() + 1}月${d.getDate()}日`;
  const todayTag = lang === "ja" ? "今日" : "今日";

  return (
    <div className="flex items-center gap-1.5">
      <Button variant="outline" size="icon" className="size-7"
              onClick={() => shift(-1)}>
        <ChevronLeft className="size-4" />
      </Button>
      <div className="flex flex-1 items-center justify-center gap-1.5 text-sm font-semibold">
        <span>{label}</span>
        {isToday && <span className="text-xs font-medium text-emerald-400">{todayTag}</span>}
      </div>
      <Button variant="outline" size="icon" className="size-7"
              disabled={isToday}
              onClick={() => shift(1)}
              title={isToday ? undefined : ""}>
        <ChevronRight className={cn("size-4", isToday && "opacity-40")} />
      </Button>
    </div>
  );
}
