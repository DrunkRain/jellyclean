import { useEffect, useState } from "react";
import { api, type ActionLog, type MarkPassResult, type PendingItem } from "../lib/api";
import { daysSince, formatBytes, formatRelative } from "../lib/format";

const ACTION_LABELS: Record<string, { label: string; color: string }> = {
  "marked-pending": { label: "Marqué", color: "text-amber-400" },
  "unmarked-pending": { label: "Démarqué (ne matche plus)", color: "text-slate-400" },
  restored: { label: "Restauré (manuel)", color: "text-emerald-400" },
  "collection-created": { label: "Collection créée", color: "text-brand-400" },
  "collection-add": { label: "Ajouté à la Collection", color: "text-slate-500" },
  "collection-remove": { label: "Retiré de la Collection", color: "text-slate-500" },
  "would-delete": { label: "Aurait supprimé (dry-run)", color: "text-amber-400" },
  deleted: { label: "Supprimé", color: "text-red-400" },
  "delete-failed": { label: "Échec suppression", color: "text-red-500" },
};

export default function Pending() {
  const [items, setItems] = useState<PendingItem[] | null>(null);
  const [logs, setLogs] = useState<ActionLog[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<MarkPassResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadAll = async () => {
    try {
      const [list, log] = await Promise.all([api.listPending(), api.actionLog(50)]);
      setItems(list);
      setLogs(log);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.runMarkPass();
      setResult(r);
      if (!r.success) setError(r.error_message);
      await loadAll();
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
    }
  };

  const handleRestore = async (jellyfinId: string) => {
    try {
      await api.restorePending(jellyfinId);
      await loadAll();
    } catch (e) {
      setError(String(e));
    }
  };

  const totalSize = (items ?? []).reduce((s, i) => s + (i.file_size_bytes || 0), 0);

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">À nettoyer</h1>
          <p className="text-slate-400 mt-2">
            Items actuellement marqués pour suppression future. Ils sont dans la Collection
            Jellyfin <strong>"Bientôt supprimé"</strong>. <span className="text-amber-400">
              Aucune suppression réelle pour l'instant
            </span>{" "}
            — c'est l'objet du Sprint 4B.
          </p>
        </div>
        <button
          onClick={handleRun}
          disabled={running}
          className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium rounded-md transition whitespace-nowrap"
        >
          {running ? "En cours…" : "🔄 Lancer un mark pass"}
        </button>
      </div>

      {result && result.success && (
        <div className="rounded-md border border-emerald-900/50 bg-emerald-950/40 p-3 text-sm text-emerald-300">
          ✓ Mark pass OK en {result.duration_seconds}s — {result.candidates_total} candidats
          identifiés, +{result.newly_marked} nouveaux marqués, −
          {result.unmarked_no_longer_matching} démarqués (ne matchent plus). Collection : {result.items_in_collection_after} items.
        </div>
      )}

      {error && (
        <div className="rounded-md border border-red-900/50 bg-red-950/40 p-3 text-sm text-red-300 font-mono">
          {error}
        </div>
      )}

      {loading && <div className="text-slate-500 text-sm">Chargement…</div>}

      {items && items.length === 0 && !loading && (
        <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-400">
          Aucun item en attente. ✨ Lance un mark pass pour appliquer la règle actuelle.
        </div>
      )}

      {items && items.length > 0 && (
        <>
          <div className="text-xs text-slate-500">
            {items.length} item{items.length > 1 ? "s" : ""} en attente ·{" "}
            <span className="font-mono">{formatBytes(totalSize)}</span> à libérer
          </div>

          <div className="rounded-lg border border-slate-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase">Type</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase">Nom</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase">Marqué</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase">
                    Suppression prévue
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-semibold uppercase">Taille</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => {
                  const daysLeft = daysSince(it.scheduled_delete_at);
                  const remaining = daysLeft !== null ? -daysLeft : null;
                  const overdue = remaining !== null && remaining <= 0;
                  return (
                    <tr key={it.jellyfin_id} className="border-t border-slate-800/60 hover:bg-slate-900/40">
                      <td className="px-3 py-2 text-center">
                        {it.media_type === "movie" ? "🎬" : "📺"}
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-medium">{it.name}</div>
                        {it.reasons.length > 0 && (
                          <div className="text-xs text-slate-500 mt-0.5">
                            {it.reasons.join(" · ")}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-2 text-slate-400 whitespace-nowrap text-xs">
                        {formatRelative(it.marked_at)}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {remaining === null ? (
                          "—"
                        ) : overdue ? (
                          <span className="text-red-400 font-medium">
                            ⏰ Échéance dépassée
                          </span>
                        ) : (
                          <span className={remaining <= 3 ? "text-amber-400" : "text-slate-300"}>
                            J−{remaining}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono text-slate-400 text-right whitespace-nowrap">
                        {formatBytes(it.file_size_bytes)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          onClick={() => handleRestore(it.jellyfin_id)}
                          className="text-xs px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded transition"
                        >
                          ↩️ Restaurer
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {logs && logs.length > 0 && (
        <div className="border-t border-slate-800 pt-6">
          <h2 className="text-xl font-bold mb-3">Journal d'activité</h2>
          <div className="rounded-lg border border-slate-800 bg-slate-900/40 max-h-96 overflow-auto">
            <table className="w-full text-xs">
              <tbody className="divide-y divide-slate-800/60">
                {logs.map((l) => {
                  const meta = ACTION_LABELS[l.action] ?? {
                    label: l.action,
                    color: "text-slate-400",
                  };
                  return (
                    <tr key={l.id} className="hover:bg-slate-900/60">
                      <td className="px-3 py-1.5 whitespace-nowrap text-slate-600 font-mono">
                        {new Date(l.timestamp).toLocaleString("fr-FR", {
                          dateStyle: "short",
                          timeStyle: "medium",
                        })}
                      </td>
                      <td className={`px-3 py-1.5 whitespace-nowrap ${meta.color}`}>
                        {meta.label}
                      </td>
                      <td className="px-3 py-1.5 truncate max-w-xs">{l.name || l.jellyfin_id}</td>
                      <td className="px-3 py-1.5 text-slate-500 truncate">{l.details}</td>
                      <td className="px-3 py-1.5 text-right">
                        {l.success ? (
                          <span className="text-emerald-500">✓</span>
                        ) : (
                          <span className="text-red-500" title={l.error_message}>✗</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
