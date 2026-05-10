// 传感器阈值——前端卡片"normal / warn / err"配色判断用，跟旧 config.js SENSOR_CFG 同义。
//
// 真值在 manager 那边 (root config.json `sensor_thresholds`)，通过 /api/manager/config
// 拉，UI 编辑入口在 manager 顶栏齿轮 → "传感器阈值" 分组。这里这一份只是本地默认值，
// 在网络拉到 config 之前兜底，避免 SensorPanel 渲染崩溃。

export interface SensorThresholds {
  breath:  { min: number; max: number };
  temp:    { min: number; max: number };
  battery: { low: number; warn: number; ok: number };
}

export const SENSOR_CFG_DEFAULT: SensorThresholds = {
  breath:  { min: 10, max: 60 },
  temp:    { min: 34, max: 38 },
  battery: { low: 20, warn: 40, ok: 60 },
};
