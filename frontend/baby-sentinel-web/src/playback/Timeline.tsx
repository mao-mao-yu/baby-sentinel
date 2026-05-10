// 24h 时间轴 — 跟旧 playback.html .timeline 行为对齐：
//  - 顶部小时刻度（每 6h 大刻度有数字）
//  - 段行：彩色横条，对应 segments；点击切到该段
//  - 事件行：emoji marker，点击跳到该 ts
//  - 红色 playhead 跟着 realTs 移动
//
// scrub 行为：只能从 playhead 手柄按下开始拖；rail 上其他位置点击 = 不响应
// （避免误触误跳；段/事件按钮自己处理 onClick）。

import { useEffect, useRef, useState } from "react";
import type { Segment, EventRow } from "@/playback/types";
import { dayStart, eventIcon, fmtTs, tsToPercent } from "@/playback/utils";
import { useSegmentS } from "@/api/manager-config";
import { cn } from "@/lib/utils";

const HOURS      = Array.from({ length: 25 }, (_, i) => i);          // 0..24
const HALF_HOURS = Array.from({ length: 24 }, (_, i) => i + 0.5);    // 0.5..23.5

interface Props {
  date:        string;
  segments:    Segment[];
  events:      EventRow[];
  realTs:      number;          // 当前播放 ts
  curIdx:      number;          // 当前段在 segments 中的下标
  onSegClick:  (idx: number) => void;
  /** 用户拖完 playhead 释放：跳到这个 ts（parent 会找包含它的段并 seek） */
  onScrubTo:   (ts: number) => void;
}

export function Timeline({ date, segments, events, realTs, curIdx, onSegClick, onScrubTo }: Props) {
  const segS = useSegmentS();   // 段固定宽度 (秒)，决定彩条画多宽 — 不画段间间隙
  const railInnerRef = useRef<HTMLDivElement>(null);   // 24h 滚动条的内层（含 width=100%/min-720）
  const railOuterRef = useRef<HTMLDivElement>(null);   // 外层 overflow-x-auto 容器
  const [scrubTs, setScrubTs] = useState<number | null>(null);
  // 拖拽平移：mouse 按下空白时记录起点 + 起始 scrollLeft，move 时反向更新 scrollLeft
  const panRef = useRef<{ startX: number; startScroll: number; pointerId: number } | null>(null);

  const start = dayStart(date);
  const realPct = tsToPercent(realTs, date);
  const headPct = scrubTs != null ? tsToPercent(scrubTs, date) : realPct;

  // 用 ref 存最新 realTs，避免 setTimeout 闭包拿到陈旧值
  const realTsRef = useRef(realTs);
  useEffect(() => { realTsRef.current = realTs; });

  // realTs 大跳（>30 秒）→ 立即把视角带到红线。视频每秒一帧的小步进 (<30s) 走 idle
  // 计时；段切换 / scrub 提交 / 进页面 auto-jump 这些产生大跳，应当跟到位。
  // 比较 ref 而不是 deps 闭包：避免每帧多渲染都触发；只有跳跃才进 if。
  const prevRealTsForJumpRef = useRef(realTs);
  useEffect(() => {
    const prev = prevRealTsForJumpRef.current;
    prevRealTsForJumpRef.current = realTs;
    if (Math.abs(realTs - prev) <= 30) return;
    const outer = railOuterRef.current;
    const inner = railInnerRef.current;
    if (!outer || !inner) return;
    const target = inner.clientWidth * tsToPercent(realTs, date) - outer.clientWidth / 2;
    outer.scrollTo({ left: Math.max(0, target), behavior: "smooth" });
  }, [realTs, date]);

  // 3s 空闲后归位红线到中心。每次用户交互（scroll / pan / scrub）都重置定时器。
  // 不再 auto-center —— 用户手动 pan 走的位置不会被视频每秒一帧推回。
  const recenterTimerRef = useRef<number | null>(null);
  function scheduleRecenter() {
    if (recenterTimerRef.current != null) clearTimeout(recenterTimerRef.current);
    recenterTimerRef.current = window.setTimeout(() => {
      recenterTimerRef.current = null;
      const outer = railOuterRef.current;
      const inner = railInnerRef.current;
      if (!outer || !inner) return;
      const target = inner.clientWidth * tsToPercent(realTsRef.current, date) - outer.clientWidth / 2;
      outer.scrollTo({ left: Math.max(0, target), behavior: "smooth" });
    }, 3000);
  }

  // 初始 mount + date 切换：触发一轮 3s idle 等待
  useEffect(() => {
    scheduleRecenter();
    return () => {
      if (recenterTimerRef.current != null) clearTimeout(recenterTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date]);

  // 鼠标滚轮 → 横向滚 timeline。React 的 onWheel 默认 passive 拦不住默认页面滚动，
  // 必须 ref + addEventListener({passive:false})。仅当 deltaX 没值（普通鼠标）时
  // 把 deltaY 转成横向；触控板的横向 deltaX 让 outer 自己消化即可。
  useEffect(() => {
    const outer = railOuterRef.current;
    if (!outer) return;
    const onWheel = (e: WheelEvent) => {
      const dx = e.deltaX !== 0 ? e.deltaX : e.deltaY;
      if (dx === 0) return;
      e.preventDefault();
      outer.scrollLeft += dx;
      scheduleRecenter();
    };
    outer.addEventListener("wheel", onWheel, { passive: false });
    return () => outer.removeEventListener("wheel", onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 只接受 playhead 手柄按下后启动 scrub；释放后 commit + 清空
  function pctFromClientX(clientX: number): number {
    const inner = railInnerRef.current;
    const outer = railOuterRef.current;
    if (!inner || !outer) return 0;
    const rect = inner.getBoundingClientRect();
    const x = Math.max(0, Math.min(inner.clientWidth, clientX - rect.left));
    return x / inner.clientWidth;
  }
  function startScrubAt(clientX: number) {
    setScrubTs(start + pctFromClientX(clientX) * 86400);
    scheduleRecenter();
  }
  function moveScrubAt(clientX: number) {
    setScrubTs(start + pctFromClientX(clientX) * 86400);
    scheduleRecenter();
  }
  function endScrub() {
    setScrubTs((cur) => {
      if (cur != null) onScrubTo(cur);
      return null;
    });
    scheduleRecenter();
  }

  return (
    // 外层 h-full：父 flex-1 槽给多少高度就吃多少；rail 容器 absolute 撑满。
    // select-none：禁止文本/元素选中，避免拖拽时出现高亮选区。
    // p-2 留点呼吸不让内容贴边；min-h-0 防 flex 父算溢出。
    // relative：给上方"大时间气泡"作 absolute 定位锚点。
    <div className="relative flex h-full min-h-0 flex-col select-none rounded-md border border-border/40 bg-card/40 p-2">
      {/* 拖动 / scrub 时在 Timeline 顶部正中显示一个大号时间气泡，方便精细对位。
          位置是固定在容器顶上方，不跟随 playhead 横向移动——避免左右边缘被裁。 */}
      {scrubTs != null && (
        <div className="pointer-events-none absolute -top-9 left-1/2 z-20 -translate-x-1/2 rounded-md bg-blue-500 px-3 py-1.5 font-mono text-base font-semibold text-white shadow-lg ring-1 ring-blue-400/50">
          {fmtTs(scrubTs)}
        </div>
      )}
      <div ref={railOuterRef}
           /* overscroll-x-contain：滚到最左/右时不冒泡到浏览器，防止 iOS 左滑触发返回上一页 */
           className="relative min-h-0 flex-1 overflow-x-auto overflow-y-hidden overscroll-x-contain"
           onScroll={scheduleRecenter}>
        {/* 内层带 onPointerDown 拖拽平移：仅在 e.target === e.currentTarget（即落在
            inner 自己上、不是按钮 / playhead）时才接管，避免吃掉子元素的点击。
            mobile 触屏自然走原生横向 overflow-x-auto，不依赖这套 mouse 逻辑。 */}
        <div ref={railInnerRef}
             className="relative h-full cursor-grab active:cursor-grabbing"
             /* 24h 总宽度：min 2400px（视口窄时也能展开）/ 200%（宽屏更舒展）。
                113 段 6 分钟时，每段约 10–12px 宽，能看清能点击；不够横向滑就行。 */
             style={{ width: "max(2400px, 200%)" }}
             onPointerDown={(e) => {
               if (e.target !== e.currentTarget) return;
               const outer = railOuterRef.current;
               if (!outer) return;
               e.currentTarget.setPointerCapture(e.pointerId);
               panRef.current = {
                 startX: e.clientX,
                 startScroll: outer.scrollLeft,
                 pointerId: e.pointerId,
               };
               scheduleRecenter();
             }}
             onPointerMove={(e) => {
               const p = panRef.current;
               const outer = railOuterRef.current;
               if (!p || !outer) return;
               outer.scrollLeft = p.startScroll - (e.clientX - p.startX);
               // pan 持续移动时也算交互，重置 3s 空闲计时（onScroll 也会触发一次，重复无害）
               scheduleRecenter();
             }}
             onPointerUp={(e) => {
               const p = panRef.current;
               panRef.current = null;
               if (p) {
                 try { e.currentTarget.releasePointerCapture(p.pointerId); } catch { /* noop */ }
               }
             }}
             onPointerCancel={() => { panRef.current = null; }}>
          {/* 时间刻度：每小时大刻度 + 数字；每半小时小刻度（无数字）。
              视觉层级：6h / 12h / 18h 大且亮，其余小时中等，半小时最弱。 */}
          <div className="pointer-events-none absolute inset-x-0 top-0 h-5">
            {HALF_HOURS.map((h) => (
              <div key={`half-${h}`} className="absolute top-0"
                   style={{ left: `${(h / 24) * 100}%` }}>
                <div className="h-1 w-px bg-border/50" />
              </div>
            ))}
            {HOURS.map((h) => (
              <div key={h} className="absolute top-0"
                   style={{ left: `${(h / 24) * 100}%` }}>
                <div className={cn("w-px",
                                   h % 6 === 0 ? "h-3 bg-muted-foreground" : "h-2 bg-border")} />
                <div className={cn(
                  "absolute left-0 top-3 -translate-x-1/2 font-mono text-[10px] tabular-nums",
                  h % 6 === 0 ? "text-foreground" : "text-muted-foreground",
                )}>
                  {String(h).padStart(2, "0")}
                </div>
              </div>
            ))}
          </div>

          {/* 段行 — 宽度按 (end_ts - ts) 真实段长画；index.csv 没 end_pts_time 时
              fallback ts+segS。这样录像断档（如 8:45 之后没了）时，bar 不会假装继续覆盖。
              点击跳到该段。 */}
          <div className="absolute inset-x-0 top-7 h-6">
            {segments.map((s, i) => {
              const endTs = s.end_ts ?? (s.ts + segS);
              const left  = tsToPercent(s.ts, date);
              const right = tsToPercent(endTs, date);
              const w = Math.max(0.002, right - left);
              return (
                <button
                  key={s.file}
                  type="button"
                  onClick={() => onSegClick(i)}
                  className={cn(
                    "absolute top-0 h-full rounded-sm border transition",
                    i === curIdx
                      ? "border-blue-300 bg-blue-500/40"
                      : "border-blue-500/30 bg-blue-500/15 hover:bg-blue-500/30",
                  )}
                  style={{ left: `${left * 100}%`, width: `${w * 100}%` }}
                  title={`${fmtTs(s.ts)} → ${fmtTs(endTs)}`}
                />
              );
            })}
          </div>

          {/* 事件行 — 点击跳到该 ts */}
          <div className="absolute inset-x-0 top-14 h-7">
            {events.map((e, i) => (
              <button
                key={`${e.ts}-${i}`}
                type="button"
                onClick={() => onScrubTo(e.ts)}
                title={`${fmtTs(e.ts)} ${e.type}`}
                className="absolute top-0 -translate-x-1/2 rounded-full bg-card/80 px-1 text-base hover:scale-125 transition"
                style={{ left: `${tsToPercent(e.ts, date) * 100}%` }}
              >
                {eventIcon(e)}
              </button>
            ))}
          </div>

          {/* playhead — 容器 16px 宽（透明 hit area），里面居中一条 2px 红线视觉标识。
              -translate-x-1/2 让手柄正中对齐 headPct 位置。 */}
          <div
            className="absolute top-0 h-full w-4 -translate-x-1/2 cursor-ew-resize"
            style={{ left: `${headPct * 100}%`, touchAction: "none" }}
            onPointerDown={(e) => {
              e.preventDefault();
              e.currentTarget.setPointerCapture(e.pointerId);
              startScrubAt(e.clientX);
            }}
            onPointerMove={(e) => {
              if (scrubTs == null) return;
              moveScrubAt(e.clientX);
            }}
            onPointerUp={(e) => {
              try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* noop */ }
              endScrub();
            }}
            onPointerCancel={endScrub}
          >
            {/* 视觉竖线：居中、2px、跟随 scrub 状态变色 */}
            <div className={cn(
              "pointer-events-none absolute left-1/2 top-0 h-full w-0.5 -translate-x-1/2",
              scrubTs != null ? "bg-blue-400" : "bg-destructive",
            )} />
            {/* 顶部小气泡显示时刻 */}
            <div className={cn(
              "pointer-events-none absolute -top-0.5 left-1/2 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded px-1.5 py-0.5 font-mono text-[10px] text-white shadow",
              scrubTs != null ? "bg-blue-500" : "bg-destructive/90",
            )}>
              {fmtTs(scrubTs ?? realTs)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
