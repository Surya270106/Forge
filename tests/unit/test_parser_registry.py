import pytest

from services.repository_memory.parser_registry import get_default_registry


@pytest.mark.parametrize(
    ("path", "source", "symbol"),
    [
        ("main.py", b"from .local import x\nclass Worker:\n def run(self):\n  print(x)\n", "Worker"),
        ("app.js", b"import { x } from './local.js';\nfunction run() { x(); }\n", "run"),
        ("model.ts", b"export interface Model { id: string }\n", "Model"),
        ("view.tsx", b"export function View() { return <div>ok</div> }\n", "View"),
    ],
)
def test_real_grammar_extracts_symbols(path, source, symbol):
    adapter = get_default_registry().get_adapter(path)
    assert adapter is not None
    tree = adapter.parse(source)
    assert not tree.root_node.has_error
    assert symbol in [item.name for item in adapter.extract_symbols(tree, source)]


def test_local_and_external_imports_are_distinguished():
    adapter = get_default_registry().get_adapter("main.py")
    assert adapter is not None
    source = b"import os\nfrom .local import x\nprint(x)\n"
    tree = adapter.parse(source)
    dependencies = adapter.extract_dependencies(tree, source)
    assert [item.is_external for item in dependencies] == [True, False]
    assert [item.callee_name for item in adapter.extract_calls(tree, source)] == ["print"]
