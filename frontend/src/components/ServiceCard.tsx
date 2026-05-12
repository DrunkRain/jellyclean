import { useState } from "react";
import { api, type ServiceConfig, type ServiceName } from "../lib/api";

const META: Record<ServiceName, { label: string; icon: string; placeholderUrl: string; hint: string }> = {
  jellyfin: {
    label: "Jellyfin",
    icon: "🪼",
    placeholderUrl: "http://jellyfin:8096",
    hint: "Clé API : Tableau de bord → Avancé → Clés API",
  },
  radarr: {
    label: "Radarr",
    icon: "🎬",
    placeholderUrl: "http://radarr:7878",
    hint: "Clé API : Settings → General → API Key",
  },
  sonarr: {
    label: "Sonarr",
    icon: "📺",
    placeholderUrl: "http://sonarr:8989",
    hint: "Clé API : Settings → General → API Key",
  },
  jellyseerr: {
    label: "Jellyseerr",
    icon: "🎟️",
    placeholderUrl: "http://jellyseerr:5055",
    hint: "Clé API : Settings → API Key",
  },
};

export default function ServiceCard({
  config,
  onChanged,
}: {
  config: ServiceConfig;
  onChanged: (updated: ServiceConfig) => void;
}) {
  const meta = META[config.service];
  const [url, setUrl] = useState(config.base_url);
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(config.enabled);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testMsg, setTestMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateSetting(config.service, {
        base_url: url,
        api_key: apiKey || undefined,
        enabled,
      });
      onChanged(updated);
      setApiKey("");
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestMsg(null);
    setError(null);
    try {
      const result = await api.testSetting(config.service);
      setTestMsg({ ok: result.success, text: result.message });
      const refreshed = await api.getSetting(config.service);
      onChanged(refreshed);
    } catch (e) {
      setTestMsg({ ok: false, text: String(e) });
    } finally {
      setTesting(false);
    }
  };

  const statusBadge = () => {
    if (config.last_test_status === "success")
      return <span className="text-emerald-400">● Connecté</span>;
    if (config.last_test_status === "failure")
      return <span className="text-red-400">● Échec</span>;
    return <span className="text-slate-500">○ Non testé</span>;
  };

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{meta.icon}</span>
          <div>
            <h3 className="font-semibold text-lg">{meta.label}</h3>
            <div className="text-xs font-mono">{statusBadge()}</div>
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer">
          <input
            type="checkbox"
            className="w-4 h-4 accent-brand-500"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          Activé
        </label>
      </div>

      <div className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">URL</label>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={meta.placeholderUrl}
            className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-md text-sm font-mono focus:outline-none focus:border-brand-500"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-400 mb-1">
            Clé API{" "}
            {config.has_api_key && (
              <span className="text-slate-600 font-mono normal-case">
                (actuelle : {config.api_key_masked})
              </span>
            )}
          </label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={config.has_api_key ? "Laisser vide pour ne pas changer" : "Coller la clé API"}
            className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-md text-sm font-mono focus:outline-none focus:border-brand-500"
          />
          <p className="text-[11px] text-slate-600 mt-1">{meta.hint}</p>
        </div>
      </div>

      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-3 py-1.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium rounded-md transition"
        >
          {saving ? "Enregistrement…" : "Enregistrer"}
        </button>
        <button
          onClick={handleTest}
          disabled={testing || !config.has_api_key || !config.base_url}
          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-30 disabled:cursor-not-allowed text-slate-200 text-sm font-medium rounded-md transition"
          title={
            !config.has_api_key || !config.base_url
              ? "Enregistre URL + clé d'abord"
              : "Tester la connexion"
          }
        >
          {testing ? "Test…" : "Tester la connexion"}
        </button>
      </div>

      {testMsg && (
        <div
          className={`text-xs font-mono p-2 rounded ${
            testMsg.ok
              ? "bg-emerald-950/40 text-emerald-300 border border-emerald-900/50"
              : "bg-red-950/40 text-red-300 border border-red-900/50"
          }`}
        >
          {testMsg.text}
        </div>
      )}

      {error && (
        <div className="text-xs font-mono p-2 rounded bg-red-950/40 text-red-300 border border-red-900/50">
          {error}
        </div>
      )}
    </div>
  );
}
