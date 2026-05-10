import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/api/manager";
import { ConfigDialog } from "@/components/ConfigDialog";
import { PairDialog } from "@/components/PairDialog";
import { CONFIG_SCHEMA } from "@/config-schema";
import { useT } from "@/i18n";
import type { ServiceState } from "@/types/manager";
import { cn } from "@/lib/utils";

const STATUS_VARIANT: Record<ServiceState["status"],
  "default" | "secondary" | "destructive" | "outline"> = {
  running: "default",
  stopped: "secondary",
  crashed: "destructive",
};

interface Props {
  svc: string;
  state: ServiceState;
}

export function ServiceCard({ svc, state }: Props) {
  const T = useT();
  const STATUS_LABEL: Record<ServiceState["status"], string> = {
    running: T.mgrStatusRunning,
    stopped: T.mgrStatusStopped,
    crashed: T.mgrStatusCrashed,
  };
  const qc = useQueryClient();
  const refetch = () => qc.invalidateQueries({ queryKey: ["status"] });

  const [cfgOpen, setCfgOpen]   = useState(false);
  const [pairOpen, setPairOpen] = useState(false);
  const [failLogOpen, setFailLogOpen] = useState(false);
  const hasSchema = !!CONFIG_SCHEMA[svc];

  // 日志区 auto-scroll：用户在底部 → 新行自动跟随；用户主动滚上去看历史
  // → 暂停自动滚动直到他重新滚回底部。stickToBottom 用 ref 不用 state，
  // 不参与 React 渲染。
  const logRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  useEffect(() => {
    const el = logRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [state.logs.length]);

  // Mutations: optimistic refetch on settle
  const startMu   = useMutation({ mutationFn: () => api.start(svc),   onSettled: refetch });
  const stopMu    = useMutation({ mutationFn: () => api.stop(svc),    onSettled: refetch });
  const restartMu = useMutation({ mutationFn: () => api.restart(svc), onSettled: refetch });

  // git 服务的"检查更新 / 更新"流程：check 是只读的快速调用，update 会跑
  // git pull + pip install + 重启 service。失败时 backend 仍返 JSON body
  // （api.ts 已经处理了 5xx body 解析），靠 r.ok 区分成败。
  const checkMu = useMutation({
    mutationFn: () => api.checkUpdate(svc),
  });
  const updateMu = useMutation({
    mutationFn: () => api.doUpdate(svc),
    onSuccess: (r) => {
      if (r.ok) {
        // service 已被 backend 重启 → 让 status query 立即重拉。
        // 同时清掉 checkMu 的"有更新"红点，避免显示陈旧信息。
        refetch();
        checkMu.reset();
      }
    },
  });

  const isRunning = state.status === "running";
  const isStopped = state.status === "stopped";

  // 渲染 update 状态行用：
  const updInfo  = checkMu.data;
  const updFail  = updateMu.data && !updateMu.data.ok ? updateMu.data : null;
  const showUpdateRow = !!state.git && (
    checkMu.isPending || checkMu.isError || !!updInfo ||
    updateMu.isPending || !!updFail
  );

  return (
    <Card className="flex flex-col gap-0 overflow-hidden py-0">
      <CardHeader className="flex flex-row items-center gap-3 border-b px-3 py-3">
        <span className="text-2xl leading-none">{state.icon}</span>
        <div className="flex flex-1 flex-col gap-0.5 min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate font-semibold">{state.name}</span>
            <Badge variant={STATUS_VARIANT[state.status]}
                   className={cn("h-5 text-[10px] uppercase tracking-wide",
                                 isRunning && "bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/15")}>
              {STATUS_LABEL[state.status]}
            </Badge>
            {state.pid != null && (
              <span className="text-xs text-muted-foreground">pid {state.pid}</span>
            )}
          </div>
          <span className="truncate text-xs text-muted-foreground">{state.desc}</span>
        </div>
      </CardHeader>

      {/* 按钮行：单行不换 + 横向滚动溢出。手机滑动自然，桌面通常一屏装得下。
          shrink-0 让按钮保持自身宽度不被压缩；no-scrollbar 隐藏视觉滚动条。 */}
      <CardContent className="flex flex-nowrap gap-1.5 overflow-x-auto no-scrollbar border-b px-3 py-2">
        <Button size="sm" variant="outline" className="shrink-0"
                disabled={isRunning || startMu.isPending}
                onClick={() => startMu.mutate()}>
          {T.mgrBtnStart}
        </Button>
        <Button size="sm" variant="outline" className="shrink-0"
                disabled={isStopped || stopMu.isPending}
                onClick={() => stopMu.mutate()}>
          {T.mgrBtnStop}
        </Button>
        <Button size="sm" variant="outline" className="shrink-0"
                disabled={restartMu.isPending}
                onClick={() => restartMu.mutate()}>
          {T.mgrBtnRestart}
        </Button>
        <Button size="sm" variant="outline" className="shrink-0"
                disabled={!hasSchema}
                title={hasSchema ? undefined : T.cfgNoSchema}
                onClick={() => setCfgOpen(true)}>
          {T.mgrBtnConfig}
        </Button>
        {state.pairable && (
          <Button size="sm" variant="outline" className="shrink-0"
                  onClick={() => setPairOpen(true)}>
            {T.mgrBtnPair}
          </Button>
        )}
        {state.git && (
          <>
            <Button size="sm" variant="outline" className="shrink-0"
                    disabled={checkMu.isPending || updateMu.isPending}
                    onClick={() => checkMu.mutate()}>
              {checkMu.isPending && <Loader2 className="size-3 animate-spin mr-1" />}
              {T.mgrBtnCheck}
            </Button>
            <Button size="sm" variant="outline" className="shrink-0"
                    disabled={!updInfo?.update_available || updateMu.isPending}
                    onClick={() => {
                      if (window.confirm(T.mgrUpdateConfirm)) updateMu.mutate();
                    }}>
              {updateMu.isPending && <Loader2 className="size-3 animate-spin mr-1" />}
              {T.mgrBtnUpdate}
            </Button>
          </>
        )}
      </CardContent>

      {showUpdateRow && (
        <div className="border-b px-3 py-2 text-xs">
          {checkMu.isPending && (
            <span className="text-muted-foreground">{T.mgrCheckRunning}</span>
          )}
          {checkMu.isError && (
            <span className="text-destructive">
              {T.mgrUpdateFail}: {String(checkMu.error)}
            </span>
          )}
          {updInfo && !updInfo.ok && (
            <span className="text-destructive">
              {T.mgrUpdateFail}: {updInfo.error ?? "?"}
            </span>
          )}
          {updInfo?.ok && !updInfo.update_available && !updateMu.isPending && !updFail && (
            <span className="flex items-center gap-1 text-emerald-400">
              <CheckCircle2 className="size-3" />{T.mgrUpdateNone}
            </span>
          )}
          {updInfo?.ok && updInfo.update_available && !updateMu.isPending && !updFail && (
            <span className="text-amber-400">
              ↑ {updInfo.behind} new — <span className="font-mono">{updInfo.latest_commit}</span>
            </span>
          )}
          {updateMu.isPending && (
            <span className="flex items-center gap-1 text-amber-400">
              <Loader2 className="size-3 animate-spin" />{T.mgrUpdateRunning}
            </span>
          )}
          {updFail && !updateMu.isPending && (
            <span className="flex items-center gap-2 text-destructive">
              <XCircle className="size-3" />
              {T.mgrUpdateFail}{updFail.step ? ` (step=${updFail.step})` : ""}
              {updFail.log && (
                <Button variant="ghost" size="sm" className="h-5 px-2 text-xs"
                        onClick={() => setFailLogOpen(true)}>
                  {T.mgrViewLog}
                </Button>
              )}
            </span>
          )}
        </div>
      )}

      <div ref={logRef}
           onScroll={(e) => {
             const el = e.currentTarget;
             // 30px 容差：滚到底附近就视为"贴底"，新行继续自动跟。
             stickToBottom.current = el.scrollTop + el.clientHeight >= el.scrollHeight - 30;
           }}
           className="h-44 overflow-y-auto bg-zinc-950/60 font-mono text-[11px] leading-snug">
        <div className="px-3 py-2">
          {state.logs.length === 0
            ? <span className="text-muted-foreground">— no output —</span>
            : state.logs.map((line, i) => (
                <div key={i} className="whitespace-pre-wrap text-zinc-300">{line}</div>
              ))}
        </div>
      </div>

      <ConfigDialog svc={svc} open={cfgOpen} onOpenChange={setCfgOpen}
                    onSavedRestart={() => restartMu.mutate()} />
      {state.pairable && (
        <PairDialog open={pairOpen} onOpenChange={setPairOpen} />
      )}

      <Dialog open={failLogOpen} onOpenChange={setFailLogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {T.mgrUpdateFail} — {svc}{updFail?.step ? ` / ${updFail.step}` : ""}
            </DialogTitle>
          </DialogHeader>
          <ScrollArea className="h-72 rounded-md border border-border/40 bg-zinc-950/60">
            <pre className="p-3 font-mono text-[11px] leading-snug whitespace-pre-wrap text-zinc-300">
              {updFail?.log ?? "(no log)"}
            </pre>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
