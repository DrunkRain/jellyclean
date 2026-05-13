from typing import Any

import httpx

from app.clients.base import BaseClient, TestResult, classify_error


class JellyseerrClient(BaseClient):
    name = "Jellyseerr"
    timeout_seconds = 20.0

    def _auth_headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key, "Accept": "application/json"}

    async def test_connection(self) -> TestResult:
        try:
            data = await self.get("/api/v1/status")
        except Exception as exc:
            return classify_error(exc, self.name)

        version = data.get("version", "?")
        return TestResult(
            success=True,
            message=f"Connecté à Jellyseerr (v{version})",
            details={"version": version, "commit_tag": data.get("commitTag")},
        )

    async def find_media_info(
        self,
        media_type: str,  # "movie" or "tv"
        tmdb_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Direct lookup of the Jellyseerr media entry by TMDB ID.

        Jellyseerr's /movie/{tmdbId} and /tv/{tmdbId} endpoints always return
        the title's TMDB data; they additionally return a `mediaInfo` block
        ONLY when Jellyseerr already tracks that title (requested or imported
        from Jellyfin). That mediaInfo.id is what we feed to delete_media.

        Returns the mediaInfo dict (with .id, .status, etc.) or None if
        Jellyseerr has no record of this title.

        We use TMDB ID exclusively here because Jellyseerr keys both movies and
        series by TMDB internally — TVDB is stored but not used as a primary
        lookup key on these endpoints.
        """
        if not tmdb_id:
            return None

        path = f"/api/v1/movie/{tmdb_id}" if media_type == "movie" else f"/api/v1/tv/{tmdb_id}"
        try:
            data = await self.get(path)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

        media_info = data.get("mediaInfo")
        # When mediaInfo is absent / null, Jellyseerr doesn't track this title.
        return media_info if isinstance(media_info, dict) else None

    async def delete_request(self, request_id: int) -> None:
        async with self._client() as c:
            resp = await c.delete(f"/api/v1/request/{request_id}")
            resp.raise_for_status()

    async def delete_media(self, media_id: int) -> None:
        """Remove a media entry from Jellyseerr.

        IMPORTANT: this is the call that actually resets a media's availability
        state in Jellyseerr — deleting only the Request leaves the Media object
        with status='Available', so the user keeps seeing the title as available
        and never gets a 'Request' button to re-add it. Deleting the Media also
        cascades to its Requests, so we don't need to delete those separately.
        """
        async with self._client() as c:
            resp = await c.delete(f"/api/v1/media/{media_id}")
            resp.raise_for_status()
