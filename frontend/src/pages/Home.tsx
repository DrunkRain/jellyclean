import { useEffect, useState } from "react";

type Health = { status: string; service: string };

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Bienvenue</h1>
        <p className="text-slate-400 mt-2">
          Nettoyage automatique pour ta stack Jellyfin / Radarr / Sonarr / Jellyseerr.
        </p>
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
        <h2 className="text-sm font-semibold text-slate-300 mb-3">État du service</h2>
        {health && (
          <div className="flex items-center gap-2 text-emerald-400 text-sm font-mono">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400" />
            {health.service} · {health.status}
          </div>
        )}
        {error && (
          <div className="text-red-400 text-sm font-mono">Erreur : {error}</div>
        )}
        {!health && !error && (
          <div className="text-slate-500 text-sm font-mono">Connexion…</div>
        )}
      </div>

      <div className="rounded-lg border border-amber-900/50 bg-amber-950/30 p-4 text-sm text-amber-200">
        🚧 Phase 1 en cours — pour commencer, va dans <strong>Paramètres</strong> et
        connecte tes services.
      </div>
    </div>
  );
}
