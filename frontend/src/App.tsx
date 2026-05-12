import { useEffect, useState } from "react";

type Health = { status: string; service: string };

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="min-h-full flex flex-col items-center justify-center px-4">
      <div className="max-w-xl w-full text-center space-y-6">
        <h1 className="text-5xl font-bold tracking-tight bg-gradient-to-r from-brand-500 to-purple-500 bg-clip-text text-transparent">
          JellyClean
        </h1>
        <p className="text-slate-400 text-lg">
          Nettoyage automatique pour la stack Jellyfin / Radarr / Sonarr / Jellyseerr.
        </p>

        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6 text-left">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">
            État du service
          </h2>
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

        <p className="text-slate-600 text-xs">
          🚧 Phase 1 (MVP) en cours de développement
        </p>
      </div>
    </div>
  );
}
