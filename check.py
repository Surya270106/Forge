import re

with open('migrations/versions/56af2791774f_initial_schema.py', 'r') as f:
    content = f.read()

tables = ['role_bindings', 'context_snapshots', 'agent_interactions', 'execution_jobs', 'mutations', 'import_jobs', 'repository_memory_versions', 'source_files', 'symbols', 'symbol_references', 'dependency_edges', 'call_edges', 'ast_cache_entries', 'indexing_jobs', 'plans', 'task_nodes', 'task_edges', 'repositories', 'repository_manifests', 'verification_jobs', 'repair_attempts']

for t in tables:
    pattern = f'op\\.create_table\\(\\s*"{t}",.*?sa\\.Column\\("organization_id"'
    if not re.search(pattern, content, re.DOTALL):
        print(f'MISSING organization_id: {t}')
print("Check complete.")
