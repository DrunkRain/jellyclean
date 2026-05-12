export type ServiceName = "jellyfin" | "radarr" | "sonarr" | "jellyseerr";
export type TestStatus = "unknown" | "success" | "failure";

export interface ServiceConfig {
  service: ServiceName;
  base_url: string;
  api_key_masked: string;
  has_api_key: boolean;
  enabled: boolean;
  last_test_status: TestStatus;
  last_test_message: string;
  last_tested_at: string | null;
}

export interface ServiceConfigUpdate {
  base_url?: string;
  api_key?: string;
  enabled?: boolean;
}

export interface ConnectionTestResult {
  success: boolean;
  message: string;
  details: Record<string, unknown>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listSettings: () => request<ServiceConfig[]>("/settings"),
  getSetting: (service: ServiceName) => request<ServiceConfig>(`/settings/${service}`),
  updateSetting: (service: ServiceName, payload: ServiceConfigUpdate) =>
    request<ServiceConfig>(`/settings/${service}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  testSetting: (service: ServiceName) =>
    request<ConnectionTestResult>(`/settings/${service}/test`, { method: "POST" }),
};
