import { useEffect, useMemo, useState } from "react";
import { api, type MediaItem, type SyncSummary } from "../lib/api";
import { daysSince, formatBytes, formatRelative } from "../lib/format";

type SortKey = "name" | "date_added" | "last_played_at" | "file_size_bytes" | "media_type";
type SortDir = "asc" | "desc";
type TypeFilter = "all" | "movie" | "series";
type WatchedFilter = "all" | "never" | "30" | "90" | "365";

export default function Library() {
  const [items, setItems] = useState<MediaItem[] | null>(null);
  const [protectedIds, setProtectedIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [watchedFilter, setWatchedFilter] = useState<WatchedFilter>("all");
  const [unmatchedOnly, setUnmatchedOnly] = useState(false);
  const [protectedOnly, setProtectedOnly] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  useEffect(() => {
    Promise.all([api.listLibrary(), api.listProtections()])
      .then(([lib, prots]) => {
        setItems(lib);
        setProtectedIds(new Set(prots.map((p) => p.jellyfin_id)));
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const toggleProtection = async (jellyfinId: string) => {
    const next = new Set(protectedIds);
    try {
      if (protectedIds.has(jellyfinId)) {
        await api.removeProtection(jellyfinId);
        next.delete(jellyfinId);
      } else {
        await api.addProtection(jellyfinId, "Protégé via la bibliothèque");
        next.add(jellyfinId);
      }
      setProtectedIds(next);
    } catch (e) {
      setError(String(e));
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    setError(null);
    setSyncResult(null);
    try {
      const summary = await api.syncLibrary();
      setSyncResult(summary);
      if (!summary.success) {
        setError(summary.error_message || "Sync échouée");
      } else {
        const fresh = await api.listLibrary();
        setItems(fresh);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setSyncing(false);
    }
  };

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = search.trim().toLowerCase();

    let out = items.filter((it) => {
      if (typeFilter !== "all" && it.media_type !== typeFilter) return false;
      if (q && !it.name.toLowerCase().includes(q)) return false;

      if (watchedFilter === "never" && it.last_played_at !== null) return false;
      if (watchedFilter !== "all" && watchedFilter !== "never") {
        const threshold = parseInt(watchedFilter, 10);
        const d = daysSince(it.last_played_at);
        if (d === null) {
          // never played counts as ">threshold" too
        } else if (d < threshold) {
          return false;
        }
      }

      if (unmatchedOnly) {
        const isUnmatched =
          (it.media_type === "movie" && it.radarr_id === null) ||
          (it.media_type === "series" && it.sonarr_id === null);
        if (!isUnmatched) return false;
      }

      if (protectedOnly && !protectedIds.has(it.jellyfin_id)) return false;

      return true;
    });

    out = [...out].sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === null && bv === null) return 0;
      if (av === null) return 1 * dir;
      if (bv === null) return -1 * dir;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });

    return out;
  }, [items, search, typeFilter, watchedFilter, unmatchedOnly, protectedOnly, protectedIds, sortKey, sortDir]);

  const totalSize = useMemo(
    () => filtered.reduce((sum, it) => sum + (it.file_size_bytes || 0), 0),
    [filtered],
  );

  const onHeaderClick = (key: SortKey) => {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sortIndicator = (key: SortKey) =>
    sortKey === key ? <span className="text-slate-400">{sortDir === "asc" ? "▲" : "▼"}</span> : null;

  return (
    <div className="space-y-6 max-w-[1400px]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Bibliothèque</h1>
          <p className="text-slate-400 mt-2">
            Vue agrégée de tes médias Jellyfin avec dernière lecture (tous users confondus) et
            matching Radarr/Sonarr. Aucune action n'est effectuée ici — c'est en lecture seule.
          </p>
        </div>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium rounded-md transition whitespace-nowrap"
        >
          {syncing ? "Synchronisation…" : "↻ Synchroniser"}
        </button>
      </div>

      {syncResult && syncResult.success && (
        <div className="rounded-md border border-emerald-900/50 bg-emerald-950/40 p-3 text-sm text-emerald-300">
          ✓ Sync OK en {syncResult.duration_seconds}s — {syncResult.movies} films,{" "}
          {syncResult.series} séries · matched {syncResult.items_matched_radarr} Radarr /{" "}
          {syncResult.items_matched_sonarr} Sonarr
        </div>
      )}

      {error && (
        <div className="rounded-md border border-red-900/50 bg-red-950/40 p-3 text-sm text-red-300 font-mono">
          {error}
        </div>
      )}

      {items && items.length === 0 && !loading && (
        <div className="rounded-md border border-amber-900/50 bg-amber-950/30 p-4 text-sm text-amber-200">
          Aucun media en cache. Clique sur <strong>Synchroniser</strong> pour récupérer ta
          bibliothèque depuis Jellyfin.
        </div>
      )}

      {items && items.length > 0 && (
        <>
          <div className="flex flex-wrap gap-3 items-center">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Rechercher un titre…"
              className="flex-1 min-w-[200px] px-3 py-2 bg-slate-950 border border-slate-800 rounded-md text-sm focus:outline-none focus:border-brand-500"
            />
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as TypeFilter)}
              className="px-3 py-2 bg-slate-950 border border-slate-800 rounded-md text-sm"
            >
              <option value="all">Tous types</option>
              <option value="movie">🎬 Films</option>
              <option value="series">📺 Séries</option>
            </select>
            <select
              value={watchedFilter}
              onChange={(e) => setWatchedFilter(e.target.value as WatchedFilter)}
              className="px-3 py-2 bg-slate-950 border border-slate-800 rounded-md text-sm"
            >
              <option value="all">Toutes lectures</option>
              <option value="never">Jamais vu</option>
              <option value="30">Pas vu &gt; 30 j</option>
              <option value="90">Pas vu &gt; 90 j</option>
              <option value="365">Pas vu &gt; 1 an</option>
            </select>
            <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
              <input
                type="checkbox"
                className="w-4 h-4 accent-brand-500"
                checked={unmatchedOnly}
                onChange={(e) => setUnmatchedOnly(e.target.checked)}
              />
              Non matchés
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
              <input
                type="checkbox"
                className="w-4 h-4 accent-brand-500"
                checked={protectedOnly}
                onChange={(e) => setProtectedOnly(e.target.checked)}
              />
              🛡️ Protégés
            </label>
          </div>

          <div className="text-xs text-slate-500">
            {filtered.length} item{filtered.length > 1 ? "s" : ""} ·{" "}
            <span className="font-mono">{formatBytes(totalSize)}</span> au total
          </div>

          <div className="rounded-lg border border-slate-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <Th onClick={() => onHeaderClick("media_type")} indicator={sortIndicator("media_type")}>
                    Type
                  </Th>
                  <Th onClick={() => onHeaderClick("name")} indicator={sortIndicator("name")}>
                    Nom
                  </Th>
                  <Th onClick={() => onHeaderClick("date_added")} indicator={sortIndicator("date_added")}>
                    Ajouté
                  </Th>
                  <Th onClick={() => onHeaderClick("last_played_at")} indicator={sortIndicator("last_played_at")}>
                    Dernière lecture
                  </Th>
                  <Th onClick={() => onHeaderClick("file_size_bytes")} indicator={sortIndicator("file_size_bytes")}>
                    Taille
                  </Th>
                  <Th>Match</Th>
                  <Th>🛡️</Th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((it) => (
                  <tr key={it.jellyfin_id} className="border-t border-slate-800/60 hover:bg-slate-900/40">
                    <td className="px-3 py-2 text-center">
                      {it.media_type === "movie" ? "🎬" : "📺"}
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-medium">{it.name}</div>
                      {it.media_type === "series" && it.series_status && (
                        <div
                          className={`text-[10px] uppercase tracking-wider mt-0.5 ${
                            it.series_status === "continuing"
                              ? "text-amber-400"
                              : "text-slate-500"
                          }`}
                        >
                          {it.series_status === "continuing"
                            ? "🟡 En cours"
                            : it.series_status === "ended"
                            ? "⚪ Terminée"
                            : "?"}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-400 whitespace-nowrap">
                      {formatRelative(it.date_added)}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {it.last_played_at ? (
                        <>
                          <div className="text-slate-200">{formatRelative(it.last_played_at)}</div>
                          {it.last_played_by && (
                            <div className="text-[10px] text-slate-500">par {it.last_played_by}</div>
                          )}
                        </>
                      ) : (
                        <span className="text-amber-400 font-medium">Jamais</span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono text-slate-400 text-right whitespace-nowrap">
                      {formatBytes(it.file_size_bytes)}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap text-xs">
                      {it.media_type === "movie" ? (
                        it.radarr_id ? (
                          <span className="text-emerald-400">✓ Radarr</span>
                        ) : (
                          <span className="text-amber-500">⚠ Non matché</span>
                        )
                      ) : it.sonarr_id ? (
                        <span className="text-emerald-400">✓ Sonarr</span>
                      ) : (
                        <span className="text-amber-500">⚠ Non matché</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <button
                        onClick={() => toggleProtection(it.jellyfin_id)}
                        title={
                          protectedIds.has(it.jellyfin_id)
                            ? "Retirer la protection"
                            : "Protéger (ne jamais supprimer)"
                        }
                        className="text-lg hover:scale-110 transition"
                      >
                        {protectedIds.has(it.jellyfin_id) ? "🛡️" : (
                          <span className="opacity-20 hover:opacity-60">🛡️</span>
                        )}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {loading && <div className="text-slate-500 text-sm">Chargement…</div>}
    </div>
  );
}

function Th({
  children,
  onClick,
  indicator,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  indicator?: React.ReactNode;
}) {
  return (
    <th
      onClick={onClick}
      className={`px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider ${
        onClick ? "cursor-pointer hover:text-slate-200 select-none" : ""
      }`}
    >
      <span className="inline-flex items-center gap-1">
        {children}
        {indicator}
      </span>
    </th>
  );
}
