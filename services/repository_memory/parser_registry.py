from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ExtractedSymbol:
    name: str
    qualname: str
    symbol_type: str
    line_start: int
    line_end: int
    snippet: str


@dataclass
class ExtractedDependency:
    import_statement: str
    is_external: bool


@dataclass
class ExtractedCall:
    callee_name: str
    call_snippet: str
    line_start: int


class LanguageAdapter:
    def supports(self, file_path: str) -> bool:
        raise NotImplementedError

    def get_language_name(self) -> str:
        raise NotImplementedError

    def get_parser_version(self) -> str:
        raise NotImplementedError

    def parse(self, content: bytes) -> Any:
        raise NotImplementedError

    def extract_symbols(self, tree: Any, content: bytes) -> list[ExtractedSymbol]:
        raise NotImplementedError

    def extract_dependencies(self, tree: Any, content: bytes) -> list[ExtractedDependency]:
        raise NotImplementedError

    def extract_calls(self, tree: Any, content: bytes) -> list[ExtractedCall]:
        raise NotImplementedError


class ParserRegistry:
    def __init__(self):
        self.adapters: list[LanguageAdapter] = []

    def register(self, adapter: LanguageAdapter):
        self.adapters.append(adapter)

    def get_adapter(self, file_path: str) -> LanguageAdapter | None:
        for adapter in self.adapters:
            if adapter.supports(file_path):
                return adapter
        return None


try:
    import tree_sitter_javascript  # type: ignore
    import tree_sitter_python
    import tree_sitter_typescript  # type: ignore
    from tree_sitter import Language, Parser, Query, QueryCursor

    # pyright: ignore
    class PythonAdapter(LanguageAdapter):  # type: ignore
        def __init__(self):
            self.lang = Language(tree_sitter_python.language())
            self.parser = Parser(self.lang)

        def supports(self, file_path: str) -> bool:
            return file_path.endswith(".py")

        def get_language_name(self) -> str:
            return "python"

        def get_parser_version(self) -> str:
            return "0.21.0"

        def parse(self, content: bytes) -> Any:
            return self.parser.parse(content)

        def extract_symbols(self, tree: Any, content: bytes) -> list[ExtractedSymbol]:
            query = Query(
                self.lang,
                """
                (class_definition name: (identifier) @class.name) @class.def
                (function_definition name: (identifier) @function.name) @function.def
            """,
            )
            symbols = []
            cursor = QueryCursor(query)
            matches = list(cursor.matches(tree.root_node))
            print("MATCHES EXTRACT_SYMBOLS:", matches)
            for match in matches:
                captures = match[1]
                class_def = captures.get("class.def", [None])[0]
                function_def = captures.get("function.def", [None])[0]
                class_name = captures.get("class.name", [None])[0]
                function_name = captures.get("function.name", [None])[0]

                node = class_def or function_def
                name_node = class_name or function_name

                if node and name_node:
                    sym_type = "class" if class_def else "function"
                    symbols.append(
                        ExtractedSymbol(
                            name=content[name_node.start_byte : name_node.end_byte].decode("utf-8"),
                            qualname=content[name_node.start_byte : name_node.end_byte].decode("utf-8"),
                            symbol_type=sym_type,
                            line_start=node.start_point[0] + 1,
                            line_end=node.end_point[0] + 1,
                            snippet=content[node.start_byte : node.end_byte].decode("utf-8"),
                        )
                    )
            return symbols

        def extract_dependencies(self, tree: Any, content: bytes) -> list[ExtractedDependency]:
            query = Query(
                self.lang,
                """
                (import_statement) @import
                (import_from_statement) @import_from
            """,
            )
            deps = []
            cursor = QueryCursor(query)
            for match in cursor.matches(tree.root_node):
                for node_list in match[1].values():
                    for node in node_list:
                        deps.append(
                            ExtractedDependency(
                                import_statement=content[node.start_byte : node.end_byte].decode("utf-8"),
                                is_external=True,  # Simulating external heuristic
                            )
                        )
            return deps

        def extract_calls(self, tree: Any, content: bytes) -> list[ExtractedCall]:
            query = Query(
                self.lang,
                """
                (call function: (identifier) @call.name) @call
                (call function: (attribute attribute: (identifier) @call.attr)) @call
            """,
            )
            calls = []
            cursor = QueryCursor(query)
            for match in cursor.matches(tree.root_node):
                captures = match[1]
                call_node = captures.get("call", [None])[0]
                name_node = captures.get("call.name", [None])[0] or captures.get("call.attr", [None])[0]

                if call_node and name_node:
                    calls.append(
                        ExtractedCall(
                            callee_name=content[name_node.start_byte : name_node.end_byte].decode("utf-8"),
                            call_snippet=content[call_node.start_byte : call_node.end_byte].decode("utf-8"),
                            line_start=call_node.start_point[0] + 1,
                        )
                    )
            return calls

except ImportError as e:
    logger.warning("tree_sitter_not_installed", error=str(e))

    # Fallback mock registry if environment has no C-extensions
    # pyright: ignore
    class PythonAdapter(LanguageAdapter):  # type: ignore
        def supports(self, file_path: str) -> bool:
            return file_path.endswith(".py")

        def get_language_name(self) -> str:
            return "python"

        def get_parser_version(self) -> str:
            return "mocked-1.0"

        def parse(self, content: bytes) -> Any:
            return {"mock": True}

        def extract_symbols(self, tree: Any, content: bytes) -> list[ExtractedSymbol]:
            return []

        def extract_dependencies(self, tree: Any, content: bytes) -> list[ExtractedDependency]:
            return []

        def extract_calls(self, tree: Any, content: bytes) -> list[ExtractedCall]:
            return []


def get_default_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(PythonAdapter())
    # Add JS/TS later
    return registry
