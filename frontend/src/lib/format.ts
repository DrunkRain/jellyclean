import type { MediaItem } from "./api";

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let val = bytes;
  let u = 0;
  while (val >= 1024 && u < units.length - 1) {
    val /= 1024;
    u++;
  }
  return `${val.toFixed(val >= 100 || u === 0 ? 0 : 1)} ${units[u]}`;
}

export function daysSince(isoDate: string | null | undefined): number | null {
  if (!isoDate) return null;
  const then = new Date(isoDate).getTime();
  if (Number.isNaN(then)) return null;
  return Math.floor((Date.now() - then) / (1000 * 60 * 60 * 24));
}

export function formatRelative(isoDate: string | null | undefined): string {
  const d = daysSince(isoDate);
  if (d === null) return "—";
  if (d === 0) return "aujourd'hui";
  if (d === 1) return "hier";
  if (d < 30) return `il y a ${d} j`;
  if (d < 365) return `il y a ${Math.floor(d / 30)} mois`;
  const years = Math.floor(d / 365);
  return `il y a ${years} an${years > 1 ? "s" : ""}`;
}

export interface MatchDiagnostic {
  matched: boolean;
  cause: "matched" | "missing-ids" | "missing-in-arr";
  short: string; // for badge text
  detail: string; // for tooltip
}

/**
 * Computes the matching diagnostic for an item.
 * Two failure modes (with different fixes):
 *   - missing-ids: Jellyfin lacks TMDB/TVDB/IMDB → identify in Jellyfin
 *   - missing-in-arr: Jellyfin has IDs but Radarr/Sonarr does not → add to *arr
 */
export function matchDiagnostic(item: MediaItem): MatchDiagnostic {
  if (item.media_type === "movie") {
    if (item.radarr_id !== null) {
      return { matched: true, cause: "matched", short: "✓ Radarr", detail: `Radarr id ${item.radarr_id}` };
    }
    if (!item.tmdb_id && !item.imdb_id) {
      return {
        matched: false,
        cause: "missing-ids",
        short: "⚠ IDs Jellyfin manquants",
        detail:
          "Aucun ID TMDB/IMDB côté Jellyfin. Fix : dans Jellyfin → l'item → ⋮ → Identifier → choisir le bon match.",
      };
    }
    const ids = [
      item.tmdb_id ? `TMDB:${item.tmdb_id}` : null,
      item.imdb_id ? `IMDB:${item.imdb_id}` : null,
    ]
      .filter(Boolean)
      .join(", ");
    return {
      matched: false,
      cause: "missing-in-arr",
      short: "⚠ Inconnu de Radarr",
      detail: `Jellyfin a les IDs (${ids}) mais Radarr ne connaît pas ce film. Fix : Radarr → Add Movie → recherche par titre.`,
    };
  }

  if (item.sonarr_id !== null) {
    return { matched: true, cause: "matched", short: "✓ Sonarr", detail: `Sonarr id ${item.sonarr_id}` };
  }
  if (!item.tvdb_id && !item.imdb_id) {
    return {
      matched: false,
      cause: "missing-ids",
      short: "⚠ IDs Jellyfin manquants",
      detail:
        "Aucun ID TVDB/IMDB côté Jellyfin. Fix : dans Jellyfin → la série → ⋮ → Identifier → choisir le bon match.",
    };
  }
  const ids = [
    item.tvdb_id ? `TVDB:${item.tvdb_id}` : null,
    item.imdb_id ? `IMDB:${item.imdb_id}` : null,
  ]
    .filter(Boolean)
    .join(", ");
  return {
    matched: false,
    cause: "missing-in-arr",
    short: "⚠ Inconnue de Sonarr",
    detail: `Jellyfin a les IDs (${ids}) mais Sonarr ne connaît pas cette série. Fix : Sonarr → Add Series → Import existing.`,
  };
}
