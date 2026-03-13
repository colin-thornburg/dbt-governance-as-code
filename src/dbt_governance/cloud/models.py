"""Pydantic models for dbt Cloud API responses and unified data types."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ColumnInfo(BaseModel):
    name: str
    description: str = ""
    data_type: str | None = None


class ExecutionInfo(BaseModel):
    """Execution metadata from dbt Cloud — not available in local mode."""
    last_run_status: str | None = None
    execution_time: float | None = None
    last_run_at: str | None = None
    last_success_run_id: int | None = None


class TestInfo(BaseModel):
    """Test attached to a model."""
    unique_id: str
    name: str
    column_name: str | None = None
    status: str | None = None
    error_message: str | None = None
    test_type: str | None = None  # "generic" or "singular"


class FreshnessInfo(BaseModel):
    max_loaded_at: str | None = None
    freshness_status: str | None = None


class ModelNode(BaseModel):
    unique_id: str
    name: str
    resource_type: str = "model"
    file_path: str = ""
    schema_name: str = ""
    database: str = ""
    materialization: str = ""
    description: str = ""
    columns: dict[str, ColumnInfo] = Field(default_factory=dict)
    depends_on_models: list[str] = Field(default_factory=list)
    depends_on_sources: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)
    tests: list[TestInfo] = Field(default_factory=list)
    raw_code: str = ""
    compiled_code: str = ""
    layer: str = ""  # Inferred: staging, intermediate, marts
    contract_enforced: bool = False
    access: str | None = None
    group: str | None = None
    execution_info: ExecutionInfo | None = None
    children: list[str] = Field(default_factory=list)

    def infer_layer(self) -> str:
        """Infer the model's layer from its file path or name."""
        fp = self.file_path.lower()
        name = self.name.lower()
        if "/staging/" in fp or name.startswith("stg_"):
            return "staging"
        if "/intermediate/" in fp or name.startswith("int_"):
            return "intermediate"
        if "/marts/" in fp or name.startswith(("fct_", "dim_")):
            return "marts"
        return "other"


class SourceNode(BaseModel):
    unique_id: str
    name: str
    source_name: str
    description: str = ""
    schema_name: str = ""
    database: str = ""
    freshness: FreshnessInfo | None = None
    loaded_at_field: str | None = None
    tags: list[str] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


class ExposureNode(BaseModel):
    unique_id: str
    name: str
    description: str = ""
    depends_on: list[str] = Field(default_factory=list)
    owner_name: str | None = None
    owner_email: str | None = None


class MetricNode(BaseModel):
    unique_id: str
    name: str
    description: str = ""
    depends_on: list[str] = Field(default_factory=list)


class CloudMetadata(BaseModel):
    """Metadata only available when scanning via dbt Cloud APIs."""
    environment_id: int
    account_id: int
    total_models: int = 0
    total_sources: int = 0
    total_tests: int = 0
    scan_timestamp: str = ""
    state_type: str = "applied"


class DAG(BaseModel):
    """Directed acyclic graph of model dependencies."""
    nodes: dict[str, list[str]] = Field(default_factory=dict)     # node_id -> parent node_ids
    children: dict[str, list[str]] = Field(default_factory=dict)  # node_id -> child node_ids

    def depth(self, node_id: str, _visited: set[str] | None = None) -> int:
        """Calculate max depth (longest path to a root) for a node."""
        if _visited is None:
            _visited = set()
        if node_id in _visited:
            return 0
        _visited.add(node_id)
        parents = self.nodes.get(node_id, [])
        if not parents:
            return 0
        return 1 + max(self.depth(p, _visited) for p in parents)

    def ancestors(self, node_id: str, _visited: set[str] | None = None) -> set[str]:
        """Get all ancestors of a node."""
        if _visited is None:
            _visited = set()
        parents = self.nodes.get(node_id, [])
        for p in parents:
            if p not in _visited:
                _visited.add(p)
                self.ancestors(p, _visited)
        return _visited

    def descendants(self, node_id: str, _visited: set[str] | None = None) -> set[str]:
        """Get all descendants of a node."""
        if _visited is None:
            _visited = set()
        kids = self.children.get(node_id, [])
        for c in kids:
            if c not in _visited:
                _visited.add(c)
                self.descendants(c, _visited)
        return _visited

    def fanout(self, node_id: str) -> int:
        """Number of direct children."""
        return len(self.children.get(node_id, []))

    def find_diamonds(self) -> list[tuple[str, str, str]]:
        """Find diamond dependency patterns (A -> B -> D, A -> C -> D)."""
        diamonds = []
        for node_id, parents in self.nodes.items():
            if len(parents) < 2:
                continue
            for i, p1 in enumerate(parents):
                p1_ancestors = self.ancestors(p1)
                for p2 in parents[i + 1:]:
                    p2_ancestors = self.ancestors(p2)
                    shared = p1_ancestors & p2_ancestors
                    if shared:
                        diamonds.append((node_id, p1, p2))
        return diamonds


class ManifestData(BaseModel):
    """Unified representation of dbt project metadata for governance checks.
    Populated from either dbt Cloud APIs or a local manifest.json."""
    models: dict[str, ModelNode] = Field(default_factory=dict)
    sources: dict[str, SourceNode] = Field(default_factory=dict)
    tests: dict[str, TestInfo] = Field(default_factory=dict)
    exposures: dict[str, ExposureNode] = Field(default_factory=dict)
    metrics: dict[str, MetricNode] = Field(default_factory=dict)
    dag: DAG = Field(default_factory=DAG)
    cloud_metadata: CloudMetadata | None = None
