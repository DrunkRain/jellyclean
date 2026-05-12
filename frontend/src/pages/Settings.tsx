import { useEffect, useState } from "react";
import { api, type ServiceConfig } from "../lib/api";
import ServiceCard from "../components/ServiceCard";

export default function Settings() {
  const [configs, setConfigs] = useState<ServiceConfig[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listSettings().then(setConfigs).catch((e) => setError(String(e)));
  }, []);

  const handleChanged = (updated: ServiceConfig) => {
    setConfigs((prev) =>
      prev ? prev.map((c) => (c.service === updated.service ? updated : c)) : prev,
    );
  };

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Paramètres</h1>
        <p className="text-slate-400 mt-2">
          Configure tes services. JellyClean lit l'état Jellyfin (lectures, bibliothèque)
          et orchestre Radarr/Sonarr pour la suppression. Jellyseerr permet de nettoyer
          les demandes liées aux médias supprimés.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-red-900/50 bg-red-950/40 p-4 text-sm text-red-300 font-mono">
          {error}
        </div>
      )}

      {!configs && !error && (
        <div className="text-slate-500 text-sm">Chargement…</div>
      )}

      {configs?.map((cfg) => (
        <ServiceCard key={cfg.service} config={cfg} onChanged={handleChanged} />
      ))}
    </div>
  );
}
