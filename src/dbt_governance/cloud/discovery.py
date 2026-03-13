"""dbt Cloud Discovery API (GraphQL) client.

Queries the environment-level endpoint for applied and definition state
of models, sources, tests, exposures, and lineage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dbt_governance.cloud.client import CloudHTTPClient
from dbt_governance.cloud.models import (
    CloudMetadata,
    ColumnInfo,
    DAG,
    ExecutionInfo,
    ExposureNode,
    FreshnessInfo,
    ManifestData,
    MetricNode,
    ModelNode,
    SourceNode,
    TestInfo,
)

MODELS_QUERY = """\
query GovernanceModels($environmentId: BigInt!, $first: Int!, $after: String) {
  environment(id: $environmentId) {
    applied {
      models(first: $first, after: $after) {
        edges {
          node {
            uniqueId
            name
            description
            rawCode
            compiledCode
            database
            schema
            alias
            materializedType
            filePath
            tags
            meta
            contractEnforced
            access
            group
            executionInfo {
              lastRunStatus
              executionTime
              executeCompletedAt
              lastSuccessRunId
            }
            tests {
              name
              columnName
              executionInfo {
                lastRunStatus
                lastRunError
              }
            }
            catalog {
              columns { name, description, type }
            }
            ancestors(types: [Model, Source]) {
              ... on ModelAppliedStateNestedNode {
                name
                uniqueId
                resourceType
              }
              ... on SourceAppliedStateNestedNode {
                sourceName
                name
                uniqueId
                resourceType
                freshness { maxLoadedAt, freshnessStatus }
              }
            }
            children {
              name
              uniqueId
              resourceType
            }
          }
        }
        pageInfo { hasNextPage, endCursor }
        totalCount
      }
    }
  }
}
"""

SOURCES_QUERY = """\
query GovernanceSources($environmentId: BigInt!, $first: Int!, $after: String) {
  environment(id: $environmentId) {
    applied {
      sources(first: $first, after: $after) {
        edges {
          node {
            uniqueId
            name
            sourceName
            description
            database
            schema
            tags
            meta
            loader
            freshness { maxLoadedAt, freshnessStatus }
          }
        }
        pageInfo { hasNextPage, endCursor }
        totalCount
      }
    }
  }
}
"""

EXPOSURES_QUERY = """\
query GovernanceExposures($environmentId: BigInt!, $first: Int!, $after: String) {
  environment(id: $environmentId) {
    applied {
      exposures(first: $first, after: $after) {
        edges {
          node {
            uniqueId
            name
            description
            ownerName
            ownerEmail
            parents { uniqueId }
          }
        }
        pageInfo { hasNextPage, endCursor }
      }
    }
  }
}
"""

PAGE_SIZE = 500


class DiscoveryClient:
    """GraphQL client for the dbt Cloud Discovery API."""

    def __init__(self, api_url: str, http_client: CloudHTTPClient):
        self.api_url = api_url
        self.http = http_client

    async def _paginate(self, query: str, env_id: int, resource_key: str) -> list[dict]:
        """Paginate through a Discovery API query, collecting all nodes."""
        all_nodes: list[dict] = []
        cursor: str | None = None

        while True:
            variables: dict[str, Any] = {"environmentId": env_id, "first": PAGE_SIZE}
            if cursor:
                variables["after"] = cursor

            data = await self.http.graphql(self.api_url, query, variables)
            applied = data.get("environment", {}).get("applied", {})
            resource = applied.get(resource_key, {})
            edges = resource.get("edges", [])

            all_nodes.extend(edge["node"] for edge in edges)

            page_info = resource.get("pageInfo", {})
            if not page_info.get("hasNextPage", False):
                break
            cursor = page_info.get("endCursor")

        return all_nodes

    async def fetch_manifest_data(self, environment_id: int, account_id: int) -> ManifestData:
        """Fetch all project metadata from the Discovery API and build a ManifestData."""
        raw_models = await self._paginate(MODELS_QUERY, environment_id, "models")
        raw_sources = await self._paginate(SOURCES_QUERY, environment_id, "sources")
        raw_exposures = await self._paginate(EXPOSURES_QUERY, environment_id, "exposures")

        models: dict[str, ModelNode] = {}
        dag_nodes: dict[str, list[str]] = {}
        dag_children: dict[str, list[str]] = {}

        for raw in raw_models:
            uid = raw["uniqueId"]

            columns: dict[str, ColumnInfo] = {}
            catalog_cols = (raw.get("catalog") or {}).get("columns") or []
            for col in catalog_cols:
                columns[col["name"]] = ColumnInfo(
                    name=col["name"],
                    description=col.get("description") or "",
                    data_type=col.get("type"),
                )

            depends_models = []
            depends_sources = []
            ancestors = raw.get("ancestors") or []
            for anc in ancestors:
                rt = anc.get("resourceType", "")
                if rt == "model":
                    depends_models.append(anc["uniqueId"])
                elif rt == "source":
                    depends_sources.append(anc["uniqueId"])

            child_ids = [c["uniqueId"] for c in (raw.get("children") or [])]

            tests: list[TestInfo] = []
            for t in raw.get("tests") or []:
                exec_info = t.get("executionInfo") or {}
                tests.append(TestInfo(
                    unique_id=f"test.{t['name']}",
                    name=t["name"],
                    column_name=t.get("columnName"),
                    status=exec_info.get("lastRunStatus"),
                    error_message=exec_info.get("lastRunError"),
                ))

            exec_raw = raw.get("executionInfo") or {}
            execution_info = ExecutionInfo(
                last_run_status=exec_raw.get("lastRunStatus"),
                execution_time=exec_raw.get("executionTime"),
                last_run_at=exec_raw.get("executeCompletedAt"),
                last_success_run_id=exec_raw.get("lastSuccessRunId"),
            ) if exec_raw else None

            model = ModelNode(
                unique_id=uid,
                name=raw["name"],
                file_path=raw.get("filePath", ""),
                schema_name=raw.get("schema", ""),
                database=raw.get("database", ""),
                materialization=raw.get("materializedType", ""),
                description=raw.get("description", ""),
                columns=columns,
                depends_on_models=depends_models,
                depends_on_sources=depends_sources,
                tags=raw.get("tags") or [],
                meta=raw.get("meta") or {},
                config={},
                tests=tests,
                raw_code=raw.get("rawCode", ""),
                compiled_code=raw.get("compiledCode", ""),
                contract_enforced=raw.get("contractEnforced", False),
                access=raw.get("access"),
                group=raw.get("group"),
                execution_info=execution_info,
                children=child_ids,
            )
            model.layer = model.infer_layer()
            models[uid] = model

            dag_nodes[uid] = depends_models + depends_sources
            dag_children[uid] = child_ids

        sources: dict[str, SourceNode] = {}
        for raw in raw_sources:
            uid = raw["uniqueId"]
            freshness_raw = raw.get("freshness")
            freshness = FreshnessInfo(
                max_loaded_at=freshness_raw.get("maxLoadedAt"),
                freshness_status=freshness_raw.get("freshnessStatus"),
            ) if freshness_raw else None

            sources[uid] = SourceNode(
                unique_id=uid,
                name=raw["name"],
                source_name=raw.get("sourceName", ""),
                description=raw.get("description", ""),
                schema_name=raw.get("schema", ""),
                database=raw.get("database", ""),
                freshness=freshness,
                tags=raw.get("tags") or [],
                meta=raw.get("meta") or {},
            )
            dag_nodes.setdefault(uid, [])

        exposures: dict[str, ExposureNode] = {}
        for raw in raw_exposures:
            uid = raw["uniqueId"]
            parent_ids = [p["uniqueId"] for p in (raw.get("parents") or [])]
            exposures[uid] = ExposureNode(
                unique_id=uid,
                name=raw["name"],
                description=raw.get("description", ""),
                depends_on=parent_ids,
                owner_name=raw.get("ownerName"),
                owner_email=raw.get("ownerEmail"),
            )

        dag = DAG(nodes=dag_nodes, children=dag_children)

        return ManifestData(
            models=models,
            sources=sources,
            tests={},
            exposures=exposures,
            metrics={},
            dag=dag,
            cloud_metadata=CloudMetadata(
                environment_id=environment_id,
                account_id=account_id,
                total_models=len(models),
                total_sources=len(sources),
                total_tests=sum(len(m.tests) for m in models.values()),
                scan_timestamp=datetime.now(timezone.utc).isoformat(),
                state_type="applied",
            ),
        )
