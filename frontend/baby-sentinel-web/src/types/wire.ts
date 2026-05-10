// Wire types — 和 backend/services/web/server.py 的 broadcast / handshake 帧对齐。
// sense-u-ble v2 起 posture / alert message 都是英文 enum；详见
// /Users/maomaoyu/Desktop/sense-u-ble/README.md。

export type Posture = "supine" | "prone" | "left_side" | "right_side" | "sitting";

export type AlertLevel = "info" | "warning" | "danger";

export interface SensorFrame {
  breath_rate: number  | null;
  temperature: number  | null;
  posture:     Posture | null;
  battery:     number  | null;
  wearing:     boolean | null;
  charge:      0 | 1 | 2 | null;
  activity:    number  | null;
  ble_ok:      boolean;
  cam_ok:      boolean;          // RTSP probe in shared/camera.py 写到 sensor_state
  last_update: string  | null;   // "HH:MM:SS"
}

// baby_log.get_stats() 字段繁多且会随业务扩展；先列常用字段 + 索引签名兜底，
// 真正用到的 hook 自己窄化。
export interface BabyStats {
  feed_count:       number;
  total_ml:         number;
  avg_ml:           number;
  last_feed_time:   string | null;
  last_feed_ml:     number | null;
  next_feed_ts:     number | null;
  mins_until_next:  number | null;
  recommended_ml:   number | null;
  interval_min:     number;
  age_days:         number;
  [key: string]: unknown;
}

export interface AlertActive {
  alert_id:  string;
  level:     AlertLevel;
  mode?:     number;       // sense-u-ble 设备原始 alertMode
  message:   string;
  timestamp: string;
}

export interface AlertEntry {
  level:     AlertLevel;
  message:   string;
  timestamp: string;
}

// ── Wire frames（discriminated union by `type`）─────────────────────────

export interface StateFrame {
  type:          "state";
  sensor?:       Partial<SensorFrame>;
  baby_stats?:   BabyStats;
  birth_date?:   string;
  alert_active?: AlertActive;
  alerts?:       AlertEntry[];
}

export interface SensorWireFrame extends Partial<SensorFrame> {
  type: "sensor";
}

export interface BabyStatsWireFrame extends BabyStats {
  type: "baby_stats";
}

export interface AlertWireFrame extends AlertEntry {
  type: "alert";
}

export interface AlertActiveWireFrame extends AlertActive {
  type: "alert_active";
}

export interface AlertDismissedFrame {
  type:     "alert_dismissed";
  alert_id: string;
}

export type WsFrame =
  | StateFrame
  | SensorWireFrame
  | BabyStatsWireFrame
  | AlertWireFrame
  | AlertActiveWireFrame
  | AlertDismissedFrame;
