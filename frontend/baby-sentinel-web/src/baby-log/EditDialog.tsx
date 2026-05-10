// 根据 entry.type 派发到对应的 picker 进入编辑模式。
// 各 picker 的 edit prop 触发 PUT /api/log/entry/{ts}，extraFooter 里的 DeleteBtn 触发 DELETE。
//
// 简单类型（sleep / bath / diaper-wet）走 SimplePicker，可改时间也可删除——
// 旧版编辑弹窗 buildEditFields 也是这一套：保留原 entry 字段，只让用户调时间。

import {
  AmountPicker, BreastPicker, NumberPicker, PoopPicker, SimplePicker,
} from "@/baby-log/pickers";
import { useT } from "@/i18n";
import type { LogEntry } from "@/baby-log/types";

interface Props {
  entry:   LogEntry | null;
  onClose: () => void;
}

export function EditDialog({ entry, onClose }: Props) {
  const T = useT();
  const open = entry !== null;

  // entry === null：所有 picker 都关着，渲染一组关闭态作占位（避免 conditional render 引发 hook 数变化）
  if (!entry) {
    return (
      <>
        <AmountPicker open={false} onClose={() => {}} type="formula" />
        <BreastPicker open={false} onClose={() => {}} />
        <PoopPicker   open={false} onClose={() => {}} />
        <NumberPicker open={false} onClose={() => {}} type="temperature" />
        <SimplePicker open={false} onClose={() => {}} title="" buildPayload={() => ({} as never)} />
      </>
    );
  }
  const wrap = { ts: entry.ts, entry };

  switch (entry.type) {
    case "formula":
    case "feed":
      return <AmountPicker open={open} onClose={onClose} type="formula" edit={wrap} />;
    case "bottle_milk":
      return <AmountPicker open={open} onClose={onClose} type="bottle_milk" edit={wrap} />;
    case "pump":
      return <AmountPicker open={open} onClose={onClose} type="pump" edit={wrap} />;
    case "breastfeed":
      return <BreastPicker open={open} onClose={onClose} edit={wrap} />;
    case "diaper": {
      const kind = (entry as { kind?: string }).kind;
      if (kind === "dirty") {
        return <PoopPicker open={open} onClose={onClose} edit={wrap} />;
      }
      // wet：只可改时间 / 删除
      return <SimplePicker open={open} onClose={onClose}
        title={T.entryWet}
        buildPayload={(time) => ({ type: "diaper", kind: "wet", time } as never)}
        edit={wrap} />;
    }
    case "temperature":
    case "height":
    case "weight":
      return <NumberPicker open={open} onClose={onClose} type={entry.type} edit={wrap} />;
    case "sleep": {
      // sleep-start / sleep-end 都用 SimplePicker 改时间。end 保留原 action 不动；
      // duration_str 由后端 update_entry 自己重算（如果它会的话），UI 不显式管。
      const action = (entry as { action?: string }).action ?? "start";
      const label = action === "end" ? T.entryWake : T.entrySleep;
      return <SimplePicker open={open} onClose={onClose}
        title={label}
        buildPayload={(time) => ({ type: "sleep", action, time } as never)}
        edit={wrap} />;
    }
    case "bath":
      return <SimplePicker open={open} onClose={onClose}
        title={T.entryBath}
        buildPayload={(time) => ({ type: "bath", time } as never)}
        edit={wrap} />;
    default:
      // 兜底——没认出的 type，给个最小 picker（只能改时间）
      return <SimplePicker open={open} onClose={onClose}
        title={String((entry as { type?: string }).type ?? "?")}
        buildPayload={(time) => ({ ...(entry as object), time } as never)}
        edit={wrap} />;
  }
}
