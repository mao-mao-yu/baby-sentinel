// 育儿日志主面板 — 倒计时 + 快捷按钮 + 日期切换 + 条目列表 四段式。
// 跟旧 index.html 右侧 panel-baby div 1:1 对齐。
// BabyLogScopeProvider 提供 viewingDate 给所有子组件（DateNav 切换、TodayList 拉取、
// pickers / QuickButtons 写入时填 date 字段）。

import { useT } from "@/i18n";
import { BabyLogScopeProvider } from "@/baby-log/scope";
import { FeedCountdown } from "@/baby-log/FeedCountdown";
import { QuickButtons } from "@/baby-log/QuickButtons";
import { DateNav } from "@/baby-log/DateNav";
import { DateStats } from "@/baby-log/DateStats";
import { TodayList } from "@/baby-log/TodayList";

export function BabyLogPanel() {
  const T = useT();
  return (
    <BabyLogScopeProvider>
      {/* h-full + flex-col：整列撑满（容器高度由父决定）；TodayList 自己 flex-1 拿
          剩余空间独立滚动。这套行为在 mobile 和 md+ 通用。 */}
      <section className="flex h-full flex-col gap-3">
        <h2 className="text-sm font-semibold text-muted-foreground">{T.labelBabyLog}</h2>
        <FeedCountdown />
        <QuickButtons />
        <DateNav />
        <DateStats />
        <TodayList />
      </section>
    </BabyLogScopeProvider>
  );
}
