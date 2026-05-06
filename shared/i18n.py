"""后端 i18n —— 用户可见字符串的 zh/ja 切换。

仅用于会被推送到用户终端（Bark / Discord / WebSocket）的字符串，
注释、内部日志保留中文不动（开发者视角）。

读取 CFG["language"]：'ja'（默认）或 'zh'。
"""

from shared.config import CFG

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
        "discord_cmd_desc":     "赤ちゃんのリアルタイム状態を表示",
        "discord_title":        "👶 赤ちゃんのリアルタイム状態",
        "discord_ble_on":       "接続中",
        "discord_ble_off":      "未接続",
        "discord_posture":      "🤸 姿勢: {value}",
        "discord_breath":       "💨 呼吸: {rate} 回/分",
        "discord_temp":         "🌡️ 体温: {value} °C",
        "discord_battery":      "{icon} バッテリー: {value}%",
        "discord_update":       "🕐 更新: {value}",

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

        "discord_cmd_desc":     "查看宝宝实时传感器状态",
        "discord_title":        "👶 宝宝实时状态",
        "discord_ble_on":       "已连接",
        "discord_ble_off":      "未连接",
        "discord_posture":      "🤸 姿势: {value}",
        "discord_breath":       "💨 呼吸: {rate} 次/分",
        "discord_temp":         "🌡️ 衣内温度: {value} °C",
        "discord_battery":      "{icon} 电量: {value}%",
        "discord_update":       "🕐 更新: {value}",

        "postures": {
            "仰卧": "仰卧", "俯卧": "俯卧",
            "左侧卧": "左侧卧", "右侧卧": "右侧卧",
            "坐姿": "坐姿",
        },
    },
}


def _lang() -> str:
    L = CFG.get("language", DEFAULT_LANG)
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
