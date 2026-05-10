// WebSocket connection layer for the main BabySentinel UI.
//
// 单一 WS 维护所有实时状态：传感器 / 育儿统计 / 告警弹窗 / 告警历史。
// 跟原 index.html 的 connectWs() 行为对齐：指数退避重连 (1s → 2s → 4s → 8s → 15s)。
//
// 暴露 Context + 多个 select hook，方便组件按需订阅，不用全部读 useWs()。

import {
  createContext, useContext, useEffect, useState,
  type ReactNode,
} from "react";
import type {
  AlertActive, AlertEntry, BabyStats, SensorFrame, WsFrame,
} from "@/types/web";

export type WsConnState = "connecting" | "open" | "closed";

interface WsContextValue {
  connectionState: WsConnState;
  sensor:        Partial<SensorFrame>;
  babyStats:     BabyStats | null;
  birthDate:     string;
  alertActive:   AlertActive | null;
  alerts:        AlertEntry[];   // 历史日志，按到达顺序追加，最多 ALERTS_MAX 条
}

const ALERTS_MAX = 50;

const defaults: WsContextValue = {
  connectionState: "connecting",
  sensor:      {},
  babyStats:   null,
  birthDate:   "",
  alertActive: null,
  alerts:      [],
};

const WsContext = createContext<WsContextValue>(defaults);

export function WsProvider({ children }: { children: ReactNode }) {
  const [conn,        setConn]        = useState<WsConnState>("connecting");
  const [sensor,      setSensor]      = useState<Partial<SensorFrame>>({});
  const [babyStats,   setBabyStats]   = useState<BabyStats | null>(null);
  const [birthDate,   setBirthDate]   = useState<string>("");
  const [alertActive, setAlertActive] = useState<AlertActive | null>(null);
  const [alerts,      setAlerts]      = useState<AlertEntry[]>([]);

  useEffect(() => {
    let cancelled = false;
    let retryDelay = 1000;
    let ws: WebSocket | null = null;
    let timer: number | null = null;

    const connect = () => {
      if (cancelled) return;
      setConn("connecting");
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);

      ws.onopen = () => {
        retryDelay = 1000;
        setConn("open");
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as WsFrame;
          switch (msg.type) {
            case "state": {
              if (msg.sensor) setSensor(msg.sensor);
              if (msg.baby_stats) setBabyStats(msg.baby_stats);
              if (msg.birth_date != null) setBirthDate(msg.birth_date);
              setAlertActive(msg.alert_active ?? null);
              if (msg.alerts) setAlerts(msg.alerts.slice(-ALERTS_MAX));
              break;
            }
            case "sensor": {
              const { type: _t, ...rest } = msg;
              void _t;
              setSensor((prev) => ({ ...prev, ...rest }));
              break;
            }
            case "baby_stats": {
              const { type: _t, ...rest } = msg;
              void _t;
              setBabyStats(rest as BabyStats);
              break;
            }
            case "alert": {
              const { type: _t, ...rest } = msg;
              void _t;
              setAlerts((prev) => [...prev, rest as AlertEntry].slice(-ALERTS_MAX));
              break;
            }
            case "alert_active": {
              const { type: _t, ...rest } = msg;
              void _t;
              setAlertActive(rest as AlertActive);
              break;
            }
            case "alert_dismissed": {
              setAlertActive((prev) =>
                prev && prev.alert_id === msg.alert_id ? null : prev,
              );
              break;
            }
          }
        } catch {
          // ignore non-JSON frames
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        setConn("closed");
        timer = window.setTimeout(connect, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 15000);
      };

      // onerror 触发后 onclose 也会触发；让 onclose 统一处理重连。
      ws.onerror = () => ws?.close();
    };

    connect();

    return () => {
      cancelled = true;
      if (timer != null) clearTimeout(timer);
      ws?.close();
    };
  }, []);

  return (
    <WsContext.Provider
      value={{ connectionState: conn, sensor, babyStats, birthDate, alertActive, alerts }}
    >
      {children}
    </WsContext.Provider>
  );
}

export const useWs          = () => useContext(WsContext);
export const useWsConn      = () => useContext(WsContext).connectionState;
export const useSensor      = () => useContext(WsContext).sensor;
export const useBabyStats   = () => useContext(WsContext).babyStats;
export const useBirthDate   = () => useContext(WsContext).birthDate;
export const useAlertActive = () => useContext(WsContext).alertActive;
export const useAlerts      = () => useContext(WsContext).alerts;
