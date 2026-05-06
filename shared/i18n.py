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

        # 姿势 enum 中文 → 显示语言
        "postures": {
            "仰卧": "仰向け", "俯卧": "うつ伏せ",
            "左侧卧": "左向き", "右侧卧": "右向き",
            "坐姿": "お座り",
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

        "postures": {
            "仰卧": "仰卧", "俯卧": "俯卧",
            "左侧卧": "左侧卧", "右侧卧": "右侧卧",
            "坐姿": "坐姿",
        },
    },
}


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


def posture_label(zh_value: str) -> str:
    """把 SQLite 里的中文 enum（'仰卧' 等）映射到当前语言。"""
    if not zh_value:
        return zh_value
    return _TR[_lang()]["postures"].get(zh_value, zh_value)


def entry_type_label(type_code: str) -> str:
    """把 baby_log entry 的 type 字段（'formula' 等）翻成当前语言显示文案。"""
    return _TR[_lang()]["entry_labels"].get(type_code, type_code)


def diaper_kind_label(kind: str) -> str:
    """尿布 kind enum（wet/dirty/both）→ emoji 显示。"""
    return _TR[_lang()]["diaper_kinds"].get(kind, kind or "")
