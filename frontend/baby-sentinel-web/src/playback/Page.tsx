// 录像回放页主组件 — 4 个数据源 + 视频/时间轴/sensor 状态机的集中处理。
// 行为对齐旧 backend/services/web/static/playback.html。

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import { useT } from "@/i18n";
import { playbackApi } from "@/playback/api";
import { Timeline } from "@/playback/Timeline";
import { VideoPanel } from "@/playback/VideoPanel";
import { QuickJumps } from "@/playback/QuickJumps";
import { dayStart, nearestSensor } from "@/playback/utils";

export function PlaybackPage() {
  const T = useT();

  // ── 1. 日期列表 ──────────────────────────────────────────────────
  const datesQ = useQuery({ queryKey: ["pb-dates"], queryFn: playbackApi.dates });
  const dates  = datesQ.data ?? [];
  const [date, setDate] = useState<string>("");
  useEffect(() => {
    // 默认选最新（list 是 desc）
    if (!date && dates.length) setDate(dates[0]);
  }, [dates, date]);

  // ── 2. 当日 segments / sensors / events 并发拉 ──────────────────
  const segsQ    = useQuery({ queryKey: ["pb-segs",    date], queryFn: () => playbackApi.segments(date), enabled: !!date });
  const sensorsQ = useQuery({ queryKey: ["pb-sensors", date], queryFn: () => playbackApi.sensors(date),  enabled: !!date });
  const eventsQ  = useQuery({ queryKey: ["pb-events",  date], queryFn: () => playbackApi.events(date),   enabled: !!date });

  const segments = useMemo(() => (segsQ.data ?? []).slice().sort((a, b) => a.ts - b.ts), [segsQ.data]);
  const sensors  = useMemo(() => (sensorsQ.data ?? []).slice().sort((a, b) => a.ts - b.ts), [sensorsQ.data]);
  const events   = eventsQ.data ?? [];

  // ── 3. 当前段 / 实时 ts ────────────────────────────────────────
  const [curIdx, setCurIdx]   = useState(0);
  const [realTs, setRealTs]   = useState<number>(0);
  const videoRef = useRef<HTMLVideoElement>(null);

  // 切日期：复位 idx + 标记未 auto-jump（让下面 effect 再跳一次到最新段）
  const autoJumpedDateRef = useRef<string | null>(null);
  useEffect(() => {
    setCurIdx(0);
    setRealTs(date ? dayStart(date) : 0);
    autoJumpedDateRef.current = null;
  }, [date]);

  // segments 一拿到：跳到最近一段（升序排过，所以是最后一个）。每个 date 只跳一次，
  // 避免用户手动切到早一段后又被拖回来。
  useEffect(() => {
    if (!date || autoJumpedDateRef.current === date || segments.length === 0) return;
    const lastIdx = segments.length - 1;
    setCurIdx(lastIdx);
    setRealTs(segments[lastIdx].ts);
    autoJumpedDateRef.current = date;
  }, [date, segments]);

  // 段切换：load 新 src，video 自动 play（autoPlay）
  function playSeg(idx: number) {
    if (idx < 0 || idx >= segments.length) return;
    setCurIdx(idx);
    const v = videoRef.current;
    if (v) { v.currentTime = 0; v.play().catch(() => {}); }
  }

  // 跳到任意 ts：找包含或最接近的段，然后段内 seek = ts - seg.ts
  function scrubTo(targetTs: number) {
    if (!segments.length) return;
    let idx = 0;
    for (let i = 0; i < segments.length; i++) {
      if (segments[i].ts <= targetTs) idx = i;
      else break;
    }
    setCurIdx(idx);
    const offset = Math.max(0, targetTs - segments[idx].ts);
    const v = videoRef.current;
    // 切 src 后要等 metadata loaded 才能设 currentTime；用一次性 listener
    if (v) {
      const apply = () => {
        v.currentTime = offset;
        v.play().catch(() => {});
        v.removeEventListener("loadedmetadata", apply);
      };
      // 如果是同一段（idx 没变 + src 没变），直接 seek
      if (v.src && v.src.endsWith(segments[idx].file)) {
        v.currentTime = offset;
        v.play().catch(() => {});
      } else {
        v.addEventListener("loadedmetadata", apply);
      }
    }
  }

  const current = segments[curIdx] ?? null;
  const currentSensor = useMemo(() => nearestSensor(sensors, realTs), [sensors, realTs]);

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-background text-foreground">
      {/* Header — 返回按钮 + 标题 + 日期下拉 */}
      <header className="shrink-0 border-b border-border/60 bg-background px-4 py-2.5">
        <div className="flex flex-wrap items-center gap-3">
          <a href="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ChevronLeft className="size-4" />{T.pbBack}
          </a>
          <h1 className="text-base font-semibold">{T.pbTitle}</h1>
          <select value={date} onChange={(e) => setDate(e.target.value)}
                  className="ml-auto rounded-md border border-border/60 bg-card/40 px-2 py-1 text-sm">
            <option value="" disabled>{T.pbSelectDatePrompt}</option>
            {dates.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
      </header>

      {/* Main 布局：跟监控页同款 2 列 grid（仅 md+），左 video+sensor，右 nav+timeline。
          mobile 单列垂直堆叠（video → sensor → quickjumps → timeline → counts）。 */}
      <main className="flex-1 overflow-hidden px-3 py-3">
        <div className="flex h-full flex-col gap-2 md:grid md:grid-cols-[1fr_minmax(420px,35%)] md:gap-4 md:overflow-hidden">

          {/* 左列：camera + sensor。mobile=auto 高（shrink-0），md+ 是 grid item 撑满 */}
          <div className="flex shrink-0 flex-col gap-3 md:min-h-0 md:overflow-hidden">
            <div className="min-h-0 md:flex-1">
              <VideoPanel
                ref={videoRef}
                current={current}
                date={date}
                realTs={realTs}
                onTimeUpdate={setRealTs}
                onEnded={() => playSeg(curIdx + 1)}
              />
            </div>

            {/* 当前传感器摘要：4 个独立 tile 各占 1/4 宽。当前时刻 ±30s 内没记录时
                显示提示替换 grid（nearestSensor 内部已按 maxGap=30 过滤）。 */}
            {current && (
              currentSensor ? (
                <div className="grid grid-cols-4 gap-2">
                  <SensorTile icon="💨"
                    value={currentSensor.breath_rate ?? "—"}
                    unit={currentSensor.breath_rate != null ? T.unitBpm : ""} />
                  <SensorTile icon="🌡️"
                    value={currentSensor.temperature != null ? currentSensor.temperature.toFixed(1) : "—"}
                    unit={currentSensor.temperature != null ? "°C" : ""} />
                  <SensorTile icon="🛏️"
                    value={currentSensor.posture
                      ? ((T.postures)[currentSensor.posture as keyof typeof T.postures] ?? currentSensor.posture)
                      : "—"} />
                  <SensorTile icon="🔋"
                    value={currentSensor.battery ?? "—"}
                    unit={currentSensor.battery != null ? "%" : ""} />
                </div>
              ) : (
                <div className="rounded-md border border-dashed border-border/60 bg-card/30 px-3 py-3 text-center text-xs text-muted-foreground">
                  {T.pbNoSensorAtTime}
                </div>
              )
            )}
          </div>

          {/* 右列：QuickJumps（固定）+ Timeline (flex-1) + counts/errors。mobile=flex-1 吃剩余空间 */}
          <div className="flex min-h-0 flex-1 flex-col gap-3 md:overflow-hidden">
            <QuickJumps segments={segments} curIdx={curIdx} realTs={realTs}
                        onSegClick={playSeg} onScrubTo={scrubTo} />

            {/* Timeline + label + counts —— 整块 flex-1，Timeline 自己 h-full 撑满 */}
            <div className="flex min-h-0 flex-1 flex-col gap-1">
              <div className="shrink-0 text-xs text-muted-foreground">{T.pbTimelineLabel}</div>
              <div className="min-h-0 flex-1">
                <Timeline date={date} segments={segments} events={events}
                          realTs={realTs} curIdx={curIdx}
                          onSegClick={playSeg} onScrubTo={scrubTo} />
              </div>
              <div className="flex shrink-0 gap-3 text-xs text-muted-foreground">
                <span>{segments.length}{T.pbCounterSegs}</span>
                <span>{events.length}{T.pbCounterEvts}</span>
              </div>
            </div>

            {/* 当日无录像 / 出错提示 */}
            {date && segsQ.isSuccess && segments.length === 0 && (
              <div className="shrink-0 rounded-md border border-border/40 bg-card/40 px-3 py-2 text-center text-sm text-muted-foreground">
                {T.pbNoSegments}
              </div>
            )}
            {(segsQ.isError || sensorsQ.isError || eventsQ.isError) && (
              <div className="shrink-0 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {T.pbLoadFail}
              </div>
            )}
          </div>

        </div>
      </main>
    </div>
  );
}

// 单个传感器 tile：emoji 顶 / 数值中 / 单位底；高度由 padding 决定，跟同行其他 tile 等高。
function SensorTile({ icon, value, unit }: {
  icon: string; value: React.ReactNode; unit?: string;
}) {
  return (
    <div className="flex min-w-0 flex-col items-center justify-center gap-0.5 rounded-md border border-border/40 bg-card/40 px-2 py-3">
      <span className="text-2xl leading-none">{icon}</span>
      <span className="truncate text-lg font-semibold tabular-nums leading-tight text-foreground">{value}</span>
      {unit && (
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{unit}</span>
      )}
    </div>
  );
}
