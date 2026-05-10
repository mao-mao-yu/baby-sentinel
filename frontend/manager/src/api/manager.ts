import type { StatusResponse, UpdateInfo } from "@/types/manager";

async function http<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  // 后端约定：所有业务返回都是 JSON 且形如 {ok: bool, ...}。失败也带 body
  // （如 doUpdate / blePair 的 500 里有 {ok:false, step, log}）。所以这里不
  // 再用 r.ok 直接抛——把 JSON 解出来由调用方检查 .ok 自己决定怎么 UI 展示。
  // 仅在 body 不是 JSON / fetch 本身失败时才抛错。
  const text = await r.text();
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(`${method} ${path} → ${r.status}: ${text.slice(0, 200) || "(empty)"}`);
  }
}

export const api = {
  status:       ()                          => http<StatusResponse>("GET",  "/api/manager/status"),
  start:        (svc: string)               => http<{ ok: boolean }>("POST", `/api/manager/${svc}/start`),
  stop:         (svc: string)               => http<{ ok: boolean }>("POST", `/api/manager/${svc}/stop`),
  restart:      (svc: string)               => http<{ ok: boolean }>("POST", `/api/manager/${svc}/restart`),
  getConfig:    ()                          => http<{ ok: boolean; config: Record<string, unknown> }>("GET", "/api/manager/config"),
  saveConfig:   (patch: Record<string, unknown>) => http<{ ok: boolean; error?: string }>("POST", "/api/manager/config", { patch }),
  checkUpdate:  (svc: string)               => http<UpdateInfo>("GET",  `/api/manager/${svc}/check_update`),
  doUpdate:     (svc: string)               => http<{ ok: boolean; step?: string; log?: string; error?: string }>("POST", `/api/manager/${svc}/update`),
  blePair:      ()                          => http<{ ok: boolean; log?: string; step?: string; error?: string }>("POST", "/api/manager/ble/pair"),
};
