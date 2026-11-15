import subprocess
from pathlib import Path

import pytest

from services.atlas import graph as atlas_graph
from services.atlas.api import _bounded_diff
from services.atlas.graph import GraphDiff, build_graph, compare_graphs, extract_file, impact, is_test_path, scan_git_revision, scan_repository


def _write(root: Path, path: str, content: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_python_import_call_and_test_evidence(tmp_path):
    _write(tmp_path, "pkg/math.py", "def add(a, b):\n    return a + b\n")
    _write(tmp_path, "pkg/use.py", "from .math import add\ndef use():\n    return add(1, 2)\n")
    _write(tmp_path, "tests/test_math.py", "from pkg.math import add\ndef test_add():\n    assert add(1, 2) == 3\n")

    graph = build_graph(scan_repository(tmp_path).facts)
    edges = {(edge.kind, edge.source, edge.target, edge.resolution, edge.evidence_line) for edge in graph.edges}
    assert ("IMPORTS", "file:pkg/use.py", "file:pkg/math.py", "RESOLVED_STATIC", 1) in edges
    assert ("CALLS", "symbol:pkg/use.py:function:use", "symbol:pkg/math.py:function:add", "RESOLVED_STATIC", 3) in edges
    assert ("TESTS", "file:tests/test_math.py", "file:pkg/math.py", "INFERRED", 1) in edges
    assert any(node.kind == "test_case" and node.name == "test_add" for node in graph.nodes)
    assert all(edge.method and edge.confidence and edge.evidence_path for edge in graph.edges)
    assert any(node.kind == "package" and node.key == "package:pkg" for node in graph.nodes)
    assert any(edge.kind == "CONTAINS" and edge.source == "package:pkg"
               and edge.target == "file:pkg/math.py" for edge in graph.edges)


def test_ambiguous_call_is_unresolved_not_guessed(tmp_path):
    _write(tmp_path, "a.py", "def run():\n    return 1\n")
    _write(tmp_path, "b.py", "def run():\n    return 2\n")
    _write(tmp_path, "c.py", "def caller():\n    return run()\n")
    graph = build_graph(scan_repository(tmp_path).facts)
    calls = [edge for edge in graph.edges if edge.kind == "CALLS" and edge.source.endswith(":caller")]
    assert len(calls) == 1
    assert calls[0].target is None and calls[0].resolution == "UNRESOLVED"


def test_typescript_relative_import_and_interface(tmp_path):
    _write(tmp_path, "src/model.ts", "export interface Model { id: string }\nexport function make(): Model { return { id: 'x' }; }\n")
    _write(tmp_path, "src/use.ts", "import { make } from './model';\nexport function use() { return make(); }\n")
    graph = build_graph(scan_repository(tmp_path).facts)
    assert any(node.kind == "interface" and node.name == "Model" for node in graph.nodes)
    assert any(edge.kind == "IMPORTS" and edge.source == "file:src/use.ts" and edge.target == "file:src/model.ts" for edge in graph.edges)
    assert any(edge.kind == "CALLS" and edge.source.endswith(":use") and edge.target == "symbol:src/model.ts:function:make" for edge in graph.edges)


def test_typescript_test_file_is_associated_with_imported_source(tmp_path):
    _write(tmp_path, "src/math.ts", "export function add(a: number, b: number) { return a + b; }\n")
    _write(tmp_path, "src/math.test.ts", "import { add } from './math';\nexport function testAdd() { return add(1, 2); }\n")
    graph = build_graph(scan_repository(tmp_path).facts)
    assert is_test_path("src/math.test.ts")
    assert is_test_path("src/math.spec.tsx")
    assert not is_test_path("src/math.ts")
    assert any(node.key == "file:src/math.test.ts" and node.kind == "test_file" for node in graph.nodes)
    assert any(edge.kind == "TESTS" and edge.source == "file:src/math.test.ts"
               and edge.target == "file:src/math.ts" and edge.resolution == "INFERRED" for edge in graph.edges)


def test_simple_inheritance_is_resolved_with_evidence(tmp_path):
    _write(tmp_path, "base.py", "class Base: pass\n")
    _write(tmp_path, "child.py", "from base import Base\nclass Child(Base): pass\n")
    _write(tmp_path, "types.ts", "interface Contract { id: string }\nclass Parent {}\nclass Child extends Parent implements Contract {}\n")
    graph = build_graph(scan_repository(tmp_path).facts)
    assert any(edge.kind == "EXTENDS" and edge.source == "symbol:child.py:class:Child"
               and edge.target == "symbol:base.py:class:Base" and edge.evidence_line == 2
               and edge.resolution == "RESOLVED_STATIC" for edge in graph.edges)
    assert any(edge.kind == "EXTENDS" and edge.source == "symbol:types.ts:class:Child"
               and edge.target == "symbol:types.ts:class:Parent" for edge in graph.edges)
    assert any(edge.kind == "IMPLEMENTS" and edge.source == "symbol:types.ts:class:Child"
               and edge.target == "symbol:types.ts:interface:Contract" for edge in graph.edges)


def test_scanner_excludes_secrets_symlinks_binary_and_generated_files(tmp_path):
    _write(tmp_path, "src/ok.py", "def ok(): pass\n")
    _write(tmp_path, ".env", "SECRET=never-index\n")
    _write(tmp_path, "src/credentials.py", "SECRET=never-index\n")
    _write(tmp_path, "node_modules/hidden.js", "function hidden() {}\n")
    (tmp_path / "src" / "binary.py").write_bytes(b"\x00\x01")
    (tmp_path / "src" / "escape.py").symlink_to(tmp_path / ".env")
    result = scan_repository(tmp_path)
    assert [fact.path for fact in result.facts] == ["src/ok.py"]
    assert all("never-index" not in str(fact) for fact in result.facts)


def test_incremental_reuse_diff_and_bounded_impact(tmp_path):
    _write(tmp_path, "a.py", "def a(): pass\n")
    _write(tmp_path, "b.py", "from a import a\ndef b(): a()\n")
    initial_scan = scan_repository(tmp_path)
    before = build_graph(initial_scan.facts)
    assert scan_repository(tmp_path, previous={fact.path: fact for fact in initial_scan.facts}).reused_files == 2
    _write(tmp_path, "a.py", "def a(): return 2\n")
    after_scan = scan_repository(tmp_path, previous={fact.path: fact for fact in initial_scan.facts})
    assert after_scan.reused_files == 1
    after = build_graph(after_scan.facts)
    diff = compare_graphs(before, after)
    assert "file:a.py" in diff.changed_nodes
    result = impact(after, ["file:a.py"], max_depth=2, max_results=10)
    assert any(item.key == "file:b.py" for item in result.items)
    assert len(impact(after, ["file:a.py"], max_depth=2, max_results=1).items) <= 1


def test_identical_file_move_is_reported_as_rename(tmp_path):
    _write(tmp_path, "old.py", "def same(): return 1\n")
    before = build_graph(scan_repository(tmp_path).facts)
    (tmp_path / "old.py").rename(tmp_path / "new.py")
    after = build_graph(scan_repository(tmp_path).facts)
    diff = compare_graphs(before, after)
    assert diff.renamed_files == (("old.py", "new.py"),)


def test_ambiguous_same_content_files_are_not_guessed_as_renames(tmp_path):
    _write(tmp_path, "old_a.py", "def same(): return 1\n")
    _write(tmp_path, "old_b.py", "def same(): return 1\n")
    before = build_graph(scan_repository(tmp_path).facts)
    (tmp_path / "old_a.py").rename(tmp_path / "new_a.py")
    (tmp_path / "old_b.py").rename(tmp_path / "new_b.py")
    assert compare_graphs(before, build_graph(scan_repository(tmp_path).facts)).renamed_files == ()


def test_pinned_revision_stays_distinct_from_dirty_workspace(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _write(tmp_path, "src/a.py", "def first(): pass\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "src/a.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Atlas", "-c",
                    "user.email=atlas@example.invalid", "commit", "-qm", "first"], check=True)
    commit = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    _write(tmp_path, "src/a.py", "def second(): pass\n")
    pinned = scan_git_revision(tmp_path, commit)
    working = scan_repository(tmp_path)
    assert pinned.fingerprint != working.fingerprint
    assert [symbol.name for symbol in pinned.facts[0].symbols] == ["first"]
    assert [symbol.name for symbol in working.facts[0].symbols] == ["second"]


def test_protected_import_path_is_not_exposed(tmp_path):
    _write(tmp_path, "main.ts", "import config from './.env';\nexport function run() { return config; }\n")
    facts = scan_repository(tmp_path).facts
    graph = build_graph(facts)
    assert ".env" not in str(facts)
    assert not any(".env" in edge.target_name for edge in graph.edges)


def test_dynamic_call_and_import_do_not_store_source_literals(tmp_path):
    _write(tmp_path, "main.ts", "import value from 'https://example.invalid/?token=secret-value';\n"
           "export function run() { return value['secret-value'](); }\n")
    facts = scan_repository(tmp_path).facts
    graph = build_graph(facts)
    assert "secret-value" not in str(facts)
    assert not any("secret-value" in str(edge) for edge in graph.edges)
    assert any(edge.kind == "CALLS" and edge.target_name == "<dynamic>"
               and edge.resolution == "UNRESOLVED" for edge in graph.edges)


def test_total_scan_budget_fails_closed(tmp_path, monkeypatch):
    _write(tmp_path, "a.py", "def first(): pass\n")
    _write(tmp_path, "b.py", "def second(): pass\n")
    monkeypatch.setattr(atlas_graph, "MAX_TOTAL_BYTES", 25)
    with pytest.raises(ValueError, match="byte limit"):
        scan_repository(tmp_path)


def test_deep_real_python_source_does_not_exhaust_parser_stack():
    source = Path(__file__).resolve().parents[2] / "services" / "atlas" / "graph.py"
    fact = extract_file("graph.py", source.read_bytes())
    assert any(symbol.name == "build_graph" for symbol in fact.symbols)


def test_snapshot_diff_response_is_bounded_and_keeps_real_totals():
    result = _bounded_diff(GraphDiff(tuple(str(number) for number in range(501)), (), (), (), ()))
    assert len(result["added_nodes"]) == 500
    assert result["totals"]["added_nodes"] == 501
    assert result["truncated"] is True
