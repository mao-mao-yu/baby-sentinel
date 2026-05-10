// 快速跳转按钮：⏮ 最早 / ⬅ 上段 / 下段 ➡ / 最新 ⏭ + ±6h ±1h
// 行为对齐旧 playback.html。

import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import type { Segment } from "@/playback/types";

interface Props {
  segments:  Segment[];
  curIdx:    number;
  realTs:    number;
  onSegClick: (idx: number) => void;
  onScrubTo:  (ts: number) => void;
}

export function QuickJumps({ segments, curIdx, realTs, onSegClick, onScrubTo }: Props) {
  const T = useT();
  const atStart = curIdx <= 0;
  const atEnd   = curIdx >= segments.length - 1 || segments.length === 0;

  return (
    // 4 列 grid：第一行段跳转 4 颗，第二行 ±h 跳转 4 颗，每颗各占 1/4 宽。
    <div className="grid grid-cols-4 gap-1.5">
      <Button size="sm" variant="outline" disabled={atStart} onClick={() => onSegClick(0)}>
        {T.pbQjFirst}
      </Button>
      <Button size="sm" variant="outline" disabled={atStart} onClick={() => onSegClick(curIdx - 1)}>
        {T.pbQjPrev}
      </Button>
      <Button size="sm" variant="outline" disabled={atEnd} onClick={() => onSegClick(curIdx + 1)}>
        {T.pbQjNext}
      </Button>
      <Button size="sm" variant="outline" disabled={atEnd} onClick={() => onSegClick(segments.length - 1)}>
        {T.pbQjLast}
      </Button>
      <Button size="sm" variant="outline" onClick={() => onScrubTo(realTs - 6 * 3600)}>−6h</Button>
      <Button size="sm" variant="outline" onClick={() => onScrubTo(realTs - 1 * 3600)}>−1h</Button>
      <Button size="sm" variant="outline" onClick={() => onScrubTo(realTs + 1 * 3600)}>+1h</Button>
      <Button size="sm" variant="outline" onClick={() => onScrubTo(realTs + 6 * 3600)}>+6h</Button>
    </div>
  );
}
