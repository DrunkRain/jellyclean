import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

/**
 * Sticky red banner that appears on every page when LIVE mode is active
 * (i.e. CleanupRule.dry_run = false). Polls the rule every 30s so any change
 * propagates without page reload.
 */
export default function LiveModeBanner() {
  const [live, setLive] = useState(false);

  useEffect(() => {
    let mounted = true;
    const refresh = async () => {
      try {
        const rule = await api.getRule();
        if (mounted) setLive(!rule.dry_run);
      } catch {
        // ignore — banner stays in last-known state
      }
    };
    refresh();
    const id = window.setInterval(refresh, 30000);
    return () => {
      mounted = false;
      window.clearInterval(id);
    };
  }, []);

  if (!live) return null;

  return (
    <div className="bg-red-700 text-white px-4 py-2 text-sm font-semibold flex items-center justify-between gap-4 sticky top-0 z-50">
      <span className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
        🔴 MODE LIVE — les suppressions sont RÉELLES (Radarr, Sonarr, Jellyseerr)
      </span>
      <Link to="/rules" className="text-xs underline opacity-90 hover:opacity-100">
        Désactiver
      </Link>
    </div>
  );
}
