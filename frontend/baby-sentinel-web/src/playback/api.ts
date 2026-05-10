// 录像页 4 个数据源——日期列表 + 当日 segments / sensors / events。
// 同源 fetch，不需要走任何 proxy。

import type { Segment, SensorRow, EventRow } from "@/playback/types";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

export const playbackApi = {
  dates:    ()                      => get<string[]>("/api/recordings"),
  segments: (date: string)          => get<Segment[]>(`/api/recordings/${date}/segments`),
  sensors:  (date: string)          => get<SensorRow[]>(`/api/recordings/${date}/sensors`),
  events:   (date: string)          => get<EventRow[]>(`/api/log/date/${date}`),
};
