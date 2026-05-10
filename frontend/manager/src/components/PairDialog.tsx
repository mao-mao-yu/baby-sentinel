import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/api/manager";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

interface Props {
  open:         boolean;
  onOpenChange: (open: boolean) => void;
}

export function PairDialog({ open, onOpenChange }: Props) {
  const T = useT();
  // 配对结果（成功或最近一次失败的 log tail）。dialog 关闭后保留，重新打开时
  // 还能看到上次结果；点"重新配对"时清空。
  const [result, setResult] = useState<
    | { ok: true;  log?: string }
    | { ok: false; log?: string; step?: string }
    | null
  >(null);

  const pairMu = useMutation({
    mutationFn: () => api.blePair(),
    onSuccess: (r) => {
      // /api/manager/ble/pair 即使 ok=false 也是 HTTP 500，会走 onError；
      // 但保险起见这里也 handle 一下 ok 字段。
      setResult(r.ok
        ? { ok: true,  log: r.log }
        : { ok: false, log: r.log, step: r.step });
    },
    onError: (e) => {
      // fetch 抛出（500 / 网络层错），尝试从 message 里抠点信息
      setResult({ ok: false, log: String(e) });
    },
  });

  const isRunning = pairMu.isPending;
  const canStart  = !isRunning;

  function start() {
    setResult(null);
    pairMu.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => {
      // 配对中不允许关，避免 backend 任务还在跑而前端以为没事了
      if (!isRunning) onOpenChange(v);
    }}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{T.pairTitle}</DialogTitle>
        </DialogHeader>

        {/* 操作步骤 */}
        <ol className="list-decimal pl-5 space-y-1 text-sm leading-relaxed">
          <li>{T.pairStep1}</li>
          <li>{T.pairStep2}</li>
          <li>{T.pairStep3}</li>
        </ol>

        {/* 状态 / 结果 */}
        {isRunning && (
          <div className="flex items-center gap-2 rounded-md border border-border/40 bg-card/40 px-3 py-2 text-sm">
            <Loader2 className="size-4 animate-spin" />
            <span>{T.pairWorking}</span>
          </div>
        )}

        {result && !isRunning && (
          <div className={cn(
            "rounded-md border px-3 py-2",
            result.ok
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              : "border-destructive/40 bg-destructive/10 text-destructive",
          )}>
            <div className="flex items-center gap-2 text-sm font-medium">
              {result.ok
                ? <><CheckCircle2 className="size-4" />{T.pairOk}</>
                : <><XCircle className="size-4" />{T.pairFail}{result.step ? ` (step=${result.step})` : ""}</>}
            </div>
          </div>
        )}

        {/* 日志 tail */}
        {result?.log && (
          <ScrollArea className="h-48 rounded-md border border-border/40 bg-zinc-950/60">
            <pre className="px-3 py-2 font-mono text-[11px] leading-snug whitespace-pre-wrap text-zinc-300">
              {result.log}
            </pre>
          </ScrollArea>
        )}

        <DialogFooter className="sm:justify-end">
          <Button variant="ghost" disabled={isRunning}
                  onClick={() => onOpenChange(false)}>
            {T.cfgCancel}
          </Button>
          <Button onClick={start} disabled={!canStart}>
            {result ? T.pairBtnAgain : T.pairBtnStart}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
