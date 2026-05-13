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

export type MediaType = "movie" | "series";
export type SeriesStatus = "continuing" | "ended" | "unknown";

export interface MediaItem {
  jellyfin_id: string;
  media_type: MediaType;
  name: string;
  tmdb_id: string | null;
  tvdb_id: string | null;
  imdb_id: string | null;
  radarr_id: number | null;
  sonarr_id: number | null;
  date_added: string | null;
  file_path: string | null;
  file_size_bytes: number | null;
  series_status: SeriesStatus | null;
  last_played_at: string | null;
  last_played_by: string | null;
  total_play_count: number;
  last_synced_at: string;
}

export interface SyncSummary {
  success: boolean;
  duration_seconds: number;
  items_total: number;
  movies: number;
  series: number;
  items_matched_radarr: number;
  items_matched_sonarr: number;
  error_message: string;
}

export interface SyncRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  success: boolean;
  items_total: number;
  items_matched_radarr: number;
  items_matched_sonarr: number;
  error_message: string;
}

export interface CleanupRule {
  enabled: boolean;
  movie_age_days: number;
  movie_unwatched_days: number;
  series_age_days: number;
  series_unwatched_days: number;
  protect_continuing_series: boolean;
  grace_period_days: number;
  dry_run: boolean;
  schedule_enabled: boolean;
  schedule_hour: number;
  updated_at: string;
}

export type CleanupRuleUpdate = Partial<Omit<CleanupRule, "updated_at">>;

export interface ScanCandidate {
  jellyfin_id: string;
  media_type: MediaType;
  name: string;
  file_size_bytes: number | null;
  date_added: string | null;
  last_played_at: string | null;
  last_played_by: string | null;
  radarr_id: number | null;
  sonarr_id: number | null;
  series_status: SeriesStatus | null;
  reasons: string[];
  deletable: boolean;
  deletable_blocker: string | null;
}

export interface ScanPreview {
  rule_enabled: boolean;
  total_items_evaluated: number;
  candidates: ScanCandidate[];
  skipped_protected: number;
  skipped_continuing_series: number;
  candidates_total_size_bytes: number;
  deletable_total_size_bytes: number;
}

export interface ProtectedItem {
  jellyfin_id: string;
  reason: string;
  created_at: string;
}

export interface PendingItem {
  jellyfin_id: string;
  media_type: MediaType;
  name: string;
  file_size_bytes: number | null;
  radarr_id: number | null;
  sonarr_id: number | null;
  tmdb_id: string | null;
  tvdb_id: string | null;
  marked_at: string;
  scheduled_delete_at: string;
  reasons: string[];
}

export interface ActionLog {
  id: number;
  timestamp: string;
  action: string;
  jellyfin_id: string;
  name: string;
  details: string;
  success: boolean;
  error_message: string;
}

export interface MarkPassResult {
  success: boolean;
  duration_seconds: number;
  rule_enabled: boolean;
  candidates_total: number;
  newly_marked: number;
  unmarked_no_longer_matching: number;
  items_in_collection_after: number;
  collection_id: string | null;
  error_message: string;
}

export interface DeletePassResult {
  success: boolean;
  duration_seconds: number;
  dry_run: boolean;
  candidates_for_deletion: number;
  deleted_count: number;
  failed_count: number;
  errors: string[];
}

export interface FullCycleResult {
  success: boolean;
  duration_seconds: number;
  sync: SyncSummary | null;
  mark_pass: MarkPassResult | null;
  delete_pass: DeletePassResult | null;
  error_message: string;
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

  listLibrary: () => request<MediaItem[]>("/library/items"),
  syncLibrary: () => request<SyncSummary>("/library/sync", { method: "POST" }),
  lastSync: () => request<SyncRun | null>("/library/sync/last"),

  getRule: () => request<CleanupRule>("/rule"),
  updateRule: (payload: CleanupRuleUpdate) =>
    request<CleanupRule>("/rule", { method: "PUT", body: JSON.stringify(payload) }),
  scanPreview: () => request<ScanPreview>("/scan/preview", { method: "POST" }),

  listProtections: () => request<ProtectedItem[]>("/protections"),
  addProtection: (jellyfinId: string, reason = "") =>
    request<ProtectedItem>(`/protections/${jellyfinId}`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  removeProtection: async (jellyfinId: string): Promise<void> => {
    const res = await fetch(`/api/protections/${jellyfinId}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
  },

  runMarkPass: () => request<MarkPassResult>("/cleanup/mark-pass", { method: "POST" }),
  runDeletePass: () => request<DeletePassResult>("/cleanup/delete-pass", { method: "POST" }),
  runFullCycle: () => request<FullCycleResult>("/cleanup/full-cycle", { method: "POST" }),
  deleteNow: (jellyfinId: string) =>
    request<DeletePassResult>(`/cleanup/pending/${jellyfinId}/delete-now`, { method: "POST" }),
  listPending: () => request<PendingItem[]>("/cleanup/pending"),
  restorePending: async (jellyfinId: string): Promise<void> => {
    const res = await fetch(`/api/cleanup/pending/${jellyfinId}/restore`, { method: "POST" });
    if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`);
  },
  actionLog: (limit = 200) => request<ActionLog[]>(`/cleanup/log?limit=${limit}`),
};
