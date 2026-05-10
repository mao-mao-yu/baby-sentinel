// viewingDate 当日的 4 项总结：瓶喂次数+量 / 母乳左右分钟 / 尿布湿便次数 / 睡眠时长
// 视觉上 2×2 卡片网格 — 每张卡片用色调 + 图标快速辨识，数字粗体 tabular-nums，
// 空态用 "—" 浅灰避免大量"0"刺眼。

import { useQuery } from "@tanstack/react-query";
import { useT } from "@/i18n";
import { logApi } from "@/baby-log/api";
import { computeDateStats, formatHm } from "@/baby-log/stats";
import { useSysToday, useViewingDate } from "@/baby-log/scope";
import { cn } from "@/lib/utils";

export function DateStats() {
  const T = useT();
  const date = useViewingDate();
  const sysToday = useSysToday();
  const q = useQuery({ queryKey: ["log", date], queryFn: () => logApi.byDate(date) });
  const entries = q.data ?? [];

  const s = computeDateStats(entries, date, sysToday);
  const hasBottle = s.bottleCount > 0;
  const hasBreast = s.bfL > 0 || s.bfR > 0;
  const hasDiaper = s.wet > 0 || s.dirty > 0;
  const hasSleep  = s.sleepMs > 0;

  return (
    <div className="grid grid-cols-2 gap-1.5">
      <StatCard icon="🍼" tone="amber">
        {hasBottle ? (
          <>
            <Num>{s.bottleCount}</Num><Sub>{T.statTimes}</Sub>
            <Sep />
            <Num>{s.bottleMl}</Num><Sub>mL</Sub>
          </>
        ) : <Empty />}
      </StatCard>

      <StatCard icon="🤱" tone="rose">
        {hasBreast ? (
          <>
            <Sub>{T.sideLeft}</Sub><Num>{s.bfL}</Num>
            <Sep />
            <Sub>{T.sideRight}</Sub><Num>{s.bfR}</Num><Sub>m</Sub>
          </>
        ) : <Empty />}
      </StatCard>

      <StatCard icon="💧" tone="cyan">
        {hasDiaper ? (
          <>
            <Num>{s.wet}</Num>
            <Sub>{" / "}</Sub>
            💩<Num>{s.dirty}</Num>
          </>
        ) : <Empty />}
      </StatCard>

      <StatCard icon="😴" tone="violet">
        {hasSleep ? <Num>{formatHm(s.sleepMs, T)}</Num> : <Empty />}
      </StatCard>
    </div>
  );
}

// ── 子组件 ─────────────────────────────────────────────────────

type Tone = "amber" | "rose" | "cyan" | "violet";

const TONE_CLS: Record<Tone, string> = {
  amber:  "border-amber-500/30 bg-amber-500/5 text-amber-200",
  rose:   "border-pink-500/30 bg-pink-500/5 text-pink-200",
  cyan:   "border-cyan-500/30 bg-cyan-500/5 text-cyan-200",
  violet: "border-violet-500/30 bg-violet-500/5 text-violet-200",
};

function StatCard({ icon, tone, children }: {
  icon: string; tone: Tone; children: React.ReactNode;
}) {
  return (
    <div className={cn(
      "flex items-center gap-2 rounded-md border px-2.5 py-1.5",
      TONE_CLS[tone],
    )}>
      <span className="shrink-0 text-base leading-none">{icon}</span>
      <span className="flex flex-1 flex-wrap items-baseline gap-x-0.5 truncate text-xs">
        {children}
      </span>
    </div>
  );
}

function Num({ children }: { children: React.ReactNode }) {
  return <span className="font-semibold tabular-nums text-foreground">{children}</span>;
}

function Sub({ children }: { children: React.ReactNode }) {
  return <span className="ml-0.5 text-[10px] text-muted-foreground">{children}</span>;
}

function Sep() {
  return <span className="mx-1 text-muted-foreground/60">·</span>;
}

function Empty() {
  return <span className="text-muted-foreground/60">—</span>;
}
