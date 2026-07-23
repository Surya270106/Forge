# Forge AI

**Current Release:** Forge AI v0.1.0-alpha.1 (Full Internal Alpha)

Forge AI is an AI-assisted software-engineering platform that securely manages autonomous coding workflows.

## Product Summary
The platform manages an end-to-end autonomous engineering workflow:
1. **Imports a repository**: Retrieves code from a remote or local source.
2. **Builds repository memory**: Uses Tree-sitter to parse source files into an indexed graph memory.
3. **Generates a structured implementation plan**: Analyzes intent and constructs an execution DAG.
4. **Requires approval**: Pauses execution until a human reviews and approves the plan.
5. **Executes controlled changes**: Tasks run within a sandboxed environment to produce code patches.
6. **Verifies results**: Formats, lints, type-checks, and runs tests on the modified code.
7. **Records audit history**: Retains full trace of agent actions, mutations, and events.

## Screenshots

*   **Repository Import:** `[Placeholder: Screenshot of the repository import interface]`
*   **Repository Indexing:** `[Placeholder: Screenshot showing Tree-sitter parsing progress and graph construction]`
*   **Symbol/Memory View:** `[Placeholder: Screenshot of the parsed memory index and codebase symbol navigation]`
*   **Plan DAG:** `[Placeholder: Screenshot visualizing the directed acyclic graph of execution tasks]`
*   **Approval Screen:** `[Placeholder: Screenshot of the human-in-the-loop plan review and approval modal]`
*   **Execution Progress:** `[Placeholder: Screenshot showing real-time logs and agent tool invocation]`
*   **Mutations:** `[Placeholder: Screenshot highlighting code diffs and patches produced by the agent]`
*   **Verification Results:** `[Placeholder: Screenshot of CI-like checks (lint, test) passing on the mutations]`
*   **Final Execution Summary:** `[Placeholder: Screenshot of the completed execution job report]`

## Architecture

```mermaid
graph TD
    UI[Next.js Frontend] --> API[FastAPI API]
    API <--> DB[(PostgreSQL)]
    API -- "Outbox Event" --> Redis[Redis Streams]
    Redis -- "Consume" --> Worker[Worker (Outbox Relay)]
    Worker --> DB
    
    subgraph Services
        API --> Memory[Tree-sitter memory engine]
        API --> Planning[Planning engine]
        API --> Execution[Execution engine]
        API --> Verification[Verification engine]
        API --> Context[Context engine]
    end
    
    Execution --> Sandbox[LocalProcessSandbox]
    Execution --> Plugin[Plugin/MCP boundary]
    Memory --> Git[Git adapter]
```

## Local Setup

### Prerequisites
- Python 3.12+ (Use `uv` for dependency management)
- Node.js v20+ (Use `npm`)
- PostgreSQL 15+
- Redis 7+

### Environment Variables
Copy `.env.example` to `.env` and fill in necessary details (e.g. `DATABASE_URL`, `REDIS_URL`).

### Setup Commands
```powershell
# 1. Install Backend Dependencies
uv sync --frozen --all-extras

# 2. Install Frontend Dependencies
cd apps/frontend
npm ci

# 3. Setup Databases
# Start PostgreSQL and Redis locally using your preferred method (e.g. Docker, Scoop)
python reset_db.py --confirm

# 4. Run Services
# API
uv run uvicorn apps.api.main:app --port 8000

# Worker
uv run python -m services.worker.main

# Frontend
cd apps/frontend
npm run dev
```

## Verification
To run the accepted Full Internal Alpha verification suite (verifies full backend/frontend build and E2E):
```powershell
python scripts\verify_full_alpha.py
```

## Security Limitations
- `LocalProcessSandbox` is limited to **trusted development fixtures**.
- Arbitrary or untrusted repository execution is **not supported**.
- `DockerSandbox` is not yet verified (blocked on environment).
- `FirecrackerSandbox` is deferred.
- Production deployment is not supported.

## Roadmap
- Docker-Isolated Alpha
- Controlled External Beta
- Production Hardening
