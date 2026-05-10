// 手机端 (md 以下) 的 3 段 tab 条 — 跟旧 .mobile-tabs 行为一致：
//   📹 监控   →  显示 camera + sensor 列
//   🍼 育儿   →  显示 baby log 列
//   📼 回放   →  跨端口跳到 server.py 的 /playback 页（旧静态 HTML，没迁）
// md+ 隐藏，桌面同时显示两列不需要切换。

import { useT } from "@/i18n";
import { useManagerConfig } from "@/api/manager-config";
import { cn } from "@/lib/utils";

export type ActiveTab = "monitor" | "baby";

interface Props {
  active:    ActiveTab;
  onChange:  (t: ActiveTab) => void;
}

export function MobileTabs({ active, onChange }: Props) {
  const T = useT();

  // playback 页跑在跟 baby-sentinel-web 同 origin（server.py:8080），相对路径直接走
  const cfgQ = useManagerConfig();
  const webPort = (cfgQ.data?.config as { web_port?: number } | undefined)?.web_port ?? 8080;
  const playbackUrl = `http://${location.hostname}:${webPort}/playback`;

  return (
    <div className="flex shrink-0 border-b border-border/60 bg-card/40 md:hidden">
      <TabBtn active={active === "monitor"} onClick={() => onChange("monitor")}>{T.mobTabMonitor}</TabBtn>
      <TabBtn active={active === "baby"   } onClick={() => onChange("baby")   }>{T.mobTabBaby   }</TabBtn>
      <a href={playbackUrl} className={cn(tabBaseCls, "text-muted-foreground")}>
        {T.mobTabPlayback}
      </a>
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
