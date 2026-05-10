// 滚轮（drum）时间选择器，行为对齐旧 index.html buildTimeCtrl + buildDrumCol：
//  - 两列：小时 0-23、分钟 0/5/10/.../55（5min 步进，与原版一致）
//  - 循环模式（cyclic）：内部把数组重复 3 份，停下时静默 recenter 中段，无视觉跳变
//  - touch / mouse 拖拽 + 抬手 snap 到最近 item，CSS 动画过渡
//  - 中段 highlight 表示当前选中
//
// 不引第三方库，本组件 ~150 行，开发体验跟原生一致。

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";

const ITEM_H = 50;     // 单 item 像素高度，跟 .drum-item height: 50px 对齐
const COL_H  = 150;    // 列容器高度（3 个 item 高，中间是选中行）

interface DrumColumnProps {
  items:    readonly number[];
  value:    number;
  onChange: (v: number) => void;
  cyclic?:  boolean;
}

export function DrumColumn({ items, value, onChange, cyclic = true }: DrumColumnProps) {
  const n = items.length;
  // 循环模式：内部数组重复 3 段，避免拖到边界；中间段下标 [n, 2n)
  const virtual = useMemo(() => cyclic ? [...items, ...items, ...items] : [...items], [items, cyclic]);
  const vLen = virtual.length;

  // 把外部 value 映射到 virtual 数组下标。开始时定位到中间段。
  const findInitIdx = () => {
    let i = items.indexOf(value);
    if (i < 0) {
      // value 不在 items（如分钟传 12，items 只有 0,5,10,...）→ 找最接近的
      i = items.reduce((best, x, idx) =>
        Math.abs(x - value) < Math.abs(items[best] - value) ? idx : best, 0);
    }
    return cyclic ? n + i : i;
  };

  const colRef   = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const stateRef = useRef({
    curIdx:      findInitIdx(),
    offsetY:     0,
    startY:      0,
    startOffset: 0,
    dragging:    false,
  });

  // 当前 highlight 用 React state 触发重渲染（其他都靠 ref + transform 直接驱动 DOM）
  const [hlIdx, setHlIdx] = useState(stateRef.current.curIdx);

  const idxToOffset = (i: number) => ITEM_H - i * ITEM_H;
  const clampIdx = (i: number) => Math.max(0, Math.min(vLen - 1, i));

  function applyOffset(v: number, animate: boolean) {
    const inner = innerRef.current;
    if (!inner) return;
    inner.style.transition = animate ? "transform .22s cubic-bezier(.33,1,.68,1)" : "none";
    inner.style.transform = `translateY(${v}px)`;
    stateRef.current.offsetY = v;
    const newIdx = clampIdx(Math.round((ITEM_H - v) / ITEM_H));
    if (newIdx !== stateRef.current.curIdx) {
      stateRef.current.curIdx = newIdx;
      setHlIdx(newIdx);
      onChange(items[newIdx % n]);
    }
  }

  function recenter() {
    if (!cyclic) return;
    const { curIdx } = stateRef.current;
    let adj = 0;
    if (curIdx < n)        adj = +n;
    if (curIdx >= n * 2)   adj = -n;
    if (adj === 0) return;
    const next = curIdx + adj;
    stateRef.current.curIdx = next;
    setHlIdx(next);
    const inner = innerRef.current;
    if (!inner) return;
    inner.style.transition = "none";
    inner.style.transform = `translateY(${idxToOffset(next)}px)`;
    stateRef.current.offsetY = idxToOffset(next);
  }

  function snapToNearest(animate = true) {
    const ni = clampIdx(Math.round((ITEM_H - stateRef.current.offsetY) / ITEM_H));
    stateRef.current.curIdx = ni;
    applyOffset(idxToOffset(ni), animate);
    if (cyclic) setTimeout(recenter, 240);
  }

  // 初始定位
  useLayoutEffect(() => {
    applyOffset(idxToOffset(stateRef.current.curIdx), false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 外部 value 变化（如打开 picker 时 reset 到 nowTime）→ 重定位
  useEffect(() => {
    const target = findInitIdx();
    if (target !== stateRef.current.curIdx) {
      stateRef.current.curIdx = target;
      setHlIdx(target);
      applyOffset(idxToOffset(target), false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  // ── 拖拽 handler ────────────────────────────────────────────
  function onStart(clientY: number) {
    stateRef.current.dragging = true;
    stateRef.current.startY = clientY;
    stateRef.current.startOffset = stateRef.current.offsetY;
    if (innerRef.current) innerRef.current.style.transition = "none";
  }
  function onMove(clientY: number) {
    if (!stateRef.current.dragging) return;
    const dy = clientY - stateRef.current.startY;
    let v = stateRef.current.startOffset + dy;
    // 两端橡皮筋（循环模式中段不会触发）
    const minOff = idxToOffset(vLen - 1), maxOff = idxToOffset(0);
    if (v > maxOff) v = maxOff + (v - maxOff) * 0.3;
    if (v < minOff) v = minOff + (v - minOff) * 0.3;
    applyOffset(v, false);
  }
  function onEnd() {
    if (!stateRef.current.dragging) return;
    stateRef.current.dragging = false;
    snapToNearest(true);
  }

  return (
    <div
      ref={colRef}
      className="relative cursor-grab overflow-hidden select-none active:cursor-grabbing"
      style={{ width: 54, height: COL_H, touchAction: "none" }}
      onTouchStart={(e) => { e.preventDefault(); onStart(e.touches[0].clientY); }}
      onTouchMove={(e)  => { e.preventDefault(); onMove(e.touches[0].clientY);  }}
      onTouchEnd={onEnd}
      onMouseDown={(e) => {
        e.preventDefault();
        onStart(e.clientY);
        const mmv = (ev: MouseEvent) => onMove(ev.clientY);
        const mup = () => {
          onEnd();
          window.removeEventListener("mousemove", mmv);
          window.removeEventListener("mouseup", mup);
        };
        window.addEventListener("mousemove", mmv);
        window.addEventListener("mouseup", mup);
      }}
    >
      {/* 中间高亮带 */}
      <div className="pointer-events-none absolute inset-x-0 z-10 border-y border-border/60"
           style={{ top: ITEM_H, height: ITEM_H }} />
      <div ref={innerRef} className="absolute inset-x-0 will-change-transform">
        {virtual.map((v, i) => (
          <div key={i}
               className={cn(
                 "flex items-center justify-center font-semibold tabular-nums transition-all",
                 i === hlIdx ? "text-foreground text-[1.55rem]" : "text-muted-foreground text-[1.4rem]",
               )}
               style={{ height: ITEM_H }}>
            {String(v).padStart(2, "0")}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Time picker：HH:MM 两列 ─────────────────────────────────

const HOURS   = Array.from({ length: 24 }, (_, i) => i);
const MINUTES = Array.from({ length: 12 }, (_, i) => i * 5);   // 0,5,...,55

interface TimeDrumPickerProps {
  value:    string;       // "HH:MM"
  onChange: (v: string) => void;
}

export function TimeDrumPicker({ value, onChange }: TimeDrumPickerProps) {
  const [hh, mm] = value.split(":").map(Number);
  // 入参分钟若非 5 倍数，DrumColumn 会自己 findClosest，但我们要回写 5 倍数
  const setHour   = (h: number) => onChange(`${pad(h)}:${pad(mm)}`);
  const setMinute = (m: number) => onChange(`${pad(hh)}:${pad(m)}`);
  return (
    <div className="flex select-none items-center justify-center gap-1">
      <DrumColumn items={HOURS}   value={hh} onChange={setHour}   />
      <div className="text-2xl font-bold leading-none mb-0.5">:</div>
      <DrumColumn items={MINUTES} value={mm} onChange={setMinute} />
    </div>
  );
}

const pad = (n: number) => String(n).padStart(2, "0");

// ── 1–60 分钟单列滚轮（母乳左右独立时长用） ────────────────────────

const MINUTES_1_60 = Array.from({ length: 60 }, (_, i) => i + 1);

interface MinDrumPickerProps {
  value:    number;
  onChange: (v: number) => void;
}

export function MinDrumPicker({ value, onChange }: MinDrumPickerProps) {
  return (
    <div className="flex select-none items-center justify-center gap-2">
      <DrumColumn items={MINUTES_1_60} value={value} onChange={onChange} cyclic={false} />
      <span className="text-xs text-muted-foreground">min</span>
    </div>
  );
}
