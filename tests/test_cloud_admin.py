"""Tests for dbt Cloud Admin API client helpers."""

from __future__ import annotations

import pytest

from dbt_governance.cloud.admin import AdminClient


class StubHTTPClient:
    def __init__(self):
        self.urls: list[str] = []

    async def get(self, url: str) -> dict:
        self.urls.append(url)
        return {"data": []}


@pytest.mark.asyncio
async def test_test_connection_uses_projects_endpoint():
    http = StubHTTPClient()
    admin = AdminClient("https://example.us1.dbt.com", 12345, http)  # type: ignore[arg-type]

    assert await admin.test_connection() is True
    assert http.urls == ["https://example.us1.dbt.com/api/v3/accounts/12345/projects/"]
