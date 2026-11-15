"""Bounded Tree-sitter extraction and conservative structural resolution."""

import hashlib
import os
import re
import stat
import subprocess
from bisect import bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from services.repository_memory.parser_registry import ParserRegistry, get_default_registry
from services.safety.policy import _protected_path

INDEXER_VERSION = "atlas-5"
IGNORED_DIRS = frozenset({".git", ".hg", ".svn", ".venv", "venv", "node_modules", "dist", "build", ".next", "coverage", "__pycache__", ".pytest_cache"})


def is_test_path(path: str) -> bool:
    name = PurePosixPath(path).name
    return (path.startswith("tests/") or "/__tests__/" in f"/{path}"
            or name.startswith("test_") or name.endswith((".test.js", ".test.jsx", ".test.ts", ".test.tsx",
                                                       ".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx")))
MAX_FILES = 2000
MAX_FILE_BYTES = 1_048_576
MAX_TOTAL_BYTES = 52_428_800
SAFE_REFERENCE = re.compile(r"[A-Za-z_@.][A-Za-z0-9_.$@/+-]{0,199}")
SENSITIVE_REFERENCE = re.compile(r"(?i)(?:^sk-|^gh[pousr]_|^github_pat_|^xox[baprs]-|password|secret|token|api[_-]?key)")


@dataclass(frozen=True)
class SymbolFact:
    name: str
    qualname: str
    kind: str
    line_start: int
    line_end: int
    parent: str | None = None


@dataclass(frozen=True)
class ImportFact:
    module: str
    names: tuple[tuple[str, str], ...]
    line: int
    dynamic: bool = False


@dataclass(frozen=True)
class CallFact:
    caller: str
    target: str
    line: int


@dataclass(frozen=True)
class InheritanceFact:
    child: str
    target: str
    kind: str
    line: int


@dataclass(frozen=True)
class FileFact:
    path: str
    checksum: str
    language: str
    parser_version: str
    symbols: tuple[SymbolFact, ...]
    imports: tuple[ImportFact, ...]
    calls: tuple[CallFact, ...]
    inherits: tuple[InheritanceFact, ...] = ()


@dataclass(frozen=True)
class ScanResult:
    facts: tuple[FileFact, ...]
    reused_files: int
    fingerprint: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class GraphNode:
    key: str
    kind: str
    name: str
    path: str | None
    line_start: int | None
    line_end: int | None
    language: str | None
    content_hash: str | None
    parser_version: str | None


@dataclass(frozen=True)
class GraphEdge:
    kind: str
    source: str
    target: str | None
    target_name: str
    evidence_path: str
    evidence_line: int
    resolution: str
    confidence: str
    method: str


@dataclass(frozen=True)
class Graph:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


@dataclass(frozen=True)
class GraphDiff:
    added_nodes: tuple[str, ...]
    removed_nodes: tuple[str, ...]
    changed_nodes: tuple[str, ...]
    added_edges: tuple[GraphEdge, ...]
    removed_edges: tuple[GraphEdge, ...]
    renamed_files: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ImpactItem:
    key: str
    depth: int
    via: tuple[GraphEdge, ...]


@dataclass(frozen=True)
class ImpactResult:
    items: tuple[ImpactItem, ...]
    truncated: bool
    unresolved: tuple[GraphEdge, ...]


def _read_safe(root: Path, relative: str, limit: int) -> bytes:
    parts = PurePosixPath(relative).parts
    if _protected_path(relative) or not parts:
        raise PermissionError("Protected path")
    if hasattr(os, "O_NOFOLLOW"):
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            try:
                info = os.fstat(descriptor)
                if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                    raise ValueError("Unsupported file size or type")
                data = os.read(descriptor, limit + 1)
                if len(data) > limit:
                    raise ValueError("File exceeds index limit")
                return data
            finally:
                os.close(descriptor)
        finally:
            os.close(directory)
    # shortcut: Windows lacks this descriptor traversal; use a Linux worker for untrusted changing trees.
    candidate = root.joinpath(*parts)
    if candidate.is_symlink() or not candidate.resolve().is_relative_to(root.resolve()) or candidate.stat().st_size > limit:
        raise ValueError("Unsafe or oversized file")
    return candidate.read_bytes()


def _text(data: bytes, node: Any) -> str:
    return data[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _imports(statement: str, line: int, language: str) -> list[ImportFact]:
    if language == "python":
        match = re.match(r"from\s+([\w.]*)\s+import\s+(.+)", statement)
        if match:
            names = []
            for item in match.group(2).strip("() ").split(","):
                pieces = item.strip().split(" as ")
                if pieces[0] and pieces[0] != "*":
                    names.append((pieces[0], pieces[-1]))
            return [ImportFact(match.group(1), tuple(names), line)]
        match = re.match(r"import\s+(.+)", statement)
        if match:
            return [ImportFact(pieces[0], (("", pieces[-1] if len(pieces) > 1 else pieces[0].split(".")[0]),), line)
                    for item in match.group(1).split(",") if (pieces := item.strip().split(" as "))[0]]
        return []
    match = re.search(r"\bfrom\s*['\"]([^'\"]+)['\"]", statement)
    if not match:
        match = re.search(r"\bimport\s*['\"]([^'\"]+)['\"]", statement)
        return [ImportFact(match.group(1), (), line)] if match else []
    module = match.group(1)
    head = statement[:match.start()]
    names = []
    named = re.search(r"\{([^}]+)\}", head)
    if named:
        for item in named.group(1).split(","):
            pieces = item.strip().split(" as ")
            if pieces[0]:
                names.append((pieces[0], pieces[-1]))
    default = re.match(r"import\s+([A-Za-z_$][\w$]*)", head)
    if default:
        names.append(("default", default.group(1)))
    return [ImportFact(module, tuple(names), line)]


def extract_file(path: str, content: bytes, registry: ParserRegistry | None = None) -> FileFact:
    registry = registry or get_default_registry()
    adapter = registry.get_adapter(path)
    if adapter is None or _protected_path(path) or b"\x00" in content or len(content) > MAX_FILE_BYTES:
        raise ValueError("Unsupported or protected source file")
    tree = adapter.parse(content)
    if tree.root_node.has_error:
        raise ValueError("Source file has syntax errors")
    symbols: list[SymbolFact] = []
    imports: list[ImportFact] = []
    calls: list[CallFact] = []
    inherits: list[InheritanceFact] = []
    newlines = [index for index, value in enumerate(content) if value == 10]

    def line_at(byte: int) -> int:
        # Tree-sitter's point accessor is unstable on some large Python syntax trees.
        return bisect_right(newlines, byte) + 1

    declaration_types = {"class_definition": "class", "class_declaration": "class",
                         "function_definition": "function", "function_declaration": "function",
                         "method_definition": "method", "interface_declaration": "interface"}

    stack: list[tuple[Any, tuple[str, ...], str | None]] = [(tree.root_node, (), None)]
    while stack:
        node, scope, caller = stack.pop()
        kind = declaration_types.get(node.type)
        if kind:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _text(content, name_node)
                qualified = ".".join((*scope, name))
                if kind == "function" and (path.startswith("tests/") or Path(path).name.startswith("test_")) and name.startswith("test_"):
                    kind = "test_case"
                symbols.append(SymbolFact(name, qualified, kind, line_at(node.start_byte),
                                          line_at(max(node.start_byte, node.end_byte - 1)), ".".join(scope) or None))
                if kind in {"class", "interface"}:
                    header = content[node.start_byte:min(node.end_byte, node.start_byte + 400)].decode("utf-8", "replace")
                    if adapter.language_name == "python":
                        match = re.search(r"\bclass\s+\w+\s*\(([^)]*)\)", header.split(":", 1)[0])
                        bases = match.group(1).split(",") if match else []
                        for base in bases:
                            if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?", base.strip()):
                                inherits.append(InheritanceFact(qualified, base.strip(), "EXTENDS", line_at(node.start_byte)))
                    else:
                        header = header.split("{", 1)[0]
                        for relation, targets in (("EXTENDS", re.search(r"\bextends\s+([^{}]+?)(?=\bimplements\b|$)", header)),
                                                  ("IMPLEMENTS", re.search(r"\bimplements\s+([^{}]+)", header))):
                            if targets:
                                for target in targets.group(1).split(","):
                                    if re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?", target.strip()):
                                        inherits.append(InheritanceFact(qualified, target.strip(), relation, line_at(node.start_byte)))
                scope = (*scope, name)
                if kind in {"function", "method", "test_case"}:
                    caller = qualified
        if node.type in {"import_statement", "import_from_statement"}:
            for item in _imports(_text(content, node), line_at(node.start_byte), adapter.language_name):
                protected = any(_protected_path(part) for part in PurePosixPath(item.module).parts
                                if part not in {".", ".."})
                if SAFE_REFERENCE.fullmatch(item.module) and not SENSITIVE_REFERENCE.search(item.module) and not protected:
                    imports.append(item)
                else:
                    imports.append(ImportFact("<redacted>", (), item.line, item.dynamic))
        if node.type in {"call", "call_expression"} and caller:
            function = node.child_by_field_name("function")
            if function is not None:
                target = _text(content, function)
                if not re.fullmatch(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)?", target) or len(target) > 128:
                    target = "<dynamic>"
                calls.append(CallFact(caller, target, line_at(node.start_byte)))
        stack.extend((child, scope, caller) for child in reversed(node.children))
        if len(symbols) + len(imports) + len(calls) + len(inherits) > 10_000:
            raise ValueError("Source file exceeds Atlas fact limit")
    return FileFact(path, hashlib.sha256(content).hexdigest(), adapter.language_name, adapter.parser_version,
                    tuple(symbols), tuple(imports), tuple(calls), tuple(inherits))


def scan_repository(root: Path, *, previous: dict[str, FileFact] | None = None,
                    max_files: int = MAX_FILES, max_bytes: int = MAX_FILE_BYTES) -> ScanResult:
    root = root.resolve(strict=True)
    registry = get_default_registry()
    facts: list[FileFact] = []
    warnings: list[str] = []
    reused = 0
    total_bytes = 0
    candidates = 0
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(name for name in folders if name not in IGNORED_DIRS
                            and not (Path(directory) / name).is_symlink()
                            and not _protected_path((Path(directory) / name).relative_to(root).as_posix()))
        for name in sorted(files):
            candidate = Path(directory) / name
            relative = candidate.relative_to(root).as_posix()
            adapter = registry.get_adapter(relative)
            if adapter is None or candidate.is_symlink() or _protected_path(relative) or candidate.stem.casefold() in {"credentials", "secret", "secrets", "token", "keys"}:
                continue
            candidates += 1
            if candidates > max_files * 2:
                raise ValueError("Repository exceeds Atlas candidate limit")
            if len(facts) >= max_files:
                raise ValueError("Repository exceeds Atlas file limit")
            try:
                content = _read_safe(root, relative, max_bytes)
                total_bytes += len(content)
                checksum = hashlib.sha256(content).hexdigest()
                old = previous.get(relative) if previous else None
                if old and old.checksum == checksum and old.parser_version == adapter.parser_version:
                    facts.append(old)
                    reused += 1
                else:
                    facts.append(extract_file(relative, content, registry))
            except (OSError, ValueError, PermissionError) as error:
                warnings.append(f"{relative}: {type(error).__name__}")
            if total_bytes > MAX_TOTAL_BYTES:
                raise ValueError("Repository exceeds Atlas byte limit")
    facts.sort(key=lambda fact: fact.path)
    digest = hashlib.sha256()
    for fact in facts:
        digest.update(f"{fact.path}\0{fact.checksum}\n".encode())
    return ScanResult(tuple(facts), reused, digest.hexdigest(), tuple(warnings))


def scan_git_revision(root: Path, commit: str, *, previous: dict[str, FileFact] | None = None) -> ScanResult:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("A full commit SHA is required")
    command = ["git", "-C", str(root), "ls-tree", "-r", "-z", "-l", commit]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
        assert process.stdout is not None
        entries = process.stdout.read(8_000_001)
        if len(entries) > 8_000_000:
            process.kill()
            raise ValueError("Repository tree listing exceeds Atlas limit")
        if process.wait(timeout=30):
            raise ValueError("Repository revision unavailable")
    registry = get_default_registry()
    facts = []
    warnings = []
    reused = 0
    total_bytes = 0
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, blob, size = metadata.split()
        if mode == b"120000" or kind != b"blob":
            continue
        try:
            relative = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            warnings.append("Non-UTF-8 repository path skipped")
            continue
        if (registry.get_adapter(relative) is None or _protected_path(relative)
                or PurePosixPath(relative).stem.casefold() in {"credentials", "secret", "secrets", "token", "keys"}
                or any(part in IGNORED_DIRS for part in PurePosixPath(relative).parts)):
            continue
        if len(facts) >= MAX_FILES:
            raise ValueError("Repository exceeds Atlas file limit")
        length = int(size)
        if length > MAX_FILE_BYTES:
            warnings.append(f"{relative}: file exceeds index limit")
            continue
        total_bytes += length
        if total_bytes > MAX_TOTAL_BYTES:
            raise ValueError("Repository exceeds Atlas byte limit")
        content = subprocess.run(["git", "-C", str(root), "cat-file", "blob", blob.decode("ascii")],
                                 capture_output=True, check=True, timeout=10).stdout
        checksum = hashlib.sha256(content).hexdigest()
        old = previous.get(relative) if previous else None
        adapter = registry.get_adapter(relative)
        if old and old.checksum == checksum and adapter and old.parser_version == adapter.parser_version:
            facts.append(old)
            reused += 1
        else:
            try:
                facts.append(extract_file(relative, content, registry))
            except ValueError as error:
                warnings.append(f"{relative}: {type(error).__name__}")
    facts.sort(key=lambda fact: fact.path)
    digest = hashlib.sha256()
    for fact in facts:
        digest.update(f"{fact.path}\0{fact.checksum}\n".encode())
    return ScanResult(tuple(facts), reused, digest.hexdigest(), tuple(warnings))


def _module_path(source: str, module: str, files: set[str]) -> str | None:
    if source.endswith(".py"):
        if module.startswith("."):
            dots = len(module) - len(module.lstrip("."))
            parts = list(PurePosixPath(source).parent.parts)
            parts = parts[:max(0, len(parts) - dots + 1)]
            base = "/".join((*parts, module[dots:].replace(".", "/")))
        else:
            base = module.replace(".", "/")
        candidates = (f"{base}.py", f"{base}/__init__.py")
    elif module.startswith("."):
        base = os.path.normpath(str(PurePosixPath(source).parent / module)).replace("\\", "/")
        candidates = tuple(f"{base}{suffix}" for suffix in ("", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"))
    else:
        return None
    return next((candidate for candidate in candidates if candidate in files), None)


def build_graph(facts: tuple[FileFact, ...] | list[FileFact]) -> Graph:
    facts = tuple(sorted(facts, key=lambda fact: fact.path))
    files = {fact.path for fact in facts}
    nodes: dict[str, GraphNode] = {
        "repository": GraphNode("repository", "repository", "repository", None, None, None, None, None, None),
        "revision": GraphNode("revision", "revision", "revision", None, None, None, None, None, None),
    }
    edges: list[GraphEdge] = [GraphEdge("CONTAINS", "repository", "revision", "revision", ".", 0,
                                       "RESOLVED_STATIC", "HIGH", "atlas-structure")]
    symbol_keys: dict[tuple[str, str], str] = {}
    for fact in facts:
        file_key = f"file:{fact.path}"
        module_key = f"module:{fact.path}"
        parent_key = "revision"
        directory = PurePosixPath(fact.path).parent
        for part in (() if directory == PurePosixPath(".") else directory.parts):
            package_path = part if parent_key == "revision" else f"{parent_key.removeprefix('package:')}/{part}"
            package_key = f"package:{package_path}"
            nodes.setdefault(package_key, GraphNode(package_key, "package", package_path,
                                                    package_path, None, None, None, None, None))
            edges.append(GraphEdge("CONTAINS", parent_key, package_key, package_path, package_path, 0,
                                   "RESOLVED_STATIC", "HIGH", "atlas-structure"))
            parent_key = package_key
        kind = "test_file" if is_test_path(fact.path) else "file"
        nodes[file_key] = GraphNode(file_key, kind, fact.path, fact.path, 1, None, fact.language, fact.checksum, fact.parser_version)
        nodes[module_key] = GraphNode(module_key, "module", fact.path, fact.path, 1, None, fact.language, fact.checksum, fact.parser_version)
        edges.append(GraphEdge("CONTAINS", "revision", file_key, fact.path, fact.path, 1,
                               "RESOLVED_STATIC", "HIGH", "atlas-structure"))
        if parent_key != "revision":
            edges.append(GraphEdge("CONTAINS", parent_key, file_key, fact.path, fact.path, 1,
                                   "RESOLVED_STATIC", "HIGH", "atlas-structure"))
        edges.append(GraphEdge("DEFINES", file_key, module_key, fact.path, fact.path, 1,
                               "RESOLVED_STATIC", "HIGH", "atlas-structure"))
        for symbol in fact.symbols:
            key = f"symbol:{fact.path}:{symbol.kind}:{symbol.qualname}"
            nodes[key] = GraphNode(key, symbol.kind, symbol.name, fact.path, symbol.line_start,
                                   symbol.line_end, fact.language, fact.checksum, fact.parser_version)
            symbol_keys[(fact.path, symbol.qualname)] = key
            parent = symbol_keys.get((fact.path, symbol.parent), module_key) if symbol.parent else module_key
            edges.append(GraphEdge("DEFINES", parent, key, symbol.qualname, fact.path, symbol.line_start,
                                   "RESOLVED_STATIC", "HIGH", "tree-sitter"))
    for fact in facts:
        file_key = f"file:{fact.path}"
        imports: dict[str, tuple[str, str]] = {}
        for item in fact.imports:
            if any(_protected_path(part) for part in PurePosixPath(item.module).parts if part not in {".", ".."}):
                continue
            destination = _module_path(fact.path, item.module, files)
            edges.append(GraphEdge("IMPORTS", file_key, f"file:{destination}" if destination else None,
                                   item.module, fact.path, item.line, "RESOLVED_STATIC" if destination else "UNRESOLVED",
                                   "HIGH" if destination else "LOW", "tree-sitter-import"))
            if destination:
                for original, alias in item.names:
                    imports[alias] = (destination, original)
                if (not item.names or item.names[0][0] == "") and item.module:
                    imports[item.module.split(".")[0]] = (destination, "")
                if nodes[file_key].kind == "test_file":
                    edges.append(GraphEdge("TESTS", file_key, f"file:{destination}", item.module, fact.path,
                                           item.line, "INFERRED", "MEDIUM", "test-import-association"))
        for relation in fact.inherits:
            source = symbol_keys.get((fact.path, relation.child))
            if not source:
                continue
            target = symbol_keys.get((fact.path, relation.target))
            if not target and relation.target in imports:
                destination, original = imports[relation.target]
                target = symbol_keys.get((destination, original)) if original else None
            edges.append(GraphEdge(relation.kind, source, target, relation.target, fact.path, relation.line,
                                   "RESOLVED_STATIC" if target else "UNRESOLVED", "HIGH" if target else "LOW",
                                   "tree-sitter-inheritance"))
        for call in fact.calls:
            caller = symbol_keys.get((fact.path, call.caller))
            if not caller:
                continue
            target: str | None = None
            if re.fullmatch(r"[A-Za-z_$][\w$]*", call.target):
                target = symbol_keys.get((fact.path, call.target))
                if not target and call.target in imports:
                    destination, original = imports[call.target]
                    target = symbol_keys.get((destination, original)) if original else None
            elif re.fullmatch(r"[A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*", call.target):
                base, member = call.target.split(".", 1)
                if base in imports:
                    destination, original = imports[base]
                    target = symbol_keys.get((destination, f"{original}.{member}" if original else member))
                elif base in {"self", "this"} and "." in call.caller:
                    target = symbol_keys.get((fact.path, f"{call.caller.rsplit('.', 1)[0]}.{member}"))
            edges.append(GraphEdge("CALLS", caller, target, call.target, fact.path, call.line,
                                   "RESOLVED_STATIC" if target else "UNRESOLVED", "HIGH" if target else "LOW",
                                   "tree-sitter-direct-call"))
    return Graph(tuple(nodes[key] for key in sorted(nodes)), tuple(sorted(set(edges), key=lambda edge: (
        edge.kind, edge.source, edge.evidence_path, edge.evidence_line, edge.target_name, edge.target or ""))))


def compare_graphs(before: Graph, after: Graph) -> GraphDiff:
    old = {node.key: node for node in before.nodes}
    new = {node.key: node for node in after.nodes}
    removed_files: dict[str, list[str]] = defaultdict(list)
    added_files: dict[str, list[str]] = defaultdict(list)
    for key, node in old.items():
        if key not in new and node.kind in {"file", "test_file"} and node.content_hash and node.path:
            removed_files[node.content_hash].append(node.path)
    for key, node in new.items():
        if key not in old and node.kind in {"file", "test_file"} and node.content_hash and node.path:
            added_files[node.content_hash].append(node.path)
    renames = tuple(sorted((paths[0], added_files[checksum][0]) for checksum, paths in removed_files.items()
                           if len(paths) == len(added_files[checksum]) == 1))
    return GraphDiff(tuple(sorted(new.keys() - old.keys())), tuple(sorted(old.keys() - new.keys())),
                     tuple(sorted(key for key in new.keys() & old.keys() if new[key] != old[key])),
                     tuple(sorted(set(after.edges) - set(before.edges), key=repr)),
                     tuple(sorted(set(before.edges) - set(after.edges), key=repr)), renames)


def impact(graph: Graph, starts: list[str], *, max_depth: int = 3, max_results: int = 100,
           kinds: frozenset[str] = frozenset({"IMPORTS", "CALLS", "TESTS", "EXTENDS", "IMPLEMENTS"}),
           min_confidence: str = "LOW") -> ImpactResult:
    if not 0 <= max_depth <= 5 or not 1 <= max_results <= 200 or len(starts) > 20:
        raise ValueError("Atlas query budget exceeded")
    if min_confidence not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValueError("Unknown confidence")
    weights = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    reverse: dict[str, list[GraphEdge]] = {}
    unresolved = []
    for edge in graph.edges:
        if edge.kind not in kinds or weights[edge.confidence] < weights[min_confidence]:
            continue
        if edge.target and edge.resolution != "UNRESOLVED":
            reverse.setdefault(edge.target, []).append(edge)
        elif edge.resolution == "UNRESOLVED":
            unresolved.append(edge)
    for group in reverse.values():
        group.sort(key=lambda edge: (edge.source, edge.kind, edge.evidence_path, edge.evidence_line))
    seen = set(starts)
    queue: deque[tuple[str, int, tuple[GraphEdge, ...]]] = deque((key, 0, ()) for key in sorted(starts))
    found = []
    truncated = False
    while queue:
        key, depth, path = queue.popleft()
        if depth >= max_depth:
            continue
        for edge in reverse.get(key, []):
            if edge.source in seen:
                continue
            if len(found) >= max_results:
                truncated = True
                break
            seen.add(edge.source)
            chain = (*path, edge)
            found.append(ImpactItem(edge.source, depth + 1, chain))
            queue.append((edge.source, depth + 1, chain))
        if truncated:
            break
    return ImpactResult(tuple(found), truncated, tuple(sorted(unresolved, key=repr)[:max_results]))
