// 设备告警阻塞弹窗 — 跟旧 index.html showAlertDialog / hideAlertDialog 协议对齐：
//
//  1. WS `alert_active` 帧到达 → useAlertActive() 返回非空 → Dialog open
//  2. 用户点关闭 → POST /api/alert/dismiss { alert_id }
//     按钮立刻禁用 + 显示"发送中"，防连点
//  3. server.py 收到 dismiss → 通知 Pi 等待中的 POST 返回 ack=true
//                          → 广播 `alert_dismissed` 帧
//  4. 全部 client 的 WsProvider 收到 alert_dismissed → 比对 alert_id → 清 alertActive
//     本组件 active 变 null → Dialog 自动关
//
// 关键：UI 不主动 hide，等 WS 同步广播——多设备打开同一个告警时，任意一台
// 点关都会让其他几台同步关掉。本机网络异常时 fetch 失败也不本地 hide
// （server.py 那边有 1h sanity timeout 兜底，正常情况不会用上）。

import { useEffect, useState } from "react";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useAlertActive } from "@/api/ws";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";

export function AlertDialog() {
  const T = useT();
  const active = useAlertActive();
  const [sending, setSending] = useState(false);

  // active 翻空（被 dismiss）→ 复位 sending 状态，下次再开弹窗按钮回到可点
  useEffect(() => {
    if (!active) setSending(false);
  }, [active]);

  async function dismiss() {
    if (!active || sending) return;
    setSending(true);
    try {
      await fetch("/api/alert/dismiss", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alert_id: active.alert_id }),
      });
      // 不主动 hide — 等 WS alert_dismissed 帧到达才关
    } catch {
      // 网络挂了：UI 卡在"发送中"会让用户困惑；放回可点状态让用户重试
      setSending(false);
    }
  }

  const tone = active?.level ?? "warning";
  const toneRing = {
    danger:  "border-destructive/60 bg-destructive/10",
    warning: "border-amber-500/60 bg-amber-500/10",
    info:    "border-blue-500/60 bg-blue-500/10",
  }[tone] ?? "border-amber-500/60 bg-amber-500/10";

  return (
    <Dialog open={!!active}>
      <DialogContent
        className="max-w-md"
        // 阻塞模式：不允许 ESC / 点遮罩关；只能走 dismiss 按钮 → 触发 Pi 那边停 LED
        onEscapeKeyDown={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle className="text-destructive">{T.alertDlgTitle}</DialogTitle>
        </DialogHeader>

        <div className={cn("rounded-md border px-3 py-3 text-center", toneRing)}>
          <div className="text-base font-semibold leading-snug whitespace-pre-line">
            {active?.message ?? ""}
          </div>
          {active?.timestamp && (
            <div className="mt-1 font-mono text-xs text-muted-foreground">
              {active.timestamp}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="destructive" disabled={sending} onClick={dismiss} className="min-w-24">
            {sending ? T.alertDlgSending : T.alertDlgClose}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
