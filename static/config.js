// BabySentinel 前端常数配置 — 修改此文件即可调整行为，无需动 index.html

// ── 连接 ──────────────────────────────────────────────────────────────────
const GO2RTC_PORT = 1984;          // go2rtc WebRTC 端口

// ── 传感器阈值 ────────────────────────────────────────────────────────────
const SENSOR_CFG = {
  breath:  { min: 10,  max: 60  },  // 正常呼吸范围 (次/min)
  temp:    { min: 34,  max: 38  },  // 正常体温范围 (°C)
  battery: { low: 20,  warn: 40, ok: 60 },  // 电量三档分级
};

// ── 姿势图标 ──────────────────────────────────────────────────────────────
const POSTURE_ICONS = {
  '仰卧':  '🙂',
  '俯卧':  '😨',
  '左侧卧': '😴',
  '右侧卧': '😴',
};

// ── 喂奶量快捷选项 (mL) ──────────────────────────────────────────────────
const FORMULA_AMOUNTS = [30, 40, 50, 60, 70, 80, 90, 100, 120, 140, 160, 200];

// ── 母乳时长快捷选项 (min) ───────────────────────────────────────────────
const BREAST_DURATIONS = [5, 10, 15, 20, 25, 30];

// ── 便便颜色 ──────────────────────────────────────────────────────────────
const POOP_COLORS = [
  { key: '白', hex: '#e0e0e0' },
  { key: '黄', hex: '#f5d300' },
  { key: '橙', hex: '#f59400' },
  { key: '茶', hex: '#8b4513' },
  { key: '绿', hex: '#2ecc71' },
  { key: '红', hex: '#e74c3c' },
  { key: '黑', hex: '#2c2c2c' },
];

// ── i18n ──────────────────────────────────────────────────────────────────
const LANGS = {
  zh: {
    bleOff: '传感器', bleOn: '传感器', svrOff: '服务器断开',
    camOff: '摄像头', camOn: '摄像头',
    offline: '离线', live: '● LIVE',
    wearUnknown: '佩戴状态未知', wearing: 'Sense-U Pro已佩戴', notWearing: '未佩戴',
    labelBreath: '💨 呼吸频率', unitBpm: '次/min',
    labelTemp: '🌡️ 衣内温度',                        // 传感器在衣物内测得的环境温度（非直接体温）
    labelBattery: '🔋 电量',
    labelConn: '📶 连接', connOn: '已连接', connOff: '未连接',
    labelPosture: '🛏️ 宝宝姿势',
    waiting: '等待数据...', postureLoading: '数据获取中...', normal: '正常', slow: '⚠ 过慢', fast: '⚠ 过快',
    postures: { '仰卧': '仰卧', '俯卧': '俯卧', '左侧卧': '左侧卧', '右侧卧': '右侧卧' },
    battFull: '电量充足', battOk: '正常', battLow: '电量偏低', battEmpty: '请充电',
    alertTitle: '⚠ 告警记录', alertWaiting: '等待连接...',
    camWaiting: '等待摄像头连接...', camHint: '请在 config.json 中填写 tapo_rtsp',
    wsConn: '已连接到 BabySentinel 服务', updated: '更新',
    muteOn: '点击取消静音', muteOff: '点击静音',
    labelBabyLog: '育儿日志', labelNextFeed: '🍼 下次喂奶',
    tabFeed: '🍼 喂奶', tabDaily: '😴 日常', tabHealth: '🌡️ 健康', tabOther: '✨ 其他',
    btnFormula: '🍼 配方奶', btnBreastL: '🤱 母乳（左）', btnBreastR: '🤱 母乳（右）', btnBottle: '🍶 母乳瓶喂',
    btnSleep: '😴 入睡', btnWake: '☀️ 醒来', btnWet: '💧 尿尿', btnDirty: '💩 便便',
    btnTemp: '🌡️ 体温', btnHeight: '📏 身高', btnWeight: '⚖️ 体重',
    btnBath: '🛁 洗澡', btnPump: '🍼 挤奶',
    selectFormula: '配方奶量 (mL)', selectBottle: '母乳量 (mL)', selectPump: '挤奶量 (mL)',
    selectBreastL: '左乳时间', selectBreastR: '右乳时间',
    poopTitle: '便便详情', poopAmt: '量',
    poopAmtSmall: '少', poopAmtNormal: '正常', poopAmtLarge: '多',
    poopCons: '硬度', poopConsSoft: '偏软', poopConsNormal: '正常', poopConsHard: '偏硬',
    poopColor: '颜色',
    tempTitle: '体温 (°C)', heightTitle: '身高 (cm)', weightTitle: '体重 (g)',
    cancel: '取消', confirm: '确认',
    statTimes: '次', feedNone: '暂无记录', feedRecMl: '推荐', lastFeed: '上次',
    cdRemain: '还有', cdOverdue: '已超过', cdHour: '小时', cdMin: '分', cdSec: '秒',
    entryFormula: '配方奶', entryBottle: '瓶喂母乳', entryBreast: '母乳',
    entrySleep: '入睡', entryWake: '醒来',           // 与按钮文字统一
    entryWet: '尿尿', entryPoop: '便便',
    entryTemp: '体温', entryHeight: '身高', entryWeight: '体重',
    entryBath: '洗澡', entryPump: '挤奶',
    sideLeft: '左', sideRight: '右', sideBoth: '双侧',
  },
  ja: {
    bleOff: 'センサー', bleOn: 'センサー', svrOff: 'サーバー切断',
    camOff: 'カメラ', camOn: 'カメラ',
    offline: 'オフライン', live: '● LIVE',
    wearUnknown: '装着状態不明', wearing: 'Sense-U Pro装着中', notWearing: '未装着',
    labelBreath: '💨 呼吸数', unitBpm: '回/min',
    labelTemp: '🌡️ 衣内温度',                        // 着衣内の環境温度（体温の直接計測ではない）
    labelBattery: '🔋 バッテリー',
    labelConn: '📶 接続', connOn: '接続中', connOff: '未接続',
    labelPosture: '🛏️ 寝姿勢',                      // 姿勢→寝姿勢（文脈に合わせ）
    waiting: 'データ待機中...', postureLoading: 'データ取得中...', normal: '正常', slow: '⚠ 遅すぎ', fast: '⚠ 速すぎ',
    postures: { '仰卧': 'あおむけ', '俯卧': 'うつ伏せ', '左侧卧': '左向き', '右侧卧': '右向き' },
    battFull: '満充電', battOk: '良好', battLow: '残量低下', battEmpty: '要充電',
    alertTitle: '⚠ アラート履歴', alertWaiting: '接続待機中...',
    camWaiting: 'カメラ接続待機中...', camHint: 'config.jsonにtapo_rtspを設定してください',
    wsConn: 'BabySentinelに接続しました', updated: '更新',
    muteOn: 'タップしてミュート解除', muteOff: 'タップしてミュート',
    labelBabyLog: '育児記録', labelNextFeed: '🍼 次の授乳',
    tabFeed: '🍼 授乳', tabDaily: '😴 日常', tabHealth: '🌡️ 健康', tabOther: '✨ その他',
    btnFormula: '🍼 粉ミルク', btnBreastL: '🤱 母乳（左）', btnBreastR: '🤱 母乳（右）', btnBottle: '🍶 母乳（瓶）',
    btnSleep: '😴 就寝', btnWake: '☀️ 起床', btnWet: '💧 おしっこ', btnDirty: '💩 うんち',
    btnTemp: '🌡️ 体温', btnHeight: '📏 身長', btnWeight: '⚖️ 体重',
    btnBath: '🛁 お風呂', btnPump: '🍼 搾乳',
    selectFormula: '粉ミルク量 (mL)', selectBottle: '母乳量 (mL)', selectPump: '搾乳量 (mL)',  // 搾乳量→母乳量（飲んだ量）
    selectBreastL: '左乳 授乳時間', selectBreastR: '右乳 授乳時間',
    poopTitle: 'うんちの記録', poopAmt: '量',
    poopAmtSmall: '少なめ', poopAmtNormal: '普通', poopAmtLarge: '多め',
    poopCons: '硬さ', poopConsSoft: 'やわらかい', poopConsNormal: '普通', poopConsHard: 'かたい',
    poopColor: '色',
    tempTitle: '体温 (°C)', heightTitle: '身長 (cm)', weightTitle: '体重 (g)',
    cancel: 'キャンセル', confirm: '記録する',        // 確認→記録する（操作の意図が明確）
    statTimes: '回', feedNone: '記録なし', feedRecMl: '推奨', lastFeed: '前回',
    cdRemain: 'あと', cdOverdue: '超過', cdHour: '時間', cdMin: '分', cdSec: '秒',
    entryFormula: '粉ミルク', entryBottle: '母乳（哺乳瓶）', entryBreast: '母乳（直接）',
    entrySleep: '就寝', entryWake: '起床',
    entryWet: 'おしっこ', entryPoop: 'うんち',       // 便→うんち（育児アプリらしい表現）
    entryTemp: '体温', entryHeight: '身長', entryWeight: '体重',
    entryBath: 'お風呂', entryPump: '搾乳',
    sideLeft: '左', sideRight: '右', sideBoth: '両側',
  },
};
