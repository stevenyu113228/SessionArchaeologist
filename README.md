# SessionArchaeologist

Transform Claude Code session histories into structured, narratively coherent research documentation — suitable for whitepapers, conference talks (DEF CON, Black Hat, CCC), and blog posts.

## The Problem

Claude Code sessions that span thousands of turns and dozens of compactions lose critical context — debugging pivots, abandoned approaches, "aha moments", and the causal chain of technical decisions. Traditional summarization optimizes for token efficiency, not narrative fidelity.

SessionArchaeologist reconstructs the full research journey with:
- **6-stage pipeline**: Parse → Chunk → Extract → Synthesize → Refine → Export
- **ReAct agent loop**: AI autonomously searches source data for evidence before writing
- **Human-in-the-loop refinement**: Annotate, expand, shrink, and restructure with full source traceability
- **Subagent support**: Zip upload of full Claude Code project directories (main session + parallel sub-agents)

## Features

| Feature | Description |
|---------|-------------|
| **JSONL / Zip Upload** | Drag & drop `.jsonl` (single session) or `.zip` (project with subagents) |
| **Auto Pipeline** | Upload → chunk → extract → synthesize → embed in one click |
| **Parallel Extraction** | 5 concurrent LLM calls via ThreadPoolExecutor + SSE progress |
| **Section-by-Section Synthesis** | 6 dedicated Opus calls per narrative section for thorough output |
| **RAG Search** | ChromaDB + text-embedding-3-large for semantic search across raw session data |
| **ReAct Agent** | Anthropic native tool-use loop — AI searches, reads, reasons, then writes |
| **Expand/Shrink** | Per-section `[+]`/`[-]` buttons — expand with RAG evidence, shrink preserving key facts |
| **Annotations** | Correction, injection, needs_detail, add_subsection, tone_change |
| **Auto-Placement** | "Let AI find the right section" — agent reads narrative and decides where to apply |
| **Translation** | One-click Sonnet translation to 繁體中文 (section-by-section) |
| **Diff View** | Unified diff between any two revisions |
| **Export** | Markdown, DOCX, slide outline, JSON + template rewrite (whitepaper, conference talk, blog, report) |
| **Dark Theme** | Terminal-native dark UI, monospace for code, proportional for prose |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    React + Tailwind UI                       │
│  Dashboard │ Session Inspector │ Narrative Editor │ Export   │
└─────────────────────────┬───────────────────────────────────┘
                          │ REST API + SSE
┌─────────────────────────▼───────────────────────────────────┐
│                   FastAPI Backend                            │
│  Parser │ Chunker │ Extractor │ Synthesizer │ Refiner       │
│                   ReAct Agent Engine                         │
└──────┬──────────────┬──────────────┬────────────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼──────┐
│ PostgreSQL  │ │  Redis    │ │ ChromaDB   │
│ (sessions,  │ │  (queue)  │ │ (vectors)  │
│  turns,     │ │           │ │            │
│  narratives)│ │           │ │            │
└─────────────┘ └───────────┘ └────────────┘
```

## Quick Start

### Docker (recommended)

```bash
# 1. Clone and configure
git clone <repo-url> && cd SessionArchaeologist
cp .env.example .env
# Edit .env with your API key

# 2. Start everything
docker compose up -d

# 3. Open http://localhost:3000
```

### Local Development

```bash
# Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
docker compose up -d postgres redis  # just infra
alembic upgrade head
uvicorn archaeologist.api.app:app --port 8000 --reload

# Frontend
cd frontend && npm install && npx vite --port 5173
```

## Configuration

Copy `.env.example` to `.env` and set:

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_BASE_URL` | API endpoint (Anthropic or compatible proxy) | `https://api.anthropic.com` |
| `ANTHROPIC_AUTH_TOKEN` | API key or JWT token | — |
| `EXTRACTION_MODEL` | Model for chunk extraction (Stage 3) | `claude-4.6-sonnet` |
| `SYNTHESIS_MODEL` | Model for narrative synthesis (Stage 4) | `claude-4.6-opus` |
| `REFINEMENT_MODEL` | Model for refinement and expand/shrink | `claude-4.6-opus` |
| `EMBEDDING_MODEL` | Model for RAG embeddings | `text-embedding-3-large` |
| `CHUNK_TARGET_TOKENS` | Target tokens per chunk | `120000` |
| `MAX_PARALLEL_EXTRACTIONS` | Concurrent extraction workers | `5` |

## Pipeline Stages

### Stage 1: Parse
Reads Claude Code `.jsonl` session files. Extracts turns, tool calls, errors, timestamps, thinking blocks. Builds session manifest with hot zones, error density, tool usage timeline.

### Stage 2: Chunk
Splits sessions into ~120K token chunks respecting narrative boundaries. Never splits inside hot zones or compact boundaries. 15K token overlap for continuity.

### Stage 3: Extract
Each chunk → LLM extraction of technical decisions, problems, pivots, discoveries, war stories, code artifacts, emotional markers. Parallel processing with SSE progress.

### Stage 4: Synthesize
Section-by-section Opus synthesis:
1. Research Overview + Timeline
2. Methodology Evolution
3. Key Technical Journey (largest section)
4. War Stories & Lessons Learned
5. Technical Artifacts
6. Open Questions & Future Work

### Stage 5: Refine
Human-in-the-loop refinement powered by ReAct agent:
- **Annotations**: Correction, injection, needs_detail, add_subsection, tone_change
- **Expand [+]**: Agent searches RAG for evidence → enriches section
- **Shrink [-]**: Condenses while preserving key facts
- **Auto-placement**: Agent determines which section to modify
- **Translation**: Section-by-section Sonnet translation

### Stage 6: Export
Markdown, DOCX (formatted with headings/code blocks/tables), slide outline, JSON. Optional template rewrite: whitepaper, conference talk, blog post, internal report.

## CLI

```bash
archaeologist ingest <path>          # Import JSONL
archaeologist chunk <session-id>     # Intelligent chunking
archaeologist extract <session-id>   # LLM extraction (parallel)
archaeologist synthesize <session-id># Narrative synthesis
archaeologist refine <id> -f f.yaml  # YAML-based refinement
archaeologist embed <session-id>     # Build vector index
archaeologist search <id> "query"    # RAG search
archaeologist export <session-id>    # Markdown export
archaeologist run <path>             # Full pipeline
```

## API Endpoints

```
POST   /api/sessions/upload          Upload .jsonl
POST   /api/sessions/upload-project  Upload .zip (main + subagents)
GET    /api/sessions                 List sessions
GET    /api/sessions/{id}            Session detail + subagents
GET    /api/sessions/{id}/turns      Paginated turns
GET    /api/sessions/{id}/chunks     List chunks

POST   /api/sessions/{id}/run-pipeline    Auto-run full pipeline
GET    /api/sessions/{id}/run-pipeline/progress  SSE progress stream

GET    /api/sessions/{id}/narratives           List revisions
GET    /api/sessions/{id}/narratives/{rev}     Get revision
PUT    /api/sessions/{id}/narratives/{rev}     Direct edit
POST   /api/sessions/{id}/narratives/{rev}/refine          Apply annotations
POST   /api/sessions/{id}/narratives/{rev}/expand-section  Expand with RAG
POST   /api/sessions/{id}/narratives/{rev}/shrink-section  Condense
POST   /api/sessions/{id}/narratives/{rev}/translate       Translate

POST   /api/sessions/{id}/search     RAG search
POST   /api/sessions/{id}/export     Export (md/docx/slides/json + templates)
```

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, SQLAlchemy, Alembic, Celery
- **Frontend**: React 19, TypeScript, Tailwind CSS, Vite
- **LLM**: Anthropic Claude (Opus for synthesis, Sonnet for extraction/translation)
- **Embedding**: OpenAI text-embedding-3-large (or compatible)
- **Vector Store**: ChromaDB
- **Database**: PostgreSQL 16
- **Queue**: Redis 7
- **Deployment**: Docker Compose (4 services)

## Project Name

"SessionArchaeologist" — because we're excavating buried research narratives from compressed session artifacts, reconstructing the full story from fragmentary records, much like how archaeologists piece together history from layered strata of artifacts. Each compaction boundary is a stratum; each hot zone is a site worth careful excavation.

## License

MIT
