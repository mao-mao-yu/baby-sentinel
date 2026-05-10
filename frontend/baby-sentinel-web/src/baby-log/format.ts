// 把一条 log entry 渲染成 (icon, summary text)。对应旧 index.html fmtEntry()。
// 不依赖 React，hook 调用方先 useT() 拿 T 再传进来。

import type { LogEntry } from "@/baby-log/types";
import type { LANGS } from "@/i18n";

type T = typeof LANGS["zh"];

export function fmtEntry(e: LogEntry, T: T): { icon: string; summary: string } {
  switch (e.type) {
    case "formula":
    case "feed": {
      const ml = (e as { amount_ml?: number }).amount_ml;
      return { icon: "🍼", summary: `${T.entryFormula}${ml ? ` ${ml}mL` : ""}` };
    }
    case "bottle_milk": {
      const ml = (e as { amount_ml?: number }).amount_ml;
      return { icon: "🍶", summary: `${T.entryBottle}${ml ? ` ${ml}mL` : ""}` };
    }
    case "pump": {
      const ml = (e as { amount_ml?: number }).amount_ml;
      return { icon: "🍶", summary: `${T.entryPump}${ml ? ` ${ml}mL` : ""}` };
    }
    case "breastfeed": {
      const r = e as { side?: string; duration_min?: number; left_min?: number; right_min?: number; amount_ml?: number };
      const parts: string[] = [];
      if (r.side === "both" || (r.left_min != null && r.right_min != null)) {
        if (r.left_min)  parts.push(`${T.sideLeft} ${r.left_min}min`);
        if (r.right_min) parts.push(`${T.sideRight} ${r.right_min}min`);
      } else if (r.side === "left"  && r.duration_min) parts.push(`${T.sideLeft} ${r.duration_min}min`);
        else if (r.side === "right" && r.duration_min) parts.push(`${T.sideRight} ${r.duration_min}min`);
        else if (r.duration_min)                       parts.push(`${r.duration_min}min`);
      const tail = r.amount_ml ? ` (${r.amount_ml}mL)` : "";
      const detail = parts.length ? ` ${parts.join(" / ")}` : "";
      return { icon: "🤱", summary: `${T.entryBreast}${detail}${tail}` };
    }
    case "sleep": {
      const s = e as { action?: string; duration_str?: string };
      if (s.action === "end") {
        return { icon: "☀️", summary: `${T.entryWake}${s.duration_str ? ` (${s.duration_str})` : ""}` };
      }
      return { icon: "😴", summary: T.entrySleep };
    }
    case "diaper": {
      const d = e as { kind?: string; amount?: string; consistency?: string; color?: string };
      if (d.kind === "wet") return { icon: "💧", summary: T.entryWet };
      const detail = [d.amount, d.consistency, d.color].filter(Boolean).map((k) => {
        // 用户可能录入旧中文 enum；尝试翻成本语言，否则原样
        const amap = { tiny: T.poopAmtTiny, small: T.poopAmtSmall, normal: T.poopAmtNormal, large: T.poopAmtLarge } as Record<string, string>;
        const cmap = { loose: T.poopConsLoose, soft: T.poopConsSoft, normal: T.poopConsNormal, hard: T.poopConsHard } as Record<string, string>;
        const colorMap = (T.poopColors ?? {}) as Record<string, string>;
        return amap[k!] ?? cmap[k!] ?? colorMap[k!] ?? k;
      }).join("/");
      return { icon: "💩", summary: `${T.entryPoop}${detail ? ` (${detail})` : ""}` };
    }
    case "temperature": {
      const v = (e as { value?: number }).value;
      return { icon: "🌡️", summary: `${T.entryTemp}${v != null ? ` ${v}°C` : ""}` };
    }
    case "height": {
      const v = (e as { value?: number }).value;
      return { icon: "📏", summary: `${T.entryHeight}${v != null ? ` ${v}cm` : ""}` };
    }
    case "weight": {
      const v = (e as { value?: number }).value;
      return { icon: "⚖️", summary: `${T.entryWeight}${v != null ? ` ${v}g` : ""}` };
    }
    case "bath":
      return { icon: "🛁", summary: T.entryBath };
    default:
      return { icon: "📝", summary: "?" };
  }
}
