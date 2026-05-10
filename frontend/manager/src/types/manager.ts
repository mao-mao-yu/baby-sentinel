// Shape of /api/manager/status response — mirrors manager.py:670-685
export type ServiceStatus = "running" | "stopped" | "crashed";

export interface ServiceState {
  status: ServiceStatus;
  returncode: number | null;
  pid: number | null;
  started_at: string | null;   // "HH:MM:SS"
  logs: string[];               // tail (last 80)
  name: string;
  icon: string;
  desc: string;
  remote: boolean;
  git: boolean;
  pairable: boolean;
}

export type StatusResponse = Record<string, ServiceState>;

export interface UpdateInfo {
  ok: boolean;
  behind?: number;
  update_available?: boolean;
  latest_commit?: string;
  error?: string;
}
