import { useState } from "react";
import { LangProvider, asLang } from "@/i18n";
import { ThemeProvider } from "@/theme";
import { WsProvider } from "@/api/ws";
import { useManagerConfig } from "@/api/manager-config";
import { Header } from "@/components/Header";
import { CameraView } from "@/components/CameraView";
import { SensorPanel } from "@/components/SensorPanel";
import { AlertDialog } from "@/components/AlertDialog";
import { AlertBanner } from "@/components/AlertBanner";
import { MobileTabs, type ActiveTab } from "@/components/MobileTabs";
import { BabyLogPanel } from "@/baby-log/Panel";
import { PlaybackPage } from "@/playback/Page";
import { cn } from "@/lib/utils";

export default function App() {
  // Manager config 的拉取统一走 useManagerConfig（其他需要 config 的组件复用同一份 cache）。
  // 这里只用它取 language，注入到下游所有 useT()。
  const cfgQ = useManagerConfig();
  const lang = asLang((cfgQ.data?.config as { language?: unknown } | undefined)?.language);

  // 轻量 pathname 路由：避免引 react-router，单独多一个 /playback 入口。
  // 录像页不需要 WebSocket（实时数据是历史回放），WsProvider 不包它，省掉无谓连接。
  const isPlayback = location.pathname === "/playback";

  return (
    <ThemeProvider>
      <LangProvider lang={lang}>
        {isPlayback ? <PlaybackPage /> : (
          <WsProvider>
            <AppShell />
          </WsProvider>
        )}
      </LangProvider>
    </ThemeProvider>
  );
}

function AppShell() {
  // mobile (md 以下) 只显示一列：tab=monitor 显左边 camera+sensor，tab=baby 显右边 baby log
  // md+ 两列同时显示，tab 条隐藏，state 不影响 layout
  const [tab, setTab] = useState<ActiveTab>("baby");

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-background text-foreground">
      <Header />
      <MobileTabs active={tab} onChange={setTab} />
      {/* Desktop (md+): 比例参照旧 index.html — 左列 1fr (camera+sensor 撑满)，
          右列 minmax(380px, 22%)（原版是 20%；这里宽 2pp 给中文按钮文字一点呼吸）。
          两列各自独立滚动；mobile (< md) 按 tab 决定外层是否滚动：
            - tab=monitor: main 滚（camera+sensor 自然堆叠）
            - tab=baby:    main 不滚，babyPanel 内的 TodayList 自己内部滚 */}
      <main className={cn(
        "flex-1 md:overflow-hidden",
        tab === "baby" ? "overflow-hidden" : "overflow-y-auto",
      )}>
        <div className={cn(
          "grid gap-4 px-3 py-3 md:h-full md:grid-cols-[1fr_minmax(380px,22%)] md:overflow-hidden",
          tab === "baby" && "h-full overflow-hidden",
        )}>
          {/* 左列在 md+ 改成 flex-col：sensor 自然高度（shrink-0），camera 撑满剩余空间。
              mobile (<md) 退回普通 stack，靠外层 main 一起滚；tab=baby 时隐藏。
              md:!flex 用强优先级把 hidden 在 md+ 上盖回——保证桌面永远两列同时显示。 */}
          <div className={cn(
            "flex flex-col gap-3 md:!flex md:h-full md:overflow-hidden md:pr-1",
            tab !== "monitor" && "hidden",
          )}>
            <div className="md:flex-1 md:min-h-0">
              <CameraView />
            </div>
            <SensorPanel />
          </div>
          {/* 右列：永远 overflow-hidden + h-full（mobile baby 模式 + md+ 通用），让
              BabyLogPanel 内部 flex 撑满 + TodayList 独立滚条。tab=monitor 时 mobile 隐藏。 */}
          <div className={cn(
            "h-full overflow-hidden md:!block",
            tab !== "baby" && "hidden",
          )}>
            <BabyLogPanel />
          </div>
        </div>
      </main>

      {/* 设备告警阻塞弹窗 + 后端业务告警吐司 — 全局 overlay，跟主布局解耦 */}
      <AlertDialog />
      <AlertBanner />
    </div>
  );
}
