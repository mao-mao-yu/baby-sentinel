// baby_log entry shapes — 跟 backend/services/web/baby_log.py add_entry/get_today 一致。
// 后端持久化是 SQLite + payload JSON，core 字段是独立列；这里只列 UI 真正用到的。

import type { PoopAmount, PoopCons, PoopColor } from "@/baby-log/constants";

export type EntryType =
  | "formula" | "bottle_milk" | "breastfeed" | "feed"  // 旧 "feed" 兼容
  | "sleep" | "diaper"
  | "temperature" | "height" | "weight"
  | "bath" | "pump";

export type Side = "left" | "right" | "both";

export interface BaseEntry {
  ts:     number;          // unix sec, primary key
  date:   string;          // "YYYY-MM-DD"
  time:   string;          // "HH:MM"
  type:   EntryType;
  // 自由 payload 兜底，避免 strict 类型挡住边角字段
  [key: string]: unknown;
}

export interface FormulaEntry extends BaseEntry {
  type: "formula" | "bottle_milk" | "feed" | "pump";
  amount_ml: number | null;
}

export interface BreastfeedEntry extends BaseEntry {
  type: "breastfeed";
  side?: Side;
  duration_min?: number;
  left_min?:     number;
  right_min?:    number;
  amount_ml?:    number | null;
}

export interface SleepEntry extends BaseEntry {
  type: "sleep";
  action: "start" | "end";
  duration_str?: string;            // sleep-end 上记录持续时长
  cross_day_wake_ts?: number;       // sleep-start 跨天唤醒时回填的 end ts
}

export interface DiaperEntry extends BaseEntry {
  type: "diaper";
  kind: "wet" | "dirty";
  amount?:      PoopAmount;
  consistency?: PoopCons;
  color?:       PoopColor;
}

export interface NumberEntry extends BaseEntry {
  type: "temperature" | "height" | "weight";
  value: number;
}

export interface BathEntry extends BaseEntry {
  type: "bath";
}

export type LogEntry =
  | FormulaEntry | BreastfeedEntry | SleepEntry | DiaperEntry | NumberEntry | BathEntry;
