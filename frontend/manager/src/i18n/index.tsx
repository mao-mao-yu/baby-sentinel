// Manager UI i18n. 单一信源是 root config.json 的 `language` 字段（同时也是
// 后端 BARK / Discord 推送语言），由 App 层在启动时拉 /api/manager/config 取，
// 通过 LangContext 注入下游组件。保存语言后 React Query 会 invalidate 该 key
// 触发自动重渲染——无需刷新页面。

import { createContext, useContext, type ReactNode } from "react";

export type Lang = "ja" | "zh";

export const LANGS = {
  zh: {
    mgrTitle: "🛠 BabySentinel 管理",
    mgrLinkMain: "→ 主界面",
    mgrLinkPlayback: "→ 回放",
    mgrStatusRunning: "运行中",
    mgrStatusStopped: "已停止",
    mgrStatusCrashed: "已崩溃",
    mgrBtnStart: "▶ 启动",
    mgrBtnStop: "■ 停止",
    mgrBtnRestart: "↺ 重启",
    mgrBtnCheck: "🔎 检查更新",
    mgrBtnUpdate: "⬇ 更新",
    mgrBtnConfig: "⚙ 配置",
    mgrBtnPair: "🔗 配对",
    mgrUpdateAvail: "有新提交可拉取",
    mgrUpdateNone: "已是最新",
    mgrUpdateConfirm: "将 git pull + pip install + 重启远端服务，继续？",
    mgrUpdateFail: "更新失败",
    mgrCheckRunning: "检查中...",
    mgrUpdateRunning: "更新中... (可能需要 1 分钟)",
    mgrViewLog: "查看日志",
    cfgTitle: "配置",
    cfgSave: "保存",
    cfgCancel: "取消",
    cfgSaved: "✓ 已保存",
    cfgSaveFail: "保存失败",
    cfgLoadFail: "读取配置失败",
    cfgRestartHint: "保存成功。需要重启 {svc} 才生效，是否现在重启？",
    cfgNoSchema: "该服务暂不支持配置编辑",
    cfgGlobalTitle: "管理器设置",
    mgrSettings: "设置",
    pairTitle: "BLE 配对",
    pairStep1: '长按设备按钮两次（约 1 秒间隔）',
    pairStep2: '看到蓝灯慢闪后，点击下方"开始配对"',
    pairStep3: "配对过程约 30s，期间 BLE 服务会临时停掉",
    pairBtnStart: "开始配对",
    pairBtnAgain: "重新配对",
    pairWorking: "配对中... (最长 ~45 秒)",
    pairOk: "✓ 配对成功，已重启 sense-u-ble 服务",
    pairFail: "✗ 配对失败",
  },
  ja: {
    mgrTitle: "🛠 BabySentinel マネージャー",
    mgrLinkMain: "→ メイン",
    mgrLinkPlayback: "→ 再生",
    mgrStatusRunning: "実行中",
    mgrStatusStopped: "停止",
    mgrStatusCrashed: "クラッシュ",
    mgrBtnStart: "▶ 起動",
    mgrBtnStop: "■ 停止",
    mgrBtnRestart: "↺ 再起動",
    mgrBtnCheck: "🔎 更新確認",
    mgrBtnUpdate: "⬇ 更新",
    mgrBtnConfig: "⚙ 設定",
    mgrBtnPair: "🔗 ペアリング",
    mgrUpdateAvail: "新しいコミットがあります",
    mgrUpdateNone: "最新です",
    mgrUpdateConfirm: "git pull + pip install + リモート再起動を行います。続けますか？",
    mgrUpdateFail: "更新失敗",
    mgrCheckRunning: "確認中...",
    mgrUpdateRunning: "更新中... (最大 1 分ほど)",
    mgrViewLog: "ログを表示",
    cfgTitle: "設定",
    cfgSave: "保存",
    cfgCancel: "キャンセル",
    cfgSaved: "✓ 保存しました",
    cfgSaveFail: "保存失敗",
    cfgLoadFail: "設定の読み込みに失敗",
    cfgRestartHint: "保存しました。{svc} の再起動が必要です。今すぐ再起動しますか？",
    cfgNoSchema: "このサービスは設定編集に未対応",
    cfgGlobalTitle: "マネージャー設定",
    mgrSettings: "設定",
    pairTitle: "BLE ペアリング",
    pairStep1: "デバイスのボタンを 2 回長押し（約 1 秒間隔）",
    pairStep2: "青色 LED がゆっくり点滅したら下の「開始」を押す",
    pairStep3: "所要時間約 30 秒。実行中は BLE サービスを一時停止します",
    pairBtnStart: "開始",
    pairBtnAgain: "もう一度",
    pairWorking: "ペアリング中... (最大 ~45 秒)",
    pairOk: "✓ ペアリング成功。sense-u-ble を再起動しました",
    pairFail: "✗ ペアリング失敗",
  },
} as const satisfies Record<Lang, Record<string, string>>;

// 启动初值（fallback）：config 还没拉到时用浏览器 locale 猜一下，避免首屏闪烁。
// 一旦 useQuery(["config"]) 拿到数据，LangProvider 会用真实值覆盖。
const initialLang: Lang = navigator.language.startsWith("ja") ? "ja" : "zh";

const LangContext = createContext<Lang>(initialLang);

export function LangProvider({ lang, children }: { lang: Lang; children: ReactNode }) {
  return <LangContext.Provider value={lang}>{children}</LangContext.Provider>;
}

export function useLang(): Lang {
  return useContext(LangContext);
}

export function useT() {
  return LANGS[useLang()];
}

/** Narrow an arbitrary `unknown` (e.g. config.json value) to Lang, with fallback. */
export function asLang(v: unknown, fallback: Lang = initialLang): Lang {
  return v === "ja" || v === "zh" ? v : fallback;
}
