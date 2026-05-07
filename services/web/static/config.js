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
    labelBreath: '💨 呼吸频率', unitBpm: '次/min',
    labelTemp: '🌡️ 衣内温度',                        // 传感器在衣物内测得的环境温度（非直接体温）
    labelBattery: '🔋 电量',
    labelConn: '📶 连接', connOn: '已连接', connOff: '未连接',
    worn: '已佩戴', notWorn: '未佩戴', charging: '充电中',
    labelPosture: '🛏️ 宝宝姿势',
    waiting: '等待数据...', postureLoading: '数据获取中...', normal: '正常', slow: '⚠ 过慢', fast: '⚠ 过快',
    postures: { '仰卧': '仰卧', '俯卧': '俯卧', '左侧卧': '左侧卧', '右侧卧': '右侧卧', '坐姿': '坐姿' },
    battFull: '电量充足', battOk: '正常', battLow: '电量偏低', battEmpty: '请充电',
    alertTitle: '⚠ 告警记录', alertWaiting: '等待连接...',
    alertDlgTitle: '🚨 设备告警', alertDlgClose: '关闭', alertDlgSending: '发送中...',
    camWaiting: '等待摄像头连接...', camHint: '请在 config.json 中填写 tapo_rtsp',
    wsConn: '已连接到 BabySentinel 服务', updated: '更新',
    muteOn: '点击取消静音', muteOff: '点击静音',
    labelBabyLog: '育儿日志', labelNextFeed: '🍼 下次喂奶',
    mobTabMonitor: '📹 监控', mobTabBaby: '🍼 育儿', mobTabPlayback: '📼 回放',
    tabFeed: '🍼 喂奶', tabDaily: '😴 日常', tabHealth: '🌡️ 健康', tabOther: '✨ 其他',
    btnFormula: '🍼 配方奶', btnBreast: '🤱 母乳', btnBottle: '🍶 母乳瓶喂',
    btnSleep: '😴 入睡', btnWake: '☀️ 醒来', btnWet: '💧 尿尿', btnDirty: '💩 便便',
    btnTemp: '🌡️ 体温', btnHeight: '📏 身高', btnWeight: '⚖️ 体重',
    btnBath: '🛁 洗澡', btnPump: '🍼 挤奶',
    selectFormula: '配方奶量 (mL)', selectBottle: '母乳量 (mL)', selectPump: '挤奶量 (mL)',
    selectBreast: '母乳记录',
    poopTitle: '便便详情', poopAmt: '量',
    poopAmtTiny: '一点点', poopAmtSmall: '少', poopAmtNormal: '通常', poopAmtLarge: '大',
    poopCons: '硬度',
    poopConsLoose: '泻', poopConsSoft: '软', poopConsNormal: '通常', poopConsHard: '硬',
    poopColor: '颜色',
    tempTitle: '体温 (°C)', heightTitle: '身高 (cm)', weightTitle: '体重 (g)',
    cancel: '取消', confirm: '确认',
    editTitle: '修改', editSave: '保存修改',
    editDelete: '🗑️ 删除记录', editConfirmDelete: '确认删除这条记录？',
    // ── 录像回放 ──
    pbBack: '返回', pbTitle: '📹 回放',
    pbSelectDatePrompt: '请选择日期', pbSelectSegment: '请选择片段',
    pbVidTime: '🎬 视频时刻',
    pbTimelineLabel: '📍 时间轴（点击跳转）',
    pbQjFirst: '⏮ 最早', pbQjLast: '最新 ⏭',
    pbQjPrev: '⬅ 上段', pbQjNext: '下段 ➡',
    pbCounterSegs: '段', pbCounterEvts: '事件',
    pbNoSegments: '该日没有录像', pbLoadFail: '加载失败',
    pbUnitMin: '分',
    // ── 服务管理 ──
    mgrTitle: '🛠 BabySentinel 管理',
    mgrLinkMain: '→ 主界面', mgrLinkPlayback: '→ 回放',
    mgrStatusRunning: '运行中', mgrStatusStopped: '已停止', mgrStatusCrashed: '已崩溃',
    mgrBtnStart: '▶ 启动', mgrBtnStop: '■ 停止', mgrBtnRestart: '↺ 重启',
    mgrBtnCheck: '🔎 检查更新', mgrBtnUpdate: '⬇ 更新',
    mgrBtnConfig: '⚙ 配置',
    mgrUpdateAvail:   '有新提交可拉取',
    mgrUpdateNone:    '已是最新',
    mgrUpdateConfirm: '将 git pull + pip install + 重启远端服务，继续？',
    mgrUpdateFail:    '更新失败',
    cfgTitle: '配置',
    cfgSave:  '保存',
    cfgCancel:'取消',
    cfgSaved: '✓ 已保存',
    cfgSaveFail: '保存失败',
    cfgLoadFail: '读取配置失败',
    cfgRestartHint: '保存成功。需要重启 {svc} 才生效，是否现在重启？',
    cfgNoSchema:    '该服务暂不支持配置编辑',
    mgrBtnPair:    '🔗 配对',
    pairTitle:     'BLE 配对',
    pairStep1:     '长按设备按钮两次（约 1 秒间隔）',
    pairStep2:     '看到蓝灯慢闪后，点击下方"开始配对"',
    pairStep3:     '配对过程约 30s，期间 BLE 服务会临时停掉',
    pairBtnStart:  '开始配对',
    pairBtnAgain:  '重新配对',
    pairWorking:   '配对中... (最长 ~45 秒)',
    pairOk:        '✓ 配对成功，已重启 sense-u-ble 服务',
    pairFail:      '✗ 配对失败',
    statTimes: '次', feedNone: '暂无记录', feedRecMl: '推荐', lastFeed: '上次',
    cdRemain: '还有', cdOverdue: '已超过', cdHour: '小时', cdMin: '分', cdSec: '秒',
    nextFeedLabel: '下次喂奶',
    entryFormula: '配方奶', entryBottle: '瓶喂母乳', entryBreast: '母乳',
    entrySleep: '入睡', entryWake: '醒来',           // 与按钮文字统一
    entryWet: '尿尿', entryPoop: '便便',
    entryTemp: '体温', entryHeight: '身高', entryWeight: '体重',
    entryBath: '洗澡', entryPump: '挤奶',
    sideLeft: '左', sideRight: '右', sideBoth: '双侧',
    sleepPrevDay: '前一天', sleepCurDay: '当天',
  },
  ja: {
    bleOff: 'センサー', bleOn: 'センサー', svrOff: 'サーバー切断',
    camOff: 'カメラ', camOn: 'カメラ',
    offline: 'オフライン', live: '● LIVE',
    labelBreath: '💨 呼吸数', unitBpm: '回/min',
    labelTemp: '🌡️ 衣内温度',                        // 着衣内の環境温度（体温の直接計測ではない）
    labelBattery: '🔋 バッテリー',
    labelConn: '📶 接続', connOn: '接続中', connOff: '未接続',
    worn: '装着中', notWorn: '未装着', charging: '充電中',
    mgrBtnConfig: '⚙ 設定',
    cfgTitle: '設定',
    cfgSave:  '保存',
    cfgCancel:'キャンセル',
    cfgSaved: '✓ 保存しました',
    cfgSaveFail: '保存失敗',
    cfgLoadFail: '設定の読み込みに失敗',
    cfgRestartHint: '保存しました。{svc} の再起動が必要です。今すぐ再起動しますか？',
    cfgNoSchema:    'このサービスは設定編集に未対応',
    mgrBtnPair:    '🔗 ペアリング',
    pairTitle:     'BLE ペアリング',
    pairStep1:     'デバイスのボタンを 2 回長押し（約 1 秒間隔）',
    pairStep2:     '青色 LED がゆっくり点滅したら下の「開始」を押す',
    pairStep3:     '所要時間約 30 秒。実行中は BLE サービスを一時停止します',
    pairBtnStart:  '開始',
    pairBtnAgain:  'もう一度',
    pairWorking:   'ペアリング中... (最大 ~45 秒)',
    pairOk:        '✓ ペアリング成功。sense-u-ble を再起動しました',
    pairFail:      '✗ ペアリング失敗',
    labelPosture: '🛏️ 寝姿勢',                      // 姿勢→寝姿勢（文脈に合わせ）
    waiting: 'データ待機中...', postureLoading: 'データ取得中...', normal: '正常', slow: '⚠ 遅すぎ', fast: '⚠ 速すぎ',
    postures: { '仰卧': 'あおむけ', '俯卧': 'うつ伏せ', '左侧卧': '左向き', '右侧卧': '右向き', '坐姿': 'お座り' },
    battFull: '満充電', battOk: '良好', battLow: '残量低下', battEmpty: '要充電',
    alertTitle: '⚠ アラート履歴', alertWaiting: '接続待機中...',
    alertDlgTitle: '🚨 デバイスアラート', alertDlgClose: '閉じる', alertDlgSending: '送信中...',
    camWaiting: 'カメラ接続待機中...', camHint: 'config.jsonにtapo_rtspを設定してください',
    wsConn: 'BabySentinelに接続しました', updated: '更新',
    muteOn: 'タップしてミュート解除', muteOff: 'タップしてミュート',
    labelBabyLog: '育児記録', labelNextFeed: '🍼 次の授乳',
    mobTabMonitor: '📹 モニター', mobTabBaby: '🍼 育児', mobTabPlayback: '📼 再生',
    tabFeed: '🍼 授乳', tabDaily: '😴 日常', tabHealth: '🌡️ 健康', tabOther: '✨ その他',
    btnFormula: '🍼 粉ミルク', btnBreast: '🤱 母乳', btnBottle: '🍶 母乳（瓶）',
    btnSleep: '😴 就寝', btnWake: '☀️ 起床', btnWet: '💧 おしっこ', btnDirty: '💩 うんち',
    btnTemp: '🌡️ 体温', btnHeight: '📏 身長', btnWeight: '⚖️ 体重',
    btnBath: '🛁 お風呂', btnPump: '🍼 搾乳',
    selectFormula: '粉ミルク量 (mL)', selectBottle: '母乳量 (mL)', selectPump: '搾乳量 (mL)',  // 搾乳量→母乳量（飲んだ量）
    selectBreast: '母乳の記録',
    poopTitle: 'うんちの記録', poopAmt: '量',
    poopAmtTiny: 'ちょこっと', poopAmtSmall: '少なめ', poopAmtNormal: 'ふつう', poopAmtLarge: '多め',
    poopCons: '硬さ',
    poopConsLoose: '下痢', poopConsSoft: 'やわらかめ', poopConsNormal: 'ふつう', poopConsHard: 'かため',
    poopColor: '色',
    tempTitle: '体温 (°C)', heightTitle: '身長 (cm)', weightTitle: '体重 (g)',
    cancel: 'キャンセル', confirm: '記録する',        // 確認→記録する（操作の意図が明確）
    editTitle: '編集', editSave: '保存',
    editDelete: '🗑️ 削除する', editConfirmDelete: 'この記録を削除しますか？',
    // ── 録画再生 ──
    pbBack: '戻る', pbTitle: '📹 再生',
    pbSelectDatePrompt: '日付を選択してください', pbSelectSegment: '片段を選択してください',
    pbVidTime: '🎬 映像時刻',
    pbTimelineLabel: '📍 タイムライン（クリックでジャンプ）',
    pbQjFirst: '⏮ 最初', pbQjLast: '最新 ⏭',
    pbQjPrev: '⬅ 前へ', pbQjNext: '次へ ➡',
    pbCounterSegs: '個', pbCounterEvts: '件',
    pbNoSegments: 'この日の録画はありません', pbLoadFail: 'データの読み込みに失敗しました',
    pbUnitMin: '分',
    // ── サービス管理 ──
    mgrTitle: '🛠 BabySentinel マネージャー',
    mgrLinkMain: '→ メイン', mgrLinkPlayback: '→ 再生',
    mgrStatusRunning: '実行中', mgrStatusStopped: '停止', mgrStatusCrashed: 'クラッシュ',
    mgrBtnStart: '▶ 起動', mgrBtnStop: '■ 停止', mgrBtnRestart: '↺ 再起動',
    mgrBtnCheck: '🔎 更新確認', mgrBtnUpdate: '⬇ 更新',
    mgrUpdateAvail:   '新しいコミットがあります',
    mgrUpdateNone:    '最新です',
    mgrUpdateConfirm: 'git pull + pip install + リモート再起動を行います。続けますか？',
    mgrUpdateFail:    '更新失敗',
    statTimes: '回', feedNone: '記録なし', feedRecMl: '推奨', lastFeed: '前回',
    cdRemain: 'あと', cdOverdue: '超過', cdHour: '時間', cdMin: '分', cdSec: '秒',
    nextFeedLabel: '次の授乳',
    entryFormula: '粉ミルク', entryBottle: '母乳（哺乳瓶）', entryBreast: '母乳（直接）',
    entrySleep: '就寝', entryWake: '起床',
    entryWet: 'おしっこ', entryPoop: 'うんち',       // 便→うんち（育児アプリらしい表現）
    entryTemp: '体温', entryHeight: '身長', entryWeight: '体重',
    entryBath: 'お風呂', entryPump: '搾乳',
    sideLeft: '左', sideRight: '右', sideBoth: '両側',
    sleepPrevDay: '前日', sleepCurDay: '当日',
  },
};
