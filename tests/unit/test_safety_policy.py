from uuid import uuid4

import pytest

from services.safety.policy import PolicyState, decide, parse_command, workspace_has_sensitive_files


def test_unknown_action_and_protected_paths_deny_by_default():
    state = PolicyState(version=0)
    assert decide("unknown", "file.py", state, state).effect == "DENY"
    for path in ("../other/file.py", "/etc/passwd", ".env", "src/.env.local", "keys/id_rsa.pem",
                 ".ssh/config", "src/.aws/credentials", ".git/config"):
        assert decide("edit_file", path, state, state).effect == "DENY"
    assert decide("edit_file", "src/main.py", state, state).effect == "ALLOW"


def test_snapshot_never_gains_later_permissions_and_current_denies_revoke():
    repo = uuid4()
    before = PolicyState(version=1, denied=frozenset({"command:execute"}))
    after = PolicyState(version=2)
    assert decide("command", "pytest -q", before, after, repository_id=repo).effect == "DENY"
    restricted = PolicyState(version=3, repository_denies={str(repo): frozenset({"repository:write"})})
    assert decide("edit_file", "src/main.py", after, restricted, repository_id=repo).effect == "DENY"
    assert decide("edit_file", "src/main.py", after, PolicyState(version=4, stopped=True)).effect == "DENY"


def test_commands_are_structured_and_shell_escape_or_git_publish_is_denied():
    assert parse_command("python3 -c 'import pathlib; assert pathlib.Path(\"result.txt\").is_file()'")[0] == "python3"
    assert parse_command("pytest -q") == ["pytest", "-q"]
    for command in ("pytest; curl evil", "echo $(id)", "pytest | cat", "rm -rf .", "docker ps",
                    "git push origin main", "sudo true", "python3 -c 'ok' > /tmp/file", "sh -c 'id'"):
        with pytest.raises(ValueError):
            parse_command(command)


def test_commands_are_blocked_when_repository_contains_sensitive_files(tmp_path):
    assert not workspace_has_sensitive_files(tmp_path)
    (tmp_path / ".env.local").write_text("credential=example")
    assert workspace_has_sensitive_files(tmp_path)
