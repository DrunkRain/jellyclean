from typing import Any

from app.clients.base import BaseClient, TestResult, classify_error


class SonarrClient(BaseClient):
    name = "Sonarr"
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
        instance_name = data.get("instanceName", "Sonarr")
        return TestResult(
            success=True,
            message=f"Connecté à {instance_name} (v{version})",
            details={"version": version, "instance_name": instance_name},
        )

    async def list_series(self) -> list[dict[str, Any]]:
        """All series known to Sonarr. Status field tells us 'continuing' vs 'ended'."""
        return await self.get(f"/api/{self.api_version}/series")
