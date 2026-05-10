// Per-service config schema for the manager UI's config editor.
//
// 修改时记得同步 config.example.json 和 root config.json 的字段名。
// key 支持 dotted-path（如 baby.name），后端按层级写回。
//
// 历史脚印：array_int 已废弃。Discord 雪花 ID 是 64-bit (~10^18)，超 JS
// Number.MAX_SAFE_INTEGER (2^53)，Number(value) 会丢精度让末几位被静默抹零
// → 频道找不到 → 推送失败。所有 ID 类字段必须用 array_str 全程当字符串处理。
//
// 归类原则：
//  - global = 跨多个 service 消费的字段（语言、告警渠道、Pi 连接、log_level、宝宝信息）
//  - 各 service entry 只含该服务**独占**的旋钮

import type { Lang } from "@/i18n";

export type FieldType =
  | "string" | "password" | "int" | "number" | "bool" | "enum" | "array_str";

export interface LocalizedString { zh: string; ja: string; }

interface BaseField {
  key:    string;            // dotted path
  label:  LocalizedString;
  hint?:  LocalizedString;
  group?: string;            // global dialog 用；service 卡的字段不用分组
}

export type FieldDef =
  | (BaseField & { type: "string" | "password" | "int" | "number" | "bool" | "array_str" })
  | (BaseField & {
      type:    "enum";
      options: { value: string; label: LocalizedString }[];
    });

export type ConfigSchema = Record<string, FieldDef[]>;

// global dialog 的分组标题。schema 字段里写 group: "alerts" 等 key，渲染时从这里取标签。
export const FIELD_GROUPS: Record<string, LocalizedString> = {
  display: { zh: "显示",         ja: "表示" },
  baby:    { zh: "宝宝信息",     ja: "赤ちゃん情報" },
  sensor:  { zh: "传感器阈值",   ja: "センサー閾値" },
  alerts:  { zh: "告警推送",     ja: "アラート通知" },
  pi:      { zh: "远端 Pi",      ja: "リモート Pi" },
  log:     { zh: "日志",         ja: "ログ" },
};

export const CONFIG_SCHEMA: ConfigSchema = {
  // ── 跨服务的全局偏好 / 共享配置（manager 顶栏齿轮入口）────────────────
  // 所有字段最终落到 root config.json，多个 Python service 通过 ROOT_CFG 读。
  // 修改 language / alert / discord / bark / pi / log_level 任一项后，
  // 影响到的服务需要在对应卡片上手动重启。
  global: [
    // ── 显示 ──
    { key: "language", group: "display", type: "enum",
      label: { zh: "界面语言", ja: "言語" },
      hint:  { zh: "影响 BARK / Discord 推送语言；改完需重启 server 才生效",
               ja: "BARK / Discord 通知言語に影響。反映には server の再起動が必要" },
      options: [
        { value: "zh", label: { zh: "中文", ja: "中国語" } },
        { value: "ja", label: { zh: "日文", ja: "日本語" } },
      ] },

    // ── 宝宝信息 ──
    { key: "baby.name", group: "baby", type: "string",
      label: { zh: "宝宝姓名", ja: "赤ちゃんの名前" } },
    { key: "baby.birth_date", group: "baby", type: "string",
      label: { zh: "出生日期 (YYYYMMDD)", ja: "誕生日 (YYYYMMDD)" } },
    { key: "baby.weight_g", group: "baby", type: "int",
      label: { zh: "出生体重 (g)", ja: "出生体重 (g)" } },
    { key: "baby.feed_type", group: "baby", type: "enum",
      label: { zh: "喂养方式", ja: "授乳方式" },
      options: [
        { value: "formula", label: { zh: "配方奶", ja: "ミルク" } },
        { value: "breast",  label: { zh: "母乳",   ja: "母乳"   } },
        { value: "mixed",   label: { zh: "混合",   ja: "混合"   } },
      ] },
    { key: "baby.feed_interval_min", group: "baby", type: "int",
      label: { zh: "喂奶间隔 (分钟)", ja: "授乳間隔 (分)" } },

    // ── 传感器阈值（仅影响 web UI 卡片着色；BARK / Discord / 弹窗告警由设备自身和 server.py 判断）──
    { key: "sensor_thresholds.breath.min", group: "sensor", type: "int",
      label: { zh: "呼吸频率正常下限 (次/min)", ja: "呼吸数 正常下限 (回/min)" } },
    { key: "sensor_thresholds.breath.max", group: "sensor", type: "int",
      label: { zh: "呼吸频率正常上限 (次/min)", ja: "呼吸数 正常上限 (回/min)" } },
    { key: "sensor_thresholds.temp.min", group: "sensor", type: "number",
      label: { zh: "衣内温度正常下限 (°C)", ja: "衣内温度 正常下限 (°C)" } },
    { key: "sensor_thresholds.temp.max", group: "sensor", type: "number",
      label: { zh: "衣内温度正常上限 (°C)", ja: "衣内温度 正常上限 (°C)" } },
    { key: "sensor_thresholds.battery.low", group: "sensor", type: "int",
      label: { zh: "电量低阈值 (%)", ja: "バッテリー 低 (%)" },
      hint:  { zh: "低于此值显示红色 ⚠️", ja: "これ未満は赤色 ⚠️" } },
    { key: "sensor_thresholds.battery.warn", group: "sensor", type: "int",
      label: { zh: "电量警告阈值 (%)", ja: "バッテリー 警告 (%)" },
      hint:  { zh: "低于此值显示黄色 🪫", ja: "これ未満は黄色 🪫" } },
    { key: "sensor_thresholds.battery.ok", group: "sensor", type: "int",
      label: { zh: "电量充足阈值 (%)", ja: "バッテリー 充足 (%)" },
      hint:  { zh: "高于此值显示常态 🔋", ja: "これ以上は通常 🔋" } },

    // ── 告警推送 ──
    { key: "alert_notify_enabled", group: "alerts", type: "bool",
      label: { zh: "启用告警推送（Discord/Bark）",
               ja: "アラート通知を有効化（Discord/Bark）" } },
    { key: "discord_token", group: "alerts", type: "password",
      label: { zh: "Discord Bot Token", ja: "Discord Bot Token" } },
    { key: "discord_channel_ids", group: "alerts", type: "array_str",
      label: { zh: "Discord 频道 ID（每行一个）", ja: "Discord チャンネル ID（1 行 1 つ）" } },
    { key: "discord_user_ids", group: "alerts", type: "array_str",
      label: { zh: "Discord 用户 ID（每行一个）", ja: "Discord ユーザー ID（1 行 1 つ）" } },
    { key: "bark_server_url", group: "alerts", type: "string",
      label: { zh: "Bark 服务器 URL", ja: "Bark サーバー URL" } },
    { key: "bark_keys", group: "alerts", type: "array_str",
      label: { zh: "Bark Key（每行一个）", ja: "Bark Key（1 行 1 つ）" } },

    // ── 远端 Pi（ble service 走 HTTP；manager.py BLE pair 走 SSH）──
    { key: "pi_host", group: "pi", type: "string",
      label: { zh: "Pi 主机地址", ja: "Pi ホストアドレス" } },
    { key: "pi_ssh_user", group: "pi", type: "string",
      label: { zh: "Pi SSH 用户名", ja: "Pi SSH ユーザー" } },
    { key: "pi_ssh_key", group: "pi", type: "string",
      label: { zh: "Pi SSH 私钥路径", ja: "Pi SSH 秘密鍵パス" } },

    // ── 日志 ──
    { key: "log_level", group: "log", type: "enum",
      label: { zh: "日志级别", ja: "ログレベル" },
      hint:  { zh: "影响所有 Python service 的日志输出",
               ja: "全 Python service のログ出力に影響" },
      options: ["DEBUG", "INFO", "WARNING", "ERROR"].map(v => ({
        value: v, label: { zh: v, ja: v },
      })) },
  ],

  // ── 单服务旋钮 ────────────────────────────────────────────────────────
  go2rtc: [
    { key: "tapo_rtsp", type: "password",
      label: { zh: "Tapo RTSP URL", ja: "Tapo RTSP URL" },
      hint:  { zh: "rtsp://user:pass@192.168.x.x:554/stream1",
               ja: "rtsp://user:pass@192.168.x.x:554/stream1" } },
    { key: "pi_audio_rtsp", type: "string",
      label: { zh: "Pi 音频 RTSP（可选）", ja: "Pi 音声 RTSP（任意）" } },
    { key: "go2rtc_port", type: "int",
      label: { zh: "go2rtc 端口", ja: "go2rtc ポート" } },
    { key: "go2rtc_path", type: "string",
      label: { zh: "go2rtc 可执行路径", ja: "go2rtc バイナリパス" } },
  ],
  ble: [
    { key: "ble_port", type: "int",
      label: { zh: "sense-u-ble 端口", ja: "sense-u-ble ポート" } },
    { key: "ble_poll_interval_s", type: "number",
      label: { zh: "BLE 轮询间隔 (秒)", ja: "BLE ポーリング間隔 (秒)" } },
    { key: "ble_health_timeout_s", type: "number",
      label: { zh: "BLE 心跳超时 (秒)", ja: "BLE ハートビートタイムアウト (秒)" } },
  ],
  server: [
    { key: "web_port", type: "int",
      label: { zh: "Web 端口", ja: "Web ポート" } },
  ],
  recorder: [
    { key: "segment_s", type: "int",
      label: { zh: "录像分段时长 (秒)", ja: "録画セグメント長 (秒)" } },
    { key: "ffmpeg_path", type: "string",
      label: { zh: "ffmpeg 可执行路径", ja: "ffmpeg バイナリパス" } },
  ],
  voice: [
    { key: "voice_service_port", type: "int",
      label: { zh: "Voice 服务端口", ja: "Voice サービスポート" } },
  ],
};

export function localized(s: LocalizedString | undefined, lang: Lang): string {
  if (!s) return "";
  return s[lang] ?? s.zh ?? "";
}
