from app.clients.base import BaseClient, TestResult, classify_error


class RadarrClient(BaseClient):
    name = "Radarr"
    api_version = "v3"

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
