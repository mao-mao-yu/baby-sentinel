// /api/log/* 客户端。后端在 backend/services/web/server.py:201-248 + baby_log.py。
// stats 由 server.py POST/PUT/DELETE 后通过 WS broadcast 推 → useBabyStats() 自动更新，
// 这里 mutation 仅触发后端 + 让 today list query invalidate 重拉。

import type { LogEntry } from "@/baby-log/types";

async function http<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(`${method} ${path} → ${r.status}: ${text.slice(0, 200) || "(empty)"}`);
  }
}

export interface AddResponse    { ok: boolean; entry?: LogEntry; stats?: unknown; error?: string }
export interface UpdateResponse { ok: boolean; entry?: LogEntry; stats?: unknown; error?: string }
export interface DeleteResponse { ok: boolean; stats?: unknown; error?: string }

export const logApi = {
  today:        ()                                  => http<LogEntry[]>("GET",  "/api/log/today"),
  byDate:       (dateStr: string)                   => http<LogEntry[]>("GET",  `/api/log/date/${dateStr}`),
  add:          (entry: Partial<LogEntry>)          => http<AddResponse>("POST", "/api/log", entry),
  update:       (ts: number, updates: Partial<LogEntry>) => http<UpdateResponse>("PUT", `/api/log/entry/${ts}`, updates),
  remove:       (ts: number)                        => http<DeleteResponse>("DELETE", `/api/log/entry/${ts}`),
};

/** "HH:MM" of current local time, the default for new entries. */
export function nowTime(): string {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
