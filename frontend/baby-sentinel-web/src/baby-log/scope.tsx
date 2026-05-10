// 育儿日志的"当前查看日期"作用域。BabyLogPanel 是 provider，TodayList /
// DateNav / pickers 通过 hook 读：
//  - useViewingDate() → "YYYY-MM-DD" (本地日期)
//  - useShiftViewingDate() → (days) => void
//  - useIsToday() → boolean
// 后端 logApi.add/update 的 payload 会自动追加 date 字段（实现见 pickers.tsx
// useEntryMutations + QuickButtons quickAdd）。
//
// 午夜跨日：sysToday 用 state 持有，后台有个 effect 每分钟 + page-visible 时
// 重新计算系统日期。新一天到来时：
//   1. sysToday 更新到新日期
//   2. 如果用户当时正在看"今天"（viewingDate === oldSysToday）→ 跟着推进到新日期
//      （TodayList 的 useQuery key 含 viewingDate，自动 refetch）
//   3. 如果用户在看历史（如昨天）→ 不动，让用户保持原视图

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

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
  const [sysToday, setSysToday] = useState(() => localDateStr());
  const [viewingDate, setViewingDate] = useState(sysToday);
  const [scrollSignal, setScrollSignal] = useState(0);

  // 跨日检测：每 30s 比一次系统日期，外加 visibilitychange 立刻回检
  // （手机 / 笔记本休眠回来后 setInterval 可能被节流，靠 vis 事件追上）
  useEffect(() => {
    const tick = () => {
      const now = localDateStr();
      setSysToday((prev) => {
        if (now === prev) return prev;
        // 新一天：viewingDate 若停在旧 today 上，跟着推进到新 today
        setViewingDate((vd) => (vd === prev ? now : vd));
        return now;
      });
    };
    const id = window.setInterval(tick, 30_000);
    const onVis = () => { if (!document.hidden) tick(); };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  const shift = useCallback((days: number) => {
    setViewingDate((cur) => {
      const d = new Date(cur + "T00:00:00");
      d.setDate(d.getDate() + days);
      const next = localDateStr(d);
      // 不允许穿越未来
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
