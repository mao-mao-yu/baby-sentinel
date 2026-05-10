import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { useT } from "@/i18n";
import { useSensor, useWsConn } from "@/api/ws";
import { useTheme } from "@/theme";
import { cn } from "@/lib/utils";

export function Header() {
  const T = useT();
  const conn = useWsConn();
  const sensor = useSensor();
  const { theme, toggle: toggleTheme } = useTheme();

  // BLE 徽章三态（沿用旧 index.html 行为）：
  //  - WS 关 → "服务器断开" 红
  //  - WS 开 + ble_ok=false → "传感器" 红 (WS 通但 BLE 没连上)
  //  - WS 开 + ble_ok=true  → "传感器" 绿
  const wsClosed = conn === "closed";
  const bleOk    = !!sensor.ble_ok;
  const bleOnline = conn === "open" && bleOk;
  const bleLabel  = wsClosed ? T.svrOff : bleOnline ? T.bleOn : T.bleOff;

  // 摄像头徽章：sensor.cam_ok 由 shared/camera.py 的 RTSP 探活循环写入 sensor_state。
  // 注意它不等于"WebRTC 视频是否已 live"——只反映 RTSP 源是否在线（ffmpeg 能 probe 通）。
  // 视频流真的开始播放在 CameraView 内部管理，UI 上 cam-badge 只看 cam_ok 就够。
  const camOnline = conn === "open" && !!sensor.cam_ok;
  const camLabel  = camOnline ? T.camOn : T.camOff;

  // Real-time clock —— 1s 一跳，只显示 HH:MM:SS
  const [clock, setClock] = useState(() => fmtClock(new Date()));
  useEffect(() => {
    const id = window.setInterval(() => setClock(fmtClock(new Date())), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="shrink-0 border-b border-border/60 bg-background px-4 py-2.5">
      <div className="flex items-center gap-3">
        <span className="text-base font-semibold tracking-tight">🍼 {T.title}</span>

        <div className="ml-auto flex items-center gap-2">
          <Pill ok={bleOnline}>{bleLabel}</Pill>
          <Pill ok={camOnline}>{camLabel}</Pill>
          <span className="hidden font-mono text-xs text-muted-foreground sm:inline">
            {clock}
          </span>
          {/* md+ 才显示——手机端 MobileTabs 里有"📼 回放" tab，这里再放就重复 */}
          <a href="/playback"
             className="hidden rounded-md border border-border/60 px-2.5 py-1 text-xs hover:bg-accent md:inline-block">
            {T.pbTitle}
          </a>
          {/* 日 / 夜模式切换——日间显月亮（点了变夜），夜间显太阳（点了变日） */}
          <button type="button"
                  onClick={toggleTheme}
                  title={theme === "dark" ? "Light" : "Dark"}
                  className="inline-flex size-8 items-center justify-center rounded-md border border-border/60 hover:bg-accent">
            {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </div>
      </div>
    </header>
  );
}

// 小药丸：左侧颜色点 + label 文字。绿/红根据 ok。
// 文字 / 圆点的绿色在亮色模式下用深色阶（700/600），夜间换浅色阶（300/400）保对比度。
function Pill({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px]",
      ok
        ? "border-emerald-600/50 bg-emerald-500/15 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/10 dark:text-emerald-300"
        : "border-destructive/40 bg-destructive/10 text-destructive",
    )}>
      <span className={cn("size-1.5 rounded-full",
                          ok ? "bg-emerald-600 dark:bg-emerald-400" : "bg-destructive")} />
      {children}
    </span>
  );
}

function fmtClock(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
