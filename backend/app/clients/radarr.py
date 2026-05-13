from typing import Any

from app.clients.base import BaseClient, TestResult, classify_error


class RadarrClient(BaseClient):
    name = "Radarr"
    api_version = "v3"
    timeout_seconds = 30.0

    def _auth_headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key, "Accept": "application/json"}

    async def test_connection(self) -> TestResult:
        try:
            data = await self.get(f"/api/{self.api_version}/system/status")
        except Exception as exc:
            return classify_error(exc, self.name)

        version = data.get("version", "?")
        instance_name = data.get("instanceName", "Radarr")
        return TestResult(
            success=True,
            message=f"Connecté à {instance_name} (v{version})",
            details={"version": version, "instance_name": instance_name},
        )

    async def list_movies(self) -> list[dict[str, Any]]:
        """All movies known to Radarr (whether file-present or just monitored)."""
        return await self.get(f"/api/{self.api_version}/movie")

    async def delete_movie(
        self,
        movie_id: int,
        delete_files: bool = True,
        add_import_exclusion: bool = False,
    ) -> None:
        """Delete a movie and (by default) its files.

        IMPORTANT: add_import_exclusion is forced to False by default. If True,
        Radarr blocklists this movie permanently — Jellyseerr re-requests would
        be silently rejected. Always keep this False for a Jellyseerr-friendly flow.
        """
        async with self._client() as c:
            resp = await c.delete(
                f"/api/{self.api_version}/movie/{movie_id}",
                params={
                    "deleteFiles": "true" if delete_files else "false",
                    "addImportExclusion": "true" if add_import_exclusion else "false",
                },
            )
            resp.raise_for_status()
