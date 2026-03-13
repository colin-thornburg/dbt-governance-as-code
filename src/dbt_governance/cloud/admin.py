"""dbt Cloud Admin API v3 (REST) client.

Used for downloading run artifacts and querying job/environment metadata.
"""

from __future__ import annotations

from dbt_governance.cloud.client import CloudHTTPClient


class AdminClient:
    """REST client for the dbt Cloud Admin API v3."""

    def __init__(self, base_url: str, account_id: int, http_client: CloudHTTPClient):
        self.base_url = base_url.rstrip("/")
        self.account_id = account_id
        self.http = http_client

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v3/accounts/{self.account_id}/{path}"

    async def get_run_artifact(self, run_id: int, path: str) -> dict:
        """Download an artifact from a completed run (manifest.json, run_results.json, etc.)."""
        url = self._url(f"runs/{run_id}/artifacts/{path}")
        return await self.http.get(url)

    async def list_jobs(self, environment_id: int | None = None) -> list[dict]:
        """List jobs, optionally filtered by environment."""
        url = self._url("jobs/")
        if environment_id:
            url += f"?environment_id={environment_id}"
        data = await self.http.get(url)
        return data.get("data", [])

    async def get_environment(self, environment_id: int) -> dict:
        """Get environment metadata."""
        url = self._url(f"environments/{environment_id}/")
        data = await self.http.get(url)
        return data.get("data", {})

    async def get_most_recent_run(self, job_id: int) -> dict | None:
        """Get the most recent run for a job."""
        url = self._url(f"runs/?job_definition_id={job_id}&order_by=-created_at&limit=1")
        data = await self.http.get(url)
        runs = data.get("data", [])
        return runs[0] if runs else None

    async def download_manifest(self, run_id: int) -> dict:
        """Download manifest.json from a completed run."""
        return await self.get_run_artifact(run_id, "manifest.json")

    async def test_connection(self) -> bool:
        """Test connectivity to the Admin API."""
        try:
            url = self._url("")
            await self.http.get(url)
            return True
        except Exception:
            return False
