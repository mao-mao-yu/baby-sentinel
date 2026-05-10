// 视频播放区 — 原生 <video> + 顶部时间码 + 底部传感器淡入条 + 中央占位提示。
// 时间同步：parent 通过 onTimeUpdate(realTs) 拿到当前 ts；本组件不直接调 sensor 查询，
// 让 parent 把 nearestSensor() 结果以 currentSensor prop 喂回来，UI 渲染。

import { forwardRef } from "react";
import type { Segment } from "@/playback/types";
import { fmtTs } from "@/playback/utils";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

interface Props {
  current:        Segment | null;     // 当前播放的段；null 显示占位
  date:           string;
  realTs:         number;             // 当前帧实际 unix sec（已含段内偏移）
  onTimeUpdate:   (realTs: number) => void;
  onEnded:        () => void;
}

export const VideoPanel = forwardRef<HTMLVideoElement, Props>(function VideoPanel(
  { current, date, realTs, onTimeUpdate, onEnded }, ref,
) {
  const T = useT();

  const handleTime = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    if (!current) return;
    onTimeUpdate(current.ts + e.currentTarget.currentTime);
  };

  return (
    // mobile (<md): aspect-video 保 16:9，跟外层 main 一起竖向布局
    // md+: aspect-auto + h-full，吃掉左列 flex-1 的剩余高度；视频内 object-contain 自适应黑边
    <div className="relative mx-auto aspect-video w-full overflow-hidden rounded-md bg-black md:aspect-auto md:h-full">
      <video
        ref={ref}
        controls
        playsInline
        autoPlay
        muted
        src={current?.url}
        onTimeUpdate={handleTime}
        onEnded={onEnded}
        className={cn("absolute inset-0 h-full w-full object-contain",
                      current ? "opacity-100" : "opacity-0")}
      />

      {/* 占位 */}
      {!current && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 text-center text-muted-foreground">
          <div className="text-4xl">📹</div>
          <p className="text-sm">{T.pbSelectSegment}</p>
        </div>
      )}

      {/* 右上时间码 */}
      {current && (
        <div className="absolute right-2 top-2 rounded-md bg-black/55 px-2 py-1 font-mono text-xs text-white">
          {date} {fmtTs(realTs)}
        </div>
      )}
      {/* 传感器信息不在视频上叠层（避免遮挡画面/控制条），由 Page 在视频下方渲染独立条 */}
    </div>
  );
});
