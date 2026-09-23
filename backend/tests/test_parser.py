"""Behavioral tests for the CodeAtlas AST parser.

Tree-sitter is treated as an external boundary here.  The parser's own
extractors and result construction run normally; only the grammar/parser
objects are represented by small AST doubles so the suite is deterministic
and does not depend on a locally compiled ``languages.so``.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.core import parser as parser_module
from app.core.parser import (
    CodeChunk,
    CodeParser,
    FileParseResult,
    LanguageGrammarNotAvailableError,
    ProgrammingLanguage,
    RawChunk,
    RepositoryParseResult,
    SymbolType,
)


class FakeNode:
    """Minimal Tree-sitter node double with source-accurate byte ranges."""

    def __init__(
        self,
        node_type: str,
        source: str,
        start_line: int,
        end_line: int,
        *,
        children: list[FakeNode] | None = None,
        fields: dict[str, FakeNode] | None = None,
    ) -> None:
        self.type = node_type
        self.children = children or []
        self._fields = fields or {}
        lines = source.splitlines() or [""]
        line_starts = [0]
        for line in source.splitlines(keepends=True):
            line_starts.append(line_starts[-1] + len(line.encode("utf-8")))
        self.start_point = (start_line - 1, 0)
        self.end_point = (end_line - 1, len(lines[end_line - 1].encode("utf-8")))
        self.start_byte = line_starts[start_line - 1]
        self.end_byte = line_starts[end_line] if end_line < len(line_starts) else len(source.encode("utf-8"))
        if node_type in {"identifier", "type_identifier", "property_identifier"}:
            # Real tree-sitter field nodes span only the identifier, not its
            # containing declaration. Preserve that contract in the double.
            tokens = list(re.finditer(r"[A-Za-z_$][A-Za-z0-9_$]*", lines[start_line - 1]))
            if tokens:
                words = [token.group(0) for token in tokens]
                keyword = next(
                    (word for word in ("def", "function", "class", "interface", "enum") if word in words),
                    None,
                )
                if keyword is not None:
                    token = tokens[words.index(keyword) + 1]
                elif words[0] in {"const", "let", "var"} or words[0] == "async":
                    token = tokens[1]
                else:
                    token = tokens[-1]
                line_offset = line_starts[start_line - 1]
                self.start_byte = line_offset + len(lines[start_line - 1][: token.start()].encode("utf-8"))
                self.end_byte = line_offset + len(lines[start_line - 1][: token.end()].encode("utf-8"))
                self.start_point = (start_line - 1, token.start())
                self.end_point = (start_line - 1, token.end())

    def child_by_field_name(self, name: str) -> FakeNode | None:
        return self._fields.get(name)


class FakeTree:
    def __init__(self, root_node: FakeNode) -> None:
        self.root_node = root_node


class FakeTreeSitterParser:
    def __init__(self, tree: FakeTree | None = None, error: Exception | None = None) -> None:
        self.tree = tree
        self.error = error

    def parse(self, _source: bytes) -> FakeTree:
        if self.error is not None:
            raise self.error
        assert self.tree is not None
        return self.tree


def make_node(
    node_type: str,
    source: str,
    start: int,
    end: int,
    *,
    children: list[FakeNode] | None = None,
    fields: dict[str, FakeNode] | None = None,
) -> FakeNode:
    return FakeNode(node_type, source, start, end, children=children, fields=fields)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    return tmp_path / "repository"


@pytest.fixture
def python_source() -> str:
    return (
        "from dataclasses import dataclass\n"
        "import asyncio\n"
        "\n"
        "@dataclass\n"
        "class Service:\n"
        "    async def run(self, value: str) -> str:\n"
        "        async for item in self.items():\n"
        "            yield item\n"
        "\n"
        "    def nested(self):\n"
        "        def helper():\n"
        "            return '✓'\n"
        "        return helper()\n"
        "\n"
        "def public_api():\n"
        "    return Service()\n"
    )


@pytest.fixture
def javascript_source() -> str:
    return (
        "import { client } from './client';\n"
        "\n"
        "export function fetchData() {\n"
        "  return client.get('/items');\n"
        "}\n"
        "\n"
        "class Controller extends BaseController {\n"
        "  async load() { return fetchData(); }\n"
        "}\n"
        "\n"
        "const transform = async (value) => value.trim();\n"
    )


@pytest.fixture
def typescript_source() -> str:
    return (
        "interface User<T> {\n"
        "  id: T;\n"
        "}\n"
        "\n"
        "enum Status { Active, Disabled }\n"
        "\n"
        "export function identify(user: User<string>): string {\n"
        "  return user.id;\n"
        "}\n"
        "\n"
        "\n"
        "const format = (user: User<string>) => user.id;\n"
    )


def empty_tree(source: str) -> FakeTree:
    return FakeTree(make_node("program", source, 1, len(source.splitlines()) or 1))


def parser_for(tree: FakeTree) -> CodeParser:
    parser = CodeParser(tree_sitter_languages_dir=Path("/tmp/test-languages"))
    parser._get_parser = Mock(return_value=FakeTreeSitterParser(tree))  # type: ignore[method-assign]
    return parser


def python_tree(source: str) -> FakeTree:
    name_service = make_node("identifier", source, 5, 5)
    name_run = make_node("identifier", source, 6, 6)
    name_nested = make_node("identifier", source, 10, 10)
    name_helper = make_node("identifier", source, 11, 11)
    name_api = make_node("identifier", source, 15, 15)
    helper = make_node("function_definition", source, 11, 12, fields={"name": name_helper})
    nested_body = make_node("block", source, 11, 12, children=[helper])
    nested = make_node(
        "function_definition",
        source,
        10,
        12,
        children=[nested_body],
        fields={"name": name_nested, "body": nested_body},
    )
    run = make_node("function_definition", source, 6, 8, fields={"name": name_run})
    decorated = make_node("decorated_definition", source, 4, 8, children=[run], fields={"definition": run})
    body = make_node("block", source, 6, 12, children=[decorated, nested])
    service = make_node("class_definition", source, 5, 12, children=[decorated, nested], fields={"name": name_service, "body": body})
    api = make_node("function_definition", source, 15, 16, fields={"name": name_api})
    imports = [
        make_node("import_from_statement", source, 1, 1),
        make_node("import_statement", source, 2, 2),
    ]
    return FakeTree(make_node("module", source, 1, 16, children=imports + [service, api]))


def javascript_tree(source: str, *, typescript: bool = False) -> FakeTree:
    name_fetch = make_node("identifier", source, 3, 3)
    name_controller = make_node("identifier", source, 7, 7)
    name_load = make_node("property_identifier", source, 8, 8)
    name_transform = make_node("identifier", source, 11, 11)
    fetch = make_node("function_declaration", source, 3, 5, fields={"name": name_fetch})
    method = make_node("method_definition", source, 8, 8, fields={"name": name_load})
    class_body = make_node("class_body", source, 8, 8, children=[method])
    controller = make_node("class_declaration", source, 7, 8, children=[class_body], fields={"name": name_controller, "body": class_body})
    declarator = make_node("variable_declarator", source, 11, 11, fields={"name": name_transform, "value": make_node("arrow_function", source, 11, 11)})
    declaration = make_node("lexical_declaration", source, 11, 11, children=[declarator])
    import_node = make_node("import_statement", source, 1, 1)
    export = make_node("export_statement", source, 3, 5, children=[fetch], fields={"declaration": fetch})
    children = [import_node, export, controller, declaration]
    if typescript:
        interface_name = make_node("type_identifier", source, 1, 1)
        enum_name = make_node("identifier", source, 5, 5)
        children = [
            make_node("interface_declaration", source, 1, 3, fields={"name": interface_name}),
            make_node("enum_declaration", source, 5, 5, fields={"name": enum_name}),
            *children[1:],
        ]
    return FakeTree(make_node("program", source, 1, len(source.splitlines()), children=children))


class TestRepositoryTraversal:
    def test_recursive_discovery_prunes_ignored_directories(self, repository: Path) -> None:
        (repository / "src" / "nested").mkdir(parents=True)
        (repository / "node_modules" / "ignored").mkdir(parents=True)
        (repository / ".git").mkdir()
        (repository / "src" / "main.py").write_text("x = 1", encoding="utf-8")
        (repository / "src" / "nested" / "util.ts").write_text("x = 1", encoding="utf-8")
        (repository / "node_modules" / "ignored" / "bad.py").write_text("x = 1", encoding="utf-8")
        (repository / ".git" / "config.py").write_text("x = 1", encoding="utf-8")

        paths = {path.relative_to(repository) for path in CodeParser._iter_repository_files(repository)}

        assert paths == {Path("src/main.py"), Path("src/nested/util.ts")}

    def test_traversal_includes_hidden_files_and_empty_directories(self, repository: Path) -> None:
        (repository / ".hidden").mkdir(parents=True)
        (repository / "empty").mkdir()
        hidden = repository / ".hidden" / "module.py"
        hidden.write_text("", encoding="utf-8")

        assert list(CodeParser._iter_repository_files(repository)) == [hidden]

    def test_mixed_repository_counts_supported_and_unsupported_files(self, repository: Path) -> None:
        repository.mkdir()
        (repository / "a.py").write_text("", encoding="utf-8")
        (repository / "b.js").write_text("", encoding="utf-8")
        (repository / "README.md").write_text("docs", encoding="utf-8")
        parser = parser_for(empty_tree(""))

        result = parser.parse_repository(7, repository)

        assert isinstance(result, RepositoryParseResult)
        assert (result.files_parsed, result.files_skipped, result.files_failed) == (2, 1, 0)
        assert result.errors == []

    def test_symlink_file_is_yielded_without_following_directory_links(self, repository: Path) -> None:
        repository.mkdir()
        target = repository / "target.py"
        link = repository / "alias.py"
        target.write_text("", encoding="utf-8")
        try:
            link.symlink_to(target)
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc}")

        assert {path.name for path in CodeParser._iter_repository_files(repository)} == {"target.py", "alias.py"}


class TestPythonParsing:
    def test_extracts_imports_classes_methods_nested_functions_and_decorators(self, tmp_path: Path, python_source: str) -> None:
        path = tmp_path / "service.py"
        path.write_text(python_source, encoding="utf-8")
        parser = parser_for(python_tree(python_source))
        result = parser.parse_file(42, path, tmp_path)

        assert result.error is None
        assert result.programming_language is ProgrammingLanguage.PYTHON
        assert [(chunk.symbol_type, chunk.symbol_name, chunk.parent_symbol) for chunk in result.chunks] == [
            (SymbolType.CLASS, "Service", None),
            (SymbolType.METHOD, "run", "Service"),
            (SymbolType.METHOD, "nested", "Service"),
            (SymbolType.METHOD, "helper", "Service"),
            (SymbolType.FUNCTION, "public_api", None),
        ]
        assert result.chunks[1].source_code.startswith("@dataclass")
        assert result.chunks[0].imports == ("from dataclasses import dataclass", "import asyncio")

    @pytest.mark.parametrize("extension, language", [(".py", ProgrammingLanguage.PYTHON), (".PY", ProgrammingLanguage.PYTHON)])
    def test_language_detection_is_case_insensitive(self, tmp_path: Path, extension: str, language: ProgrammingLanguage) -> None:
        path = tmp_path / f"source{extension}"
        path.write_text("", encoding="utf-8")
        result = parser_for(empty_tree("")).parse_file(1, path, tmp_path)
        assert result.programming_language is language


class TestJavaScriptAndTypeScriptParsing:
    def test_extracts_exports_classes_methods_and_arrow_functions(self, tmp_path: Path, javascript_source: str) -> None:
        path = tmp_path / "app.js"
        path.write_text(javascript_source, encoding="utf-8")
        parser = parser_for(javascript_tree(javascript_source))
        result = parser.parse_file(3, path, tmp_path)

        assert [(c.symbol_type, c.symbol_name, c.parent_symbol) for c in result.chunks] == [
            (SymbolType.FUNCTION, "fetchData", None),
            (SymbolType.CLASS, "Controller", None),
            (SymbolType.METHOD, "load", "Controller"),
            (SymbolType.ARROW_FUNCTION, "transform", None),
        ]
        assert result.chunks[0].source_code.startswith("export function")
        assert result.chunks[0].imports == ("import { client } from './client';",)

    def test_extracts_typescript_interfaces_enums_and_functions(self, tmp_path: Path, typescript_source: str) -> None:
        path = tmp_path / "types.ts"
        path.write_text(typescript_source, encoding="utf-8")
        parser = parser_for(javascript_tree(typescript_source, typescript=True))
        result = parser.parse_file(4, path, tmp_path)

        assert result.programming_language is ProgrammingLanguage.TYPESCRIPT
        assert [chunk.symbol_type for chunk in result.chunks[:2]] == [SymbolType.INTERFACE, SymbolType.ENUM]
        assert [chunk.symbol_name for chunk in result.chunks[:2]] == ["User", "Status"]


class TestChunkGeneration:
    def test_chunk_metadata_checksums_and_stable_ids(self, tmp_path: Path, python_source: str) -> None:
        path = tmp_path / "service.py"
        path.write_text(python_source, encoding="utf-8")
        parser = parser_for(python_tree(python_source))
        first = parser.parse_file(9, path, tmp_path)
        second = parser.parse_file(9, path, tmp_path)

        assert all(isinstance(chunk, CodeChunk) for chunk in first.chunks)
        assert [chunk.chunk_id for chunk in first.chunks] == [chunk.chunk_id for chunk in second.chunks]
        assert all(len(chunk.chunk_id) == 16 for chunk in first.chunks)
        assert all(chunk.checksum == parser_module.compute_sha256_of_text(chunk.source_code) for chunk in first.chunks)
        assert all(chunk.relative_path == "service.py" and chunk.repository_id == 9 for chunk in first.chunks)
        assert all(chunk.start_line <= chunk.end_line for chunk in first.chunks)

    def test_chunk_ids_change_when_identity_changes(self) -> None:
        raw = RawChunk(SymbolType.FUNCTION, "run", None, 1, 2, "def run(): pass")
        first = CodeParser._build_chunk_id(1, "a.py", raw)
        changed_file = CodeParser._build_chunk_id(1, "b.py", raw)
        changed_repo = CodeParser._build_chunk_id(2, "a.py", raw)
        assert len({first, changed_file, changed_repo}) == 3

    def test_empty_and_comment_only_files_produce_valid_empty_results(self, tmp_path: Path) -> None:
        for name, text in (("empty.py", ""), ("comments.py", "# Unicode ✓\n# no symbols\n")):
            path = tmp_path / name
            path.write_text(text, encoding="utf-8")
            result = parser_for(empty_tree(text)).parse_file(1, path, tmp_path)
            assert isinstance(result, FileParseResult)
            assert result.error is None
            assert result.chunks == []

    def test_unicode_source_is_preserved_in_chunk_text(self, tmp_path: Path) -> None:
        source = "def café():\n    return '😀'\n"
        path = tmp_path / "unicode.py"
        path.write_text(source, encoding="utf-8")
        name = make_node("identifier", source, 1, 1)
        function = make_node("function_definition", source, 1, 2, fields={"name": name})
        result = parser_for(FakeTree(make_node("module", source, 1, 2, children=[function]))).parse_file(1, path, tmp_path)
        assert result.chunks[0].source_code == source


class TestParserErrors:
    def test_missing_grammar_is_a_configuration_error(self, tmp_path: Path) -> None:
        parser = CodeParser(tree_sitter_languages_dir=tmp_path / "missing")
        with pytest.raises(LanguageGrammarNotAvailableError, match="languages.so"):
            parser._get_parser(parser_module._LANGUAGE_SPECS[0])

    def test_file_read_error_is_returned(self, tmp_path: Path, mocker) -> None:
        path = tmp_path / "missing.py"
        # Create the file so stat() succeeds, then mock read_bytes to fail.
        path.write_text("x = 1", encoding="utf-8")
        mocker.patch.object(Path, "read_bytes", side_effect=PermissionError("denied"))
        result = parser_for(empty_tree("")).parse_file(1, path, tmp_path)
        assert result.programming_language is ProgrammingLanguage.PYTHON
        assert result.error == "denied"
        assert result.chunks == []

    def test_tree_sitter_failure_isolated_to_file(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.py"
        path.write_text("def broken(:", encoding="utf-8")
        parser = CodeParser(tree_sitter_languages_dir=tmp_path)
        parser._get_parser = Mock(return_value=FakeTreeSitterParser(error=ValueError("parse failed")))  # type: ignore[method-assign]
        result = parser.parse_file(1, path, tmp_path)
        assert result.error == "parse failed"
        assert result.chunks == []

    def test_extractor_failure_is_returned(self, tmp_path: Path, mocker) -> None:
        path = tmp_path / "broken.py"
        path.write_text("x = 1", encoding="utf-8")
        parser = parser_for(empty_tree("x = 1"))
        mocker.patch.object(parser._extractors[ProgrammingLanguage.PYTHON], "extract_chunks", side_effect=RuntimeError("extract failed"))
        result = parser.parse_file(1, path, tmp_path)
        assert result.error == "extract failed"

    @pytest.mark.parametrize("extension", [".md", ".txt", ".bin", ".java"])
    def test_unsupported_extensions_are_rejected(self, tmp_path: Path, extension: str) -> None:
        path = tmp_path / f"unknown{extension}"
        path.write_text("content", encoding="utf-8")
        result = parser_for(empty_tree("content")).parse_file(1, path, tmp_path)
        assert result.programming_language is None
        assert result.error == "Unsupported file extension."

    def test_repository_continues_after_one_file_failure(self, tmp_path: Path, mocker) -> None:
        good = tmp_path / "good.py"
        bad = tmp_path / "bad.py"
        good.write_text("", encoding="utf-8")
        bad.write_text("", encoding="utf-8")
        parser = parser_for(empty_tree(""))
        original = parser.parse_file

        def parse_file_with_one_failure(repository_id: int, path: Path, root: Path, spec=None) -> FileParseResult:
            if path.name == "bad.py":
                return FileParseResult("bad.py", ProgrammingLanguage.PYTHON, error="bad")
            return original(repository_id, path, root, spec)

        mocker.patch.object(parser, "parse_file", side_effect=parse_file_with_one_failure)
        result = parser.parse_repository(1, tmp_path)
        assert (result.files_parsed, result.files_failed) == (1, 1)
        assert result.errors == ["bad.py: bad"]


class TestParserPerformance:
    def test_traversal_handles_many_files_without_special_casing(self, tmp_path: Path) -> None:
        for index in range(200):
            path = tmp_path / f"module_{index}.py"
            path.write_text("", encoding="utf-8")
        discovered = list(CodeParser._iter_repository_files(tmp_path))
        assert len(discovered) == 200
        assert len({path.name for path in discovered}) == 200


class TestParserFileSizeLimit:
    """Regression tests for the configurable max-file-bytes limit."""

    def test_file_below_limit_is_parsed_normally(self, tmp_path: Path) -> None:
        """A file smaller than the limit is parsed and produces chunks."""
        path = tmp_path / "small.py"
        path.write_text("def hello():\n    return 42\n", encoding="utf-8")
        # Use a limit well above the file size.
        parser = CodeParser(max_file_bytes=10_000)
        result = parser.parse_file(1, path, tmp_path)
        assert result.error is None
        assert len(result.chunks) == 1
        assert result.chunks[0].symbol_name == "hello"

    def test_file_above_limit_is_skipped_safely(self, tmp_path: Path) -> None:
        """A file exceeding the limit returns an error without reading its content."""
        path = tmp_path / "large.py"
        # File size ~50 bytes, limit 10 bytes -> exceeds.
        path.write_text("def hello():\n    return 42\n", encoding="utf-8")
        parser = CodeParser(max_file_bytes=10)
        result = parser.parse_file(1, path, tmp_path)
        assert result.error is not None
        assert "exceeds configured size limit" in result.error
        assert result.chunks == []

    def test_repository_with_oversized_file_does_not_fail_indexing(self, tmp_path: Path) -> None:
        """An oversized file is counted as skipped; the rest of the repo parses normally."""
        small = tmp_path / "small.py"
        large = tmp_path / "large.py"
        small.write_text("def small():\n    return 1\n", encoding="utf-8")
        # 200+ bytes, limit 50 -> exceeds.
        large.write_text("def large():\n    return 2\n" * 20, encoding="utf-8")
        parser = CodeParser(max_file_bytes=50)
        result = parser.parse_repository(1, tmp_path)
        # 1 parsed, 1 skipped (oversized), 0 failed
        assert result.files_parsed == 1
        assert result.files_skipped == 1
        assert result.files_failed == 0
        assert len(result.chunks) == 1
        assert result.chunks[0].symbol_name == "small"
        # Error list should be empty (oversized is not an error)
        assert result.errors == []

    def test_configured_limit_is_respected(self, tmp_path: Path) -> None:
        """The limit parameter is honoured; a file at exactly the boundary parses."""
        path = tmp_path / "exact.py"
        # Content is 25 bytes (without trailing newline)
        path.write_text("def exact():\n    return 3", encoding="utf-8")
        parser = CodeParser(max_file_bytes=25)
        result = parser.parse_file(1, path, tmp_path)
        assert result.error is None
        assert len(result.chunks) == 1

        # Same file, limit 24 -> should skip
        parser2 = CodeParser(max_file_bytes=24)
        result2 = parser2.parse_file(1, path, tmp_path)
        assert result2.error is not None
        assert "exceeds configured size limit" in result2.error
