from typing import Any

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

    async def list_all_requests(self) -> list[dict[str, Any]]:
        """Paginate through all Jellyseerr requests. Used to find the request
        that originally brought a media into the library so we can clean it up
        when the media is deleted (otherwise Jellyseerr keeps thinking the
        media is 'available' and the user can't cleanly re-request it)."""
        out: list[dict[str, Any]] = []
        skip = 0
        page_size = 100
        # Jellyseerr API uses ?take=&skip=. We cap at 50 pages = 5000 requests
        # (way more than any real homelab will have).
        for _ in range(50):
            data = await self.get(
                "/api/v1/request",
                params={"take": page_size, "skip": skip, "filter": "all", "sort": "added"},
            )
            page = data.get("results", [])
            if not page:
                break
            out.extend(page)
            if len(page) < page_size:
                break
            skip += page_size
        return out

    async def find_request_for_media(
        self,
        media_type: str,  # "movie" or "tv"
        tmdb_id: str | None = None,
        tvdb_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Locate the Jellyseerr request that brought this media in. Matches
        on tmdbId for movies, tvdbId for series. Returns the most recent matching
        request (by id descending) or None."""
        if not tmdb_id and not tvdb_id:
            return None

        all_requests = await self.list_all_requests()
        matches: list[dict[str, Any]] = []
        for req in all_requests:
            media = req.get("media") or {}
            if media.get("mediaType") != media_type:
                continue
            if media_type == "movie" and tmdb_id and str(media.get("tmdbId")) == str(tmdb_id):
                matches.append(req)
            elif media_type == "tv" and tvdb_id and str(media.get("tvdbId")) == str(tvdb_id):
                matches.append(req)

        if not matches:
            return None
        matches.sort(key=lambda r: r.get("id", 0), reverse=True)
        return matches[0]

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
