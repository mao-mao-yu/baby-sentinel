// 非阻塞告警吐司 — 跟旧 index.html addAlert + alert-banner 行为对齐：
//  - WS `alert` 帧（喂奶提醒 / BLE 心跳超时 / 后端业务告警）追加进 useAlerts()
//  - 仅 level=warning|danger 才弹，info 静默
//  - 8 秒自动收
//  - 新告警进来覆盖旧的（旧的提前消失）
//
// 设备告警 (`alert_active`) 走 AlertDialog 阻塞模态，跟这里互不干扰；
// 一个告警可能同时在 alert_active 和 alerts 历史里出现，弹窗 + 吐司都会触发，正常。

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { useAlerts } from "@/api/ws";
import type { AlertEntry } from "@/types/web";
import { cn } from "@/lib/utils";

const HIDE_AFTER_MS = 8000;

export function AlertBanner() {
  const alerts = useAlerts();
  const [shown, setShown] = useState<AlertEntry | null>(null);
  const prevLenRef = useRef(0);

  // 监听 alerts 列表"恰好+1"事件 → 视为新到的实时告警，弹吐司。
  // handshake 批量塞进来 N 条历史（length 跳变 N>1）时不弹，避免每次重连都刷一堆旧告警。
  useEffect(() => {
    const prev = prevLenRef.current;
    prevLenRef.current = alerts.length;
    if (alerts.length !== prev + 1) return;
    const e = alerts[alerts.length - 1];
    if (e && (e.level === "danger" || e.level === "warning")) {
      setShown(e);
    }
  }, [alerts]);

  useEffect(() => {
    if (!shown) return;
    const id = window.setTimeout(() => setShown(null), HIDE_AFTER_MS);
    return () => clearTimeout(id);
  }, [shown]);

  if (!shown) return null;

  const toneCls = shown.level === "danger"
    ? "border-destructive/60 bg-destructive/15 text-destructive"
    : "border-amber-500/60 bg-amber-500/15 text-amber-300";

  return (
    <div className={cn(
      "fixed bottom-3 left-1/2 z-50 -translate-x-1/2",
      "flex max-w-[92vw] items-center gap-2 rounded-md border px-3 py-2 text-sm shadow-lg",
      "backdrop-blur",
      toneCls,
    )}>
      <span className="font-mono text-[11px] opacity-80">{shown.timestamp}</span>
      <span className="line-clamp-2">{shown.message}</span>
      <button onClick={() => setShown(null)}
              className="ml-1 rounded p-0.5 text-current opacity-70 hover:opacity-100"
              aria-label="dismiss">
        <X className="size-3.5" />
      </button>
    </div>
  );
}
