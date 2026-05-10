// 育儿日志快捷按钮 — 4 个 tab (喂奶/日常/健康/其他) 各组按钮。
// 行为对齐旧 index.html — 所有按钮点击都打开 picker（确认 + 时间），不再静默直加。

import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n";
import { useBabyStats } from "@/api/ws";
import {
  AmountPicker, BreastPicker, NumberPicker, PoopPicker, SimplePicker, WakePicker,
} from "@/baby-log/pickers";
import { cn } from "@/lib/utils";

type PickerKey =
  | null
  | { kind: "formula" | "bottle_milk" | "pump" }
  | { kind: "breast" }
  | { kind: "poop" }
  | { kind: "number"; type: "temperature" | "height" | "weight" }
  | { kind: "sleep_start" }
  | { kind: "wake" }
  | { kind: "wet" }
  | { kind: "bath" };

export function QuickButtons() {
  const T = useT();
  const stats = useBabyStats();
  const sleeping = !!(stats as { sleeping_since?: number | null } | null)?.sleeping_since;

  const [picker, setPicker] = useState<PickerKey>(null);
  const close = () => setPicker(null);

  return (
    <>
      <Tabs defaultValue="feed" className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="feed">{T.tabFeed}</TabsTrigger>
          <TabsTrigger value="daily">{T.tabDaily}</TabsTrigger>
          <TabsTrigger value="health">{T.tabHealth}</TabsTrigger>
          <TabsTrigger value="other">{T.tabOther}</TabsTrigger>
        </TabsList>

        <TabsContent value="feed" className="mt-2">
          <Row>
            <QBtn onClick={() => setPicker({ kind: "formula"     })}>{T.btnFormula}</QBtn>
            <QBtn onClick={() => setPicker({ kind: "breast"      })}>{T.btnBreast}</QBtn>
            <QBtn onClick={() => setPicker({ kind: "bottle_milk" })}>{T.btnBottle}</QBtn>
          </Row>
        </TabsContent>

        <TabsContent value="daily" className="mt-2">
          <Row>
            <QBtn disabled={sleeping}
                  onClick={() => setPicker({ kind: "sleep_start" })}>
              {T.btnSleep}
            </QBtn>
            <QBtn disabled={!sleeping}
                  onClick={() => setPicker({ kind: "wake" })}>
              {T.btnWake}
            </QBtn>
            <QBtn onClick={() => setPicker({ kind: "wet" })}>{T.btnWet}</QBtn>
            <QBtn onClick={() => setPicker({ kind: "poop" })}>{T.btnDirty}</QBtn>
          </Row>
        </TabsContent>

        <TabsContent value="health" className="mt-2">
          <Row>
            <QBtn onClick={() => setPicker({ kind: "number", type: "temperature" })}>{T.btnTemp}</QBtn>
            <QBtn onClick={() => setPicker({ kind: "number", type: "height" })}>{T.btnHeight}</QBtn>
            <QBtn onClick={() => setPicker({ kind: "number", type: "weight" })}>{T.btnWeight}</QBtn>
          </Row>
        </TabsContent>

        <TabsContent value="other" className="mt-2">
          <Row>
            <QBtn onClick={() => setPicker({ kind: "bath" })}>{T.btnBath}</QBtn>
            <QBtn onClick={() => setPicker({ kind: "pump" })}>{T.btnPump}</QBtn>
          </Row>
        </TabsContent>
      </Tabs>

      {/* Picker dispatch — 一次只开一个，由 picker.kind 决定哪个 dialog open */}
      <AmountPicker
        open={picker?.kind === "formula" || picker?.kind === "bottle_milk" || picker?.kind === "pump"}
        onClose={close}
        type={picker && (picker.kind === "formula" || picker.kind === "bottle_milk" || picker.kind === "pump")
              ? picker.kind : "formula"} />
      <BreastPicker open={picker?.kind === "breast"} onClose={close} />
      <PoopPicker   open={picker?.kind === "poop"}   onClose={close} />
      <NumberPicker open={picker?.kind === "number"} onClose={close}
                    type={picker?.kind === "number" ? picker.type : "temperature"} />

      {/* sleep-start / wet / bath：纯确认 picker，只填时间 */}
      <SimplePicker open={picker?.kind === "sleep_start"} onClose={close}
                    title={T.btnSleep}
                    buildPayload={(time) => ({ type: "sleep", action: "start", time } as never)} />
      <SimplePicker open={picker?.kind === "wet"} onClose={close}
                    title={T.btnWet}
                    buildPayload={(time) => ({ type: "diaper", kind: "wet", time } as never)} />
      <SimplePicker open={picker?.kind === "bath"} onClose={close}
                    title={T.btnBath}
                    buildPayload={(time) => ({ type: "bath", time } as never)} />

      {/* 起床：单独 picker 显示当前累计睡眠时长 */}
      <WakePicker open={picker?.kind === "wake"} onClose={close} />
    </>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-wrap gap-2">{children}</div>;
}

function QBtn({ children, onClick, disabled }: {
  children: React.ReactNode; onClick: () => void; disabled?: boolean;
}) {
  return (
    <Button variant="outline" size="sm"
            onClick={onClick} disabled={disabled}
            className={cn("h-9 flex-1 min-w-[5.5rem]")}>
      {children}
    </Button>
  );
}
