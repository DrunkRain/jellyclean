# JellyClean

Un utilitaire de nettoyage de bibliothèque pour la stack **Jellyfin / Radarr / Sonarr / Jellyseerr**.

Inspiré de [Maintainerr](https://github.com/jorenn92/Maintainerr) (Plex), mais conçu nativement pour **Jellyfin**, avec une interface web et un suivi intégré des dernières lectures.

## ✨ Fonctionnalités prévues

- Identifier les médias téléchargés depuis longtemps mais non regardés
- Les marquer dans une Collection Jellyfin "Bientôt supprimé" (visible côté users)
- Délai configurable avant suppression effective
- Suppression propre via les APIs Radarr/Sonarr **sans bloquer les futures demandes** Jellyseerr
- Nettoyage automatique de la demande Jellyseerr correspondante (état cohérent pour re-demande future)
- Protection par série (séries en cours, "ne jamais toucher", etc.)
- **Dry-run par défaut** — rien n'est supprimé sans activation explicite
- Interface web complète (pas de YAML)

## 🚀 Déploiement via Portainer

Dans Portainer → **Stacks** → **Add stack** → **Repository** :

| Champ | Valeur |
|---|---|
| Repository URL | `https://github.com/DrunkRain/jellyclean` |
| Repository reference | `refs/heads/main` |
| Compose path | `docker-compose.yml` |

Puis **Deploy the stack**. L'image est pré-buildée sur GHCR (multi-arch amd64/arm64), donc le pull est instantané.

Une fois lancé : http://`<ip-serveur>`:8080

## 🐳 Déploiement direct (docker compose)

```bash
git clone https://github.com/DrunkRain/jellyclean
cd jellyclean
docker compose up -d
```

## 🛠️ Stack technique

- **Backend** : Python 3.12 + FastAPI + SQLAlchemy + APScheduler
- **Frontend** : React + Vite + TypeScript + Tailwind
- **DB** : SQLite (mono-fichier, persisté dans le volume)
- **Image** : multi-stage, mono-container

## 📋 État actuel

🚧 En cours de développement. Phase 1 (MVP) en cours.

## 📝 Licence

MIT
