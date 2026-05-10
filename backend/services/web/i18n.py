"""后端 i18n —— 用户可见字符串的 zh/ja 切换。

仅用于会被推送到用户终端（Bark / Discord / WebSocket）的字符串，
注释、内部日志保留中文不动（开发者视角）。

读取 ROOT_CFG["language"]：'ja'（默认）或 'zh'。
"""

from shared.config import ROOT_CFG

DEFAULT_LANG = "ja"

_TR: dict[str, dict] = {
    "ja": {
        # 告警消息
        "alert_prone":  "🚨 うつ伏せ警告\n{seconds} 秒間うつ伏せの状態が続いています。すぐに確認してください。",
        "alert_breath": "🫁 呼吸異常警告\n呼吸数 {rate} 回/分の状態が {seconds} 秒続いています。すぐに確認してください。",
        "alert_feed":   "🍼 授乳の時間です\n最後の授乳から {duration} が経過しています。\n{name}の授乳をお忘れなく 💕",

        # 时长格式
        "duration_h_m": "{h}時間{m}分",
        "duration_m":   "{m}分",

        # Discord 状态卡片
        "discord_cmd_desc_sensor":  "赤ちゃんのセンサーをリアルタイム表示",
        "discord_cmd_desc_today":   "今日の育児記録を表示",
        "discord_cmd_desc_log":     "育児イベントを記録",
        "discord_title":        "👶 赤ちゃんのリアルタイム状態",
        "discord_ble_on":       "接続中",
        "discord_ble_off":      "未接続",
        "discord_posture":      "🤸 姿勢: {value}",
        "discord_breath":       "💨 呼吸: {rate} 回/分",
        "discord_temp":         "🌡️ 体温: {value} °C",
        "discord_battery":      "{icon} バッテリー: {value}%",
        "discord_update":       "🕐 更新: {value}",

        # Discord 今日育儿记录卡片
        "discord_today_title":     "📅 今日の育児記録",
        "discord_today_empty":     "今日はまだ記録がありません。",
        "discord_today_summary":   "📊 サマリー",
        "discord_today_entries":   "📝 詳細",
        "discord_today_feeds":     "🍼 授乳 {count} 回 / 合計 {total} mL",
        "discord_today_diapers":   "👶 オムツ おしっこ {wet} / うんち {dirty}",
        "discord_today_sleep":     "😴 睡眠 {duration}（最長 {longest}）",

        # 育儿记录条目标签
        "entry_labels": {
            "formula":     "粉ミルク",
            "breastfeed":  "母乳",
            "bottle_milk": "母乳（瓶）",
            "feed":        "授乳",
            "diaper":      "オムツ",
            "sleep":       "睡眠",
            "bath":        "お風呂",
            "pump":        "搾乳",
            "temperature": "体温",
            "weight":      "体重",
            "height":      "身長",
        },
        "entry_sleep_start": "就寝",
        "entry_sleep_end":   "起床",
        "side_left":  "左",
        "side_right": "右",
        "side_both":  "両側",
        "diaper_kinds": {"wet": "💧", "dirty": "💩", "both": "💧💩"},
        "diaper_kind_wet":   "おしっこ",
        "diaper_kind_dirty": "うんち",
        "diaper_kind_both":  "両方",

        # Discord /log UI
        "log_menu_title":    "📝 記録するイベントを選択:",
        "log_pick_side":     "🤱 授乳側を選択:",
        "log_pick_kind":     "👶 オムツの種類を選択:",
        "log_undo_btn":      "↩️ 直近を取り消す",
        "log_logged":        "✅ 記録しました",
        "log_undone":        "↩️ 取り消しました",
        "log_no_undo":       "ℹ️ 今日はまだ記録がありません",
        "log_unavailable":   "❌ /log 利用不可：書き込みパスが無効",
        "log_invalid_arg":   "❌ 入力が無効です",
        "log_failed":        "❌ 記録に失敗",
        "log_unknown_action":"❌ 未知の操作",
        "log_field_amount_ml":"ミリリットル / mL",
        "log_field_minutes":  "分 / Minutes",
        "log_field_temp":     "体温 °C (例: 37.2)",
        "log_field_weight":   "グラム / Grams",
        "log_field_height":   "センチ / cm",
        "log_field_time":     "時刻 HH:MM (空=今)",

        # 姿势 enum (sense-u-ble v2 起统一英文) → 显示语言
        "postures": {
            "supine":     "仰向け",
            "prone":      "うつ伏せ",
            "left_side":  "左向き",
            "right_side": "右向き",
            "sitting":    "お座り",
        },

        # 设备告警 mode 字符串 (sense-u-ble README "Alert modes" 表) → 显示语言
        "alert_modes": {
            "prone alert":              "🚨 うつ伏せ警告",
            "temperature high":         "🌡️ 高温警告",
            "temperature low":          "❄️ 低温警告",
            "cooling reminder":         "💨 クールダウンのお知らせ",
            "breath fast":              "🫁 呼吸過多",
            "breath weak":              "🫁 呼吸微弱",
            "prone + breath weak":      "🚨 うつ伏せ + 呼吸微弱",
            "activity alert":           "⚡ 活動異常",
            "prone sleep breath weak":  "🚨 うつ伏せ就寝 + 呼吸微弱",
        },
    },
    "zh": {
        "alert_prone":  "🚨 俯卧警告\n持续 {seconds} 秒处于俯卧状态，请立即确认。",
        "alert_breath": "🫁 呼吸异常警告\n呼吸 {rate} 次/分持续 {seconds} 秒，请立即确认。",
        "alert_feed":   "🍼 该喂奶了\n距上次喂奶已过 {duration}\n请记得喂{name} 💕",

        "duration_h_m": "{h}小时{m}分",
        "duration_m":   "{m}分",

        "discord_cmd_desc_sensor":  "查看宝宝实时传感器状态",
        "discord_cmd_desc_today":   "查看今天的育儿记录",
        "discord_cmd_desc_log":     "记录育儿事件",
        "discord_title":        "👶 宝宝实时状态",
        "discord_ble_on":       "已连接",
        "discord_ble_off":      "未连接",
        "discord_posture":      "🤸 姿势: {value}",
        "discord_breath":       "💨 呼吸: {rate} 次/分",
        "discord_temp":         "🌡️ 衣内温度: {value} °C",
        "discord_battery":      "{icon} 电量: {value}%",
        "discord_update":       "🕐 更新: {value}",

        "discord_today_title":     "📅 今日育儿记录",
        "discord_today_empty":     "今天还没有任何记录。",
        "discord_today_summary":   "📊 概览",
        "discord_today_entries":   "📝 详细",
        "discord_today_feeds":     "🍼 喂奶 {count} 次 / 共 {total} mL",
        "discord_today_diapers":   "👶 尿布 湿 {wet} / 便便 {dirty}",
        "discord_today_sleep":     "😴 睡眠 {duration}（最长 {longest}）",

        "entry_labels": {
            "formula":     "配方奶",
            "breastfeed":  "母乳",
            "bottle_milk": "瓶喂母乳",
            "feed":        "喂奶",
            "diaper":      "尿布",
            "sleep":       "睡眠",
            "bath":        "洗澡",
            "pump":        "挤奶",
            "temperature": "体温",
            "weight":      "体重",
            "height":      "身高",
        },
        "entry_sleep_start": "入睡",
        "entry_sleep_end":   "醒来",
        "side_left":  "左",
        "side_right": "右",
        "side_both":  "双侧",
        "diaper_kinds": {"wet": "💧", "dirty": "💩", "both": "💧💩"},
        "diaper_kind_wet":   "尿",
        "diaper_kind_dirty": "便便",
        "diaper_kind_both":  "都有",

        # Discord /log UI
        "log_menu_title":    "📝 选择要记录的事件:",
        "log_pick_side":     "🤱 选择哺乳侧:",
        "log_pick_kind":     "👶 选择尿布类型:",
        "log_undo_btn":      "↩️ 撤销最后一条",
        "log_logged":        "✅ 已记录",
        "log_undone":        "↩️ 已撤销",
        "log_no_undo":       "ℹ️ 今日暂无记录可撤销",
        "log_unavailable":   "❌ /log 不可用：服务端未启用写入",
        "log_invalid_arg":   "❌ 参数错误",
        "log_failed":        "❌ 记录失败",
        "log_unknown_action":"❌ 未知操作",
        "log_field_amount_ml":"毫升 / mL",
        "log_field_minutes":  "分钟 / Minutes",
        "log_field_temp":     "体温 °C（如 37.2）",
        "log_field_weight":   "克 / Grams",
        "log_field_height":   "厘米 / cm",
        "log_field_time":     "时间 HH:MM (留空=现在)",

        "postures": {
            "supine":     "仰卧",
            "prone":      "俯卧",
            "left_side":  "左侧卧",
            "right_side": "右侧卧",
            "sitting":    "坐姿",
        },

        "alert_modes": {
            "prone alert":              "🚨 俯卧警告",
            "temperature high":         "🌡️ 温度过高",
            "temperature low":          "❄️ 温度过低",
            "cooling reminder":         "💨 散热提醒",
            "breath fast":              "🫁 呼吸过快",
            "breath weak":              "🫁 呼吸微弱",
            "prone + breath weak":      "🚨 俯卧 + 呼吸微弱",
            "activity alert":           "⚡ 活动异常",
            "prone sleep breath weak":  "🚨 俯卧睡眠 + 呼吸微弱",
        },
    },
}

# sense-u-ble v1 (旧固件 / 旧 sensors_db 历史行) 用中文 enum，v2 起统一英文。
# 入站时归一化到英文，让后续 i18n 表只维护一套 key。
_LEGACY_POSTURE_ZH_TO_EN = {
    "仰卧":   "supine",
    "俯卧":   "prone",
    "左侧卧": "left_side",
    "右侧卧": "right_side",
    "坐姿":   "sitting",
}


def normalize_posture(value: str | None) -> str | None:
    """把姿势 enum 归一化到英文 (兼容旧中文历史数据)。"""
    if not value:
        return value
    return _LEGACY_POSTURE_ZH_TO_EN.get(value, value)


def _lang() -> str:
    L = ROOT_CFG.get("language", DEFAULT_LANG)
    return L if L in _TR else DEFAULT_LANG


def t(key: str, **kw) -> str:
    """取 i18n 字符串，支持 .format(**kw) 模板。"""
    table = _TR[_lang()]
    s = table.get(key)
    if s is None:
        s = _TR[DEFAULT_LANG].get(key, key)
    if isinstance(s, str) and kw:
        try:
            return s.format(**kw)
        except (KeyError, IndexError):
            return s
    return s


def posture_label(value: str) -> str:
    """姿势 enum → 当前语言显示文案。兼容旧中文 enum (legacy sensors_db 行)。"""
    if not value:
        return value
    en = normalize_posture(value)
    return _TR[_lang()]["postures"].get(en, en)


def alert_mode_label(en_message: str) -> str:
    """sense-u-ble 设备告警的英文 message → 当前语言显示文案。
    未命中表的字符串原样返回 (以后固件新增 mode 时不致丢消息)。"""
    if not en_message:
        return en_message
    return _TR[_lang()]["alert_modes"].get(en_message, en_message)


def entry_type_label(type_code: str) -> str:
    """把 baby_log entry 的 type 字段（'formula' 等）翻成当前语言显示文案。"""
    return _TR[_lang()]["entry_labels"].get(type_code, type_code)


def diaper_kind_label(kind: str) -> str:
    """尿布 kind enum（wet/dirty/both）→ emoji 显示。"""
    return _TR[_lang()]["diaper_kinds"].get(kind, kind or "")
