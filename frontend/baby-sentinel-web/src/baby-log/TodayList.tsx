// 当日条目列表：升序（00:00 在最上）+ 滚动行为对齐旧 renderTodayLog()：
//
// 1. 用户在底部 → 新条目自动跟到新底部
// 2. 用户在中间手动滚 → 内容增长不打扰，scrollTop 保持
// 3. 切日期/删条目让总高度变短到 scrollTop 位置以下 → clamp 到新底部
// 4. mutation 添加成功 → scrollSignal bump → 下一次 entries 更新后平滑滚到底部
//    （新条目时间戳 ≈ now，永远在最后；不需要单独 scrollIntoView 某个 ts）

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useT } from "@/i18n";
import { logApi } from "@/baby-log/api";
import { fmtEntry } from "@/baby-log/format";
import { EditDialog } from "@/baby-log/EditDialog";
import { useScrollSignal, useViewingDate } from "@/baby-log/scope";
import type { LogEntry } from "@/baby-log/types";
import { cn } from "@/lib/utils";

export function TodayList() {
  const T = useT();
  const date = useViewingDate();
  const q = useQuery({ queryKey: ["log", date], queryFn: () => logApi.byDate(date) });
  const entries = q.data ?? [];
  const [editing, setEditing] = useState<LogEntry | null>(null);

  const scrollEl = useRef<HTMLDivElement>(null);
  const wasAtBottomRef = useRef(true);            // 初始视为贴底，首次渲染滚到底
  const pendingScrollBottomRef = useRef(false);   // mutation 后 + 下次 entries 变化时滚到底

  // mutation 成功 → scope.bumpScroll() → scrollSignal 增。这里只标记，下面 layout effect
  // 等 entries 真正更新后再滚（避免对旧 DOM 算 scrollHeight）。
  const scrollSignal = useScrollSignal();
  useEffect(() => {
    if (scrollSignal > 0) pendingScrollBottomRef.current = true;
  }, [scrollSignal]);

  const onScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    wasAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
  };

  useLayoutEffect(() => {
    const el = scrollEl.current;
    if (!el) return;

    if (pendingScrollBottomRef.current) {
      // 新条目刚加进来 → 平滑滚到新底部
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      pendingScrollBottomRef.current = false;
    } else if (wasAtBottomRef.current) {
      // 之前贴底、列表自然增长 → 直接跟到新底部
      el.scrollTop = el.scrollHeight;
    } else if (el.scrollTop + el.clientHeight > el.scrollHeight) {
      // 切日期 / 删条目 后列表变短，超出新底部 → clamp 到底
      el.scrollTop = Math.max(0, el.scrollHeight - el.clientHeight);
    }
    // else 保持 scrollTop（默认行为，浏览器自动）
  }, [entries]);

  return (
    <>
      {/* flex-1 min-h-0 overflow-y-auto：内部独立滚条；上下其他兄弟 (countdown / tabs /
          datenav / stats) 不滚。mobile + md+ 一致行为。
          overscroll-contain：拽到顶/底时不把滚动事件冒泡给祖先 → 防 iOS rubber-band
          抬整个 UI。 */}
      <div ref={scrollEl} onScroll={onScroll}
           className="flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain rounded-md border border-border/40 bg-card/40">
        {entries.length === 0 ? (
          <div className="px-3 py-4 text-center text-xs text-muted-foreground">
            {q.isLoading ? "…" : T.feedNone}
          </div>
        ) : (
          [...entries]
            .sort((a, b) => a.ts - b.ts)
            .map((e) => <Row key={e.ts} entry={e} onEdit={() => setEditing(e)} T={T} />)
        )}
      </div>
      <EditDialog entry={editing} onClose={() => setEditing(null)} />
    </>
  );
}

function Row({ entry, onEdit, T }: {
  entry: LogEntry;
  onEdit: () => void;
  T: ReturnType<typeof useT>;
}) {
  const f = fmtEntry(entry, T);
  return (
    <button type="button" onClick={onEdit}
            className={cn(
              "flex items-center gap-2.5 border-b border-border/30 px-3 py-2 text-left text-sm last:border-b-0",
              "transition hover:bg-accent/40",
            )}>
      <span className="w-12 shrink-0 font-mono text-xs text-muted-foreground">
        {entry.time || "--"}
      </span>
      <span className="text-base">{f.icon}</span>
      <span className="truncate">{f.summary}</span>
    </button>
  );
}
