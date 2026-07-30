# Forge AI

Forge is an autonomous AI software engineering platform. It deeply indexes your repositories, generates architectural plans based on natural language intent, and executes those plans in isolated sandboxes before seamlessly pushing verified code to GitHub.

## Core Engines

- **Repository Memory Engine**: Parses your codebase using Tree-sitter to build a comprehensive symbol graph, tracking dependencies, imports, and architectural patterns.
- **AI Context Engine**: Assembles deep repository knowledge and intelligently injects it into LLM prompts to eliminate hallucinations and produce hyper-grounded code mutations.
- **Planning Engine**: Translates high-level natural language intents into deterministic Directed Acyclic Graphs (DAGs) consisting of file edits, bash commands, and verifications.
- **Execution Sandbox**: Runs all generated plans in secure, isolated Docker containers, preventing dangerous commands from affecting the host machine.
- **Verification DAG**: Multi-pass diagnostic engine that analyzes execution failures (e.g., test failures, lint errors) and autonomously patches the code until the build is green.

## Architecture

- **Backend**: FastAPI (Python 3.12+), SQLAlchemy (PostgreSQL + asyncpg), Redis Streams for event-driven architecture, LiteLLM for multi-provider AI support.
- **Frontend**: Next.js 14, React, Tailwind-free custom CSS with frosted glass aesthetics, WebSocket real-time terminal streaming.
- **Infrastructure**: Docker Compose for local orchestration, UV for Python dependency management.

## Setup & Run

1. Copy `.env.example` to `.env` and fill in your keys.
2. Start infrastructure: `docker compose up -d postgres redis`
3. Run the backend API: `uv run uvicorn apps.api.main:app --reload`
4. Run the background worker: `uv run python apps/worker/main.py`
5. Start the frontend: `cd apps/frontend && npm run dev`

Navigate to `http://localhost:3000` to access the Forge dashboard.
