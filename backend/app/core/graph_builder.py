"""
Repository dependency graph engine for CodeAtlas AI.

This module constructs, queries, traverses, and serializes a structured
dependency graph describing a repository's architecture: directories,
files, classes, functions, methods, imports, and the relationships between
them. It consumes the strongly typed output of ``app.core.parser`` and never
reparses source files.

The graph is a first-class, self-contained data structure — it does not
depend on NetworkX or any visualization library. Its serialized form is
suitable for consumption by any frontend graph renderer (D3.js,
Cytoscape.js, Graphviz, etc.), but this module never generates rendering
code itself.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.parser import ParsedFile, ParsedSymbol, RepositoryParseResult
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Symbol types treated as class-like when resolving inheritance targets,
# used to disambiguate identically named functions and classes during
# best-effort symbol resolution.
_CLASS_LIKE_SYMBOL_TYPES = frozenset({"class", "interface"})


class GraphError(Exception):
    """Base exception for all dependency graph failures."""


class DuplicateNodeError(GraphError):
    """Raised when a node identifier is added to a graph more than once."""


class NodeNotFoundError(GraphError):
    """Raised when an operation references a node identifier that doesn't exist."""


class InvalidEdgeError(GraphError):
    """Raised when an edge references a node identifier that doesn't exist."""


class MalformedParserOutputError(GraphError):
    """Raised when parser output is missing data required to build the graph."""


class GraphNotFoundError(GraphError):
    """Raised when a requested repository graph has not been built or cached."""


class NodeType(str, Enum):
    """The category of repository entity a graph node represents."""

    REPOSITORY = "repository"
    DIRECTORY = "directory"
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    IMPORT = "import"
    EXTERNAL_MODULE = "external_module"
    EXTERNAL_SYMBOL = "external_symbol"


class RelationshipType(str, Enum):
    """The category of relationship a graph edge represents between two nodes."""

    IMPORTS = "IMPORTS"
    IMPORTED_BY = "IMPORTED_BY"
    CALLS = "CALLS"
    CALLED_BY = "CALLED_BY"
    CONTAINS = "CONTAINS"
    DEFINED_IN = "DEFINED_IN"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"
    REFERENCES = "REFERENCES"
    USES = "USES"
    EXPORTS = "EXPORTS"


# Relationship pairs that are recorded in both directions whenever one is
# established, keeping traversal helpers like `ancestors`/`descendants`
# usable regardless of which direction a caller queries from.
_INVERSE_RELATIONSHIPS: dict[RelationshipType, RelationshipType] = {
    RelationshipType.IMPORTS: RelationshipType.IMPORTED_BY,
    RelationshipType.IMPORTED_BY: RelationshipType.IMPORTS,
    RelationshipType.CALLS: RelationshipType.CALLED_BY,
    RelationshipType.CALLED_BY: RelationshipType.CALLS,
    RelationshipType.CONTAINS: RelationshipType.DEFINED_IN,
    RelationshipType.DEFINED_IN: RelationshipType.CONTAINS,
}


@dataclass(frozen=True)
class GraphNode:
    """A single strongly typed entity within a repository dependency graph."""

    node_id: str
    repository_id: str
    node_type: NodeType
    name: str
    file_path: str | None
    symbol_type: str | None
    language: str | None
    start_line: int | None
    end_line: int | None
    parent_node_id: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_serializable(self) -> dict[str, Any]:
        """Return a JSON-friendly representation of this node."""
        return {
            "id": self.node_id,
            "repository_id": self.repository_id,
            "type": self.node_type.value,
            "name": self.name,
            "file_path": self.file_path,
            "symbol_type": self.symbol_type,
            "language": self.language,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "parent_node_id": self.parent_node_id,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GraphEdge:
    """A directed, strongly typed relationship between two graph nodes."""

    source_id: str
    target_id: str
    relationship: RelationshipType
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_serializable(self) -> dict[str, Any]:
        """Return a JSON-friendly representation of this edge."""
        return {
            "source": self.source_id,
            "target": self.target_id,
            "relationship": self.relationship.value,
            "weight": self.weight,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GraphStatistics:
    """Aggregate structural statistics describing a repository graph."""

    total_nodes: int
    total_edges: int
    density: float
    isolated_node_count: int
    connected_component_count: int
    relationship_counts: dict[str, int]


class RepositoryGraph:
    """
    A directed, strongly typed dependency graph for a single repository.

    Storage is a plain adjacency-list structure (no third-party graph
    library), giving predictable O(1) node lookup and O(degree) traversal
    per step, which keeps construction and querying linear in the size of
    the repository rather than quadratic.
    """

    def __init__(self, repository_id: str) -> None:
        self.repository_id = repository_id
        self._nodes: dict[str, GraphNode] = {}
        self._outgoing: dict[str, list[GraphEdge]] = {}
        self._incoming: dict[str, list[GraphEdge]] = {}

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def add_node(self, node: GraphNode) -> None:
        """
        Add a node to the graph.

        Raises:
            DuplicateNodeError: If a node with the same identifier already
                exists in the graph.
        """
        if node.node_id in self._nodes:
            raise DuplicateNodeError(f"Node '{node.node_id}' already exists.")

        self._nodes[node.node_id] = node
        self._outgoing.setdefault(node.node_id, [])
        self._incoming.setdefault(node.node_id, [])

    def has_node(self, node_id: str) -> bool:
        """Return whether a node with ``node_id`` exists in the graph."""
        return node_id in self._nodes

    def add_edge(self, edge: GraphEdge) -> None:
        """
        Add a directed edge to the graph.

        Raises:
            InvalidEdgeError: If either endpoint does not exist as a node.
        """
        if edge.source_id not in self._nodes:
            raise InvalidEdgeError(
                f"Edge source '{edge.source_id}' does not exist as a node."
            )
        if edge.target_id not in self._nodes:
            raise InvalidEdgeError(
                f"Edge target '{edge.target_id}' does not exist as a node."
            )

        self._outgoing[edge.source_id].append(edge)
        self._incoming[edge.target_id].append(edge)

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship: RelationshipType,
        weight: float = 1.0,
        metadata: dict[str, Any] | None = None,
        bidirectional: bool = True,
    ) -> None:
        """
        Add an edge and, when a known inverse relationship exists, its
        reverse edge as well (e.g. CALLS paired with CALLED_BY).

        This keeps the graph queryable from either direction without
        requiring every caller to manually maintain inverse edges.
        """
        self.add_edge(
            GraphEdge(
                source_id=source_id,
                target_id=target_id,
                relationship=relationship,
                weight=weight,
                metadata=dict(metadata or {}),
            )
        )

        inverse = _INVERSE_RELATIONSHIPS.get(relationship)
        if bidirectional and inverse is not None:
            self.add_edge(
                GraphEdge(
                    source_id=target_id,
                    target_id=source_id,
                    relationship=inverse,
                    weight=weight,
                    metadata=dict(metadata or {}),
                )
            )

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_node(self, node_id: str) -> GraphNode:
        """
        Return the node identified by ``node_id``.

        Raises:
            NodeNotFoundError: If no such node exists.
        """
        try:
            return self._nodes[node_id]
        except KeyError as exc:
            raise NodeNotFoundError(f"Node '{node_id}' does not exist.") from exc

    def find_by_file(self, file_path: str) -> list[GraphNode]:
        """Return all nodes associated with ``file_path``."""
        return [node for node in self._nodes.values() if node.file_path == file_path]

    def find_by_symbol(self, symbol_name: str) -> list[GraphNode]:
        """Return all nodes whose name matches ``symbol_name``."""
        return [node for node in self._nodes.values() if node.name == symbol_name]

    def find_by_node_type(self, node_type: NodeType) -> list[GraphNode]:
        """Return all nodes of the given ``node_type``."""
        return [node for node in self._nodes.values() if node.node_type is node_type]

    def all_nodes(self) -> list[GraphNode]:
        """Return every node currently in the graph."""
        return list(self._nodes.values())

    def all_edges(self) -> list[GraphEdge]:
        """Return every edge currently in the graph."""
        return [edge for edges in self._outgoing.values() for edge in edges]

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def outgoing_edges(
        self, node_id: str, relationship: RelationshipType | None = None
    ) -> list[GraphEdge]:
        """Return edges leaving ``node_id``, optionally filtered by relationship."""
        edges = self._incoming_or_outgoing(node_id, self._outgoing)
        if relationship is None:
            return edges
        return [edge for edge in edges if edge.relationship is relationship]

    def incoming_edges(
        self, node_id: str, relationship: RelationshipType | None = None
    ) -> list[GraphEdge]:
        """Return edges entering ``node_id``, optionally filtered by relationship."""
        edges = self._incoming_or_outgoing(node_id, self._incoming)
        if relationship is None:
            return edges
        return [edge for edge in edges if edge.relationship is relationship]

    def _incoming_or_outgoing(
        self, node_id: str, index: dict[str, list[GraphEdge]]
    ) -> list[GraphEdge]:
        if node_id not in self._nodes:
            raise NodeNotFoundError(f"Node '{node_id}' does not exist.")
        return list(index[node_id])

    def neighbors(
        self, node_id: str, relationship: RelationshipType | None = None
    ) -> list[GraphNode]:
        """Return the distinct nodes directly reachable from ``node_id``."""
        target_ids = {
            edge.target_id for edge in self.outgoing_edges(node_id, relationship)
        }
        return [self._nodes[target_id] for target_id in target_ids]

    def descendants(
        self,
        node_id: str,
        relationship: RelationshipType | None = None,
        max_depth: int | None = None,
    ) -> list[GraphNode]:
        """
        Return all nodes reachable from ``node_id`` by following outgoing edges.

        Traversal is breadth-first and cycle-safe: nodes are visited at most
        once even if the graph contains cycles (e.g. mutually recursive
        function calls or circular imports).
        """
        return self._traverse(node_id, self._outgoing, relationship, max_depth)

    def ancestors(
        self,
        node_id: str,
        relationship: RelationshipType | None = None,
        max_depth: int | None = None,
    ) -> list[GraphNode]:
        """
        Return all nodes that can reach ``node_id`` by following outgoing edges.

        Implemented as descendant traversal over the incoming-edge index, so
        it shares the same cycle-safe, breadth-first behavior.
        """
        return self._traverse(node_id, self._incoming, relationship, max_depth)

    def _traverse(
        self,
        start_node_id: str,
        index: dict[str, list[GraphEdge]],
        relationship: RelationshipType | None,
        max_depth: int | None,
    ) -> list[GraphNode]:
        if start_node_id not in self._nodes:
            raise NodeNotFoundError(f"Node '{start_node_id}' does not exist.")

        effective_max_depth = (
            max_depth
            if max_depth is not None
            else get_settings().graph_max_traversal_depth
        )
        visited: set[str] = {start_node_id}
        queue: deque[tuple[str, int]] = deque([(start_node_id, 0)])
        results: list[GraphNode] = []

        while queue:
            current_id, depth = queue.popleft()
            if depth >= effective_max_depth:
                continue

            for edge in index[current_id]:
                if relationship is not None and edge.relationship is not relationship:
                    continue
                neighbor_id = self._other_endpoint(edge, current_id, index)
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                results.append(self._nodes[neighbor_id])
                queue.append((neighbor_id, depth + 1))

        return results

    @staticmethod
    def _other_endpoint(
        edge: GraphEdge, current_id: str, index: dict[str, list[GraphEdge]]
    ) -> str:
        # `index` is either the outgoing or incoming adjacency map; the
        # endpoint we haven't already visited is whichever side of the edge
        # isn't `current_id`.
        return edge.target_id if edge.source_id == current_id else edge.source_id

    def shortest_path(
        self,
        source_id: str,
        target_id: str,
        relationship_types: set[RelationshipType] | None = None,
    ) -> list[str] | None:
        """
        Return the shortest directed path of node identifiers from
        ``source_id`` to ``target_id``, following only outgoing edges.

        Returns:
            An ordered list of node identifiers from source to target
            (inclusive), or ``None`` if no path exists.

        Raises:
            NodeNotFoundError: If either endpoint does not exist.
        """
        if source_id not in self._nodes:
            raise NodeNotFoundError(f"Node '{source_id}' does not exist.")
        if target_id not in self._nodes:
            raise NodeNotFoundError(f"Node '{target_id}' does not exist.")

        if source_id == target_id:
            return [source_id]

        visited: set[str] = {source_id}
        queue: deque[list[str]] = deque([[source_id]])

        while queue:
            path = queue.popleft()
            current_id = path[-1]

            for edge in self._outgoing[current_id]:
                if relationship_types and edge.relationship not in relationship_types:
                    continue
                if edge.target_id in visited:
                    continue
                new_path = [*path, edge.target_id]
                if edge.target_id == target_id:
                    return new_path
                visited.add(edge.target_id)
                queue.append(new_path)

        return None

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def statistics(self) -> GraphStatistics:
        """Compute aggregate structural statistics for this graph."""
        total_nodes = len(self._nodes)
        total_edges = sum(len(edges) for edges in self._outgoing.values())

        max_possible_edges = total_nodes * (total_nodes - 1)
        density = (total_edges / max_possible_edges) if max_possible_edges > 0 else 0.0

        isolated_node_count = sum(
            1
            for node_id in self._nodes
            if not self._outgoing[node_id] and not self._incoming[node_id]
        )

        relationship_counts: dict[str, int] = {}
        for edges in self._outgoing.values():
            for edge in edges:
                key = edge.relationship.value
                relationship_counts[key] = relationship_counts.get(key, 0) + 1

        return GraphStatistics(
            total_nodes=total_nodes,
            total_edges=total_edges,
            density=density,
            isolated_node_count=isolated_node_count,
            connected_component_count=self._count_connected_components(),
            relationship_counts=relationship_counts,
        )

    def _count_connected_components(self) -> int:
        """Count weakly connected components, treating edges as undirected."""
        unvisited = set(self._nodes.keys())
        component_count = 0

        while unvisited:
            component_count += 1
            start = next(iter(unvisited))
            queue: deque[str] = deque([start])
            unvisited.discard(start)

            while queue:
                current_id = queue.popleft()
                neighbor_ids = {edge.target_id for edge in self._outgoing[current_id]}
                neighbor_ids |= {edge.source_id for edge in self._incoming[current_id]}
                for neighbor_id in neighbor_ids:
                    if neighbor_id in unvisited:
                        unvisited.discard(neighbor_id)
                        queue.append(neighbor_id)

        return component_count

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_serializable(self) -> dict[str, Any]:
        """
        Return a JSON-friendly representation of the full graph.

        The structure is a plain ``{"nodes": [...], "edges": [...]}``
        mapping deliberately compatible with common frontend graph
        libraries (D3.js, Cytoscape.js) without coupling this module to any
        of them.
        """
        return {
            "repository_id": self.repository_id,
            "nodes": [node.to_serializable() for node in self._nodes.values()],
            "edges": [edge.to_serializable() for edge in self.all_edges()],
        }


class GraphBuilder:
    """
    Constructs a ``RepositoryGraph`` from parser output.

    All graph-construction policy (node identifier schemes, relationship
    inference, external-symbol resolution) lives here so ``RepositoryGraph``
    itself remains a pure, builder-agnostic data structure.
    """

    def build(self, parse_result: RepositoryParseResult) -> RepositoryGraph:
        """
        Build a complete ``RepositoryGraph`` from a repository parse result.

        Raises:
            MalformedParserOutputError: If required parser output fields are
                missing or structurally invalid.
        """
        repository_id = getattr(parse_result, "repository_id", None)
        files = getattr(parse_result, "files", None)
        if repository_id is None or files is None:
            raise MalformedParserOutputError(
                "RepositoryParseResult must provide 'repository_id' and 'files'."
            )
        repository_id = str(repository_id)

        logger.info("Graph generation started for repository '%s'.", repository_id)

        graph = RepositoryGraph(repository_id=repository_id)
        self._add_repository_node(graph, repository_id)

        symbol_index = self._build_directories_and_files(graph, repository_id, files)
        self._link_symbols(graph, repository_id, files, symbol_index)
        self._link_imports(graph, repository_id, files, symbol_index)

        stats = graph.statistics()
        logger.info(
            "Graph generation completed for repository '%s': %d node(s), "
            "%d edge(s).",
            repository_id,
            stats.total_nodes,
            stats.total_edges,
        )

        return graph

    # ------------------------------------------------------------------
    # Repository / directory / file structure
    # ------------------------------------------------------------------

    def _add_repository_node(self, graph: RepositoryGraph, repository_id: str) -> str:
        node_id = self._repository_node_id(repository_id)
        graph.add_node(
            GraphNode(
                node_id=node_id,
                repository_id=repository_id,
                node_type=NodeType.REPOSITORY,
                name=repository_id,
                file_path=None,
                symbol_type=None,
                language=None,
                start_line=None,
                end_line=None,
                parent_node_id=None,
            )
        )
        return node_id

    def _build_directories_and_files(
        self,
        graph: RepositoryGraph,
        repository_id: str,
        files: list[ParsedFile],
    ) -> dict[tuple[str, str], str]:
        """
        Create directory and file nodes for every parsed file.

        Returns:
            A mapping of ``(file_path, symbol_name)`` to node identifier,
            used by later passes to resolve call and inheritance targets
            without repeated linear scans.
        """
        symbol_index: dict[tuple[str, str], str] = {}

        for parsed_file in files:
            file_path = getattr(parsed_file, "file_path", None)
            if not file_path:
                raise MalformedParserOutputError(
                    "Encountered a ParsedFile with no 'file_path'."
                )

            parent_id = self._ensure_directory_chain(graph, repository_id, file_path)
            file_node_id = self._add_file_node(graph, repository_id, parsed_file, parent_id)

            symbols = getattr(parsed_file, "symbols", []) or []
            self._add_symbol_nodes(
                graph, repository_id, parsed_file, file_node_id, symbols, symbol_index
            )

        return symbol_index

    def _ensure_directory_chain(
        self, graph: RepositoryGraph, repository_id: str, file_path: str
    ) -> str:
        """Create any missing directory nodes along ``file_path`` and return the
        node id of the immediate parent (the deepest directory, or the
        repository node for a top-level file)."""
        parts = file_path.split("/")[:-1]
        parent_id = self._repository_node_id(repository_id)
        accumulated_path = ""

        for part in parts:
            accumulated_path = f"{accumulated_path}/{part}" if accumulated_path else part
            directory_node_id = self._directory_node_id(repository_id, accumulated_path)

            if not graph.has_node(directory_node_id):
                graph.add_node(
                    GraphNode(
                        node_id=directory_node_id,
                        repository_id=repository_id,
                        node_type=NodeType.DIRECTORY,
                        name=part,
                        file_path=accumulated_path,
                        symbol_type=None,
                        language=None,
                        start_line=None,
                        end_line=None,
                        parent_node_id=parent_id,
                    )
                )
                graph.add_relationship(parent_id, directory_node_id, RelationshipType.CONTAINS)

            parent_id = directory_node_id

        return parent_id

    def _add_file_node(
        self,
        graph: RepositoryGraph,
        repository_id: str,
        parsed_file: ParsedFile,
        parent_id: str,
    ) -> str:
        file_path = parsed_file.file_path
        file_node_id = self._file_node_id(repository_id, file_path)
        language = getattr(parsed_file, "language", "unknown")

        graph.add_node(
            GraphNode(
                node_id=file_node_id,
                repository_id=repository_id,
                node_type=NodeType.FILE,
                name=file_path.rsplit("/", maxsplit=1)[-1],
                file_path=file_path,
                symbol_type=None,
                language=language,
                start_line=None,
                end_line=None,
                parent_node_id=parent_id,
            )
        )
        graph.add_relationship(parent_id, file_node_id, RelationshipType.CONTAINS)
        return file_node_id

    def _add_symbol_nodes(
        self,
        graph: RepositoryGraph,
        repository_id: str,
        parsed_file: ParsedFile,
        file_node_id: str,
        symbols: list[ParsedSymbol],
        symbol_index: dict[tuple[str, str], str],
    ) -> None:
        file_path = parsed_file.file_path
        language = getattr(parsed_file, "language", "unknown")

        for symbol in symbols:
            symbol_name = getattr(symbol, "name", None)
            if not symbol_name:
                raise MalformedParserOutputError(
                    f"Encountered a ParsedSymbol with no 'name' in '{file_path}'."
                )

            symbol_type = getattr(symbol, "symbol_type", "symbol")
            symbol_type = getattr(symbol_type, "value", symbol_type)
            start_line = getattr(symbol, "start_line", None)
            node_id = self._symbol_node_id(
                repository_id, file_path, symbol_name, start_line
            )

            graph.add_node(
                GraphNode(
                    node_id=node_id,
                    repository_id=repository_id,
                    node_type=self._node_type_for_symbol(symbol_type),
                    name=symbol_name,
                    file_path=file_path,
                    symbol_type=symbol_type,
                    language=language,
                    start_line=start_line,
                    end_line=getattr(symbol, "end_line", None),
                    parent_node_id=file_node_id,
                    metadata=dict(getattr(symbol, "metadata", {}) or {}),
                )
            )
            symbol_index[(file_path, symbol_name)] = node_id

    # ------------------------------------------------------------------
    # Symbol relationships (containment, inheritance, calls)
    # ------------------------------------------------------------------

    def _link_symbols(
        self,
        graph: RepositoryGraph,
        repository_id: str,
        files: list[ParsedFile],
        symbol_index: dict[tuple[str, str], str],
    ) -> None:
        for parsed_file in files:
            file_path = parsed_file.file_path
            file_node_id = self._file_node_id(repository_id, file_path)
            symbols = getattr(parsed_file, "symbols", []) or []

            for symbol in symbols:
                symbol_name = symbol.name
                node_id = symbol_index[(file_path, symbol_name)]

                self._link_containment(
                    graph, file_path, file_node_id, symbol, node_id, symbol_index
                )
                self._link_inheritance(graph, repository_id, file_path, symbol, node_id)
                self._link_calls(graph, repository_id, file_path, symbol, node_id, symbol_index)

    def _link_containment(
        self,
        graph: RepositoryGraph,
        file_path: str,
        file_node_id: str,
        symbol: ParsedSymbol,
        node_id: str,
        symbol_index: dict[tuple[str, str], str],
    ) -> None:
        parent_symbol_name = getattr(symbol, "parent_symbol", None)
        parent_node_id = (
            symbol_index.get((file_path, parent_symbol_name))
            if parent_symbol_name
            else None
        )
        container_id = parent_node_id or file_node_id
        graph.add_relationship(container_id, node_id, RelationshipType.CONTAINS)

    def _link_inheritance(
        self,
        graph: RepositoryGraph,
        repository_id: str,
        file_path: str,
        symbol: ParsedSymbol,
        node_id: str,
    ) -> None:
        base_class_names = getattr(symbol, "base_classes", None) or []
        for base_name in base_class_names:
            target_id = self._resolve_or_create_external(
                graph, repository_id, base_name, NodeType.EXTERNAL_SYMBOL
            )
            graph.add_relationship(node_id, target_id, RelationshipType.INHERITS)

    def _link_calls(
        self,
        graph: RepositoryGraph,
        repository_id: str,
        file_path: str,
        symbol: ParsedSymbol,
        node_id: str,
        symbol_index: dict[tuple[str, str], str],
    ) -> None:
        called_symbol_names = getattr(symbol, "calls", None) or []
        for called_name in called_symbol_names:
            target_id = symbol_index.get((file_path, called_name))
            if target_id is None:
                target_id = self._resolve_or_create_external(
                    graph, repository_id, called_name, NodeType.EXTERNAL_SYMBOL
                )
            graph.add_relationship(node_id, target_id, RelationshipType.CALLS)

    # ------------------------------------------------------------------
    # Import relationships
    # ------------------------------------------------------------------

    def _link_imports(
        self,
        graph: RepositoryGraph,
        repository_id: str,
        files: list[ParsedFile],
        symbol_index: dict[tuple[str, str], str],
    ) -> None:
        file_paths_by_module_hint = {
            parsed_file.file_path: parsed_file.file_path for parsed_file in files
        }

        for parsed_file in files:
            file_path = parsed_file.file_path
            file_node_id = self._file_node_id(repository_id, file_path)
            import_statements = getattr(parsed_file, "imports", []) or []

            for import_path in import_statements:
                target_file_path = self._resolve_import_target(
                    import_path, file_paths_by_module_hint
                )

                if target_file_path is not None:
                    target_id = self._file_node_id(repository_id, target_file_path)
                else:
                    target_id = self._resolve_or_create_external(
                        graph, repository_id, import_path, NodeType.EXTERNAL_MODULE
                    )

                graph.add_relationship(file_node_id, target_id, RelationshipType.IMPORTS)

    @staticmethod
    def _resolve_import_target(
        import_path: str, known_file_paths: dict[str, str]
    ) -> str | None:
        """
        Best-effort resolution of an import statement to a repository file.

        Matches by normalized suffix so both relative (``./utils``) and
        module-style (``app.core.utils``) import spellings can resolve
        against a known file path such as ``app/core/utils.py``. Returns
        ``None`` when no repository file plausibly corresponds to the
        import, in which case the caller treats it as an external
        dependency.
        """
        normalized_import = import_path.replace(".", "/").strip("/")

        for file_path in known_file_paths:
            normalized_file = file_path.rsplit(".", maxsplit=1)[0]
            if normalized_file == normalized_import or normalized_file.endswith(
                f"/{normalized_import}"
            ):
                return file_path

        return None

    def _resolve_or_create_external(
        self,
        graph: RepositoryGraph,
        repository_id: str,
        name: str,
        node_type: NodeType,
    ) -> str:
        """
        Return the node id for an external dependency, creating it if needed.

        External nodes represent symbols or modules outside the indexed
        repository (third-party libraries, unresolved imports) so that
        relationships pointing outward are still recorded rather than
        silently dropped.
        """
        node_id = self._external_node_id(repository_id, node_type, name)
        if not graph.has_node(node_id):
            graph.add_node(
                GraphNode(
                    node_id=node_id,
                    repository_id=repository_id,
                    node_type=node_type,
                    name=name,
                    file_path=None,
                    symbol_type=None,
                    language=None,
                    start_line=None,
                    end_line=None,
                    parent_node_id=None,
                )
            )
        return node_id

    @staticmethod
    def _node_type_for_symbol(symbol_type: str) -> NodeType:
        normalized = str(getattr(symbol_type, "value", symbol_type)).strip().lower()
        if normalized in {"arrow_function"}:
            return NodeType.FUNCTION
        if normalized in _CLASS_LIKE_SYMBOL_TYPES | {"enum"}:
            return NodeType.CLASS
        if normalized == "method":
            return NodeType.METHOD
        return NodeType.FUNCTION

    @staticmethod
    def _repository_node_id(repository_id: str) -> str:
        return f"repository:{repository_id}"

    @staticmethod
    def _directory_node_id(repository_id: str, directory_path: str) -> str:
        return f"directory:{repository_id}:{directory_path}"

    @staticmethod
    def _file_node_id(repository_id: str, file_path: str) -> str:
        return f"file:{repository_id}:{file_path}"

    @staticmethod
    def _symbol_node_id(
        repository_id: str, file_path: str, symbol_name: str, start_line: int | None
    ) -> str:
        return f"symbol:{repository_id}:{file_path}:{symbol_name}:{start_line or 0}"

    @staticmethod
    def _external_node_id(repository_id: str, node_type: NodeType, name: str) -> str:
        return f"external:{repository_id}:{node_type.value}:{name}"


class GraphService:
    """
    Public interface for repository dependency graph construction and querying.

    This is the only graph-related type the rest of the backend should
    depend on. It builds graphs via ``GraphBuilder`` and caches them by
    repository id, so repeated traversal, search, and serialization
    requests never trigger redundant graph construction.
    """

    def __init__(
        self,
        builder: GraphBuilder | None = None,
        graph_directory: Path | None = None,
    ) -> None:
        self._builder = builder or GraphBuilder()
        self._graphs: dict[str, RepositoryGraph] = {}
        self._graph_directory = graph_directory or get_settings().REPOSITORIES_DIR.parent / "graphs"

    @staticmethod
    def _normalize_repository_id(repository_id: str | int) -> str:
        """Return the canonical cache key used for a repository graph."""
        normalized = str(repository_id).strip()
        if not normalized:
            raise GraphError("Repository id must not be empty.")
        return normalized

    def build_graph(self, parse_result: RepositoryParseResult) -> RepositoryGraph:
        """
        Build a repository's dependency graph and cache it for future calls.

        Rebuilding is intentional and explicit: this method always
        constructs a fresh graph from ``parse_result`` and replaces any
        previously cached graph for the same repository, which is the
        entry point for both initial indexing and future incremental
        re-indexing after a repository update.
        """
        graph = self.build_staged_graph(parse_result)
        self.publish_graph(graph)
        return graph

    def build_staged_graph(self, parse_result: RepositoryParseResult) -> RepositoryGraph:
        """Build a graph without changing the currently published graph."""
        graph = self._builder.build(parse_result)
        return graph

    def publish_graph(self, graph: RepositoryGraph) -> None:
        """Persist and publish a fully built graph in one filesystem commit."""
        repository_id = self._normalize_repository_id(graph.repository_id)
        self._graph_directory.mkdir(parents=True, exist_ok=True)
        target = self._graph_directory / f"{repository_id}.json"
        temporary = target.with_suffix(f".json.tmp-{id(graph)}")
        temporary.write_text(json.dumps(graph.to_serializable()), encoding="utf-8")
        temporary.replace(target)
        self._graphs[repository_id] = graph
        stats = graph.statistics()
        logger.info(
            "Graph cached repository_id=%s nodes=%d edges=%d cache_size=%d",
            repository_id,
            stats.total_nodes,
            stats.total_edges,
            len(self._graphs),
        )

    def get_graph(self, repository_id: str | int) -> RepositoryGraph:
        """
        Return the cached graph for ``repository_id``.

        Raises:
            GraphNotFoundError: If no graph has been built for this
                repository yet.
        """
        normalized_repository_id = self._normalize_repository_id(repository_id)
        graph = self._graphs.get(normalized_repository_id)
        if graph is None:
            graph = self._load_persisted_graph(normalized_repository_id)
            if graph is not None:
                self._graphs[normalized_repository_id] = graph
        logger.info(
            "Graph lookup repository_id=%s found=%s",
            normalized_repository_id,
            graph is not None,
        )
        if graph is None:
            raise GraphNotFoundError(
                f"No graph has been built for repository '{normalized_repository_id}'."
            )
        return graph

    def _load_persisted_graph(self, repository_id: str) -> RepositoryGraph | None:
        path = self._graph_directory / f"{repository_id}.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            graph = RepositoryGraph(repository_id=repository_id)
            for raw_node in payload.get("nodes", []):
                graph.add_node(GraphNode(
                    node_id=raw_node["id"], repository_id=raw_node.get("repository_id", repository_id),
                    node_type=NodeType(raw_node["type"]), name=raw_node.get("name", ""),
                    file_path=raw_node.get("file_path"), symbol_type=raw_node.get("symbol_type"),
                    language=raw_node.get("language"), start_line=raw_node.get("start_line"),
                    end_line=raw_node.get("end_line"), parent_node_id=raw_node.get("parent_node_id"),
                    metadata=raw_node.get("metadata", {}),
                ))
            for raw_edge in payload.get("edges", []):
                graph.add_edge(GraphEdge(
                    source_id=raw_edge["source"], target_id=raw_edge["target"],
                    relationship=RelationshipType(raw_edge["relationship"]),
                    weight=raw_edge.get("weight", 1.0), metadata=raw_edge.get("metadata", {}),
                ))
            return graph
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Persisted graph could not be loaded repository_id=%s error=%s", repository_id, exc)
            return None

    def has_graph(self, repository_id: str | int) -> bool:
        """Return whether a graph is currently cached for ``repository_id``."""
        normalized_repository_id = self._normalize_repository_id(repository_id)
        found = normalized_repository_id in self._graphs
        logger.info("Graph cache check repository_id=%s found=%s", normalized_repository_id, found)
        return found

    def invalidate(self, repository_id: str | int) -> None:
        """Evict the cached graph for ``repository_id``, if present."""
        normalized_repository_id = self._normalize_repository_id(repository_id)
        self._graphs.pop(normalized_repository_id, None)
        logger.info("Invalidated cached graph for repository '%s'.", normalized_repository_id)

    def delete_persisted_graph(self, repository_id: str | int) -> None:
        """Delete graph data as part of an explicit repository deletion."""
        normalized = self._normalize_repository_id(repository_id)
        self.invalidate(normalized)
        try:
            (self._graph_directory / f"{normalized}.json").unlink(missing_ok=True)
        except OSError as exc:
            raise GraphError(f"Failed to delete persisted graph '{normalized}'.") from exc

    def find_by_file(self, repository_id: str, file_path: str) -> list[GraphNode]:
        """Return all nodes associated with ``file_path`` in a repository's graph."""
        return self.get_graph(repository_id).find_by_file(file_path)

    def find_by_symbol(self, repository_id: str, symbol_name: str) -> list[GraphNode]:
        """Return all nodes named ``symbol_name`` in a repository's graph."""
        return self.get_graph(repository_id).find_by_symbol(symbol_name)

    def find_by_node_type(
        self, repository_id: str, node_type: NodeType
    ) -> list[GraphNode]:
        """Return all nodes of ``node_type`` in a repository's graph."""
        return self.get_graph(repository_id).find_by_node_type(node_type)

    def get_descendants(
        self,
        repository_id: str,
        node_id: str,
        relationship: RelationshipType | None = None,
        max_depth: int | None = None,
    ) -> list[GraphNode]:
        """Return all nodes reachable from ``node_id`` in a repository's graph."""
        logger.info(
            "Traversal requested: descendants of '%s' in repository '%s'.",
            node_id,
            repository_id,
        )
        return self.get_graph(repository_id).descendants(node_id, relationship, max_depth)

    def get_ancestors(
        self,
        repository_id: str,
        node_id: str,
        relationship: RelationshipType | None = None,
        max_depth: int | None = None,
    ) -> list[GraphNode]:
        """Return all nodes that can reach ``node_id`` in a repository's graph."""
        logger.info(
            "Traversal requested: ancestors of '%s' in repository '%s'.",
            node_id,
            repository_id,
        )
        return self.get_graph(repository_id).ancestors(node_id, relationship, max_depth)

    def get_shortest_path(
        self,
        repository_id: str,
        source_id: str,
        target_id: str,
        relationship_types: set[RelationshipType] | None = None,
    ) -> list[str] | None:
        """Return the shortest path between two nodes in a repository's graph."""
        return self.get_graph(repository_id).shortest_path(
            source_id, target_id, relationship_types
        )

    def get_statistics(self, repository_id: str) -> GraphStatistics:
        """Return aggregate structural statistics for a repository's graph."""
        return self.get_graph(repository_id).statistics()

    def serialize(self, repository_id: str | int) -> dict[str, Any]:
        """Return a JSON-friendly representation of a repository's full graph."""
        logger.info("Serializing graph for repository '%s'.", repository_id)
        return self.get_graph(repository_id).to_serializable()


@lru_cache(maxsize=1)
def get_graph_service() -> GraphService:
    """Return the process-wide graph service shared by indexing and API reads."""
    return GraphService()
