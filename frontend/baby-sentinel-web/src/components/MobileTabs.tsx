// 手机端 (md 以下) 的 2 段 tab 条：
//   📹 监控   →  显示 camera + sensor 列
//   🍼 育儿   →  显示 baby log 列
// 回放在 Header 顶栏右上角的按钮里（mobile + md+ 都显示）。
// md+ 整条隐藏，桌面同时显示两列不需要切换。

import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

export type ActiveTab = "monitor" | "baby";

interface Props {
  active:    ActiveTab;
  onChange:  (t: ActiveTab) => void;
}

export function MobileTabs({ active, onChange }: Props) {
  const T = useT();
  return (
    <div className="flex shrink-0 border-b border-border/60 bg-card/40 md:hidden">
      <TabBtn active={active === "monitor"} onClick={() => onChange("monitor")}>{T.mobTabMonitor}</TabBtn>
      <TabBtn active={active === "baby"   } onClick={() => onChange("baby")   }>{T.mobTabBaby   }</TabBtn>
    </div>
  );
}

const tabBaseCls =
  "flex-1 px-2 py-2.5 text-center text-sm border-b-2 transition-colors";

function TabBtn({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button type="button" onClick={onClick}
            className={cn(
              tabBaseCls,
              active
                ? "border-blue-400 text-foreground"
                : "border-transparent text-muted-foreground",
            )}>
      {children}
    </button>
  );
}
