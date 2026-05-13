from typing import Any

from app.clients.base import BaseClient, TestResult, classify_error

# Fields we always want from /Items — adjust here if we need more later.
ITEM_FIELDS_MOVIE = "DateCreated,ProviderIds,MediaSources,UserData,Path,Genres"
ITEM_FIELDS_SERIES = "DateCreated,ProviderIds,UserData,Path,Genres,Status"


class JellyfinClient(BaseClient):
    name = "Jellyfin"
    timeout_seconds = 30.0  # library queries can be slow on big servers

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f'MediaBrowser Token="{self.api_key}"',
            "Accept": "application/json",
        }

    async def test_connection(self) -> TestResult:
        try:
            data = await self.get("/System/Info")
        except Exception as exc:
            return classify_error(exc, self.name)

        server_name = data.get("ServerName", "?")
        version = data.get("Version", "?")
        return TestResult(
            success=True,
            message=f"Connecté à {server_name} (Jellyfin v{version})",
            details={"server_name": server_name, "version": version, "id": data.get("Id")},
        )

    async def list_users(self) -> list[dict[str, Any]]:
        """All users on the server. Used to aggregate last-played across users."""
        return await self.get("/Users")

    async def list_movies(self) -> list[dict[str, Any]]:
        """Admin view of every Movie in the library, with provider IDs + media sources."""
        data = await self.get(
            "/Items",
            params={
                "Recursive": "true",
                "IncludeItemTypes": "Movie",
                "Fields": ITEM_FIELDS_MOVIE,
            },
        )
        return data.get("Items", [])

    async def list_series(self) -> list[dict[str, Any]]:
        """Admin view of every Series in the library, with provider IDs + Status."""
        data = await self.get(
            "/Items",
            params={
                "Recursive": "true",
                "IncludeItemTypes": "Series",
                "Fields": ITEM_FIELDS_SERIES,
            },
        )
        return data.get("Items", [])

    async def list_user_played(self, user_id: str) -> list[dict[str, Any]]:
        """Items (movies + series) that a given user has played at least once.

        Returns each item with its per-user UserData (LastPlayedDate, PlayCount).
        Series UserData on Jellyfin reflects 'last episode played' for that user.
        """
        data = await self.get(
            f"/Users/{user_id}/Items",
            params={
                "Recursive": "true",
                "IncludeItemTypes": "Movie,Series",
                "Fields": "UserData",
                "Filters": "IsPlayed",
            },
        )
        return data.get("Items", [])

    # ===== Collection (BoxSet) management =====

    async def find_collection_by_name(self, name: str) -> dict[str, Any] | None:
        """Locate a Collection (BoxSet) by exact display name. Returns None if not found."""
        data = await self.get(
            "/Items",
            params={
                "Recursive": "true",
                "IncludeItemTypes": "BoxSet",
                "SearchTerm": name,
            },
        )
        for it in data.get("Items", []):
            if (it.get("Name") or "").strip().lower() == name.strip().lower():
                return it
        return None

    async def create_collection(self, name: str, item_ids: list[str]) -> dict[str, Any]:
        """Create a Collection. Jellyfin requires at least one seed item id."""
        if not item_ids:
            raise ValueError("create_collection needs at least one item id")
        async with self._client() as c:
            resp = await c.post(
                "/Collections",
                params={"name": name, "ids": ",".join(item_ids)},
            )
            resp.raise_for_status()
            return resp.json()

    async def add_to_collection(self, collection_id: str, item_ids: list[str]) -> None:
        if not item_ids:
            return
        async with self._client() as c:
            resp = await c.post(
                f"/Collections/{collection_id}/Items",
                params={"ids": ",".join(item_ids)},
            )
            resp.raise_for_status()

    async def remove_from_collection(self, collection_id: str, item_ids: list[str]) -> None:
        if not item_ids:
            return
        async with self._client() as c:
            resp = await c.delete(
                f"/Collections/{collection_id}/Items",
                params={"ids": ",".join(item_ids)},
            )
            resp.raise_for_status()

    async def list_collection_items(self, collection_id: str) -> list[dict[str, Any]]:
        """Items currently inside a given Collection."""
        data = await self.get(
            "/Items",
            params={"ParentId": collection_id, "Recursive": "true"},
        )
        return data.get("Items", [])
