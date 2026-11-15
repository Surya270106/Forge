from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from packages.shared.config import ForgeSettings
from services.execution.run_capsules import MAX_ARTIFACT_BYTES, canonical_bytes, content_sha256, verified_artifact


def test_canonical_hash_and_artifact_integrity():
    assert canonical_bytes({"b": 2, "a": 1}) == canonical_bytes({"a": 1, "b": 2})
    content = canonical_bytes({"status": "FAILED", "secret": None})
    artifact = SimpleNamespace(content=content.decode(), size_bytes=len(content), sha256=content_sha256(content))
    assert verified_artifact(artifact) == content
    artifact.content += " "
    with pytest.raises(ValueError, match="integrity"):
        verified_artifact(artifact)
    assert MAX_ARTIFACT_BYTES == 16_384


def test_artifact_limits_cannot_exceed_database_bounds():
    for values in ({"capsule_artifact_max_bytes": 0}, {"capsule_artifact_max_bytes": 16_385},
                   {"capsule_artifact_max_count": -1}, {"capsule_artifact_max_count": 3}):
        with pytest.raises(ValidationError):
            ForgeSettings(**values)
