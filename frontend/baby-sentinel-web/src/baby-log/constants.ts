// 育儿日志快捷选项常量。改这里 → 影响 AmountPicker / BreastPicker / PoopPicker。

export const FORMULA_AMOUNTS = [30, 40, 50, 60, 70, 80, 90, 100, 120, 140, 160, 200];
export const BREAST_DURATIONS = [5, 10, 15, 20, 25, 30];

// 便便颜色 - 7 档色板，hex 用于色块按钮
export const POOP_COLORS: { key: string; hex: string }[] = [
  { key: "white",  hex: "#e0e0e0" },
  { key: "yellow", hex: "#f5d300" },
  { key: "orange", hex: "#f59400" },
  { key: "brown",  hex: "#8b4513" },
  { key: "green",  hex: "#2ecc71" },
  { key: "red",    hex: "#e74c3c" },
  { key: "black",  hex: "#2c2c2c" },
];

// 便便量 / 硬度 4 档（key 用于 i18n + 后端持久化值）
export const POOP_AMOUNT_KEYS  = ["tiny", "small", "normal", "large"] as const;
export const POOP_CONS_KEYS    = ["loose", "soft", "normal", "hard"]  as const;

export type PoopAmount = typeof POOP_AMOUNT_KEYS[number];
export type PoopCons   = typeof POOP_CONS_KEYS[number];
export type PoopColor  = typeof POOP_COLORS[number]["key"];
