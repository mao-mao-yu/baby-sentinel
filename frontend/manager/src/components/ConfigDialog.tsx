import { Fragment, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input }  from "@/components/ui/input";
import { Label }  from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api } from "@/api/manager";
import {
  CONFIG_SCHEMA, FIELD_GROUPS, localized, type FieldDef,
} from "@/config-schema";
import { getPath } from "@/lib/path";
import { useLang, useT, type Lang } from "@/i18n";
import { cn } from "@/lib/utils";

interface Props {
  svc:          string;
  open:         boolean;
  onOpenChange: (open: boolean) => void;
  /** Service to restart after save. Pass `null` to skip the restart prompt
   *  entirely (e.g. for the global settings dialog where there's no single
   *  service that "owns" these fields). */
  onSavedRestart: ((svc: string) => void) | null;
  /** Override the dialog title. Default: `${T.cfgTitle} — ${svc}`. */
  titleOverride?: string;
}

export function ConfigDialog({
  svc, open, onOpenChange, onSavedRestart, titleOverride,
}: Props) {
  const T      = useT();
  const lang   = useLang();
  const fields = CONFIG_SCHEMA[svc];
  const qc     = useQueryClient();

  // Fetch current config only while dialog is open — invalidated on save.
  const cfgQ = useQuery({
    queryKey: ["config"],
    queryFn:  api.getConfig,
    enabled:  open && !!fields,
  });

  // Form state, keyed by dotted path. Hydrated from cfgQ.data when it lands.
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [msg, setMsg]   = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  useEffect(() => {
    if (!cfgQ.data?.config || !fields) return;
    const init: Record<string, unknown> = {};
    for (const f of fields) init[f.key] = getPath(cfgQ.data.config, f.key);
    setForm(init);
    setMsg(null);
  }, [cfgQ.data, fields]);

  const saveMu = useMutation({
    mutationFn: (patch: Record<string, unknown>) => api.saveConfig(patch),
    onSuccess: (r) => {
      if (!r.ok) {
        setMsg({ kind: "err", text: `${T.cfgSaveFail}: ${r.error ?? ""}` });
        return;
      }
      setMsg({ kind: "ok", text: T.cfgSaved });
      qc.invalidateQueries({ queryKey: ["config"] });
      // 全局设置 (onSavedRestart=null) 不属于任一 service，跳过重启提示——
      // 用户可以自己在卡片上 restart 影响到的服务。
      if (onSavedRestart) {
        const ok = window.confirm(T.cfgRestartHint.replace("{svc}", svc));
        if (ok) onSavedRestart(svc);
      }
    },
    onError: (e) => setMsg({ kind: "err", text: `${T.cfgSaveFail}: ${String(e)}` }),
  });

  if (!fields) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader><DialogTitle>{T.cfgTitle}</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">{T.cfgNoSchema}</p>
        </DialogContent>
      </Dialog>
    );
  }

  function submit() {
    saveMu.mutate(form);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-xl overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>{titleOverride ?? `${T.cfgTitle} — ${svc}`}</DialogTitle>
        </DialogHeader>

        {cfgQ.isLoading && <p className="text-sm text-muted-foreground">…</p>}
        {cfgQ.error && <p className="text-sm text-destructive">{T.cfgLoadFail}</p>}

        {cfgQ.data && (
          <div className="flex-1 overflow-y-auto pr-2 space-y-4">
            {fields.map((f, i) => {
              const prevGroup = i > 0 ? fields[i - 1].group : undefined;
              const showHeader = !!f.group && f.group !== prevGroup;
              return (
                <Fragment key={f.key}>
                  {showHeader && (
                    <h3 className={cn(
                      "text-xs font-semibold uppercase tracking-wider text-muted-foreground",
                      "border-b border-border/40 pb-1",
                      i > 0 && "mt-2",
                    )}>
                      {localized(FIELD_GROUPS[f.group!], lang)}
                    </h3>
                  )}
                  <FieldRow f={f} lang={lang}
                            value={form[f.key]}
                            onChange={(v) => setForm((s) => ({ ...s, [f.key]: v }))} />
                </Fragment>
              );
            })}
          </div>
        )}

        <DialogFooter className="flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-2">
          <span className={cn("text-xs",
                              msg?.kind === "ok"  && "text-emerald-400",
                              msg?.kind === "err" && "text-destructive")}>
            {msg?.text}
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)}>{T.cfgCancel}</Button>
            <Button onClick={submit} disabled={saveMu.isPending || !cfgQ.data}>
              {T.cfgSave}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Field renderers ───────────────────────────────────────────────────

function FieldRow({ f, lang, value, onChange }: {
  f: FieldDef;
  lang: Lang;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const id    = `cfg-${f.key.replace(/\./g, "_")}`;
  const label = localized(f.label, lang);
  const hint  = f.hint ? localized(f.hint, lang) : "";

  if (f.type === "bool") {
    return (
      <div className="flex items-center justify-between rounded-md border border-border/40 bg-card/40 px-3 py-2">
        <div className="flex flex-col">
          <Label htmlFor={id} className="text-sm">{label}</Label>
          {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
        </div>
        <Switch id={id} checked={!!value} onCheckedChange={onChange} />
      </div>
    );
  }

  if (f.type === "enum") {
    return (
      <div className="space-y-1.5">
        <Label htmlFor={id} className="text-sm">{label}</Label>
        <Select value={(value as string) ?? ""} onValueChange={onChange}>
          <SelectTrigger id={id}><SelectValue /></SelectTrigger>
          <SelectContent>
            {f.options.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {localized(o.label, lang)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
    );
  }

  if (f.type === "array_str") {
    const text = Array.isArray(value) ? (value as unknown[]).join("\n") : "";
    return (
      <div className="space-y-1.5">
        <Label htmlFor={id} className="text-sm">{label}</Label>
        <Textarea id={id} value={text} rows={3}
                  onChange={(e) => onChange(
                    e.target.value.split(/\r?\n/).map(s => s.trim()).filter(Boolean),
                  )} />
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
    );
  }

  // string / password / int / number
  const inputType = f.type === "password" ? "password"
                  : (f.type === "int" || f.type === "number") ? "number"
                  : "text";
  const step = f.type === "number" ? "any" : f.type === "int" ? "1" : undefined;
  const stringValue =
    value == null ? "" : (typeof value === "number" ? String(value) : String(value));

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-sm">{label}</Label>
      <Input id={id} type={inputType} step={step} value={stringValue}
             onChange={(e) => {
               const v = e.target.value;
               if (f.type === "int") {
                 if (v === "") return onChange(null);
                 const n = parseInt(v, 10);
                 return onChange(Number.isNaN(n) ? null : n);
               }
               if (f.type === "number") {
                 if (v === "") return onChange(null);
                 const n = parseFloat(v);
                 return onChange(Number.isNaN(n) ? null : n);
               }
               onChange(v);
             }} />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
