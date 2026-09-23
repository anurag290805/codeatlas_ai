"""
Repository dependency graph API routes for CodeAtlas AI.

This router exposes read-only REST endpoints over repository dependency
graphs: full graph retrieval, node/edge listing, node detail lookup,
traversal (neighbors, ancestors, descendants), shortest-path queries,
statistics, and health/status. Every graph operation is delegated to
``GraphService``; this module contains no graph-building or traversal
logic of its own.

Graphs are constructed elsewhere in the indexing pipeline. If a repository
has not yet been indexed into a graph, endpoints here respond with a 404
rather than building one on demand.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.core.auth import get_workspace_id
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.graph_builder import (
    GraphError,
    GraphNode,
    GraphNotFoundError,
    GraphService,
    GraphStatistics,
    get_graph_service as get_shared_graph_service,
    NodeNotFoundError,
    NodeType,
    RelationshipType,
)
from app.db import crud
from app.db.database import get_db
from app.core.workspace import ensure_workspace
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/repositories/{repository_id}/graph", tags=["graph"], dependencies=[Depends(ensure_workspace)])

def get_graph_service() -> GraphService:
    """FastAPI dependency returning the shared ``GraphService`` instance."""
    return get_shared_graph_service()


# ----------------------------------------------------------------------
# Response schemas
# ----------------------------------------------------------------------


class GraphNodeResponse(BaseModel):
    """A single repository graph node, ready for frontend consumption."""

    id: str
    repository_id: str
    type: str
    name: str
    file_path: str | None
    symbol_type: str | None
    language: str | None
    start_line: int | None
    end_line: int | None
    parent_node_id: str | None
    metadata: dict = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, node: GraphNode) -> "GraphNodeResponse":
        return cls(**node.to_serializable())


class GraphEdgeResponse(BaseModel):
    """A single repository graph edge, ready for frontend consumption."""

    source: str
    target: str
    relationship: str
    weight: float
    metadata: dict = Field(default_factory=dict)


class RepositoryGraphResponse(BaseModel):
    """The complete serialized dependency graph for a repository."""

    repository_id: str
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]


class GraphStatisticsResponse(BaseModel):
    """Aggregate structural statistics for a repository's graph."""

    total_nodes: int
    total_edges: int
    density: float
    isolated_node_count: int
    connected_component_count: int
    relationship_counts: dict[str, int]

    @classmethod
    def from_domain(cls, stats: GraphStatistics) -> "GraphStatisticsResponse":
        return cls(
            total_nodes=stats.total_nodes,
            total_edges=stats.total_edges,
            density=stats.density,
            isolated_node_count=stats.isolated_node_count,
            connected_component_count=stats.connected_component_count,
            relationship_counts=stats.relationship_counts,
        )


class TraversalResponse(BaseModel):
    """Result of a neighbor/ancestor/descendant traversal request."""

    origin_node_id: str
    direction: Literal["incoming", "outgoing"]
    max_depth: int | None
    relationship_filter: str | None
    nodes: list[GraphNodeResponse]


class PathResponse(BaseModel):
    """Result of a shortest-path query between two nodes."""

    source_id: str
    target_id: str
    path_found: bool
    node_ids: list[str] = Field(default_factory=list)


class GraphHealthResponse(BaseModel):
    """Availability status of a repository's dependency graph."""

    repository_id: str
    graph_available: bool
    total_nodes: int | None = None
    total_edges: int | None = None


# ----------------------------------------------------------------------
# Shared dependencies / helpers
# ----------------------------------------------------------------------


def _ensure_repository_exists(db: Session, repository_id: str, workspace_id: str) -> None:
    """
    Verify a repository record exists before serving graph data for it.

    Raises:
        HTTPException: 404 if no repository with ``repository_id`` exists.
    """
    repository = crud.get_repository(db, repository_id, workspace_id=workspace_id)
    if repository is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repository_id}' was not found.",
        )


def _get_graph_or_404(graph_service: GraphService, repository_id: str):
    """
    Return the cached dependency graph for a repository or raise a 404.

    Raises:
        HTTPException: 404 if the repository has not yet been indexed into
            a dependency graph.
    """
    try:
        return graph_service.get_graph(repository_id)
    except GraphNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No dependency graph has been generated for repository "
            f"'{repository_id}'.",
        ) from exc


def _parse_relationship_type(value: str | None) -> RelationshipType | None:
    """
    Parse an optional relationship-type query parameter.

    Raises:
        HTTPException: 400 if ``value`` does not match a known relationship.
    """
    if value is None:
        return None
    try:
        return RelationshipType(value.strip().upper())
    except ValueError as exc:
        valid_values = ", ".join(member.value for member in RelationshipType)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid relationship type '{value}'. Valid values: {valid_values}.",
        ) from exc


def _parse_relationship_types(value: str | None) -> set[RelationshipType] | None:
    """
    Parse an optional comma-separated list of relationship types.

    Raises:
        HTTPException: 400 if any entry does not match a known relationship.
    """
    if value is None:
        return None
    return {_parse_relationship_type(entry) for entry in value.split(",") if entry.strip()}


def _parse_node_type(value: str | None) -> NodeType | None:
    """
    Parse an optional node-type query parameter.

    Raises:
        HTTPException: 400 if ``value`` does not match a known node type.
    """
    if value is None:
        return None
    try:
        return NodeType(value.strip().lower())
    except ValueError as exc:
        valid_values = ", ".join(member.value for member in NodeType)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid node type '{value}'. Valid values: {valid_values}.",
        ) from exc


def _to_node_responses(nodes: list[GraphNode]) -> list[GraphNodeResponse]:
    return [GraphNodeResponse.from_domain(node) for node in nodes]


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------


@router.get(
    "",
    response_model=RepositoryGraphResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a repository's full dependency graph",
    description="Returns the complete serialized dependency graph (all "
    "nodes and edges) for a repository, suitable for direct consumption by "
    "a frontend graph visualization library.",
)
async def get_repository_graph(
    repository_id: str,
    db: Session = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
    workspace_id: str = Depends(get_workspace_id),
) -> RepositoryGraphResponse:
    _ensure_repository_exists(db, repository_id, workspace_id)
    logger.info("Full graph requested for repository '%s'.", repository_id)

    try:
        serialized = graph_service.serialize(repository_id)
    except GraphNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No dependency graph has been generated for repository "
            f"'{repository_id}'.",
        ) from exc
    except GraphError as exc:
        logger.error("Graph serialization failed for '%s': %s", repository_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to serialize the repository graph.",
        ) from exc

    return RepositoryGraphResponse(
        repository_id=serialized["repository_id"],
        nodes=[GraphNodeResponse(**node) for node in serialized["nodes"]],
        edges=[GraphEdgeResponse(**edge) for edge in serialized["edges"]],
    )


@router.get(
    "/statistics",
    response_model=GraphStatisticsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve graph statistics",
    description="Returns aggregate structural statistics for a repository's "
    "dependency graph, such as node/edge counts, density, and connected "
    "components.",
)
async def get_graph_statistics(
    repository_id: str,
    db: Session = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
    workspace_id: str = Depends(get_workspace_id),
) -> GraphStatisticsResponse:
    _ensure_repository_exists(db, repository_id, workspace_id)
    logger.info("Graph statistics requested for repository '%s'.", repository_id)

    graph = _get_graph_or_404(graph_service, repository_id)
    return GraphStatisticsResponse.from_domain(graph.statistics())


@router.get(
    "/nodes",
    response_model=list[GraphNodeResponse],
    status_code=status.HTTP_200_OK,
    summary="List graph nodes",
    description="Returns nodes from a repository's dependency graph, "
    "optionally filtered by file path, symbol name, or node type.",
)
async def list_graph_nodes(
    repository_id: str,
    file_path: str | None = Query(default=None, description="Filter nodes by file path."),
    symbol_name: str | None = Query(default=None, description="Filter nodes by symbol name."),
    node_type: str | None = Query(default=None, description="Filter nodes by node type."),
    db: Session = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
    workspace_id: str = Depends(get_workspace_id),
) -> list[GraphNodeResponse]:
    _ensure_repository_exists(db, repository_id, workspace_id)
    graph = _get_graph_or_404(graph_service, repository_id)

    if file_path is not None:
        nodes = graph.find_by_file(file_path)
    elif symbol_name is not None:
        nodes = graph.find_by_symbol(symbol_name)
    elif node_type is not None:
        nodes = graph.find_by_node_type(_parse_node_type(node_type))
    else:
        nodes = graph.all_nodes()

    logger.info(
        "Listed %d node(s) for repository '%s' (file_path=%s, symbol_name=%s, "
        "node_type=%s).",
        len(nodes),
        repository_id,
        file_path,
        symbol_name,
        node_type,
    )
    return _to_node_responses(nodes)


@router.get(
    "/edges",
    response_model=list[GraphEdgeResponse],
    status_code=status.HTTP_200_OK,
    summary="List graph edges",
    description="Returns all relationship edges in a repository's "
    "dependency graph, optionally filtered by relationship type.",
)
async def list_graph_edges(
    repository_id: str,
    relationship: str | None = Query(
        default=None, description="Filter edges by relationship type."
    ),
    db: Session = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
    workspace_id: str = Depends(get_workspace_id),
) -> list[GraphEdgeResponse]:
    _ensure_repository_exists(db, repository_id, workspace_id)
    graph = _get_graph_or_404(graph_service, repository_id)
    relationship_type = _parse_relationship_type(relationship)

    edges = graph.all_edges()
    if relationship_type is not None:
        edges = [edge for edge in edges if edge.relationship is relationship_type]

    logger.info(
        "Listed %d edge(s) for repository '%s' (relationship=%s).",
        len(edges),
        repository_id,
        relationship,
    )
    return [GraphEdgeResponse(**edge.to_serializable()) for edge in edges]


@router.get(
    "/nodes/{node_id}",
    response_model=GraphNodeResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a single graph node",
    description="Returns full detail for a single node in a repository's "
    "dependency graph.",
)
async def get_graph_node(
    repository_id: str,
    node_id: str,
    db: Session = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
    workspace_id: str = Depends(get_workspace_id),
) -> GraphNodeResponse:
    _ensure_repository_exists(db, repository_id, workspace_id)
    graph = _get_graph_or_404(graph_service, repository_id)

    logger.info("Node '%s' requested for repository '%s'.", node_id, repository_id)

    try:
        node = graph.get_node(node_id)
    except NodeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' was not found in repository '{repository_id}'.",
        ) from exc

    return GraphNodeResponse.from_domain(node)


@router.get(
    "/neighbors/{node_id}",
    response_model=TraversalResponse,
    status_code=status.HTTP_200_OK,
    summary="Explore nodes related to a given node",
    description="Traverses outgoing or incoming relationships from a node. "
    "With the default max_depth of 1 this returns immediate neighbors; "
    "larger values return descendants (outgoing) or ancestors (incoming).",
)
async def get_graph_neighbors(
    repository_id: str,
    node_id: str,
    direction: Literal["incoming", "outgoing"] = Query(
        default="outgoing", description="Traversal direction."
    ),
    relationship: str | None = Query(
        default=None, description="Restrict traversal to a single relationship type."
    ),
    max_depth: int = Query(
        default=1, ge=1, description="Maximum traversal depth."
    ),
    db: Session = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
    workspace_id: str = Depends(get_workspace_id),
) -> TraversalResponse:
    _ensure_repository_exists(db, repository_id, workspace_id)
    relationship_type = _parse_relationship_type(relationship)

    logger.info(
        "Traversal requested for node '%s' in repository '%s' "
        "(direction=%s, max_depth=%d, relationship=%s).",
        node_id,
        repository_id,
        direction,
        max_depth,
        relationship,
    )

    try:
        if direction == "outgoing":
            related_nodes = graph_service.get_descendants(
                repository_id, node_id, relationship_type, max_depth
            )
        else:
            related_nodes = graph_service.get_ancestors(
                repository_id, node_id, relationship_type, max_depth
            )
    except GraphNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No dependency graph has been generated for repository "
            f"'{repository_id}'.",
        ) from exc
    except NodeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' was not found in repository '{repository_id}'.",
        ) from exc

    return TraversalResponse(
        origin_node_id=node_id,
        direction=direction,
        max_depth=max_depth,
        relationship_filter=relationship,
        nodes=_to_node_responses(related_nodes),
    )


@router.get(
    "/path",
    response_model=PathResponse,
    status_code=status.HTTP_200_OK,
    summary="Find the shortest relationship path between two nodes",
    description="Returns the shortest directed path of node identifiers "
    "from a source node to a target node, optionally restricted to a set "
    "of relationship types.",
)
async def get_shortest_path(
    repository_id: str,
    source_id: str = Query(..., description="Identifier of the path's starting node."),
    target_id: str = Query(..., description="Identifier of the path's destination node."),
    relationship_types: str | None = Query(
        default=None,
        description="Comma-separated relationship types to restrict traversal to.",
    ),
    db: Session = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
    workspace_id: str = Depends(get_workspace_id),
) -> PathResponse:
    _ensure_repository_exists(db, repository_id, workspace_id)
    parsed_relationship_types = _parse_relationship_types(relationship_types)

    logger.info(
        "Shortest path requested in repository '%s' from '%s' to '%s'.",
        repository_id,
        source_id,
        target_id,
    )

    try:
        path = graph_service.get_shortest_path(
            repository_id, source_id, target_id, parsed_relationship_types
        )
    except GraphNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No dependency graph has been generated for repository "
            f"'{repository_id}'.",
        ) from exc
    except NodeNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return PathResponse(
        source_id=source_id,
        target_id=target_id,
        path_found=path is not None,
        node_ids=path or [],
    )


@router.get(
    "/health",
    response_model=GraphHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Check dependency graph availability",
    description="Returns whether a dependency graph has been generated for "
    "a repository, along with basic size information when available.",
)
async def get_graph_health(
    repository_id: str,
    db: Session = Depends(get_db),
    graph_service: GraphService = Depends(get_graph_service),
    workspace_id: str = Depends(get_workspace_id),
) -> GraphHealthResponse:
    _ensure_repository_exists(db, repository_id, workspace_id)

    try:
        graph = graph_service.get_graph(repository_id)
    except GraphNotFoundError:
        return GraphHealthResponse(repository_id=repository_id, graph_available=False)

    stats = graph.statistics()
    return GraphHealthResponse(
        repository_id=repository_id,
        graph_available=True,
        total_nodes=stats.total_nodes,
        total_edges=stats.total_edges,
    )
