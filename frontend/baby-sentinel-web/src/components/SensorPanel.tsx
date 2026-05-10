// 传感器面板：一行 3 个 status pill + 一行 3 张主卡片
// 行为对齐旧 backend/services/web/static/index.html 的 renderSensor() 函数。

import { useT } from "@/i18n";
import { useSensor, useWsConn } from "@/api/ws";
import { useSensorThresholds } from "@/api/manager-config";
import type { Posture, SensorFrame } from "@/types/wire";
import { cn } from "@/lib/utils";

export function SensorPanel() {
  const sensor = useSensor();
  return (
    <div className="space-y-2.5">
      <StatusRow s={sensor} />
      <SensorGrid s={sensor} />
    </div>
  );
}

// ── 状态行：连接 + 电量 + 上次更新 ────────────────────────────────────
function StatusRow({ s }: { s: Partial<SensorFrame> }) {
  const T = useT();
  const conn = useWsConn();
  const thresh = useSensorThresholds();
  const wsClosed = conn === "closed";
  const bleOk = !!s.ble_ok && !wsClosed;

  // Connection pill：BLE 已连显示 (worn/notWorn)，未连只显示状态
  const connText = bleOk ? T.connOn : T.connOff;
  const wearingSuffix =
    bleOk && s.wearing != null ? `(${s.wearing ? T.worn : T.notWorn})` : "";

  // Battery pill：3 档颜色 + 充电图标
  const batt = s.battery ?? null;
  const battTier = batt == null
    ? "n/a"
    : batt < thresh.battery.low ? "err"
    : batt < thresh.battery.warn ? "warn"
    : "ok";
  const battIcon = batt == null ? "🔋"
                  : batt >= thresh.battery.ok ? "🔋"
                  : batt >= thresh.battery.low ? "🪫"
                  : "⚠️";
  const chargeIcon = s.charge === 1 ? "⚡" : s.charge === 2 ? "🔌" : null;

  // Last update pill
  const updateText = s.last_update ? `${T.updated} ${s.last_update}` : T.waiting;

  return (
    <div className="flex gap-1.5 text-xs">
      <Pill tone={bleOk ? "ok" : "err"}>
        <span className={cn("font-medium",
                            bleOk ? "text-emerald-700 dark:text-emerald-300" : "text-destructive")}>
          {connText}
        </span>
        {wearingSuffix && (
          <span className={cn("text-[10px]",
                              s.wearing
                                ? "text-emerald-700/80 dark:text-emerald-300/80"
                                : "text-amber-700/80 dark:text-amber-300/80")}>
            {wearingSuffix}
          </span>
        )}
      </Pill>

      <Pill tone={battTier === "err" ? "err" : battTier === "warn" ? "warn" : "ok"}>
        <span>{battIcon}</span>
        <span className="font-medium">{batt ?? "--"}</span>
        <span className="text-[10px] text-muted-foreground">%</span>
        {chargeIcon && <span className="ml-0.5">{chargeIcon}</span>}
      </Pill>

      <Pill tone={s.last_update ? "ok" : "neutral"}>
        <span className={cn("size-1.5 rounded-full",
                            s.last_update ? "bg-emerald-400" : "bg-muted-foreground")} />
        <span className="text-muted-foreground">{updateText}</span>
      </Pill>
    </div>
  );
}

// ── 主卡片网格：呼吸 / 体温 / 姿势 ──────────────────────────────────
function SensorGrid({ s }: { s: Partial<SensorFrame> }) {
  const T = useT();
  const thresh = useSensorThresholds();

  // Breath
  const breathR = s.breath_rate ?? null;
  const breathInRange = breathR != null
    && breathR >= thresh.breath.min && breathR <= thresh.breath.max;
  const breathSub = breathR == null ? T.waiting
                  : breathInRange   ? T.normal
                  : breathR < thresh.breath.min ? T.slow : T.fast;
  const breathTone =
    breathR == null ? "default" : breathInRange ? "default" : "alert";

  // Temperature
  const tempV = s.temperature ?? null;
  const tempInRange = tempV != null
    && tempV >= thresh.temp.min && tempV <= thresh.temp.max;
  const tempTone =
    tempV == null ? "default" : tempInRange ? "default" : "warn";
  const tempColor =
    tempV == null ? "text-muted-foreground"
    : tempInRange ? "text-foreground"
    : tempV > thresh.temp.max ? "text-destructive" : "text-blue-400";

  // Posture
  const posture = (s.posture as Posture | null | undefined) ?? null;
  const postureLabel =
    posture ? (T.postures[posture] ?? posture) : "";
  const isProne = posture === "prone";
  const postureTone =
    posture == null ? "default" : isProne ? "alert" : "default";

  return (
    <div className="grid grid-cols-3 gap-2">
      <SensorCard tone={breathTone}>
        <CardLabel>{T.labelBreath}</CardLabel>
        <CardValue className={cn(breathR == null ? "text-muted-foreground"
                                : breathInRange ? "text-foreground" : "text-destructive")}>
          {breathR ?? "--"}
        </CardValue>
        <CardUnit>{T.unitBpm}</CardUnit>
        <CardSub>{breathSub}</CardSub>
      </SensorCard>

      <SensorCard tone={tempTone}>
        <CardLabel>{T.labelTemp}</CardLabel>
        <CardValue className={tempColor}>
          {tempV != null ? tempV.toFixed(1) : "--"}
        </CardValue>
        <CardUnit>°C</CardUnit>
      </SensorCard>

      <SensorCard tone={postureTone}>
        <CardLabel>{T.labelPosture}</CardLabel>
        {posture ? (
          <img src={`/static/images/${posture}.png`}
               alt={postureLabel}
               className="my-1 max-h-16 w-auto object-contain" />
        ) : (
          <CardSub className="my-2">{T.postureLoading}</CardSub>
        )}
        <CardValue className={cn("text-base",
                                 isProne ? "text-destructive" : "text-foreground")}>
          {postureLabel || "--"}
        </CardValue>
      </SensorCard>
    </div>
  );
}

// ── 通用 Pill / Card 子组件 ────────────────────────────────────────

type Tone = "ok" | "warn" | "err" | "neutral";
function Pill({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  const cls = {
    ok:      "border-emerald-500/40 bg-emerald-500/10",
    warn:    "border-amber-500/40 bg-amber-500/10",
    err:     "border-destructive/40 bg-destructive/10",
    neutral: "border-border/60 bg-card/40",
  }[tone];
  // flex-1 让 3 个 pill 在 status row 里平均填满（原版 .status-pill { flex: 1 }）。
  return (
    <span className={cn(
      "flex flex-1 items-center justify-center gap-1.5 rounded-full border px-2.5 py-1",
      cls,
    )}>
      {children}
    </span>
  );
}

type CardTone = "default" | "alert" | "warn";
function SensorCard({ tone, children }: { tone: CardTone; children: React.ReactNode }) {
  const cls = {
    default: "border-border/40 bg-card/40",
    alert:   "border-destructive/60 bg-destructive/10",
    warn:    "border-amber-500/60 bg-amber-500/10",
  }[tone];
  return (
    <div className={cn(
      "flex flex-col items-center justify-between gap-0.5 rounded-md border p-2 text-center transition-colors",
      cls,
    )}>
      {children}
    </div>
  );
}

function CardLabel({ children }: { children: React.ReactNode }) {
  return <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{children}</div>;
}

function CardValue({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("text-2xl font-semibold leading-none", className)}>{children}</div>;
}

function CardUnit({ children }: { children: React.ReactNode }) {
  return <div className="text-[10px] text-muted-foreground">{children}</div>;
}

function CardSub({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("text-[10px] text-muted-foreground", className)}>{children}</div>;
}
