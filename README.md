<div align="center">

# 🧭 CodeAtlas AI

**Ask questions about any GitHub repo in plain English — get grounded answers with file-and-line citations, not hallucinations.**

*A retrieval-augmented code intelligence platform with grounded answers and file-level citations.*

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React_19-Frontend-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-Frontend-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Store-FF6F00?style=flat-square)](https://www.trychroma.com/)
[![License](https://img.shields.io/badge/License-See_LICENSE-lightgrey?style=flat-square)](LICENSE)

[Features](#-features) • [Architecture](#-architecture) • [Quick Start](#-local-installation) • [API](#-api-documentation) • [Roadmap](#-roadmap)

</div>

---

## 🚀 What is CodeAtlas AI?

CodeAtlas AI turns a raw GitHub repository into a **queryable knowledge base**. Point it at a repo, and it parses the code into real semantic units — not just text chunks — builds a searchable dependency graph, and answers natural-language questions with **retrieval-augmented generation grounded in file- and line-level citations**.

Parsing, embeddings, vector search, and repository indexing run in CodeAtlas; Gemini generation is performed server-side with the configured backend secret.

> **Why it's interesting from an engineering standpoint:** most "chat with your code" tools are thin wrappers around an LLM API and a vector store. CodeAtlas AI instead does real static analysis (Tree-sitter AST parsing → symbol/class/function extraction → dependency graph construction) *before* anything touches an embedding model, so answers are traceable back to actual code structure — not just fuzzy text similarity.

---

## ✨ Features

| | |
|---|---|
| 🔍 **Semantic Code Search** | Local Sentence Transformer embeddings + ChromaDB vector search across an entire repository |
| 💬 **Grounded Q&A** | Natural-language questions answered via RAG, with every answer traceable to source |
| 📍 **File & Line Citations** | No hallucinated references — every claim points to real code |
| 🕸️ **Dependency Graph Explorer** | Traverse files, symbols, imports, and relationships; query neighbors and shortest paths between nodes |
| 🌳 **AST-Level Parsing** | Tree-sitter extracts classes, functions, methods, interfaces, enums, and arrow functions from Python, JavaScript, and TypeScript |
| 🤖 **Gemini Grounded Inference** | Server-side Gemini generation constrained by retrieved repository context |
| ⚡ **Streaming Responses** | `/query/stream` for real-time, token-by-token answers |
| 🐳 **One-Command Docker Deploy** | Full stack (backend, SQLite, ChromaDB, repo storage) via Docker Compose |
| 🧩 **Clean Layered Architecture** | Strict separation between HTTP, orchestration, domain logic, and persistence |
| 🛡️ **Repository-Scoped Retrieval** | Search is isolated per repository to prevent cross-context leakage |

---

## 🏗️ Architecture

CodeAtlas AI follows a strict **ingest → understand → retrieve → generate** pipeline:

```text
                 GitHub Repository
                        │
                        ▼
                 Repository Import
                        │
        ┌───────────────┼───────────────┐
        │                               ▼
        │                      Dependency Graph
        ▼
   Tree-sitter Parser
   (AST → classes, functions,
    methods, interfaces, enums)
        │
        ▼
  Sentence Transformers
   (local embeddings)
        │
        ▼
       ChromaDB
   (vector storage)
        │
        ▼
      Retriever
 (search → filter → dedupe →
    rerank → assemble context)
        │
        ▼
       Gemini
  (server-side generation)
        │
        ▼
 Grounded Answer + Citations
```

**Layered backend design:**

```text
codeatlas-ai/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routers — HTTP concerns only
│   │   ├── core/             # Parser, embeddings, retrieval, LLM, graph
│   │   ├── db/                # SQLite + CRUD helpers
│   │   ├── models/            # DB and API schemas
│   │   └── main.py            # Application factory & middleware
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/                  # Vite + React 19 client
├── docker-compose.yml
└── README.md
```

SQLite handles application metadata locally, while production can use Render
PostgreSQL via `DATABASE_URL`; ChromaDB handles searchable vectors — each
store is used for what it's actually good at, rather than forcing one database
to do both jobs.

---

## 🛠️ Tech Stack

<div align="center">

| Layer | Technology |
|---|---|
| **Backend Framework** | FastAPI |
| **Code Parsing** | Tree-sitter (multi-language AST parsing) |
| **Embeddings** | Sentence Transformers (`BAAI/bge-small-en-v1.5`, local) |
| **Vector Store** | ChromaDB |
| **LLM Inference** | Gemini Interactions API (`gemini-2.5-flash`, configurable) |
| **Metadata Store** | SQLite locally / PostgreSQL on Render |
| **Frontend** | React 19 + TypeScript + Vite |
| **Frontend Data/State** | TanStack Query |
| **Frontend Routing** | React Router |
| **Visualization** | Recharts (analytics), React Flow (dependency graph) |
| **Styling** | Tailwind CSS |
| **Containerization** | Docker + Docker Compose |

</div>

---

## 📦 Requirements

- Python 3.11
- Git
- Docker & Docker Compose *(optional)*
- Gemini API key configured on the backend
- 8 GB+ RAM recommended for local embedding workloads

---

## ⚙️ Local Installation

```bash
git clone https://github.com/your-org/codeatlas-ai.git
cd codeatlas-ai
python3.11 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
```

**Windows (PowerShell):**

```powershell
py -3.11 -m venv backend\.venv
backend\.venv\Scripts\Activate.ps1
```

Gemini is used for AI query generation. Copy `backend/.env.example` and set `GEMINI_API_KEY` in the backend environment.

---

## 🔧 Configuration

```bash
cp backend/.env.example backend/.env
```

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `CodeAtlas AI` | Application name |
| `DEBUG` | `True` | Development diagnostics — set `False` in production |
| `DATABASE_URL` | `sqlite:///./codeatlas.db` locally | SQLAlchemy database URL. Set this to the Render PostgreSQL connection string in production; `postgres://` is normalized automatically to `postgresql://`. |
| `GEMINI_API_KEY` | unset | Backend/Render secret used for server-side Gemini requests; never expose it to Vite |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Configurable Gemini model for repository Q&A |
| `GEMINI_TIMEOUT_SECONDS` | `60` | Gemini request timeout |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local embedding model |
| `CHROMA_DB_PATH` | `./data/chroma` | ChromaDB persistence path |
| `LOG_LEVEL` | `INFO` | Application log level |

Config resolution order: repository-root `.env` → `backend/.env` (wins on conflict) → shell environment variables (highest priority). Relative paths resolve from the repository root. `CHROMA_DB_PATH`/`CHROMA_PERSIST_DIRECTORY` are aliases.

> 🔒 Never commit `.env` files, credentials, databases, vector stores, or model caches.

For Render, configure the Supabase PostgreSQL connection string as the backend
service's `DATABASE_URL` environment variable. The backend selects PostgreSQL whenever that variable is set to a
PostgreSQL URL; otherwise it uses the local SQLite file. Startup only creates
missing tables and checks connectivity—it does not reset or overwrite existing
production data. Repository records, indexing metadata, and vectors therefore
remain in Supabase across deploys and restarts.

---

## ▶️ Running the Backend

```bash
cd backend
source .venv/bin/activate
DEBUG=true python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API available at `http://localhost:8000`. `GET /api/query/health` reports RAG and Gemini readiness. All feature routers live under the `/api` prefix.

For Render, use the backend root directory (`backend`), build with
`pip install -r requirements.txt`, and start with
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set `GEMINI_API_KEY`,
`GEMINI_MODEL`, `WORKSPACE_SESSION_SECRET`, and a production
`CORS_ALLOWED_ORIGINS` containing the exact deployed frontend origin. Keep all
Gemini variables on the backend service only. ChromaDB remains the active vector
backend and persists vectors under `CHROMA_DB_PATH`.

The Render Free filesystem is ephemeral. Repository clones are intentionally
used as a disposable working cache: an import can clone and index a public
GitHub repository in the running service, while metadata and vectors persist in
Supabase. After a restart, pending imports are recovered and cloned again; a
repository's file-preview endpoints require the clone to be present locally.

### Optional external API evaluation

The public-apis catalog was evaluated for developer-facing value. No new external API was added in this pass: repository Q&A and indexing have no dependency on third-party metadata services, and introducing unauthenticated/rate-limited calls would add failure modes without a corresponding UI contract. The highest-value future candidates are GitHub repository metadata and OSV vulnerability metadata, both behind explicit, cached feature services rather than the query path.

| API / Service | CodeAtlas feature | Value | Auth required | Rate limits | Integrated? |
|---|---|---|---|---|---|
| GitHub REST API | repository activity, releases, contributors | High for repository overview | Public data usually no; tokens improve limits/private access | Yes | No |
| OSV API | dependency vulnerability intelligence | High for risk analysis | No API key for basic use | Service limits apply | No |
| npm/PyPI registries | latest dependency metadata | Medium; useful after manifest extraction | Usually no for public packages | Yes | No |

---

## 🐳 Docker Usage

```bash
# Build and start
docker compose up --build

# Run in background
docker compose up -d

# Logs / stop
docker compose logs -f backend
docker compose down
```

The Compose setup exposes port `8000`, persists SQLite/ChromaDB/repositories/logs, live-mounts `backend/app` for development, and runs as a **non-root container user**.

---

## 📖 API Documentation

Interactive docs once the backend is running:

- **Swagger UI** → [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc** → [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI Schema** → [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

<details>
<summary><strong>System</strong></summary>

```text
GET /health
GET /version
```
</details>

<details>
<summary><strong>Repository</strong></summary>

```text
POST   /repositories
GET    /repositories
GET    /repositories/{repository_id}
GET    /repositories/{repository_id}/status
POST   /repositories/{repository_id}/update
POST   /repositories/{repository_id}/reindex
DELETE /repositories/{repository_id}
GET    /repositories/health/check
```
</details>

<details>
<summary><strong>Query</strong></summary>

```text
POST /query
POST /query/stream
POST /repositories/{repository_id}/query
GET  /query/health
```
</details>

<details>
<summary><strong>Dependency Graph</strong></summary>

```text
GET /repositories/{repository_id}/graph
GET /repositories/{repository_id}/graph/statistics
GET /repositories/{repository_id}/graph/nodes
GET /repositories/{repository_id}/graph/nodes/{node_id}
GET /repositories/{repository_id}/graph/edges
GET /repositories/{repository_id}/graph/neighbors/{node_id}
GET /repositories/{repository_id}/graph/path
GET /repositories/{repository_id}/graph/health
```
</details>

---

## 🔄 How It Works

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant TS as Tree-sitter
    participant ST as Sentence Transformers
    participant DB as ChromaDB
    participant G as Graph Builder
    participant Gm as Gemini

    U->>API: Submit GitHub repo URL
    API->>API: Validate & clone repository
    API->>TS: Parse source files
    TS-->>API: Symbols + citation metadata
    API->>ST: Generate embeddings
    ST-->>DB: Store vectors + metadata
    API->>G: Extract relationships
    G-->>DB: Persist dependency graph

    U->>API: Ask a question
    API->>DB: Embed → search → filter → dedupe → rerank
    DB-->>API: Assembled context
    API->>Gm: Generate grounded answer
    Gm-->>API: Answer
    API-->>U: Answer + file/line citations
```

---

## 🧪 Development

```bash
# Run tests
pytest -q

# Run with coverage
pytest --cov=backend/app --cov-report=term-missing
```

Tests isolate Gemini, embedding, vector-store, filesystem, and Git operations behind deterministic fixtures and mocks — the suite never hits real network or inference services.

---

## 🖥️ Frontend Development

Vite + React 19 + TypeScript, with React Router, TanStack Query, Tailwind CSS, Recharts, and React Flow.

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend origin |
| `VITE_API_PREFIX` | `/api` | FastAPI router prefix |

System probes (`/health`, `/version`) ride the same prefixed API client as feature routes, so they reach the backend behind prefix-only gateways (e.g. Vercel monorepo); the backend also keeps root-level `/health` for load balancers and the Docker healthcheck. ⚠️ Never place secrets in `VITE_`-prefixed variables — they ship straight to the browser.

---

## 🚢 Production Deployment

```bash
cd frontend
npm run build
npm run preview
```

Deploy `frontend/dist` to any static host. For Vercel/Netlify: project root `frontend`, build command `npm run build`, publish directory `dist`. Set `VITE_API_BASE_URL` / `VITE_API_PREFIX` in the host's environment settings, and make sure the backend's CORS config allows the deployed frontend origin.

**Required backend env var (separate frontend/backend hosts):** when the frontend and backend live on different origins (e.g. Vercel frontend → Render backend), set `CORS_ALLOWED_ORIGINS` on the backend to the exact deployed frontend origin, e.g. `CORS_ALLOWED_ORIGINS=https://codeatlas-ai.vercel.app`. Without it the browser blocks every cross-origin API response (the frontend shows "Backend: Unavailable" / request timeout even though the backend endpoints return 200).

For a full-stack deploy, run `docker compose up --build` from the repository root — the backend owns SQLite, ChromaDB, indexing, and server-side Gemini access, while the frontend deploys independently.

---

## 🎯 Design Principles

- **Server-side Gemini** — one explicit, configurable AI provider
- **Strict layering** — HTTP, orchestration, domain, and persistence never bleed into each other
- **Deterministic citations** — every answer is traceable, never hand-waved
- **Typed contracts** — explicit validation end-to-end
- **Lazy model loading** — fast startup, models load only when needed
- **Repository-scoped search** — no cross-repo context leakage
- **Graceful degradation** — partial failures during indexing/retrieval don't take down the system

---

## 🗺️ Roadmap

- [ ] Go, Rust, Java, and C# parsing
- [ ] Improved call-graph and cross-file reference resolution
- [ ] Incremental indexing via file checksums and Git commits
- [ ] Background job queues for large repositories
- [ ] Hybrid lexical + semantic retrieval
- [ ] Richer interactive graph visualization
- [ ] Multi-user workspaces and access controls
- [ ] Metrics, tracing, and production deployment manifests
- [ ] Dedicated global search endpoint (files + symbols)
- [ ] Dedicated analytics endpoint (commits, storage, processing history)
- [ ] End-to-end browser tests and visual regression coverage

---

## 📸 Screenshots

*Coming soon — dashboard, repository workspace, AI chat, dependency graph, and analytics views, in both dark and light themes.* Drop images under `docs/screenshots/` to populate this section.

---

## 📄 License

Distributed under the license included in [`LICENSE`](LICENSE).

<div align="center">

**Built for developers who want to understand a codebase, not just search it.**

</div>
# CodeAtlas AI

CodeAtlas is a Gemini-only code intelligence workspace. It ingests public GitHub repositories, parses and chunks source code, creates Sentence Transformer embeddings, stores them in ChromaDB, and answers grounded questions with file citations.

## Developer intelligence

Indexed repositories expose optional, feature-isolated intelligence endpoints and views for:

- GitHub public metadata (stars, forks, watchers, issues, branch, license)
- npm and PyPI package metadata from supported repository manifests
- OSV vulnerability matching for pinned dependency versions
- normalized dependency and security results with refreshable frontend queries

Supported manifests are `package.json`, `package-lock.json`, `requirements.txt`, and `pyproject.toml`. External provider failures do not stop repository ingestion or RAG.

## Appearance

The UI supports System, Light, Dark, and a branded Colorful theme. The selection is persisted by `next-themes` and applies without a reload.

## Environment variables

Backend deployment requires `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_SECONDS`, `GEMINI_MAX_TOKENS`, `GEMINI_TEMPERATURE`, `CORS_ALLOWED_ORIGINS`, `WORKSPACE_SESSION_SECRET`, and the existing `DATABASE_URL`. Public GitHub, OSV, npm, and PyPI APIs do not require keys.

## Workspace isolation

Before account login exists, each browser receives an opaque, signed,
HttpOnly workspace cookie. Repository ownership is derived server-side from
that workspace; the frontend cannot choose an owner. Chroma collections use
an HMAC-independent SHA-256 namespace derived from the workspace ID plus the
repository ID. Existing repositories with no `workspace_id` are quarantined
and are not visible to normal requests. To migrate one safely, explicitly
assign it to the intended workspace in a controlled database migration after
identifying that workspace; never backfill all legacy rows to one workspace.

The frontend uses `VITE_API_BASE_URL` and `VITE_API_PREFIX`. Never place `GEMINI_API_KEY` in frontend or Vercel environment variables.

## Local checks

Run the backend test suite with `pytest -q` from `backend/`, and the frontend checks with `npm run lint` and `npm run build` from `frontend/`.
