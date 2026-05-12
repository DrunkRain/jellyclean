from app.clients.base import BaseClient, TestResult, classify_error


class JellyfinClient(BaseClient):
    name = "Jellyfin"

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
