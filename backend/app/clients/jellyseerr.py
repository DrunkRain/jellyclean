from app.clients.base import BaseClient, TestResult, classify_error


class JellyseerrClient(BaseClient):
    name = "Jellyseerr"

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
