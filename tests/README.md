# Verification suites

Forge separates fast capability tests from checks that require external infrastructure.

| Path | Scope | Prerequisites |
| --- | --- | --- |
| `tests/test_rfc*.py` | Backend capability and regression coverage | Python environment |
| `tests/integration` | Worker and sandbox integration | Redis, database, or Docker as declared by the test |
| `tests/security` | RLS and container-boundary behavior | Dedicated PostgreSQL or Docker |
| `tests/e2e` | Backend workflow coverage | Running Forge stack and Docker where declared |
| `apps/frontend/e2e` | Browser workflow coverage | Running frontend and supporting API |

Run the backend suite from the repository root:

```bash
uv run pytest tests -v
```

Docker-specific checks can be selected when the daemon and sandbox images are available:

```bash
uv run pytest tests/integration/test_docker_sandbox.py \
  tests/security/test_docker_sandbox_security.py \
  tests/e2e/test_docker_execution_workflow.py -v
```

The current internal-alpha suite contains explicitly skipped scenarios whose mocks or
product workflows need revision, including the frontend Playwright workflow. A skipped
test is documented missing coverage, not evidence of a passing workflow. Report pass,
fail, skip, and blocked results separately when validating a change.

Tests that access infrastructure must use isolated test data. Never point reset, RLS, or
execution tests at a shared or production environment.
