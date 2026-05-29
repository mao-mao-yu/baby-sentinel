// 育儿日志的 5 种 picker dialog + 编辑/删除流程。
// 对应旧 index.html buildAmountPicker / buildBreastPicker / buildPoopPicker /
// buildNumberPicker / showEditPicker / simpleConfirmPicker。
//
// 公用模板 PickerDialog（标题 + 时间控件 + 主体 + 取消/确认 footer）下面收住了
// 所有变体；每个具体 picker 只关心"主体长啥样、确认时往后端 POST 啥"。

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Toggle } from "@/components/ui/toggle";
import { TimeDrumPicker, MinDrumPicker } from "@/baby-log/DrumPicker";
import { useT } from "@/i18n";
import { logApi, nowTime } from "@/baby-log/api";
import { useBumpScroll, useSysToday, useViewingDate } from "@/baby-log/scope";
import { formatHm } from "@/baby-log/stats";
import {
  FORMULA_AMOUNTS, POOP_AMOUNT_KEYS, POOP_COLORS, POOP_CONS_KEYS,
  type PoopAmount, type PoopColor, type PoopCons,
} from "@/baby-log/constants";
import type { LogEntry, Side } from "@/baby-log/types";
import { useBabyStats } from "@/api/ws";
import { cn } from "@/lib/utils";

// ── 通用骨架 ────────────────────────────────────────────────────────

interface PickerShellProps {
  open:        boolean;
  onClose:     () => void;
  title:       string;
  time:        string;
  onTimeChange: (v: string) => void;
  onSubmit:    () => void;
  submitLabel: string;
  /** 真正的请求 in-flight：禁用确认（防连点）。取消依然可点（让用户随时关）。 */
  submitting?: boolean;
  /** 表单是否合法。false 时禁用确认按钮，但取消不受影响。默认 true。 */
  canSubmit?:  boolean;
  children:    ReactNode;
  /** 编辑模式额外渲染的右侧按钮（删除）。 */
  extraFooter?: ReactNode;
}

function PickerShell(p: PickerShellProps) {
  const T = useT();
  const submitDisabled = !!p.submitting || p.canSubmit === false;
  return (
    <Dialog open={p.open} onOpenChange={(v) => { if (!v) p.onClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{p.title}</DialogTitle>
        </DialogHeader>

        {/* drum 滚轮时间选择 — 不带 label，控件本身已经是 HH:MM 形态够明显 */}
        <TimeDrumPicker value={p.time} onChange={p.onTimeChange} />

        <div className="space-y-3">{p.children}</div>

        {/* Footer 设计：按动作层级分两行
            ┌─ 主操作行（永远显示） ──────────────┐
            │              [取消]  [保存]        │ → 右对齐，保存在最右最显眼位置
            ├─ 危险操作行（仅 edit 模式） ─────────┤
            │  [🗑️ 删除记录]                     │ → 左下角，分割线隔开，物理远离保存
            └────────────────────────────────────┘
            删除是 ghost+红字而非实心红底——不跟保存争视觉权重 */}
        <DialogFooter className="flex flex-col gap-3 sm:flex-col sm:items-stretch sm:space-x-0">
          <div className="flex justify-end gap-2">
            {/* 取消永远可点 — 表单非法 / 提交中都不影响关闭意图 */}
            <Button variant="outline" onClick={p.onClose}>
              {T.cancel}
            </Button>
            <Button onClick={p.onSubmit} disabled={submitDisabled}>
              {p.submitLabel}
            </Button>
          </div>
          {p.extraFooter && (
            <>
              <div className="h-px w-full bg-border/60" />
              <div className="flex justify-start">{p.extraFooter}</div>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── 用 mutation 触发 add/update/delete ─────────────────────────────

function useEntryMutations(onDone: () => void) {
  const qc = useQueryClient();
  const date = useViewingDate();
  const bumpScroll = useBumpScroll();
  const refresh = () => {
    // 当前查看的那天的 list cache 失效；其他天的 cache 保留，下次切回时也会自动重拉。
    qc.invalidateQueries({ queryKey: ["log", date] });
    onDone();
  };
  // mutationFn 自动 inject `date: viewingDate`，让浏览器看哪天就往哪天写。
  // caller 显式传 e.date 时由它覆盖（spread 顺序）。
  const add = useMutation({
    mutationFn: (e: Partial<LogEntry>) => logApi.add({ date, ...e }),
    onSuccess: () => { refresh(); bumpScroll(); },   // 添加后让 TodayList 滚到新条目
  });
  const update = useMutation({
    mutationFn: ({ ts, updates }: { ts: number; updates: Partial<LogEntry> }) => logApi.update(ts, updates),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: (ts: number) => logApi.remove(ts), onSuccess: refresh });
  return { add, update, remove };
}

// ── 数量 picker (formula / bottle_milk / pump) ──────────────────────

interface AmountPickerProps {
  open:    boolean;
  onClose: () => void;
  type:    "formula" | "bottle_milk" | "pump";
  edit?:   { ts: number; entry: LogEntry };
}

export function AmountPicker({ open, onClose, type, edit }: AmountPickerProps) {
  const T = useT();
  const stats = useBabyStats();
  const recommend = stats?.recommended_ml ?? 60;

  const initial = (edit?.entry as { amount_ml?: number } | undefined)?.amount_ml
    ?? recommend;
  const [amount, setAmount] = useState<number>(initial);
  const [time, setTime]     = useState<string>(edit?.entry.time ?? nowTime());

  useEffect(() => {
    if (open) {
      // 注意 deps 不含 recommend —— 它会随 babyStats WS 广播更新（喂奶计时
      // 推进 / 其他端写记录都触发）。若列进 deps，用户打开 picker 选好时间
      // 后被广播触发的重跑会把 time 重置回 nowTime()，覆盖用户选择。
      // edit 用 edit?.ts（primitive）而不是整个 object —— EditDialog 的 wrap
      // 每次渲染都新建，对象引用 dep 会让 WS 触发的父重渲染重置用户选择。
      setAmount((edit?.entry as { amount_ml?: number } | undefined)?.amount_ml ?? recommend);
      setTime(edit?.entry.time ?? nowTime());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, edit?.ts]);

  const { add, update, remove } = useEntryMutations(onClose);
  const submitting = add.isPending || update.isPending || remove.isPending;

  const title = type === "formula" ? T.selectFormula
              : type === "bottle_milk" ? T.selectBottle
              : T.selectPump;

  function submit() {
    const payload = { type, amount_ml: amount || null, time };
    edit ? update.mutate({ ts: edit.ts, updates: payload }) : add.mutate(payload);
  }

  return (
    <PickerShell open={open} onClose={onClose}
      title={edit ? T.editTitle : title}
      time={time} onTimeChange={setTime}
      onSubmit={submit} submitting={submitting}
      submitLabel={edit ? T.editSave : T.confirm}
      extraFooter={edit ? <DeleteBtn onConfirm={() => remove.mutate(edit.ts)} /> : null}>
      <NumberStepper value={amount} onChange={setAmount} min={0} max={500} step={5} unit="mL" />
      <div className="grid grid-cols-4 gap-1.5">
        {FORMULA_AMOUNTS.map((v) => (
          <Button key={v} type="button" variant={v === amount ? "default" : "outline"}
                  size="sm" onClick={() => setAmount(v)}
                  className="h-9 text-xs">
            {v}
            {v === recommend && <span className="ml-0.5 text-amber-300">★</span>}
          </Button>
        ))}
      </div>
    </PickerShell>
  );
}

// ── 母乳 picker (left/right/both + duration) ─────────────────────────

interface BreastPickerProps {
  open:    boolean;
  onClose: () => void;
  edit?:   { ts: number; entry: LogEntry };
}

// 母乳 picker — 左右各 checkbox 启用，启用侧显示一个 1-60 分钟滚轮独立选时长。
// 至少勾一侧才能确认。
//   - 仅勾左：           {side:"left",  duration_min: leftMin}
//   - 仅勾右：           {side:"right", duration_min: rightMin}
//   - 两侧都勾：          {side:"both",  left_min, right_min}
// fmtEntry / stats 都已支持上述三种 payload。
export function BreastPicker({ open, onClose, edit }: BreastPickerProps) {
  const T = useT();
  const e = edit?.entry as
    { side?: Side; duration_min?: number; left_min?: number; right_min?: number; amount_ml?: number }
    | undefined;

  // 编辑模式初值：根据原 entry 的 side 字段反推哪侧勾上 + 该侧时长是多少。
  // 单侧条目用 duration_min 当时长；both 条目用各自的 left_min/right_min。
  const initLeftEnabled  = e ? (e.side === "both" || e.side === "left")  : true;
  const initRightEnabled = e ? (e.side === "both" || e.side === "right") : true;
  // 新建态默认 5 分钟（最常见的母乳单侧时长）；编辑态则吃原 entry 的值
  const initLeftMin  = e?.left_min  ?? (e?.side === "left"  ? e?.duration_min ?? 5 : 5);
  const initRightMin = e?.right_min ?? (e?.side === "right" ? e?.duration_min ?? 5 : 5);

  const [leftEnabled,  setLeftEnabled]  = useState<boolean>(initLeftEnabled);
  const [rightEnabled, setRightEnabled] = useState<boolean>(initRightEnabled);
  const [leftMin,      setLeftMin]      = useState<number>(initLeftMin);
  const [rightMin,     setRightMin]     = useState<number>(initRightMin);
  const [time,         setTime]         = useState<string>(edit?.entry.time ?? nowTime());

  useEffect(() => {
    if (!open) return;
    setLeftEnabled(initLeftEnabled);
    setRightEnabled(initRightEnabled);
    setLeftMin(initLeftMin);
    setRightMin(initRightMin);
    setTime(edit?.entry.time ?? nowTime());
    // edit?.ts 而非 edit —— 见 AmountPicker 同处注释
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, edit?.ts]);

  const { add, update, remove } = useEntryMutations(onClose);
  const submitting = add.isPending || update.isPending || remove.isPending;
  const canSubmit = leftEnabled || rightEnabled;

  function submit() {
    const base: Record<string, unknown> = { type: "breastfeed", time };
    if (leftEnabled && rightEnabled) {
      base.side = "both";
      base.left_min  = leftMin;
      base.right_min = rightMin;
    } else if (leftEnabled) {
      base.side = "left";
      base.duration_min = leftMin;
    } else {
      base.side = "right";
      base.duration_min = rightMin;
    }
    edit ? update.mutate({ ts: edit.ts, updates: base }) : add.mutate(base);
  }

  return (
    <PickerShell open={open} onClose={onClose}
      title={edit ? T.editTitle : T.selectBreast}
      time={time} onTimeChange={setTime}
      onSubmit={submit} submitting={submitting} canSubmit={canSubmit}
      submitLabel={edit ? T.editSave : T.confirm}
      extraFooter={edit ? <DeleteBtn onConfirm={() => remove.mutate(edit.ts)} /> : null}>
      <div className="grid grid-cols-2 gap-3">
        <SideColumn label={T.sideLeft}
                    enabled={leftEnabled} onEnabledChange={setLeftEnabled}
                    min={leftMin} onMinChange={setLeftMin} />
        <SideColumn label={T.sideRight}
                    enabled={rightEnabled} onEnabledChange={setRightEnabled}
                    min={rightMin} onMinChange={setRightMin} />
      </div>
    </PickerShell>
  );
}

function SideColumn({ label, enabled, onEnabledChange, min, onMinChange }: {
  label: string;
  enabled: boolean; onEnabledChange: (v: boolean) => void;
  min: number;     onMinChange:    (v: number) => void;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-md border border-border/40 bg-card/40 p-2">
      {/* Toggle: 大按钮样式，点一下选中→变色，再点取消→恢复。 */}
      <Toggle
        pressed={enabled}
        onPressedChange={onEnabledChange}
        size="lg"
        className={cn(
          "h-10 w-full text-base font-semibold",
          // 选中态：emerald 边 + 浅色背景 + 高亮文字；未选：低调灰
          "data-[state=on]:border-emerald-500/60 data-[state=on]:bg-emerald-500/15 data-[state=on]:text-emerald-300",
          "data-[state=off]:border-border/60 data-[state=off]:bg-card/40 data-[state=off]:text-muted-foreground",
          "border transition-colors",
        )}
      >
        {label}
      </Toggle>
      <div className={enabled ? "" : "opacity-30 pointer-events-none"}>
        <MinDrumPicker value={min} onChange={onMinChange} />
      </div>
    </div>
  );
}

// ── 便便 picker (amount + consistency + color) ──────────────────────

interface PoopPickerProps {
  open:    boolean;
  onClose: () => void;
  edit?:   { ts: number; entry: LogEntry };
}

export function PoopPicker({ open, onClose, edit }: PoopPickerProps) {
  const T = useT();
  const e = edit?.entry as { amount?: PoopAmount; consistency?: PoopCons; color?: PoopColor } | undefined;

  const [amount,      setAmount]      = useState<PoopAmount>(e?.amount      ?? "normal");
  const [consistency, setConsistency] = useState<PoopCons>  (e?.consistency ?? "normal");
  const [color,       setColor]       = useState<PoopColor> (e?.color       ?? "yellow");
  const [time, setTime] = useState<string>(edit?.entry.time ?? nowTime());

  useEffect(() => {
    if (!open) return;
    setAmount     (e?.amount      ?? "normal");
    setConsistency(e?.consistency ?? "normal");
    setColor      (e?.color       ?? "yellow");
    setTime(edit?.entry.time ?? nowTime());
    // edit?.ts 而非 edit/e —— 见 AmountPicker 同处注释
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, edit?.ts]);

  const { add, update, remove } = useEntryMutations(onClose);
  const submitting = add.isPending || update.isPending || remove.isPending;

  const amtLabels = { tiny: T.poopAmtTiny, small: T.poopAmtSmall, normal: T.poopAmtNormal, large: T.poopAmtLarge } as Record<string, string>;
  const consLabels = { loose: T.poopConsLoose, soft: T.poopConsSoft, normal: T.poopConsNormal, hard: T.poopConsHard } as Record<string, string>;

  function submit() {
    const payload = { type: "diaper", kind: "dirty", amount, consistency, color, time } as Partial<LogEntry>;
    edit ? update.mutate({ ts: edit.ts, updates: payload }) : add.mutate(payload);
  }

  return (
    <PickerShell open={open} onClose={onClose}
      title={edit ? T.editTitle : T.poopTitle}
      time={time} onTimeChange={setTime}
      onSubmit={submit} submitting={submitting}
      submitLabel={edit ? T.editSave : T.confirm}
      extraFooter={edit ? <DeleteBtn onConfirm={() => remove.mutate(edit.ts)} /> : null}>
      <PoopSection label={T.poopAmt}>
        <SegmentedKeys keys={POOP_AMOUNT_KEYS} active={amount} onPick={setAmount} labels={amtLabels} />
      </PoopSection>
      <PoopSection label={T.poopCons}>
        <SegmentedKeys keys={POOP_CONS_KEYS} active={consistency} onPick={setConsistency} labels={consLabels} />
      </PoopSection>
      <PoopSection label={T.poopColor}>
        <div className="grid grid-cols-7 gap-2">
          {POOP_COLORS.map((c) => {
            const isActive = color === c.key;
            return (
              <button key={c.key} type="button"
                      onClick={() => setColor(c.key)}
                      style={{ backgroundColor: c.hex }}
                      title={(T.poopColors)[c.key] ?? c.key}
                      aria-pressed={isActive}
                      className={cn(
                        "relative h-10 rounded-md border-2 transition-all",
                        isActive
                          ? "border-foreground scale-110 shadow-md"
                          : "border-border/60 opacity-70 hover:opacity-100 hover:scale-105",
                      )}>
                {/* 选中态额外画一个白色钩 ✓ 提高可读性（深色色块上） */}
                {isActive && (
                  <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-base font-bold drop-shadow-[0_0_2px_rgba(0,0,0,0.6)]"
                        style={{ color: ["white", "yellow"].includes(c.key) ? "#000" : "#fff" }}>
                    ✓
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </PoopSection>
    </PickerShell>
  );
}

// 便便 picker 通用 section 容器 — label uppercase + tracking 区分层级；
// 内容区不包卡片避免 modal 视觉过重，只靠 label 排版区分。
function PoopSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <Label className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </Label>
      {children}
    </div>
  );
}

// ── 数值 picker (temp / height / weight) ────────────────────────────

interface NumberPickerProps {
  open:    boolean;
  onClose: () => void;
  type:    "temperature" | "height" | "weight";
  edit?:   { ts: number; entry: LogEntry };
}

export function NumberPicker({ open, onClose, type, edit }: NumberPickerProps) {
  const T = useT();
  const cfg = NUMBER_CFG[type];
  const e = edit?.entry as { value?: number } | undefined;
  const initial = e?.value ?? cfg.default;

  const [value, setValue] = useState<number>(initial);
  const [time,  setTime]  = useState<string>(edit?.entry.time ?? nowTime());

  useEffect(() => {
    if (!open) return;
    setValue(e?.value ?? cfg.default);
    setTime(edit?.entry.time ?? nowTime());
    // edit?.ts 而非 edit/e —— 见 AmountPicker 同处注释
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, edit?.ts]);

  const { add, update, remove } = useEntryMutations(onClose);
  const submitting = add.isPending || update.isPending || remove.isPending;

  const title = type === "temperature" ? T.tempTitle
              : type === "height"      ? T.heightTitle
              : T.weightTitle;

  function submit() {
    const payload = { type, value, time };
    edit ? update.mutate({ ts: edit.ts, updates: payload }) : add.mutate(payload);
  }

  return (
    <PickerShell open={open} onClose={onClose}
      title={edit ? T.editTitle : title}
      time={time} onTimeChange={setTime}
      onSubmit={submit} submitting={submitting}
      submitLabel={edit ? T.editSave : T.confirm}
      extraFooter={edit ? <DeleteBtn onConfirm={() => remove.mutate(edit.ts)} /> : null}>
      <NumberStepper value={value} onChange={setValue} min={cfg.min} max={cfg.max} step={cfg.step} unit={cfg.unit} />
    </PickerShell>
  );
}

const NUMBER_CFG = {
  temperature: { min: 35,   max: 42,    step: 0.1, default: 37,   unit: "°C" },
  height:      { min: 30,   max: 100,   step: 0.5, default: 50,   unit: "cm" },
  weight:      { min: 1000, max: 15000, step: 10,  default: 3000, unit: "g"  },
} as const;

// ── 简单确认 picker (sleep start / wet / bath) ──────────────────

interface SimplePickerProps {
  open:    boolean;
  onClose: () => void;
  title:   string;
  buildPayload: (time: string) => Partial<LogEntry>;
  /** 编辑模式 — 走 PUT 更新该条 ts，并显示删除按钮。 */
  edit?:   { ts: number; entry: LogEntry };
}

export function SimplePicker({ open, onClose, title, buildPayload, edit }: SimplePickerProps) {
  const T = useT();
  const [time, setTime] = useState<string>(edit?.entry.time ?? nowTime());
  useEffect(() => {
    if (open) setTime(edit?.entry.time ?? nowTime());
    // edit?.ts 而非 edit —— 见 AmountPicker 同处注释
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, edit?.ts]);

  const { add, update, remove } = useEntryMutations(onClose);
  const submitting = add.isPending || update.isPending || remove.isPending;

  function submit() {
    const payload = buildPayload(time);
    edit ? update.mutate({ ts: edit.ts, updates: payload }) : add.mutate(payload);
  }

  return (
    <PickerShell open={open} onClose={onClose}
      title={edit ? `${T.editTitle} — ${title}` : title}
      time={time} onTimeChange={setTime}
      onSubmit={submit} submitting={submitting}
      submitLabel={edit ? T.editSave : T.confirm}
      extraFooter={edit ? <DeleteBtn onConfirm={() => remove.mutate(edit.ts)} /> : null}>
      <p className="text-sm text-muted-foreground text-center">{title}</p>
    </PickerShell>
  );
}

// ── 起床 picker — 带睡眠时长实时显示 ─────────────────────────────
// 行为对齐旧 index.html btn-wake handler：
//  - viewing 是今天 → 用 babyStats.sleeping_since 算时长
//  - viewing 是历史日期 → 暂不算（显示 --），跨日 _findOpenSleepStartTs 边角先省

interface WakePickerProps {
  open:    boolean;
  onClose: () => void;
}

export function WakePicker({ open, onClose }: WakePickerProps) {
  const T = useT();
  const stats = useBabyStats() as null | { sleeping_since?: number | null };
  const date = useViewingDate();
  const sysToday = useSysToday();
  const sleepingSince = (date === sysToday) ? (stats?.sleeping_since ?? null) : null;

  const [time, setTime] = useState<string>(nowTime());
  useEffect(() => { if (open) setTime(nowTime()); }, [open]);

  const { add } = useEntryMutations(onClose);

  // wakeTs 必须按 viewingDate + time 拼，否则跨日历史录入会算错
  const durationSec = useMemo(() => {
    if (!sleepingSince) return null;
    const [h, m] = time.split(":").map(Number);
    const [vy, vmo, vd] = date.split("-").map(Number);
    const wakeTs = new Date(vy, vmo - 1, vd, h, m).getTime() / 1000;
    const diff = wakeTs - sleepingSince;
    return diff > 0 ? diff : null;
  }, [time, date, sleepingSince]);

  function submit() {
    add.mutate({ type: "sleep", action: "end", time });
  }

  return (
    <PickerShell open={open} onClose={onClose}
      title={T.btnWake}
      time={time} onTimeChange={setTime}
      onSubmit={submit} submitting={add.isPending}
      submitLabel={T.confirm}>
      <div className="rounded-md border border-border/40 bg-card/40 px-3 py-2 text-center">
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{T.entrySleep}</div>
        <div className="text-2xl font-semibold leading-tight">
          {durationSec ? formatHm(durationSec * 1000, T) : "--"}
        </div>
      </div>
    </PickerShell>
  );
}

// ── 子元件：数值步进 / 预设网格 / 段控 / 删除按钮 ────────────────

function NumberStepper({ value, onChange, min, max, step, unit }: {
  value: number; onChange: (v: number) => void;
  min: number; max: number; step: number; unit?: string;
}) {
  const clamp = (v: number) => Math.max(min, Math.min(max, +v.toFixed(2)));
  // 本地文本态：让用户能清空 / 输中间态（删光重输、输小数点）。
  // 踩过的坑：之前 onChange 里 clamp(parseFloat(e)||0) —— 清空时 parseFloat("")=NaN
  // → ||0 → clamp(0) → 弹回 min（体重 min=1000），根本删不掉重输。
  // 现在：编辑时只夹上限（防溢出）实时上报 parent，下限留到失焦再补；
  // 空 / 非法输入不上报，保留上一个合法值。
  const [text, setText] = useState(String(value));
  useEffect(() => {
    // 仅当外部 value 与当前文本数值不一致才同步（+/- 按钮 / 重开 picker）；
    // 避免覆盖用户正在输的中间态（如 "3." / "3.5"）。
    if (parseFloat(text) !== value) setText(String(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <div className="flex items-center gap-2">
      <Button type="button" variant="outline" size="sm"
              onClick={() => onChange(clamp(value - step))}>−</Button>
      <Input type="number" value={text}
             onChange={(e) => {
               setText(e.target.value);
               const n = parseFloat(e.target.value);
               if (!isNaN(n)) onChange(Math.min(max, n));   // 只夹上限，下限 blur 补
             }}
             onBlur={() => {
               const n = parseFloat(text);
               const v = isNaN(n) ? value : clamp(n);
               setText(String(v));
               onChange(v);
             }}
             min={min} max={max} step={step}
             className="h-9 text-center" />
      <Button type="button" variant="outline" size="sm"
              onClick={() => onChange(clamp(value + step))}>+</Button>
      {unit && <span className="text-xs text-muted-foreground">{unit}</span>}
    </div>
  );
}

function SegmentedKeys<K extends string>({ keys, active, onPick, labels }: {
  keys: readonly K[]; active: K; onPick: (k: K) => void; labels: Record<string, string>;
}) {
  // variant="outline"：每颗 item 有边框，看起来像真正的分段控件而不是孤立文字按钮
  return (
    <ToggleGroup type="single" variant="outline" value={active}
                 onValueChange={(v) => v && onPick(v as K)}
                 className="grid w-full grid-cols-4 gap-0">
      {keys.map((k) => (
        <ToggleGroupItem key={k} value={k} className="text-xs">
          {labels[k] ?? k}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

function DeleteBtn({ onConfirm }: { onConfirm: () => void }) {
  const T = useT();
  // ghost + 红字：层级低于保存（实心 primary）和取消（描边 outline），同时颜色提示破坏性
  return (
    <Button type="button" variant="ghost" size="sm"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={() => { if (window.confirm(T.editConfirmDelete)) onConfirm(); }}>
      {T.editDelete}
    </Button>
  );
}
