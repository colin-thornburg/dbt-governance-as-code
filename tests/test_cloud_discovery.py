"""Tests for dbt Cloud Discovery API manifest loading."""

from __future__ import annotations

import pytest

from dbt_governance.cloud.discovery import DiscoveryClient


class _FakeHTTPClient:
    async def graphql(self, url: str, query: str, variables: dict | None = None) -> dict:
        if "lineage(" in query:
            return {
                "environment": {
                    "applied": {
                        "lineage": [
                            {
                                "uniqueId": "model.test.stg_orders",
                                "parentIds": ["source.test.ecommerce.raw_orders"],
                            },
                            {
                                "uniqueId": "model.test.int_orders",
                                "parentIds": ["model.test.stg_orders"],
                            },
                        ]
                    }
                }
            }

        if "models(first:" in query:
            return {
                "environment": {
                    "applied": {
                        "models": {
                            "edges": [
                                {
                                    "node": {
                                        "uniqueId": "model.test.stg_orders",
                                        "name": "stg_orders",
                                        "description": "",
                                        "rawCode": "select * from {{ source('ecommerce', 'raw_orders') }}",
                                        "compiledCode": "select * from raw_orders",
                                        "database": "analytics",
                                        "schema": "staging",
                                        "alias": "stg_orders",
                                        "materializedType": "view",
                                        "filePath": "models/staging/stg_orders.sql",
                                        "tags": [],
                                        "meta": {},
                                        "contractEnforced": False,
                                        "access": None,
                                        "group": None,
                                        "executionInfo": None,
                                        "tests": [],
                                        "catalog": {"columns": []},
                                        "ancestors": [
                                            {
                                                "sourceName": "ecommerce",
                                                "name": "raw_orders",
                                                "uniqueId": "source.test.ecommerce.raw_orders",
                                                "resourceType": "source",
                                                "freshness": None,
                                            }
                                        ],
                                        "children": [
                                            {
                                                "name": "int_orders",
                                                "uniqueId": "model.test.int_orders",
                                                "resourceType": "model",
                                            }
                                        ],
                                    }
                                },
                                {
                                    "node": {
                                        "uniqueId": "model.test.int_orders",
                                        "name": "int_orders",
                                        "description": "",
                                        "rawCode": "select * from {{ ref('stg_orders') }}",
                                        "compiledCode": "select * from stg_orders",
                                        "database": "analytics",
                                        "schema": "intermediate",
                                        "alias": "int_orders",
                                        "materializedType": "view",
                                        "filePath": "models/intermediate/int_orders.sql",
                                        "tags": [],
                                        "meta": {},
                                        "contractEnforced": False,
                                        "access": None,
                                        "group": None,
                                        "executionInfo": None,
                                        "tests": [],
                                        "catalog": {"columns": []},
                                        # This intentionally includes the transitive source ancestor.
                                        "ancestors": [
                                            {
                                                "name": "stg_orders",
                                                "uniqueId": "model.test.stg_orders",
                                                "resourceType": "model",
                                            },
                                            {
                                                "sourceName": "ecommerce",
                                                "name": "raw_orders",
                                                "uniqueId": "source.test.ecommerce.raw_orders",
                                                "resourceType": "source",
                                                "freshness": None,
                                            },
                                        ],
                                        "children": [],
                                    }
                                },
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "totalCount": 2,
                        }
                    }
                }
            }

        if "sources(first:" in query:
            return {
                "environment": {
                    "applied": {
                        "sources": {
                            "edges": [
                                {
                                    "node": {
                                        "uniqueId": "source.test.ecommerce.raw_orders",
                                        "name": "raw_orders",
                                        "sourceName": "ecommerce",
                                        "description": "",
                                        "database": "raw",
                                        "schema": "ecommerce",
                                        "tags": [],
                                        "meta": {},
                                        "loader": "fivetran",
                                        "freshness": None,
                                    }
                                }
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "totalCount": 1,
                        }
                    }
                }
            }

        if "exposures(first:" in query:
            return {
                "environment": {
                    "applied": {
                        "exposures": {
                            "edges": [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                }
            }

        raise AssertionError(f"Unexpected query: {query}")


@pytest.mark.asyncio
async def test_discovery_client_uses_direct_lineage_not_transitive_ancestors():
    client = DiscoveryClient("https://metadata.cloud.getdbt.com/graphql", _FakeHTTPClient())

    manifest = await client.fetch_manifest_data(environment_id=123, account_id=456)

    stg_orders = manifest.models["model.test.stg_orders"]
    int_orders = manifest.models["model.test.int_orders"]

    assert stg_orders.depends_on_sources == ["source.test.ecommerce.raw_orders"]
    assert stg_orders.depends_on_models == []
    assert int_orders.depends_on_models == ["model.test.stg_orders"]
    assert int_orders.depends_on_sources == []

    assert manifest.dag.nodes["model.test.int_orders"] == ["model.test.stg_orders"]
    assert manifest.dag.children["source.test.ecommerce.raw_orders"] == ["model.test.stg_orders"]
    assert manifest.dag.children["model.test.stg_orders"] == ["model.test.int_orders"]
