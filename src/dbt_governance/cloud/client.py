"""Base HTTP client with auth and retry logic for dbt Cloud APIs."""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3


def get_api_token() -> str:
    """Resolve the dbt Cloud API token from environment."""
    token = os.environ.get("DBT_CLOUD_API_TOKEN", "")
    if not token:
        raise EnvironmentError(
            "DBT_CLOUD_API_TOKEN environment variable is not set. "
            "Generate a service token in dbt Cloud: Account Settings → Service Tokens"
        )
    return token


class CloudHTTPClient:
    """Thin wrapper around httpx with auth headers and retries."""

    def __init__(self, token: str | None = None, timeout: float = DEFAULT_TIMEOUT):
        self.token = token or get_api_token()
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "authorization": f"Bearer {self.token}",
                    "content-type": "application/json",
                },
            )
        return self._client

    async def graphql(self, url: str, query: str, variables: dict[str, Any] | None = None) -> dict:
        """Execute a GraphQL query against the Discovery API."""
        client = await self._get_client()
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                if "errors" in data:
                    raise RuntimeError(f"GraphQL errors: {data['errors']}")
                return data.get("data", {})
            except (httpx.HTTPStatusError, httpx.ConnectError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    continue
        raise last_error  # type: ignore[misc]

    async def get(self, url: str) -> dict:
        """Execute a GET request against the Admin API."""
        client = await self._get_client()
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.ConnectError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    continue
        raise last_error  # type: ignore[misc]

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
