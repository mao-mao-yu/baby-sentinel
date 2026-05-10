// Wire types — 跟 backend/services/web/server.py 录像相关 endpoint 对齐。

export interface Segment {
  file:    string;
  ts:      number;          // 段开始 unix 秒（带 sub-second，来自 index.csv start_pts_time）
  end_ts?: number;          // 段结束 unix 秒（来自 index.csv end_pts_time，可能没有）
  url:     string;          // 形如 /recordings/{date}/video/{file}
}

export interface SensorRow {
  ts:           number;
  breath_rate?: number | null;
  temperature?: number | null;
  posture?:     string | null;
  battery?:     number | null;
  [key: string]: unknown;
}

export interface EventRow {
  ts:    number;
  type:  string;
  time?: string;
  [key: string]: unknown;
}
