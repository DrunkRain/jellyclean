from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class TestResult:
    success: bool
    message: str
    details: dict[str, Any]


class BaseClient:
    """Common HTTP plumbing for the *arr / Jellyfin / Jellyseerr clients."""

    name: str = "service"
    timeout_seconds: float = 10.0

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _auth_headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._auth_headers(),
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        async with self._client() as c:
            resp = await c.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp

    async def get(self, path: str, **kwargs) -> Any:
        resp = await self._request("GET", path, **kwargs)
        return resp.json()

    async def test_connection(self) -> TestResult:
        """Override per-client. Must validate both reachability AND auth."""
        raise NotImplementedError


def classify_error(exc: Exception, service: str) -> TestResult:
    """Build a uniform TestResult from an exception during a connection test."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return TestResult(
                success=False,
                message=f"Auth refusée par {service} (HTTP {code}). Vérifie la clé API.",
                details={"status_code": code},
            )
        return TestResult(
            success=False,
            message=f"{service} a répondu HTTP {code}.",
            details={"status_code": code},
        )
    if isinstance(exc, httpx.ConnectError):
        return TestResult(
            success=False,
            message=f"Connexion impossible à {service}. Vérifie l'URL et que le service est joignable.",
            details={"error_type": "ConnectError"},
        )
    if isinstance(exc, httpx.TimeoutException):
        return TestResult(
            success=False,
            message=f"Timeout en contactant {service}.",
            details={"error_type": "Timeout"},
        )
    return TestResult(
        success=False,
        message=f"Erreur inattendue : {exc.__class__.__name__}: {exc}",
        details={"error_type": exc.__class__.__name__},
    )
