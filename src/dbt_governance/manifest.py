"""Local manifest.json parser — fallback mode for environments without dbt Cloud API access."""

from __future__ import annotations

import json
from pathlib import Path

from dbt_governance.cloud.models import (
    ColumnInfo,
    DAG,
    ExposureNode,
    ManifestData,
    MetricNode,
    ModelNode,
    SourceNode,
    TestInfo,
)


def load_manifest(path: Path | str) -> ManifestData:
    """Parse a local manifest.json and produce a ManifestData."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    with open(path) as f:
        raw = json.load(f)

    return parse_manifest(raw)


def parse_manifest(raw: dict) -> ManifestData:
    """Parse a raw manifest dict into structured ManifestData."""
    raw_nodes = raw.get("nodes", {})
    raw_sources = raw.get("sources", {})
    raw_exposures = raw.get("exposures", {})
    raw_metrics = raw.get("metrics", {})

    models: dict[str, ModelNode] = {}
    tests_by_model: dict[str, list[TestInfo]] = {}
    dag_nodes: dict[str, list[str]] = {}
    dag_children: dict[str, list[str]] = {}

    test_nodes: dict[str, dict] = {}
    for uid, node in raw_nodes.items():
        if node.get("resource_type") == "test":
            test_nodes[uid] = node
            depends_on = node.get("depends_on", {}).get("nodes", [])
            for dep in depends_on:
                tests_by_model.setdefault(dep, []).append(TestInfo(
                    unique_id=uid,
                    name=node.get("name", ""),
                    column_name=node.get("column_name"),
                    test_type=node.get("test_metadata", {}).get("name"),
                ))

    for uid, node in raw_nodes.items():
        if node.get("resource_type") != "model":
            continue

        columns: dict[str, ColumnInfo] = {}
        for col_name, col_data in node.get("columns", {}).items():
            columns[col_name] = ColumnInfo(
                name=col_name,
                description=col_data.get("description", ""),
                data_type=col_data.get("data_type"),
            )

        depends_on = node.get("depends_on", {})
        dep_nodes = depends_on.get("nodes", [])
        depends_models = [d for d in dep_nodes if d.startswith("model.")]
        depends_sources = [d for d in dep_nodes if d.startswith("source.")]

        config = node.get("config", {})

        model = ModelNode(
            unique_id=uid,
            name=node.get("name", ""),
            file_path=node.get("original_file_path", node.get("path", "")),
            schema_name=node.get("schema", ""),
            database=node.get("database", ""),
            materialization=config.get("materialized", ""),
            description=node.get("description", ""),
            columns=columns,
            depends_on_models=depends_models,
            depends_on_sources=depends_sources,
            tags=node.get("tags", []),
            meta=node.get("meta", {}),
            config=config,
            tests=tests_by_model.get(uid, []),
            raw_code=node.get("raw_code", node.get("raw_sql", "")),
            compiled_code=node.get("compiled_code", node.get("compiled_sql", "")),
            contract_enforced=config.get("contract", {}).get("enforced", False),
            access=node.get("access"),
            group=node.get("group"),
        )
        model.layer = model.infer_layer()
        models[uid] = model

        dag_nodes[uid] = depends_models + depends_sources

    sources: dict[str, SourceNode] = {}
    for uid, node in raw_sources.items():
        sources[uid] = SourceNode(
            unique_id=uid,
            name=node.get("name", ""),
            source_name=node.get("source_name", ""),
            description=node.get("description", ""),
            schema_name=node.get("schema", ""),
            database=node.get("database", ""),
            loaded_at_field=node.get("loaded_at_field"),
            tags=node.get("tags", []),
            meta=node.get("meta", {}),
        )
        dag_nodes.setdefault(uid, [])

    for uid in models:
        dag_children.setdefault(uid, [])
    for uid, parents in dag_nodes.items():
        for parent in parents:
            dag_children.setdefault(parent, [])
            if uid not in dag_children[parent]:
                dag_children[parent].append(uid)

    exposures: dict[str, ExposureNode] = {}
    for uid, node in raw_exposures.items():
        dep_nodes = node.get("depends_on", {}).get("nodes", [])
        exposures[uid] = ExposureNode(
            unique_id=uid,
            name=node.get("name", ""),
            description=node.get("description", ""),
            depends_on=dep_nodes,
            owner_name=node.get("owner", {}).get("name"),
            owner_email=node.get("owner", {}).get("email"),
        )

    metrics: dict[str, MetricNode] = {}
    for uid, node in raw_metrics.items():
        dep_nodes = node.get("depends_on", {}).get("nodes", [])
        metrics[uid] = MetricNode(
            unique_id=uid,
            name=node.get("name", ""),
            description=node.get("description", ""),
            depends_on=dep_nodes,
        )

    return ManifestData(
        models=models,
        sources=sources,
        tests={},
        exposures=exposures,
        metrics=metrics,
        dag=DAG(nodes=dag_nodes, children=dag_children),
    )
