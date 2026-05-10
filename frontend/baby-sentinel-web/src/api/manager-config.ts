// Manager (9091) 拥有全局 config (lang / sensor 阈值 / baby info / 告警渠道 / Pi 等)。
// 这里把 fetcher 和 selector 集中起来，所有需要全局 config 的组件都共用同一个
// React Query cache（queryKey: "mgr-config"）。manager UI 那边保存后会 invalidate
// 自己的 cache；但跨进程到这里的 cache 不会自动失效，用户需刷新页面（v1）。

import { useQuery } from "@tanstack/react-query";
import { SENSOR_CFG_DEFAULT, type SensorThresholds } from "@/config-ui";

export interface ManagerConfigResponse {
  ok:     boolean;
  config: Record<string, unknown>;
}

export async function fetchManagerConfig(): Promise<ManagerConfigResponse> {
  const r = await fetch("/api/manager/config");
  if (!r.ok) throw new Error(`/api/manager/config → ${r.status}`);
  return r.json();
}

export function useManagerConfig() {
  return useQuery({ queryKey: ["mgr-config"], queryFn: fetchManagerConfig });
}

/** go2rtc 浏览器端 WebRTC 接入端口（config.go2rtc_port，默认 1984）。 */
export function useGo2rtcPort(): number {
  const q = useManagerConfig();
  const cfg = q.data?.config as { go2rtc_port?: number } | undefined;
  return cfg?.go2rtc_port ?? 1984;
}

/** 录像分段时长 (秒)，回放时间轴每段彩条的固定宽度推估用。默认 360s = 6min。 */
export function useSegmentS(): number {
  const q = useManagerConfig();
  const cfg = q.data?.config as { segment_s?: number } | undefined;
  return cfg?.segment_s ?? 360;
}

export function useSensorThresholds(): SensorThresholds {
  const q = useManagerConfig();
  const cfg = q.data?.config as
    { sensor_thresholds?: Partial<SensorThresholds> } | undefined;
  const t = cfg?.sensor_thresholds;
  // 字段任一缺失时合并默认值，UI 不会崩。
  return {
    breath:  { ...SENSOR_CFG_DEFAULT.breath,  ...(t?.breath  ?? {}) },
    temp:    { ...SENSOR_CFG_DEFAULT.temp,    ...(t?.temp    ?? {}) },
    battery: { ...SENSOR_CFG_DEFAULT.battery, ...(t?.battery ?? {}) },
  };
}
