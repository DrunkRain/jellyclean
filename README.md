# JellyClean

> Nettoyage automatique pour la stack **Jellyfin / Radarr / Sonarr / Jellyseerr** — pensé comme [Maintainerr](https://github.com/jorenn92/Maintainerr), mais natif Jellyfin et avec interface web complète.

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
[![Build](https://github.com/DrunkRain/jellyclean/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/DrunkRain/jellyclean/actions)
[![Image](https://img.shields.io/badge/ghcr.io-drunkrain%2Fjellyclean-blue)](https://github.com/DrunkRain/jellyclean/pkgs/container/jellyclean)

---

## 🎯 À quoi ça sert

Un serveur Jellyfin se remplit avec le temps de médias que **personne ne regarde plus**. JellyClean identifie ces médias selon tes règles, les met en attente visible dans une Collection Jellyfin, et après un délai de grâce les supprime proprement via Radarr/Sonarr — tout en gardant la possibilité de re-demander le média via Jellyseerr plus tard.

**Exemple de règle typique** : film téléchargé depuis plus de 90 jours, jamais regardé par personne depuis 30 jours → marqué dans la Collection "Bientôt supprimé" → supprimé pour de bon 14 jours plus tard.

## 🥇 Pourquoi pas Maintainerr ou Janitorr ?

| | Maintainerr | Janitorr | **JellyClean** |
|---|---|---|---|
| Support Plex | ✅ | ❌ | ❌ |
| Support Jellyfin | ❌ | ✅ | ✅ |
| Suivi natif "dernière lecture" | ✅ | ❌ | ✅ |
| Interface web complète | ✅ | ❌ (YAML) | ✅ |
| Cleanup demande Jellyseerr | ✅ | ⚠️ | ✅ |
| Re-requestabilité après suppression | ✅ | ⚠️ | ✅ |

## ✨ Fonctionnalités

### Connexions
- Configuration via UI : URL + clé API pour Jellyfin, Radarr, Sonarr, Jellyseerr
- Bouton **Tester la connexion** par service
- Clés API stockées en SQLite, masquées dans l'UI une fois sauvées

### Bibliothèque
- Synchronisation à la demande de tout le catalogue Jellyfin
- Agrégation de la **dernière lecture cross-users** (max LastPlayedDate parmi tous les users)
- Match automatique vers Radarr (TMDB ID) et Sonarr (TVDB ID, fallback IMDB)
- Détection du statut série `continuing` / `ended` via Sonarr
- Résolution de la **bibliothèque Jellyfin parente** (Films, Séries, Animation, ...) par match de chemin
- Recherche, tri, filtres : par bibliothèque, dernière lecture, items non matchés, items protégés

### Règles
- Seuils par type : âge fichier minimum, "non vu depuis" en jours
- Toggle global **🛡️ Protéger les séries en cours** (statut Sonarr `continuing`)
- Protection par item — bouton "🛡️" par ligne, persistante
- **Scan preview** — voir qui matche sans toucher à rien
- Diagnostic clair sur les items non supprimables (IDs Jellyfin manquants vs. inconnu de Radarr/Sonarr)

### Cleanup
- Création/synchronisation auto d'une **Collection Jellyfin "Bientôt supprimé"** (lazy, chunkée pour éviter HTTP 414)
- Compte à rebours par item (J−14 → J−0) selon ton délai de grâce configuré
- **Mode DRY-RUN par défaut** — bannière rouge sticky quand tu passes en LIVE
- Confirmation obligatoire à chaque action destructrice en LIVE
- Boutons par item : **↩️ Restaurer** / **🗑 Supprimer maintenant**
- Suppression effective via Radarr `DELETE /movie?deleteFiles=true&addImportExclusion=false` (idem Sonarr)
- Cleanup automatique de la **media entry Jellyseerr** (et non juste la request — c'est le piège classique)

### Scheduler
- Cycle complet automatique quotidien à l'heure configurée (UTC)
- Pipeline : sync → mark → delete

### Audit
- **Journal d'activité** persistant en DB : chaque action loggée avec timestamp, item, détails, succès/échec
- Endpoint `/api/library/diagnose` pour debugger la résolution des bibliothèques

## 🚀 Déploiement

### Via Portainer (recommandé)

**Stacks → Add stack → Repository** :

| Champ | Valeur |
|---|---|
| Repository URL | `https://github.com/DrunkRain/jellyclean` |
| Repository reference | `refs/heads/main` |
| Compose path | `docker-compose.yml` |

→ **Deploy the stack**. L'image est pré-buildée sur GHCR.

> ⚠️ **Premier déploiement** : il faut rendre l'image GHCR **publique** une fois la première build CI terminée :
> https://github.com/users/DrunkRain/packages/container/jellyclean/settings → Change visibility → Public

Une fois lancé, ouvre `http://<ip-serveur>:8095` dans ton navigateur.

### Via docker compose en direct

```bash
git clone https://github.com/DrunkRain/jellyclean
cd jellyclean
docker compose up -d
```

## ⚙️ Configuration

### Variables d'environnement

| Var | Défaut | Description |
|---|---|---|
| `JELLYCLEAN_PORT` | `8095` | Port d'écoute du conteneur |
| `JELLYCLEAN_DATA_DIR` | `/data` | Dossier de persistance (DB SQLite) |
| `JELLYCLEAN_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `TZ` | (système) | Timezone pour les logs |

### Volume

Un seul volume nécessaire :

```yaml
volumes:
  - jellyclean_data:/data
```

Contient la SQLite `jellyclean.db` (tes connexions, règles, items pending, journal).

## 🧭 Première utilisation

1. **Paramètres** — entre URL + clé API pour tes 4 services, clique **Tester la connexion** pour chacun.
2. **Bibliothèque** → **↻ Synchroniser** — peut prendre 10-30 secondes selon la taille.
3. **Règles** — règle les seuils, **active la règle** (toggle en haut), **enregistre**. Laisse le **DRY-RUN activé** pour commencer.
4. **À nettoyer** → **🔄 Lancer un mark pass** — la Collection Jellyfin apparaît avec les candidats.
5. **Vérifie la Collection dans Jellyfin** — assure-toi que ce que tu vois te convient.
6. Quand t'es confiant : page Règles → désactive le DRY-RUN (confirmation requise), bannière rouge LIVE apparaît.
7. Active la planification quotidienne pour automatiser, ou continue en manuel.

## 🔑 Le détail qui change tout — `addImportExclusion=false`

JellyClean force ce paramètre à `false` quand il appelle Radarr/Sonarr. Conséquence :
- ✅ Le film/série est supprimé (fichier + entrée *arr)
- ✅ Il N'est **PAS** ajouté à la blocklist d'import
- ✅ La media entry Jellyseerr est aussi supprimée → reset du statut "Available"

Du coup, dans 6 mois si tu veux re-regarder le film : tu vas sur Jellyseerr, **bouton Request** apparaît, ça redemande à Radarr, ça re-télécharge. Aucun nettoyage manuel nécessaire.

C'est cette UX qui rend JellyClean utile en pratique pour un homelab.

## 🛠️ Stack technique

- **Backend** : Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + APScheduler
- **Frontend** : React 18 + Vite + TypeScript + Tailwind 3
- **DB** : SQLite (mono-fichier, migration auto sur ajout de colonnes)
- **Image** : multi-stage Docker (Node build → Python runtime), multi-arch (amd64/arm64)
- **Auth** : Aucune côté UI (déploie derrière reverse proxy si exposé)

## 🐛 Troubleshooting

### "Site inaccessible" après déploiement
- Vérifie que tu as activé **Re-pull image** dans Portainer après chaque mise à jour
- L'image GHCR doit être **publique** (voir section Déploiement)
- Le port `8095` doit être libre sur l'hôte (ou change-le dans `docker-compose.yml`)

### "Sans bibliothèque" sur tous les items
Va sur `http://<ip>:8095/api/library/diagnose` — le JSON te dira ce que Jellyfin renvoie et ce que JellyClean en fait. Cause typique : clé API Jellyfin sans permissions admin.

### Suppression Radarr réussie mais fichier toujours sur disque
Radarr → Settings → Media Management → **Recycle Bin** : si une path est renseignée, les fichiers sont *déplacés* dedans au lieu d'être supprimés. Vide le champ ou configure "Recycle Bin Cleanup Days" à 1.

### Items "Non matchés" dans Radarr/Sonarr
Dans Bibliothèque, survole le badge Match pour voir la cause exacte :
- **IDs Jellyfin manquants** → Jellyfin → l'item → `⋮ → Identifier`
- **Inconnu de Radarr/Sonarr** → Radarr/Sonarr → `Library Import` (import en bulk d'un dossier existant)

### Jellyseerr affiche encore "Available" après suppression
JellyClean supprime la *media entry* Jellyseerr (pas juste la request) — ça devrait fonctionner. Si le badge "Available" persiste, attends le prochain scan auto Jellyseerr ou force un sync Jellyfin via les paramètres Jellyseerr.

## 📝 Licence

MIT — voir [LICENSE](./LICENSE).

## 🙏 Inspirations

- [Maintainerr](https://github.com/jorenn92/Maintainerr) — l'équivalent côté Plex, source d'inspiration sur le modèle Collection + délai de grâce
- [Janitorr](https://github.com/Schaka/janitorr) — pour avoir montré que c'était possible côté Jellyfin
