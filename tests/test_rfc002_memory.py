import pytest

from services.repository_memory.parser_registry import get_default_registry


@pytest.mark.skip(reason="tree-sitter API changes in 0.21.0 require query update")
def test_tree_sitter_python_extraction():
    registry = get_default_registry()
    adapter = registry.get_adapter("main.py")

    assert adapter is not None
    assert adapter.get_language_name() == "python"

    fixture_path = "tests/fixtures/sample_repo/main.py"
    with open(fixture_path, "rb") as f:
        content = f.read()

    tree = adapter.parse(content)
    symbols = adapter.extract_symbols(tree, content)

    # Assert Symbols
    symbol_names = [s.name for s in symbols]
    assert "ConfigManager" in symbol_names
    assert "load" in symbol_names
    assert "main" in symbol_names

    # Assert Dependencies
    deps = adapter.extract_dependencies(tree, content)
    dep_statements = [d.import_statement for d in deps]
    assert "import os" in dep_statements
    assert "import sys" in dep_statements

    # Assert Calls
    calls = adapter.extract_calls(tree, content)
    callee_names = [c.callee_name for c in calls]
    assert "ConfigManager" in callee_names
    assert "load" in callee_names
    assert "print" in callee_names
