"""AST-aware source code parsing for CodeAtlas AI.

This module is the sole component responsible for turning a cloned
repository into embedding-ready, semantically meaningful code chunks. It
discovers supported source files, parses them into Tree-sitter ASTs,
walks those ASTs to identify logical units (functions, classes, methods,
interfaces, enums, arrow functions), and emits each unit as a
`CodeChunk` carrying full citation metadata.

No embedding generation, vector storage, or LLM interaction happens
here — this module's only output is structured, in-memory data that the
indexing pipeline can hand off to an embedding stage.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from tree_sitter import Language, Node, Parser
from tree_sitter_languages import get_language as get_packaged_language

from app.config import get_settings
from app.utils.file_utils import compute_sha256_of_text
from app.utils.logger import get_logger

logger = get_logger(__name__)

_COMPILED_LIBRARY_FILENAME = "languages.so"

# Directories never traversed during repository discovery, regardless of
# which language's files they might otherwise contain.
_IGNORED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "dist",
        "build",
        "target",
        "venv",
        ".venv",
        "__pycache__",
        ".idea",
        ".vscode",
    }
)


class ProgrammingLanguage(str, Enum):
    """Languages CodeAtlas AI can parse."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"


class SymbolType(str, Enum):
    """Category of a semantic code unit extracted from an AST."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    ARROW_FUNCTION = "arrow_function"
    INTERFACE = "interface"
    ENUM = "enum"


class ParserError(RuntimeError):
    """Base exception for unrecoverable parser configuration errors."""


class LanguageGrammarNotAvailableError(ParserError):
    """Raised when a required compiled Tree-sitter grammar cannot be found."""


@dataclass(frozen=True)
class RawChunk:
    """A semantic code unit as identified by a language extractor.

    Intentionally free of repository- and file-level context (repository
    id, relative path, checksum) so that extractors remain reusable
    across files and repositories; `CodeParser` enriches instances of
    this into full `CodeChunk` objects.
    """

    symbol_type: SymbolType
    symbol_name: str
    parent_symbol: str | None
    start_line: int
    end_line: int
    source_code: str


@dataclass(frozen=True)
class CodeChunk:
    """A fully contextualized, embedding-ready semantic code chunk.

    Carries everything downstream components need to generate an
    embedding and later cite the chunk's origin without re-parsing the
    source file.
    """

    repository_id: int
    chunk_id: str
    relative_path: str
    programming_language: ProgrammingLanguage
    symbol_type: SymbolType
    symbol_name: str
    parent_symbol: str | None
    imports: tuple[str, ...]
    start_line: int
    end_line: int
    source_code: str
    checksum: str

    @property
    def name(self) -> str:
        """Compatibility name used by graph-building consumers."""
        return self.symbol_name

    @property
    def file_path(self) -> str:
        """Compatibility alias for the relative source path."""
        return self.relative_path

    @property
    def language(self) -> str:
        """Return the serialized programming-language value."""
        return self.programming_language.value

    @property
    def code(self) -> str:
        """Compatibility alias for the source text."""
        return self.source_code


@dataclass
class FileParseResult:
    """Outcome of parsing a single source file."""

    relative_path: str
    programming_language: ProgrammingLanguage | None
    chunks: list[CodeChunk] = field(default_factory=list)
    error: str | None = None

    @property
    def file_path(self) -> str:
        """Compatibility alias used by graph construction."""
        return self.relative_path

    @property
    def language(self) -> str:
        """Return the file language as a string."""
        return self.programming_language.value if self.programming_language else "unknown"

    @property
    def symbols(self) -> list[CodeChunk]:
        """Expose semantic chunks under the graph builder's symbol name."""
        return self.chunks

    @property
    def imports(self) -> tuple[str, ...]:
        """Return file imports from its first chunk, when available."""
        return self.chunks[0].imports if self.chunks else ()


@dataclass
class RepositoryParseResult:
    """Aggregate outcome of parsing an entire repository."""

    repository_id: int
    files_parsed: int
    files_skipped: int
    files_failed: int
    chunks: list[CodeChunk] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    files: list[FileParseResult] = field(default_factory=list)


# Names retained for consumers written against the earlier parser contract.
ParsedFile = FileParseResult
ParsedSymbol = CodeChunk


def _node_text(node: Node | None, source_bytes: bytes) -> str:
    """Return the source text spanned by a node, tolerant of bad encoding.

    Args:
        node: The AST node to extract text from, or None.
        source_bytes: The full source file content as bytes.

    Returns:
        The decoded text for the node, or an empty string if `node` is
        None. Undecodable byte sequences are replaced rather than
        raising, so a single malformed encoding never aborts parsing.
    """
    if node is None:
        return ""
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _extract_field_name(node: Node, source_bytes: bytes, field_name: str) -> str:
    """Extract the text of a named child field, defaulting to a placeholder.

    Args:
        node: The AST node whose field should be read.
        source_bytes: The full source file content as bytes.
        field_name: The Tree-sitter field name to look up (e.g. "name").

    Returns:
        The field's text, or "<anonymous>" if the field is absent.
    """
    name_node = node.child_by_field_name(field_name)
    return _node_text(name_node, source_bytes) if name_node is not None else "<anonymous>"


def _build_raw_chunk(
    node: Node,
    symbol_type: SymbolType,
    symbol_name: str,
    parent_symbol: str | None,
    source_bytes: bytes,
) -> RawChunk:
    """Construct a `RawChunk` describing the full span of an AST node.

    Args:
        node: The node whose source range and text define the chunk.
        symbol_type: The kind of symbol this chunk represents.
        symbol_name: The symbol's name.
        parent_symbol: The name of the enclosing class, if any.
        source_bytes: The full source file content as bytes.

    Returns:
        A `RawChunk` populated with line range and source text.
    """
    return RawChunk(
        symbol_type=symbol_type,
        symbol_name=symbol_name,
        parent_symbol=parent_symbol,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        source_code=_node_text(node, source_bytes),
    )


ChunkHandler = Callable[[Node, Node, bytes, "str | None", "list[RawChunk]"], None]


class LanguageExtractor(ABC):
    """Extracts imports and semantic chunks from a parsed AST.

    Each supported language implements this interface. Extractors are
    stateless with respect to any single file: all per-file context is
    passed as arguments rather than stored on the instance, so a single
    extractor instance is reused across every file of its language.
    """

    language: ClassVar[ProgrammingLanguage]

    @abstractmethod
    def extract_imports(self, root_node: Node, source_bytes: bytes) -> list[str]:
        """Return the top-level import statements found in a file, as text."""

    @abstractmethod
    def extract_chunks(
        self, root_node: Node, source_bytes: bytes, imports: list[str]
    ) -> list[RawChunk]:
        """Return every semantic code unit found in a file's AST."""


class PythonExtractor(LanguageExtractor):
    """Extracts imports, classes, and functions/methods from Python ASTs."""

    language: ClassVar[ProgrammingLanguage] = ProgrammingLanguage.PYTHON

    def __init__(self) -> None:
        self._handlers: dict[str, ChunkHandler] = {
            "function_definition": self._handle_function,
            "class_definition": self._handle_class,
        }

    def extract_imports(self, root_node: Node, source_bytes: bytes) -> list[str]:
        return [
            _node_text(child, source_bytes).strip()
            for child in root_node.children
            if child.type in ("import_statement", "import_from_statement")
        ]

    def extract_chunks(
        self, root_node: Node, source_bytes: bytes, imports: list[str]
    ) -> list[RawChunk]:
        chunks: list[RawChunk] = []
        self._walk(root_node, source_bytes, None, chunks)
        return chunks

    def _walk(
        self, node: Node, source_bytes: bytes, parent_class: str | None, chunks: list[RawChunk]
    ) -> None:
        """Recursively visit children, dispatching known definitions to handlers."""
        for child in node.children:
            # Decorators wrap the actual definition; unwrap to inspect it
            # while keeping `child` (the decorated node) as the chunk's
            # source range so decorators are preserved in the chunk text.
            target = child
            if child.type == "decorated_definition":
                inner = child.child_by_field_name("definition")
                if inner is not None:
                    target = inner

            handler = self._handlers.get(target.type)
            if handler is not None:
                handler(child, target, source_bytes, parent_class, chunks)
            else:
                self._walk(child, source_bytes, parent_class, chunks)

    def _handle_function(
        self,
        definition_node: Node,
        function_node: Node,
        source_bytes: bytes,
        parent_class: str | None,
        chunks: list[RawChunk],
    ) -> None:
        name = _extract_field_name(function_node, source_bytes, "name")
        symbol_type = SymbolType.METHOD if parent_class else SymbolType.FUNCTION
        chunks.append(_build_raw_chunk(definition_node, symbol_type, name, parent_class, source_bytes))

        # Recurse into the function body to find nested function/class
        # definitions; parent_class is preserved unchanged.
        body = function_node.child_by_field_name("body")
        if body is not None:
            self._walk(body, source_bytes, parent_class, chunks)

    def _handle_class(
        self,
        definition_node: Node,
        class_node: Node,
        source_bytes: bytes,
        parent_class: str | None,
        chunks: list[RawChunk],
    ) -> None:
        name = _extract_field_name(class_node, source_bytes, "name")
        chunks.append(_build_raw_chunk(definition_node, SymbolType.CLASS, name, parent_class, source_bytes))

        body = class_node.child_by_field_name("body")
        if body is not None:
            self._walk(body, source_bytes, name, chunks)


class JavaScriptExtractor(LanguageExtractor):
    """Extracts imports, classes, functions, methods, and arrow functions from JS ASTs."""

    language: ClassVar[ProgrammingLanguage] = ProgrammingLanguage.JAVASCRIPT

    def __init__(self) -> None:
        self._handlers: dict[str, ChunkHandler] = {
            "function_declaration": self._handle_function,
            "class_declaration": self._handle_class,
            "method_definition": self._handle_method,
            "lexical_declaration": self._handle_variable_declaration,
            "variable_declaration": self._handle_variable_declaration,
        }

    def extract_imports(self, root_node: Node, source_bytes: bytes) -> list[str]:
        return [
            _node_text(child, source_bytes).strip()
            for child in root_node.children
            if child.type == "import_statement"
        ]

    def extract_chunks(
        self, root_node: Node, source_bytes: bytes, imports: list[str]
    ) -> list[RawChunk]:
        chunks: list[RawChunk] = []
        self._walk(root_node, source_bytes, None, chunks)
        return chunks

    def _walk(
        self, node: Node, source_bytes: bytes, parent_class: str | None, chunks: list[RawChunk]
    ) -> None:
        """Recursively visit children, unwrapping exports before dispatch."""
        for child in node.children:
            target = child
            if child.type == "export_statement":
                declaration = child.child_by_field_name("declaration")
                if declaration is not None:
                    target = declaration

            handler = self._handlers.get(target.type)
            if handler is not None:
                handler(child, target, source_bytes, parent_class, chunks)
            else:
                self._walk(child, source_bytes, parent_class, chunks)

    def _handle_function(
        self,
        definition_node: Node,
        function_node: Node,
        source_bytes: bytes,
        parent_class: str | None,
        chunks: list[RawChunk],
    ) -> None:
        name = _extract_field_name(function_node, source_bytes, "name")
        chunks.append(
            _build_raw_chunk(definition_node, SymbolType.FUNCTION, name, parent_class, source_bytes)
        )
        body = function_node.child_by_field_name("body")
        if body is not None:
            self._walk(body, source_bytes, parent_class, chunks)

    def _handle_class(
        self,
        definition_node: Node,
        class_node: Node,
        source_bytes: bytes,
        parent_class: str | None,
        chunks: list[RawChunk],
    ) -> None:
        name = _extract_field_name(class_node, source_bytes, "name")
        chunks.append(_build_raw_chunk(definition_node, SymbolType.CLASS, name, parent_class, source_bytes))
        body = class_node.child_by_field_name("body")
        if body is not None:
            self._walk(body, source_bytes, name, chunks)

    def _handle_method(
        self,
        definition_node: Node,
        method_node: Node,
        source_bytes: bytes,
        parent_class: str | None,
        chunks: list[RawChunk],
    ) -> None:
        name = _extract_field_name(method_node, source_bytes, "name")
        chunks.append(_build_raw_chunk(definition_node, SymbolType.METHOD, name, parent_class, source_bytes))

    def _handle_variable_declaration(
        self,
        definition_node: Node,
        declaration_node: Node,
        source_bytes: bytes,
        parent_class: str | None,
        chunks: list[RawChunk],
    ) -> None:
        """Emit a chunk for each declarator whose value is a function/arrow function."""
        for declarator in declaration_node.children:
            if declarator.type != "variable_declarator":
                continue

            value_node = declarator.child_by_field_name("value")
            if value_node is None or value_node.type not in (
                "arrow_function",
                "function",
                "function_expression",
            ):
                continue

            name = _extract_field_name(declarator, source_bytes, "name")
            chunks.append(
                _build_raw_chunk(
                    definition_node, SymbolType.ARROW_FUNCTION, name, parent_class, source_bytes
                )
            )


class TypeScriptExtractor(JavaScriptExtractor):
    """Extends JavaScript extraction with TypeScript-only constructs."""

    language: ClassVar[ProgrammingLanguage] = ProgrammingLanguage.TYPESCRIPT

    def __init__(self) -> None:
        super().__init__()
        self._handlers["interface_declaration"] = self._handle_interface
        self._handlers["enum_declaration"] = self._handle_enum

    def _handle_interface(
        self,
        definition_node: Node,
        interface_node: Node,
        source_bytes: bytes,
        parent_class: str | None,
        chunks: list[RawChunk],
    ) -> None:
        name = _extract_field_name(interface_node, source_bytes, "name")
        chunks.append(
            _build_raw_chunk(definition_node, SymbolType.INTERFACE, name, parent_class, source_bytes)
        )

    def _handle_enum(
        self,
        definition_node: Node,
        enum_node: Node,
        source_bytes: bytes,
        parent_class: str | None,
        chunks: list[RawChunk],
    ) -> None:
        name = _extract_field_name(enum_node, source_bytes, "name")
        chunks.append(_build_raw_chunk(definition_node, SymbolType.ENUM, name, parent_class, source_bytes))


@dataclass(frozen=True)
class LanguageSpec:
    """Binds a language to its file extensions, grammar, and extractor."""

    language: ProgrammingLanguage
    grammar_name: str
    extensions: tuple[str, ...]
    extractor_factory: Callable[[], LanguageExtractor]


# Registry of supported languages. Adding a new language (e.g. Go, Rust)
# requires only: a new LanguageExtractor subclass, a compiled grammar
# added to the shared library, and one new entry here.
_LANGUAGE_SPECS: tuple[LanguageSpec, ...] = (
    LanguageSpec(ProgrammingLanguage.PYTHON, "python", (".py",), PythonExtractor),
    LanguageSpec(
        ProgrammingLanguage.JAVASCRIPT,
        "javascript",
        (".js", ".jsx", ".mjs", ".cjs"),
        JavaScriptExtractor,
    ),
    LanguageSpec(ProgrammingLanguage.TYPESCRIPT, "typescript", (".ts", ".tsx"), TypeScriptExtractor),
)

_EXTENSION_TO_SPEC: dict[str, LanguageSpec] = {
    extension: spec for spec in _LANGUAGE_SPECS for extension in spec.extensions
}


@lru_cache(maxsize=None)
def _load_language(languages_dir: Path, grammar_name: str) -> Language:
    """Load a compiled Tree-sitter grammar, caching by (directory, grammar).

    Args:
        languages_dir: Directory expected to contain the compiled
            grammar library.
        grammar_name: Name of the grammar to load from the library
            (e.g. "python", "javascript", "typescript").

    Returns:
        The loaded `Language`.

    Raises:
        LanguageGrammarNotAvailableError: If the compiled library file
            does not exist.
    """
    library_path = languages_dir / _COMPILED_LIBRARY_FILENAME
    if not library_path.is_file():
        raise LanguageGrammarNotAvailableError(
            f"Compiled Tree-sitter grammar library not found at {library_path}. "
            "Use the installed tree-sitter-languages package or provide a valid "
            "custom compiled grammar directory."
        )
    return Language(str(library_path), grammar_name)


@lru_cache(maxsize=None)
def _load_packaged_language(grammar_name: str) -> Language:
    """Load a grammar from the portable ``tree-sitter-languages`` package.

    The package ships a platform-specific compiled grammar library and
    exposes it through a stable API. Calling that API avoids relying on the
    location of a virtual environment, site-packages layout, or operating
    system-specific path conventions.
    """
    try:
        return get_packaged_language(grammar_name)
    except Exception as exc:  # noqa: BLE001 - package exposes no narrower error.
        raise LanguageGrammarNotAvailableError(
            f"Tree-sitter grammar '{grammar_name}' is unavailable from the "
            "installed tree-sitter-languages package. Install the pinned "
            "tree-sitter-languages dependency or configure a valid compiled "
            "grammar directory."
        ) from exc


class CodeParser:
    """Parses repositories into semantically chunked, citation-ready code.

    Discovers supported source files within a repository, parses each
    with the appropriate Tree-sitter grammar, and delegates AST walking
    to a per-language `LanguageExtractor` to produce `CodeChunk` objects.
    A single instance can be reused across multiple repositories; parsed
    grammars and parsers are cached per language rather than rebuilt per
    file.
    """

    def __init__(
        self,
        tree_sitter_languages_dir: Path | None = None,
        max_file_bytes: int | None = None,
    ) -> None:
        """Initialize the parser with a directory of compiled grammars.

        Args:
            tree_sitter_languages_dir: Directory containing the compiled
                Tree-sitter grammar library. Defaults to the path
                configured in application settings.
            max_file_bytes: Maximum source file size to parse, in bytes.
                Files larger than this limit are skipped. Defaults to the
                configured application setting.
        """
        settings = get_settings()
        self._languages_dir = tree_sitter_languages_dir or settings.TREE_SITTER_LANGUAGES_DIR
        # An explicitly supplied directory is an intentional custom grammar
        # override. The default path may be absent because the supported
        # package already bundles the grammars.
        self._allow_packaged_grammars = tree_sitter_languages_dir is None
        self._max_file_bytes = max_file_bytes or settings.parser_max_file_bytes
        self._parsers: dict[ProgrammingLanguage, Parser] = {}
        self._extractors: dict[ProgrammingLanguage, LanguageExtractor] = {
            spec.language: spec.extractor_factory() for spec in _LANGUAGE_SPECS
        }

    def parse_repository(
        self,
        repository_id: int,
        repository_root: Path,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> RepositoryParseResult:
        """Parse every supported source file in a repository.

        Individual file failures never abort the run: each file is
        parsed independently, and failures are collected into the
        result's `errors` list.

        Args:
            repository_id: Identifier of the repository being parsed.
            repository_root: Local filesystem path of the cloned
                repository.

        Returns:
            Aggregate parsing results, including every extracted chunk
            and a summary of files parsed, skipped, and failed.
        """
        logger.info(
            "Repository parsing started: repository_id=%s root=%s", repository_id, repository_root
        )

        chunks: list[CodeChunk] = []
        files: list[FileParseResult] = []
        errors: list[str] = []
        files_parsed = 0
        files_skipped = 0
        files_failed = 0

        discovered_files = list(self._iter_repository_files(repository_root))
        candidate_files = [path for path in discovered_files if path.suffix.lower() in _EXTENSION_TO_SPEC]
        files_skipped = len(discovered_files) - len(candidate_files)
        if progress_callback:
            progress_callback("discovering", 0, len(candidate_files))

        for file_path in candidate_files:
            spec = _EXTENSION_TO_SPEC.get(file_path.suffix.lower())
            if spec is None:
                continue

            file_result = self.parse_file(repository_id, file_path, repository_root, spec)
            if file_result.error is not None:
                # Distinguish size-limit skips (expected) from genuine parse failures.
                if "exceeds configured size limit" in file_result.error:
                    files_skipped += 1
                    logger.info("Skipped oversized file: %s", file_result.relative_path)
                else:
                    files_failed += 1
                    errors.append(f"{file_result.relative_path}: {file_result.error}")
                    logger.warning("Failed to parse file: %s", file_result.relative_path)
                continue

            files_parsed += 1
            files.append(file_result)
            chunks.extend(file_result.chunks)
            if progress_callback:
                progress_callback("chunking", files_parsed, len(candidate_files))

        logger.info(
            "Repository parsing completed: repository_id=%s files_parsed=%d "
            "files_skipped=%d files_failed=%d chunks=%d",
            repository_id,
            files_parsed,
            files_skipped,
            files_failed,
            len(chunks),
        )

        return RepositoryParseResult(
            repository_id=repository_id,
            files_parsed=files_parsed,
            files_skipped=files_skipped,
            files_failed=files_failed,
            chunks=chunks,
            errors=errors,
            files=files,
        )

    def parse_file(
        self,
        repository_id: int,
        file_path: Path,
        repository_root: Path,
        language_spec: LanguageSpec | None = None,
    ) -> FileParseResult:
        """Parse a single source file into semantic chunks.

        Args:
            repository_id: Identifier of the owning repository.
            file_path: Absolute path of the file to parse.
            repository_root: Root of the repository, used to compute the
                file's relative path for citations.
            language_spec: The file's language spec, if already known
                (avoids re-inferring it from the extension). Inferred
                from the file extension when omitted.

        Returns:
            The parsing outcome for this file: either populated chunks,
            or an `error` describing why parsing failed.
        """
        relative_path = str(file_path.relative_to(repository_root))
        spec = language_spec or _EXTENSION_TO_SPEC.get(file_path.suffix.lower())

        if spec is None:
            return FileParseResult(
                relative_path=relative_path,
                programming_language=None,
                error="Unsupported file extension.",
            )

        # Skip files exceeding the configured size limit without reading them.
        try:
            file_size = file_path.stat().st_size
        except OSError as exc:
            logger.warning("Failed to stat file %s: %s", relative_path, exc)
            return FileParseResult(
                relative_path=relative_path, programming_language=spec.language, error=str(exc)
            )
        if file_size > self._max_file_bytes:
            logger.info(
                "Skipping file %s (size=%d bytes, limit=%d bytes)",
                relative_path, file_size, self._max_file_bytes
            )
            return FileParseResult(
                relative_path=relative_path,
                programming_language=spec.language,
                error=f"File exceeds configured size limit ({self._max_file_bytes} bytes).",
            )

        try:
            source_bytes = file_path.read_bytes()
        except OSError as exc:
            logger.warning("Failed to read file %s: %s", relative_path, exc)
            return FileParseResult(
                relative_path=relative_path, programming_language=spec.language, error=str(exc)
            )

        try:
            parser = self._get_parser(spec)
            tree = parser.parse(source_bytes)
        except LanguageGrammarNotAvailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - Tree-sitter surfaces no specific exception type.
            logger.warning("Failed to parse file %s: %s", relative_path, exc)
            return FileParseResult(
                relative_path=relative_path, programming_language=spec.language, error=str(exc)
            )

        extractor = self._extractors[spec.language]
        try:
            imports = extractor.extract_imports(tree.root_node, source_bytes)
            raw_chunks = extractor.extract_chunks(tree.root_node, source_bytes, imports)
        except Exception as exc:  # noqa: BLE001 - guards against extractor bugs on malformed ASTs.
            logger.warning("Semantic extraction failed for %s: %s", relative_path, exc)
            return FileParseResult(
                relative_path=relative_path, programming_language=spec.language, error=str(exc)
            )

        chunks = [
            self._to_code_chunk(repository_id, relative_path, spec.language, imports, raw_chunk)
            for raw_chunk in raw_chunks
        ]

        return FileParseResult(
            relative_path=relative_path, programming_language=spec.language, chunks=chunks
        )

    def _get_parser(self, spec: LanguageSpec) -> Parser:
        """Return a cached `Parser` configured for the given language.

        Args:
            spec: The language spec identifying which grammar to load.

        Returns:
            A `Parser` instance, created and cached on first use.

        Raises:
            LanguageGrammarNotAvailableError: If the grammar cannot be
                loaded from the configured languages directory.
        """
        parser = self._parsers.get(spec.language)
        if parser is not None:
            return parser

        try:
            language = _load_language(self._languages_dir, spec.grammar_name)
        except LanguageGrammarNotAvailableError:
            if not self._allow_packaged_grammars:
                raise
            logger.info(
                "Using bundled tree-sitter grammar: language=%s package=tree-sitter-languages",
                spec.grammar_name,
            )
            language = _load_packaged_language(spec.grammar_name)
        parser = Parser()
        parser.set_language(language)
        self._parsers[spec.language] = parser
        return parser

    @staticmethod
    def _iter_repository_files(repository_root: Path) -> Iterator[Path]:
        """Yield every file under a repository root, pruning ignored directories.

        Uses `os.walk` rather than `Path.rglob` so ignored directories
        (`.git`, `node_modules`, etc.) can be pruned before descending
        into them, avoiding unnecessary filesystem traversal on large
        repositories.

        Args:
            repository_root: Root directory to walk.

        Yields:
            Absolute paths of every file found, excluding ignored
            directories.
        """
        for current_dir, subdirectories, filenames in os.walk(repository_root):
            subdirectories[:] = [
                name for name in subdirectories if name not in _IGNORED_DIRECTORIES
            ]
            for filename in filenames:
                yield Path(current_dir) / filename

    @staticmethod
    def _to_code_chunk(
        repository_id: int,
        relative_path: str,
        language: ProgrammingLanguage,
        imports: list[str],
        raw_chunk: RawChunk,
    ) -> CodeChunk:
        """Enrich a `RawChunk` with repository- and file-level context.

        Args:
            repository_id: Identifier of the owning repository.
            relative_path: File path relative to the repository root.
            language: Programming language of the source file.
            imports: Import statements collected from the file.
            raw_chunk: The extractor-produced chunk to enrich.

        Returns:
            A fully populated `CodeChunk`.
        """
        checksum = compute_sha256_of_text(raw_chunk.source_code)
        chunk_id = CodeParser._build_chunk_id(repository_id, relative_path, raw_chunk)

        return CodeChunk(
            repository_id=repository_id,
            chunk_id=chunk_id,
            relative_path=relative_path,
            programming_language=language,
            symbol_type=raw_chunk.symbol_type,
            symbol_name=raw_chunk.symbol_name,
            parent_symbol=raw_chunk.parent_symbol,
            imports=tuple(imports),
            start_line=raw_chunk.start_line,
            end_line=raw_chunk.end_line,
            source_code=raw_chunk.source_code,
            checksum=checksum,
        )

    @staticmethod
    def _build_chunk_id(repository_id: int, relative_path: str, raw_chunk: RawChunk) -> str:
        """Derive a stable, deterministic identifier for a chunk.

        The identifier is a hash of the repository, file path, qualified
        symbol name, and line range, so the same logical chunk produces
        the same id across repeated parses of unchanged code.

        Args:
            repository_id: Identifier of the owning repository.
            relative_path: File path relative to the repository root.
            raw_chunk: The chunk to derive an identifier for.

        Returns:
            A 16-character hexadecimal identifier.
        """
        qualified_name = (
            f"{raw_chunk.parent_symbol}.{raw_chunk.symbol_name}"
            if raw_chunk.parent_symbol
            else raw_chunk.symbol_name
        )
        identity_string = (
            f"{repository_id}:{relative_path}:{qualified_name}:"
            f"{raw_chunk.start_line}-{raw_chunk.end_line}"
        )
        return compute_sha256_of_text(identity_string)[:16]


# Compatibility names used by the indexing and API layers.
RepositoryParser = CodeParser
RepositoryParseError = ParserError
