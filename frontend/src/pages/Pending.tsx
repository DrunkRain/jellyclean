import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type ActionLog,
  type CleanupRule,
  type DeletePassResult,
  type FullCycleResult,
  type MarkPassResult,
  type PendingItem,
} from "../lib/api";
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
  "jellyseerr-media-deleted": { label: "Jellyseerr nettoyé (media)", color: "text-emerald-400" },
  "jellyseerr-request-deleted": { label: "Jellyseerr nettoyé (request, fallback)", color: "text-amber-400" },
  "jellyseerr-skipped": { label: "Cleanup Jellyseerr ignoré", color: "text-slate-500" },
  "jellyseerr-cleanup-failed": { label: "Échec cleanup Jellyseerr", color: "text-amber-500" },
};

type AnyResult =
  | { kind: "mark"; data: MarkPassResult }
  | { kind: "delete"; data: DeletePassResult }
  | { kind: "cycle"; data: FullCycleResult };

export default function Pending() {
  const [items, setItems] = useState<PendingItem[] | null>(null);
  const [logs, setLogs] = useState<ActionLog[] | null>(null);
  const [rule, setRule] = useState<CleanupRule | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<"mark" | "delete" | "cycle" | "delete-now" | null>(null);
  const [result, setResult] = useState<AnyResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadAll = async () => {
    try {
      const [list, log, r] = await Promise.all([
        api.listPending(),
        api.actionLog(50),
        api.getRule(),
      ]);
      setItems(list);
      setLogs(log);
      setRule(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleMark = async () => {
    setRunning("mark");
    setError(null);
    setResult(null);
    try {
      const r = await api.runMarkPass();
      setResult({ kind: "mark", data: r });
      if (!r.success) setError(r.error_message);
      await loadAll();
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(null);
    }
  };

  const handleDeletePass = async () => {
    if (!rule) return;
    if (!rule.dry_run) {
      const ok = window.confirm(
        "🔴 MODE LIVE actif.\n\nLe delete pass va RÉELLEMENT supprimer tous les items dont " +
          "le délai est dépassé (Radarr/Sonarr + Jellyseerr).\n\nContinuer ?",
      );
      if (!ok) return;
    }
    setRunning("delete");
    setError(null);
    setResult(null);
    try {
      const r = await api.runDeletePass();
      setResult({ kind: "delete", data: r });
      await loadAll();
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(null);
    }
  };

  const handleFullCycle = async () => {
    if (!rule) return;
    if (!rule.dry_run) {
      const ok = window.confirm(
        "🔴 MODE LIVE actif.\n\nLe cycle complet va sync + mark + DELETE des items expirés. " +
          "Réel.\n\nContinuer ?",
      );
      if (!ok) return;
    }
    setRunning("cycle");
    setError(null);
    setResult(null);
    try {
      const r = await api.runFullCycle();
      setResult({ kind: "cycle", data: r });
      if (!r.success && r.error_message) setError(r.error_message);
      await loadAll();
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(null);
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

  const handleDeleteNow = async (jellyfinId: string, name: string) => {
    if (!rule) return;
    if (!rule.dry_run) {
      const ok = window.confirm(
        `🔴 MODE LIVE — Supprimer "${name}" maintenant ?\n\nLe fichier sera supprimé via ` +
          "Radarr/Sonarr (definitivement). La demande Jellyseerr sera nettoyée.",
      );
      if (!ok) return;
    }
    setRunning("delete-now");
    try {
      const r = await api.deleteNow(jellyfinId);
      setResult({ kind: "delete", data: r });
      await loadAll();
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(null);
    }
  };

  const totalSize = (items ?? []).reduce((s, i) => s + (i.file_size_bytes || 0), 0);

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex-1 min-w-0">
          <h1 className="text-3xl font-bold">À nettoyer</h1>
          <p className="text-slate-400 mt-2">
            Items dans la Collection Jellyfin <strong>"Bientôt supprimé"</strong>, en attente
            de leur échéance. {rule?.dry_run ? (
              <span className="text-emerald-400">DRY-RUN actif — rien ne sera réellement supprimé.</span>
            ) : (
              <span className="text-red-400 font-semibold">🔴 MODE LIVE — les suppressions sont réelles.</span>
            )}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={handleMark}
            disabled={!!running}
            className="px-3 py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 text-sm font-medium rounded-md transition whitespace-nowrap"
          >
            {running === "mark" ? "Mark…" : "🏷️ Mark pass"}
          </button>
          <button
            onClick={handleDeletePass}
            disabled={!!running}
            className={`px-3 py-2 disabled:opacity-50 text-white text-sm font-medium rounded-md transition whitespace-nowrap ${
              rule?.dry_run ? "bg-slate-800 hover:bg-slate-700" : "bg-red-700 hover:bg-red-600"
            }`}
          >
            {running === "delete" ? "Delete…" : "🗑️ Delete pass"}
          </button>
          <button
            onClick={handleFullCycle}
            disabled={!!running}
            className="px-3 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium rounded-md transition whitespace-nowrap"
          >
            {running === "cycle" ? "Cycle…" : "▶ Cycle complet"}
          </button>
        </div>
      </div>

      {rule && !rule.enabled && (
        <div className="rounded-md border border-amber-900/50 bg-amber-950/30 p-3 text-sm text-amber-200 flex items-center justify-between gap-4">
          <span>
            ⚠ La règle est <strong>désactivée</strong>. Le mark pass ne marquera rien tant que tu
            ne l'as pas activée.
          </span>
          <Link
            to="/rules"
            className="text-xs px-3 py-1.5 bg-amber-900/40 hover:bg-amber-900/60 rounded border border-amber-700/40 whitespace-nowrap"
          >
            Aller activer la règle →
          </Link>
        </div>
      )}

      {result?.kind === "mark" && result.data.success && result.data.rule_enabled && (
        <div className="rounded-md border border-emerald-900/50 bg-emerald-950/40 p-3 text-sm text-emerald-300">
          ✓ Mark pass OK en {result.data.duration_seconds}s — {result.data.candidates_total}{" "}
          candidats identifiés, +{result.data.newly_marked} nouveaux marqués, −
          {result.data.unmarked_no_longer_matching} démarqués. Collection :{" "}
          {result.data.items_in_collection_after} items.
        </div>
      )}

      {result?.kind === "mark" && !result.data.rule_enabled && (
        <div className="rounded-md border border-amber-900/50 bg-amber-950/30 p-3 text-sm text-amber-200">
          ⚠ {result.data.candidates_total} candidats matcheraient la règle, mais elle est
          désactivée. Va l'activer dans <Link to="/rules" className="underline">Règles</Link>.
        </div>
      )}

      {result?.kind === "delete" && (
        <div
          className={`rounded-md border p-3 text-sm ${
            result.data.dry_run
              ? "border-emerald-900/50 bg-emerald-950/40 text-emerald-300"
              : "border-red-700/60 bg-red-950/40 text-red-200"
          }`}
        >
          {result.data.dry_run
            ? `✓ DRY-RUN delete pass en ${result.data.duration_seconds}s — ${result.data.deleted_count} item${
                result.data.deleted_count > 1 ? "s" : ""
              } AURAIENT été supprimés (rien n'a bougé), ${result.data.failed_count} en échec.`
            : `🔴 LIVE delete pass en ${result.data.duration_seconds}s — ${result.data.deleted_count} supprimé${
                result.data.deleted_count > 1 ? "s" : ""
              }, ${result.data.failed_count} en échec.`}
          {result.data.errors.length > 0 && (
            <ul className="mt-2 text-xs space-y-0.5">
              {result.data.errors.map((e) => (
                <li key={e}>• {e}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {result?.kind === "cycle" && (
        <div
          className={`rounded-md border p-3 text-sm space-y-1 ${
            result.data.success
              ? "border-emerald-900/50 bg-emerald-950/40 text-emerald-300"
              : "border-amber-900/50 bg-amber-950/30 text-amber-200"
          }`}
        >
          <div className="font-semibold">
            ▶ Cycle complet terminé en {result.data.duration_seconds}s
          </div>
          {result.data.sync && (
            <div className="text-xs opacity-90">
              · Sync : {result.data.sync.movies} films, {result.data.sync.series} séries
              ({result.data.sync.duration_seconds}s)
            </div>
          )}
          {result.data.mark_pass && (
            <div className="text-xs opacity-90">
              · Mark : +{result.data.mark_pass.newly_marked} marqués, −
              {result.data.mark_pass.unmarked_no_longer_matching} démarqués
            </div>
          )}
          {result.data.delete_pass && (
            <div className="text-xs opacity-90">
              · Delete ({result.data.delete_pass.dry_run ? "dry-run" : "LIVE"}) :{" "}
              {result.data.delete_pass.deleted_count} traités,{" "}
              {result.data.delete_pass.failed_count} en échec
            </div>
          )}
          {result.data.error_message && (
            <div className="text-xs">⚠ {result.data.error_message}</div>
          )}
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
                        <div className="flex gap-1 justify-end">
                          <button
                            onClick={() => handleRestore(it.jellyfin_id)}
                            disabled={!!running}
                            className="text-xs px-2 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-30 text-slate-200 rounded transition"
                            title="Retirer de la liste à supprimer"
                          >
                            ↩️ Restaurer
                          </button>
                          <button
                            onClick={() => handleDeleteNow(it.jellyfin_id, it.name)}
                            disabled={!!running}
                            className={`text-xs px-2 py-1 disabled:opacity-30 text-white rounded transition ${
                              rule?.dry_run
                                ? "bg-slate-800 hover:bg-slate-700"
                                : "bg-red-700 hover:bg-red-600"
                            }`}
                            title={
                              rule?.dry_run
                                ? "Supprimer maintenant (DRY-RUN — simulé)"
                                : "Supprimer maintenant (RÉEL)"
                            }
                          >
                            🗑 Supprimer
                          </button>
                        </div>
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
