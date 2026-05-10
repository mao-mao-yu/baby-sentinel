// 育儿日志的"当前查看日期"作用域。BabyLogPanel 是 provider，TodayList /
// DateNav / pickers 通过 hook 读：
//  - useViewingDate() → "YYYY-MM-DD" (本地日期)
//  - useShiftViewingDate() → (days) => void
//  - useIsToday() → boolean
// 后端 logApi.add/update 的 payload 会自动追加 date 字段（实现见 pickers.tsx
// useEntryMutations + QuickButtons quickAdd）。

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

export function localDateStr(d?: Date): string {
  d = d ?? new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

interface Ctx {
  viewingDate: string;
  sysToday:    string;
  shift:       (days: number) => void;
  setDate:     (d: string) => void;
  /** 一次性事件计数：mutation 成功后递增，TodayList useEffect 监听到后会
   *  下一次 entries 更新完滚到底部展示新条目。 */
  scrollSignal: number;
  bumpScroll:  () => void;
}

const BabyLogScopeContext = createContext<Ctx | null>(null);

export function BabyLogScopeProvider({ children }: { children: ReactNode }) {
  const sysToday = localDateStr();
  const [viewingDate, setViewingDate] = useState(sysToday);
  const [scrollSignal, setScrollSignal] = useState(0);

  const shift = useCallback((days: number) => {
    setViewingDate((cur) => {
      const d = new Date(cur + "T00:00:00");
      d.setDate(d.getDate() + days);
      const next = localDateStr(d);
      // 不允许穿越未来；若 sysToday 跨过午夜（用户长时间不刷新），下一次进 effect 时再追上
      return next > sysToday ? sysToday : next;
    });
  }, [sysToday]);

  const bumpScroll = useCallback(() => setScrollSignal((n) => n + 1), []);

  return (
    <BabyLogScopeContext.Provider value={{
      viewingDate, sysToday, shift, setDate: setViewingDate, scrollSignal, bumpScroll,
    }}>
      {children}
    </BabyLogScopeContext.Provider>
  );
}

function useScope(): Ctx {
  const c = useContext(BabyLogScopeContext);
  if (!c) throw new Error("useScope outside BabyLogScopeProvider");
  return c;
}

export const useViewingDate     = () => useScope().viewingDate;
export const useSysToday        = () => useScope().sysToday;
export const useIsViewingToday  = () => { const s = useScope(); return s.viewingDate === s.sysToday; };
export const useShiftViewingDate = () => useScope().shift;
export const useScrollSignal    = () => useScope().scrollSignal;
export const useBumpScroll      = () => useScope().bumpScroll;
