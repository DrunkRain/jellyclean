import { useEffect, useState } from "react";
import { api, type CleanupRule, type ScanPreview } from "../lib/api";
import { formatBytes, formatRelative } from "../lib/format";

export default function Rules() {
  const [rule, setRule] = useState<CleanupRule | null>(null);
  const [draft, setDraft] = useState<CleanupRule | null>(null);
  const [saving, setSaving] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [preview, setPreview] = useState<ScanPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    api
      .getRule()
      .then((r) => {
        setRule(r);
        setDraft(r);
      })
      .catch((e) => setError(String(e)));
  }, []);

  const dirty =
    rule &&
    draft &&
    (Object.keys(draft) as (keyof CleanupRule)[]).some(
      (k) => k !== "updated_at" && draft[k] !== rule[k],
    );

  const handleSave = async () => {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const { updated_at: _u, ...payload } = draft;
      const saved = await api.updateRule(payload);
      setRule(saved);
      setDraft(saved);
      setSavedAt(Date.now());
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleScan = async () => {
    setScanning(true);
    setPreview(null);
    setError(null);
    try {
      const result = await api.scanPreview();
      setPreview(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setScanning(false);
    }
  };

  if (!draft) {
    return <div className="text-slate-500 text-sm">Chargement…</div>;
  }

  const set = <K extends keyof CleanupRule>(key: K, value: CleanupRule[K]) =>
    setDraft({ ...draft, [key]: value });

  const movieCandidates = preview?.candidates.filter((c) => c.media_type === "movie") ?? [];
  const seriesCandidates = preview?.candidates.filter((c) => c.media_type === "series") ?? [];
  const undeletableCount = preview?.candidates.filter((c) => !c.deletable).length ?? 0;

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-3xl font-bold">Règles</h1>
        <p className="text-slate-400 mt-2">
          Définis les seuils. Le scan ci-dessous est un <strong>aperçu</strong> — rien n'est
          modifié, c'est juste pour visualiser ce qui matcherait.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-red-900/50 bg-red-950/40 p-3 text-sm text-red-300 font-mono">
          {error}
        </div>
      )}

      <div className="grid md:grid-cols-2 gap-4">
        <RuleCard title="🎬 Films" icon="🎬">
          <NumberInput
            label="Âge fichier minimum (jours)"
            help="Le fichier doit être présent depuis au moins ce nombre de jours."
            value={draft.movie_age_days}
            onChange={(v) => set("movie_age_days", v)}
          />
          <NumberInput
            label="Non vu depuis (jours)"
            help="Et n'a pas été lu par AUCUN user depuis ce nombre de jours."
            value={draft.movie_unwatched_days}
            onChange={(v) => set("movie_unwatched_days", v)}
          />
        </RuleCard>

        <RuleCard title="📺 Séries" icon="📺">
          <NumberInput
            label="Âge fichier minimum (jours)"
            value={draft.series_age_days}
            onChange={(v) => set("series_age_days", v)}
          />
          <NumberInput
            label="Non vu depuis (jours)"
            value={draft.series_unwatched_days}
            onChange={(v) => set("series_unwatched_days", v)}
          />
          <Toggle
            label="🛡️ Protéger les séries en cours (Sonarr: continuing)"
            checked={draft.protect_continuing_series}
            onChange={(v) => set("protect_continuing_series", v)}
          />
        </RuleCard>
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-5 space-y-3">
        <h3 className="font-semibold">Suppression (Sprint 4)</h3>
        <p className="text-xs text-slate-500">
          Ces réglages ne s'appliquent pas encore — ils seront utilisés quand la phase
          suppression sera implémentée.
        </p>
        <NumberInput
          label="Délai avant suppression effective (jours)"
          help="Durée pendant laquelle un item reste dans la Collection 'Bientôt supprimé' avant suppression réelle."
          value={draft.grace_period_days}
          onChange={(v) => set("grace_period_days", v)}
        />
        <Toggle
          label="Mode DRY-RUN (recommandé tant que tu n'es pas confiant)"
          checked={draft.dry_run}
          onChange={(v) => set("dry_run", v)}
        />
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium rounded-md transition"
        >
          {saving ? "Enregistrement…" : "Enregistrer la règle"}
        </button>
        {dirty && !saving && <span className="text-xs text-amber-400">Modifications non enregistrées</span>}
        {savedAt && Date.now() - savedAt < 3000 && !dirty && (
          <span className="text-xs text-emerald-400">✓ Enregistré</span>
        )}
      </div>

      <div className="border-t border-slate-800 pt-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold">Aperçu du scan</h2>
            <p className="text-slate-400 text-sm mt-1">
              Évalue les règles contre le cache local. Lance d'abord un sync dans
              Bibliothèque si tu veux les données les plus fraîches.
            </p>
          </div>
          <button
            onClick={handleScan}
            disabled={scanning}
            className="px-4 py-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium rounded-md transition whitespace-nowrap"
          >
            {scanning ? "Scan…" : "🔍 Lancer un scan (aperçu)"}
          </button>
        </div>

        {preview && (
          <div className="mt-6 space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="Items évalués" value={preview.total_items_evaluated.toString()} />
              <Stat
                label="Candidats"
                value={preview.candidates.length.toString()}
                accent="amber"
              />
              <Stat
                label="Espace récupérable"
                value={formatBytes(preview.deletable_total_size_bytes)}
                accent="emerald"
              />
              <Stat
                label="Protégés / En cours"
                value={`${preview.skipped_protected} / ${preview.skipped_continuing_series}`}
              />
            </div>

            {undeletableCount > 0 && (
              <div className="rounded-md border border-amber-900/50 bg-amber-950/30 p-3 text-sm text-amber-200">
                ⚠ {undeletableCount} item{undeletableCount > 1 ? "s" : ""} match
                {undeletableCount > 1 ? "ent" : ""} la règle mais ne{" "}
                {undeletableCount > 1 ? "sont" : "est"} pas matché
                {undeletableCount > 1 ? "s" : ""} dans Radarr/Sonarr → ne pourra pas être
                supprimé proprement. Vérifie les ProviderIds dans Jellyfin.
              </div>
            )}

            {preview.candidates.length === 0 && (
              <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-400">
                Aucun candidat avec les seuils actuels. ✨
              </div>
            )}

            <CandidateGroup title="🎬 Films candidats" items={movieCandidates} />
            <CandidateGroup title="📺 Séries candidates" items={seriesCandidates} />
          </div>
        )}
      </div>
    </div>
  );
}

function RuleCard({
  title,
  icon: _icon,
  children,
}: {
  title: string;
  icon: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-5 space-y-4">
      <h3 className="font-semibold text-lg">{title}</h3>
      {children}
    </div>
  );
}

function NumberInput({
  label,
  help,
  value,
  onChange,
}: {
  label: string;
  help?: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="block text-xs font-medium text-slate-400 mb-1">{label}</label>
      <input
        type="number"
        min={0}
        max={3650}
        value={value}
        onChange={(e) => onChange(parseInt(e.target.value, 10) || 0)}
        className="w-32 px-3 py-2 bg-slate-950 border border-slate-800 rounded-md text-sm font-mono focus:outline-none focus:border-brand-500"
      />
      {help && <p className="text-[11px] text-slate-600 mt-1">{help}</p>}
    </div>
  );
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
      <input
        type="checkbox"
        className="w-4 h-4 accent-brand-500"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "amber" | "emerald";
}) {
  const colorMap = {
    amber: "text-amber-400",
    emerald: "text-emerald-400",
  };
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`text-xl font-bold mt-1 ${accent ? colorMap[accent] : "text-white"}`}>
        {value}
      </div>
    </div>
  );
}

function CandidateGroup({
  title,
  items,
}: {
  title: string;
  items: import("../lib/api").ScanCandidate[];
}) {
  if (items.length === 0) return null;
  const totalSize = items.reduce((s, i) => s + (i.file_size_bytes || 0), 0);
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 overflow-hidden">
      <div className="px-4 py-2 bg-slate-900 text-sm font-semibold flex items-center justify-between">
        <span>
          {title} <span className="text-slate-500 font-normal">({items.length})</span>
        </span>
        <span className="text-slate-500 text-xs font-mono">{formatBytes(totalSize)}</span>
      </div>
      <div className="divide-y divide-slate-800/60">
        {items.map((c) => (
          <div key={c.jellyfin_id} className="px-4 py-3 flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <div className="font-medium truncate flex items-center gap-2">
                {c.name}
                {!c.deletable && (
                  <span
                    title={c.deletable_blocker ?? ""}
                    className="text-[10px] px-1.5 py-0.5 bg-amber-950 text-amber-400 rounded uppercase tracking-wider"
                  >
                    Non supprimable
                  </span>
                )}
              </div>
              <div className="text-xs text-slate-500 mt-1 space-y-0.5">
                {c.reasons.map((r) => (
                  <div key={r}>• {r}</div>
                ))}
                {c.last_played_by && (
                  <div className="text-slate-600">
                    Dernier visionnage : {formatRelative(c.last_played_at)} par {c.last_played_by}
                  </div>
                )}
              </div>
            </div>
            <div className="text-right text-xs font-mono text-slate-400 whitespace-nowrap">
              {formatBytes(c.file_size_bytes)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
