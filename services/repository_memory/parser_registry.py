"""Tree-sitter adapters for repository symbols, imports, and calls."""

from dataclasses import dataclass
from typing import Any

import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Parser


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
    extensions: tuple[str, ...] = ()
    language_name = "unknown"
    parser_version = "unknown"

    def __init__(self, language: Language):
        self.parser = Parser(language)

    def supports(self, file_path: str) -> bool:
        return file_path.lower().endswith(self.extensions)

    def get_language_name(self) -> str:
        return self.language_name

    def get_parser_version(self) -> str:
        return self.parser_version

    def parse(self, content: bytes) -> Any:
        return self.parser.parse(content)

    @staticmethod
    def _walk(root: Any):
        stack = [root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    def extract_symbols(self, tree: Any, content: bytes) -> list[ExtractedSymbol]:
        symbol_types = {
            "class_definition": "class",
            "class_declaration": "class",
            "function_definition": "function",
            "function_declaration": "function",
            "method_definition": "method",
            "interface_declaration": "interface",
            "type_alias_declaration": "type",
        }
        symbols = []
        for node in self._walk(tree.root_node):
            symbol_type = symbol_types.get(node.type)
            if not symbol_type:
                continue
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            name = content[name_node.start_byte : name_node.end_byte].decode("utf-8", "replace")
            snippet = content[node.start_byte : min(node.end_byte, node.start_byte + 4000)].decode("utf-8", "replace")
            symbols.append(ExtractedSymbol(name, name, symbol_type, node.start_point.row + 1, node.end_point.row + 1, snippet))
        return symbols

    def extract_dependencies(self, tree: Any, content: bytes) -> list[ExtractedDependency]:
        imports = []
        for node in self._walk(tree.root_node):
            if node.type not in {"import_statement", "import_from_statement"}:
                continue
            statement = content[node.start_byte : node.end_byte].decode("utf-8", "replace")
            if self.language_name == "python":
                external = not statement.startswith("from .")
            else:
                external = not any(marker in statement for marker in ('from ".', "from '.", 'import ".', "import '."))
            imports.append(ExtractedDependency(statement, external))
        return imports

    def extract_calls(self, tree: Any, content: bytes) -> list[ExtractedCall]:
        calls = []
        for node in self._walk(tree.root_node):
            if node.type not in {"call", "call_expression"}:
                continue
            function = node.child_by_field_name("function")
            if function is None:
                continue
            name_node = function.child_by_field_name("attribute") or function.child_by_field_name("property") or function
            name = content[name_node.start_byte : name_node.end_byte].decode("utf-8", "replace")
            snippet = content[node.start_byte : min(node.end_byte, node.start_byte + 1000)].decode("utf-8", "replace")
            calls.append(ExtractedCall(name, snippet, node.start_point.row + 1))
        return calls


class PythonAdapter(LanguageAdapter):
    extensions = (".py",)
    language_name = "python"
    parser_version = "0.25.0"

    def __init__(self):
        super().__init__(Language(tree_sitter_python.language()))


class JavaScriptAdapter(LanguageAdapter):
    extensions = (".js", ".jsx", ".mjs", ".cjs")
    language_name = "javascript"
    parser_version = "0.25.0"

    def __init__(self):
        super().__init__(Language(tree_sitter_javascript.language()))


class TypeScriptAdapter(LanguageAdapter):
    extensions = (".ts", ".mts", ".cts")
    language_name = "typescript"
    parser_version = "0.23.2"

    def __init__(self):
        super().__init__(Language(tree_sitter_typescript.language_typescript()))


class TSXAdapter(TypeScriptAdapter):
    extensions = (".tsx",)
    language_name = "tsx"

    def __init__(self):
        LanguageAdapter.__init__(self, Language(tree_sitter_typescript.language_tsx()))


class ParserRegistry:
    def __init__(self):
        self.adapters: list[LanguageAdapter] = []

    def register(self, adapter: LanguageAdapter):
        self.adapters.append(adapter)

    def get_adapter(self, file_path: str) -> LanguageAdapter | None:
        return next((adapter for adapter in self.adapters if adapter.supports(file_path)), None)


def get_default_registry() -> ParserRegistry:
    registry = ParserRegistry()
    for adapter in (PythonAdapter(), JavaScriptAdapter(), TypeScriptAdapter(), TSXAdapter()):
        registry.register(adapter)
    return registry
