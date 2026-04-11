# SessionArchaeologist — Project Specification

## Overview

Build a self-hosted, agent-based system called **SessionArchaeologist** that transforms raw Claude Code session histories (JSONL from `~/.claude/projects/`) into structured, narratively coherent research documentation — suitable for whitepapers, conference talks (DEF CON, Black Hat, CCC style), and blog posts.

The core problem: Claude Code sessions that span thousands of turns and dozens of compactions lose critical context — debugging pivots, abandoned approaches, "aha moments", and the causal chain of technical decisions. Traditional summarization (including Claude Code's built-in compact) optimizes for token efficiency, not narrative fidelity. This system reconstructs the full research journey with human-in-the-loop refinement.

## Tech Stack

- **Backend**: FastAPI + Celery + Redis (task queue) + PostgreSQL (metadata & state) + ChromaDB or Qdrant (vector store)
- **Frontend**: React + TypeScript + Tailwind CSS
- **LLM**: Anthropic Claude API (Opus for synthesis, Sonnet for bulk extraction)
- **Embedding**: OpenAI `text-embedding-3-large` (dim=3072) via API
- **File format**: Reads `.jsonl` session files from Claude Code's `~/.claude/` directory structure

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     React Web UI                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Session   │ │ Timeline │ │ Narrative│ │ Human Review  │  │
│  │ Ingester  │ │ Explorer │ │ Editor   │ │ & Refinement  │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
└─────────────────────┬───────────────────────────────────────┘
                      │ REST API
┌─────────────────────▼───────────────────────────────────────┐
│                   FastAPI Backend                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Ingestion│ │ Pipeline │ │ Narrative│ │ Refinement    │  │
│  │ Service  │ │ Manager  │ │ Agent    │ │ Agent         │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │
└──────┬──────────────┬──────────────┬────────────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼──────┐
│  Celery     │ │ PostgreSQL│ │ Vector     │
│  + Redis    │ │ (metadata)│ │ Store      │
└─────────────┘ └───────────┘ └────────────┘
```

## Detailed Pipeline — 6 Stages

---

### Stage 1: Ingestion & Structural Parsing

**Goal**: Parse raw JSONL into a structured, indexed representation without any LLM calls.

**Input**: One or more `.jsonl` files from `~/.claude/projects/` or user upload.

**Processing**:
1. Parse each line of the JSONL. Claude Code session format typically contains message objects with fields like:
   - `type` (e.g. `user`, `assistant`, `system`, `summary`)
   - `message` (the actual content — can be nested with `content` blocks)
   - `timestamp` or positional ordering
   - Tool use blocks (`tool_name`, `tool_input`, `tool_result`)
   - System messages that indicate compaction events (look for summary/compaction markers)

2. For each turn, extract and store:
   - `turn_index`: sequential position
   - `timestamp`: if available, otherwise infer from ordering
   - `role`: user / assistant / system / tool_result
   - `content_text`: flattened text content
   - `tool_calls`: list of `{tool_name, command_or_input_summary, output_snippet}`
   - `is_compact_boundary`: boolean — detect where compaction summaries appear
   - `is_error`: boolean — detect error outputs, tracebacks, failed commands
   - `token_estimate`: rough token count (chars / 4 as approximation)
   - `content_hash`: for deduplication

3. Build a **Session Manifest**:
   - Total turns, total estimated tokens
   - Compact boundary positions (list of turn indices where compaction occurred)
   - Error density map (sliding window error frequency)
   - Tool usage frequency timeline
   - "Hot zones" — regions with high turn density in short time spans (likely debugging/iteration)

4. Store everything in PostgreSQL with proper indexing on `turn_index`, `timestamp`, `is_compact_boundary`, `is_error`.

**Output**: Session manifest JSON + all turns stored in DB.

**Important**: The JSONL format may vary between Claude Code versions. The parser should be resilient — log warnings on unparseable lines rather than crashing. Include a "raw preview" mode so the user can inspect what was parsed before proceeding.

---

### Stage 2: Intelligent Chunking

**Goal**: Split the session into overlapping chunks optimized for LLM processing, respecting narrative boundaries.

**Strategy**:
- Target chunk size: **120K tokens** of content (leaving room for system prompt + output in a 200K Sonnet context, or use Opus with larger budget)
- **Never split inside a compact boundary region** — always include the full compaction summary with the chunk it belongs to
- **Never split inside a hot zone** — keep debugging sequences intact
- **Overlap**: 15K tokens between consecutive chunks (tail of chunk N = head of chunk N+1)
- Prefer splitting at natural boundaries: user messages that start a new topic/task, long time gaps between turns, or after a tool call sequence completes

**Algorithm**:
1. Walk through turns sequentially, accumulating token count
2. When approaching chunk boundary (120K), scan ahead for the nearest "safe split point" within ±20K tokens
3. Safe split points (priority order):
   a. Large time gap (> 30 min between turns)
   b. User message that introduces a new topic (heuristic: no reference to previous tool output)
   c. End of a tool call → tool result → assistant response sequence
   d. Any user message (fallback)
4. Record overlap regions for cross-chunk continuity verification

**Output**: Ordered list of chunks with metadata: `{chunk_id, start_turn, end_turn, overlap_start_turn, estimated_tokens, contains_compact_boundaries: bool, hot_zone_count: int}`

---

### Stage 3: Chunk-Level Extraction (Map Phase)

**Goal**: Extract structured research notes from each chunk using LLM.

**LLM**: Claude Sonnet (cost-efficient for extraction tasks; switch to Opus if quality is insufficient)

**System Prompt for Extraction**:
```
You are a research archaeology assistant. You are analyzing a segment of a long
Claude Code session where a security researcher conducted technical research.
Your job is to extract structured notes that preserve the NARRATIVE of the research
process — not just the final results, but the journey: what was tried, what failed,
what pivoted, what was discovered accidentally.

This chunk is segment {chunk_id} of {total_chunks} in chronological order.
{if has_overlap}The first ~{overlap_tokens} tokens overlap with the previous chunk
for continuity — do not duplicate notes from that region unless adding new insight.{/if}

Extract the following in JSON format:

{
  "time_range": "approximate start-end based on any timestamps or contextual clues",
  "executive_summary": "2-3 sentence overview of what happened in this segment",
  "technical_decisions": [
    {
      "decision": "what was decided",
      "context": "why — what problem prompted this",
      "alternatives_considered": ["other approaches mentioned or tried"],
      "outcome": "did it work? what happened?"
    }
  ],
  "problems_encountered": [
    {
      "problem": "description of the issue",
      "symptoms": "error messages, unexpected behavior",
      "debugging_steps": ["what was tried to diagnose"],
      "resolution": "how it was fixed, or 'unresolved' / 'pivoted away'",
      "root_cause": "if identified",
      "lesson_learned": "generalizable takeaway, if any"
    }
  ],
  "pivots": [
    {
      "from": "original approach/direction",
      "to": "new approach/direction",
      "trigger": "what caused the change",
      "was_beneficial": true/false/null
    }
  ],
  "discoveries": [
    {
      "finding": "something learned or uncovered",
      "significance": "why it matters",
      "was_expected": true/false
    }
  ],
  "tools_and_commands": [
    "notable commands, scripts, or tool invocations worth preserving verbatim"
  ],
  "code_artifacts": [
    {
      "description": "what this code does",
      "language": "python/bash/etc",
      "snippet_or_reference": "short snippet if critical, otherwise describe"
    }
  ],
  "emotional_markers": [
    "moments of frustration, excitement, surprise — inferred from conversation tone"
  ],
  "open_questions": [
    "questions raised but not answered in this segment"
  ],
  "continuity_hooks": {
    "unresolved_from_previous": ["threads picked up from earlier"],
    "carried_forward": ["threads that continue into next segment"]
  }
}

Be thorough. Missing a pivot or a debugging dead-end is worse than being verbose.
The user wants to write a conference talk about this research — the "war stories" matter.
```

**Execution**: Run all chunks via Celery tasks (parallel where possible, but maintain ordering for overlap dedup). Store each chunk's extraction result in PostgreSQL linked to the session.

**Cost estimation**: Surface estimated API cost to the user before executing. Allow user to select Sonnet vs Opus per-stage.

---

### Stage 4: Narrative Synthesis (Reduce Phase)

**Goal**: Merge all chunk extractions into a single coherent research narrative.

**LLM**: Claude Opus (this is the quality-critical step)

**Process**:
1. If total extracted notes fit within ~800K tokens → single Opus call
2. If not → hierarchical reduce:
   - Group chunk extractions into batches of 5-10
   - Merge each batch into a "section narrative" (Opus)
   - Merge all section narratives into final narrative (Opus)

**System Prompt for Synthesis**:
```
You are helping a security researcher reconstruct the complete narrative arc of a
deep research project conducted over many Claude Code sessions. You have structured
extraction notes from {total_chunks} chronological segments.

Your task: Synthesize these into a coherent research narrative document with the
following structure:

## 1. Research Overview
- What was the research goal?
- What was the final outcome/finding?
- Timeline (start to end, major milestones)

## 2. Methodology Evolution
- How did the approach change over time?
- What was the initial plan vs what actually happened?

## 3. Key Technical Journey
For each major phase of the research, write a section that includes:
- What was being attempted
- What worked and what didn't
- Critical debugging moments (with enough technical detail to be educational)
- Pivots and their triggers

## 4. War Stories & Lessons Learned
- The most interesting failures and what they taught
- Unexpected discoveries
- Things that would be done differently in hindsight

## 5. Technical Artifacts
- Key tools, scripts, configurations that were developed
- Reusable techniques

## 6. Open Questions & Future Work
- Unresolved threads
- Natural extensions of the research

Write in a voice suitable for a technical conference talk or whitepaper.
Be specific — use actual error messages, command outputs, and code references
from the notes. The audience is technical peers who would appreciate the
debugging details and methodology, not just polished results.

Preserve the chronological flow — the reader should feel the progression
of the research, including the dead ends.
```

**Output**: A structured markdown document — the "draft narrative".

---

### Stage 5: Human Review & Refinement Loop (THE KEY DIFFERENTIATOR)

**Goal**: Let the user iteratively refine the narrative using their memory and domain expertise.

This is where the web UI becomes critical. The user will:

#### 5a. Timeline Review
- Display an interactive timeline visualization of the entire session
- Each chunk is a segment on the timeline, colored by:
  - 🔴 High error density (debugging zones)
  - 🟡 Pivots detected
  - 🟢 Productive progress
  - 🔵 Compact boundaries
- User can click any segment to see the raw turns AND the extracted notes side-by-side
- User can flag segments: "this extraction missed something important" or "this is wrong"

#### 5b. Narrative Editor
- Display the Stage 4 narrative in a rich editor (consider Tiptap or Lexical)
- Each section/paragraph has a "source" indicator showing which chunks it was derived from
- User can:
  - **Annotate**: Add inline comments like "Actually, the reason I tried this was because of X" or "This part is wrong — what really happened was Y"
  - **Flag for re-extraction**: Mark a section as "needs more detail from source" → system re-queries the relevant chunks with a targeted prompt
  - **Inject memory**: Add context the LLM couldn't know: "I was at a conference when I thought of this", "I got the idea from talking to colleague X", personal motivations, political context within the team
  - **Reorder / restructure**: Drag sections to change narrative flow
  - **Set tone**: Per-section tone markers: "technical deep-dive", "war story / casual", "executive summary", "skip this"

#### 5c. Refinement Agent
When the user submits annotations/corrections, the Refinement Agent:

1. Collects all user feedback for the current revision
2. For sections flagged "needs more detail":
   - Uses RAG (Stage 6) to retrieve relevant raw turns
   - Re-runs extraction on those specific turns with a focused prompt informed by the user's annotation
3. For sections with user corrections/injections:
   - Rewrites the section incorporating the user's input while maintaining narrative flow
4. For tone changes:
   - Rewrites affected sections in the requested tone
5. Produces a new revision of the full narrative
6. Presents a diff view to the user showing what changed

**Revision history**: Every revision is stored. The user can diff any two revisions, rollback, or branch.

**Convergence**: After each refinement cycle, the system asks: "Rate this revision 1-5 for completeness and accuracy." Track scores over revisions. Suggest "this narrative may be ready for final export" when scores stabilize at 4+.

---

### Stage 6: RAG Detail Retrieval (Supporting Infrastructure)

**Goal**: Enable on-demand retrieval of specific raw content from the original session.

**Embedding Pipeline**:
1. Each turn from Stage 1 → embed with `text-embedding-3-large` (dim=3072)
2. For long turns (>2000 tokens), split into paragraphs and embed separately, maintaining parent turn reference
3. Store in ChromaDB or Qdrant with metadata filters: `turn_index`, `role`, `is_error`, `chunk_id`, `has_tool_call`
4. Also embed each Stage 3 extraction note → enables "find the raw data behind this summary"

**Query Modes**:
- **Semantic search**: "find where I debugged the MTU issue with WireGuard"
- **Temporal search**: "what happened between turn 500-600"
- **Error search**: "show me all tracebacks related to certificate errors"
- **Tool search**: "find all bash commands involving iptables"
- **Hybrid**: Combine semantic similarity with metadata filters

**UI Integration**: In the Narrative Editor, user can:
- Highlight any text → "Find source" → shows top-5 matching raw turns
- Open a search panel → query the full session → insert relevant content into the narrative

---

## Web UI Design

### Pages / Views

#### 1. Dashboard
- List of imported sessions with metadata (date range, turn count, token count, processing status)
- "Import new session" button (file upload or path input)
- Quick stats: total sessions, total tokens processed, narratives generated

#### 2. Session Inspector
- Left panel: Session manifest — stats, hot zones, compact boundaries
- Center: Scrollable turn-by-turn view with syntax highlighting for code blocks
- Right panel: Chunk boundaries visualized, extraction status per chunk
- Top: Interactive timeline bar (scrub to navigate)

#### 3. Pipeline Control
- Step-by-step pipeline progress with status indicators
- Cost estimation before each LLM-calling stage (show model, est. tokens, est. cost)
- User can configure: model choice per stage, chunk size, overlap size
- "Run next stage" / "Run all" controls
- Real-time Celery task monitoring (progress bars, ETA)

#### 4. Narrative Workspace (Primary working area)
- Split view: Narrative editor (left 60%) + Source explorer (right 40%)
- Narrative editor:
  - Rich text with section headers matching the Stage 4 template
  - Inline annotation system (similar to Google Docs comments)
  - Section-level controls: tone selector, "needs more detail" flag, "mark as verified"
  - Paragraph-level provenance links (click to see source chunks)
- Source explorer:
  - RAG search interface
  - Raw turn viewer with highlights matching current narrative section
  - "Insert into narrative" button for relevant finds

#### 5. Export
- Export formats:
  - Markdown (for further editing)
  - DOCX (whitepaper format with ToC, headers, code blocks)
  - Slide outline (structured for PPTX generation — section → slide mapping)
  - JSON (structured data for programmatic consumption)
- Template selection: "Whitepaper", "Conference Talk Notes", "Blog Post", "Internal Report"
- Each template adjusts the final Opus rewrite prompt for appropriate tone/structure

### UI/UX Requirements
- Dark theme default (the user is a security researcher who stares at terminals)
- Monospace font for code/raw content, proportional for narrative text
- Keyboard shortcuts for common actions (navigate chunks, approve sections, search)
- WebSocket for real-time pipeline progress updates
- Responsive but desktop-first (this is a workstation tool)

---

## Data Models (PostgreSQL)

```sql
-- Core session data
sessions (
  id UUID PK,
  name TEXT,
  source_path TEXT,
  imported_at TIMESTAMP,
  total_turns INT,
  total_tokens_est BIGINT,
  manifest JSONB,  -- the Stage 1 manifest
  status TEXT  -- 'imported', 'chunked', 'extracted', 'synthesized', 'refining'
)

-- Individual turns from the JSONL
turns (
  id UUID PK,
  session_id UUID FK,
  turn_index INT,
  role TEXT,
  content_text TEXT,
  tool_calls JSONB,
  is_compact_boundary BOOL,
  is_error BOOL,
  token_estimate INT,
  content_hash TEXT,
  raw_jsonl_line JSONB,  -- preserve original for debugging
  INDEX (session_id, turn_index)
)

-- Chunks derived from intelligent splitting
chunks (
  id UUID PK,
  session_id UUID FK,
  chunk_index INT,
  start_turn INT,
  end_turn INT,
  overlap_start_turn INT,
  token_estimate INT,
  hot_zone_count INT,
  contains_compact_boundary BOOL,
  extraction_status TEXT,  -- 'pending', 'processing', 'done', 'failed'
  extraction_result JSONB,  -- Stage 3 output
  extraction_model TEXT,
  extraction_cost_est FLOAT
)

-- Narrative revisions
narratives (
  id UUID PK,
  session_id UUID FK,
  revision INT,
  parent_revision INT NULL,
  content_md TEXT,
  synthesis_model TEXT,
  user_score INT NULL,
  created_at TIMESTAMP,
  annotations JSONB  -- user feedback that triggered this revision
)

-- User annotations on narrative sections
annotations (
  id UUID PK,
  narrative_id UUID FK,
  section_path TEXT,  -- e.g. "key_technical_journey.phase_2.paragraph_3"
  annotation_type TEXT,  -- 'correction', 'injection', 'needs_detail', 'tone_change', 'verified'
  content TEXT,
  source_chunk_ids UUID[],
  resolved BOOL DEFAULT FALSE,
  created_at TIMESTAMP
)
```

---

## API Endpoints

```
POST   /api/sessions/import          -- Upload JSONL file(s)
GET    /api/sessions                  -- List all sessions
GET    /api/sessions/{id}             -- Session detail + manifest
GET    /api/sessions/{id}/turns       -- Paginated turns (with filters)
GET    /api/sessions/{id}/turns/{idx} -- Single turn detail

POST   /api/sessions/{id}/chunk       -- Trigger Stage 2 chunking
GET    /api/sessions/{id}/chunks      -- List chunks with status

POST   /api/sessions/{id}/extract              -- Trigger Stage 3 (all chunks)
POST   /api/sessions/{id}/chunks/{cid}/extract -- Trigger Stage 3 (single chunk)
GET    /api/sessions/{id}/chunks/{cid}/result  -- Get extraction result

POST   /api/sessions/{id}/synthesize  -- Trigger Stage 4 narrative synthesis
GET    /api/sessions/{id}/narratives  -- List all revisions
GET    /api/sessions/{id}/narratives/{rev}  -- Get specific revision

POST   /api/sessions/{id}/narratives/{rev}/annotate  -- Add user annotation
POST   /api/sessions/{id}/narratives/{rev}/refine    -- Trigger Stage 5 refinement
GET    /api/sessions/{id}/narratives/diff/{rev1}/{rev2} -- Diff two revisions

POST   /api/sessions/{id}/search      -- RAG search (Stage 6)
POST   /api/sessions/{id}/export      -- Export narrative in chosen format

GET    /api/pipeline/{id}/status       -- Pipeline progress (WebSocket upgrade available)
GET    /api/config                     -- Current model/cost configuration
PUT    /api/config                     -- Update configuration
```

---

## Configuration

```yaml
# config.yaml
llm:
  extraction_model: "claude-sonnet-4-20250514"  # Stage 3
  synthesis_model: "claude-opus-4-20250514"      # Stage 4
  refinement_model: "claude-opus-4-20250514"     # Stage 5
  anthropic_api_key: "${ANTHROPIC_API_KEY}"

embedding:
  model: "text-embedding-3-large"
  dimensions: 3072
  openai_api_key: "${OPENAI_API_KEY}"

chunking:
  target_chunk_tokens: 120000
  overlap_tokens: 15000
  max_lookahead_tokens: 20000

pipeline:
  max_parallel_extractions: 5  # Celery concurrency for Stage 3
  cost_confirmation_threshold: 5.00  # USD — require user confirmation above this

vector_store:
  provider: "chromadb"  # or "qdrant"
  persist_directory: "./data/vectordb"

database:
  url: "postgresql://localhost:5432/session_archaeologist"

redis:
  url: "redis://localhost:6379/0"
```

---

## Development Notes

### JSONL Format Investigation
The JSONL format from Claude Code may vary. Before building the full parser, the first task should be:
1. Read 2-3 sample JSONL files from `~/.claude/projects/`
2. Document the actual schema (field names, nesting structure, how compactions appear)
3. Handle edge cases: multi-line tool outputs, binary content references, image blocks
4. Build the parser to match the REAL format, not assumptions

### Prompt Engineering Considerations
- The extraction prompt (Stage 3) is the most critical piece — it determines what information survives. Iterate on it with real data before running full pipelines.
- For Stage 5 refinement, the prompt should include both the previous narrative version AND the user's annotations, with clear instructions on what changed and what to preserve.
- Consider adding a "research domain" configuration — the extraction prompts can be tuned for security research vs. software engineering vs. data science contexts.

### Cost Management
- Always show estimated cost before executing LLM stages
- Cache extraction results — if a chunk hasn't changed, don't re-extract
- Allow "dry run" mode that shows what would be sent to the API without actually calling it
- Track actual spend per session and per pipeline run

### RAG Quality
- text-embedding-3-large handles code content well, but for very short error messages or commands, consider also storing exact-match / BM25 indices alongside vector search
- The hybrid search (semantic + keyword + metadata filter) will outperform pure vector search significantly for this use case
- Consider using Qdrant's built-in hybrid search if choosing Qdrant as the vector store

### Extensibility
- The Stage 3 extraction JSON schema should be configurable — different research types may need different fields
- Export templates should be pluggable — user can define custom Opus prompts for their specific conference format
- Consider a plugin system for custom JSONL formats (e.g., from other LLM tools, not just Claude Code)

---

## Implementation Priority

1. **Phase 1 (Core Pipeline)**: JSONL parser → Chunking → Extraction → Synthesis → Basic markdown export. CLI-only is fine for this phase. Get the pipeline working end-to-end with real data.

2. **Phase 2 (Web UI - Read Path)**: Dashboard, Session Inspector, Timeline visualization, Pipeline progress view. User can import, run pipeline, and view results.

3. **Phase 3 (Web UI - Write Path)**: Narrative Editor with annotations, Refinement Agent loop, Revision history + diff view. This is where the human-in-the-loop magic happens.

4. **Phase 4 (RAG + Search)**: Embedding pipeline, vector store integration, search UI in Narrative Workspace, "Find source" feature.

5. **Phase 5 (Export + Polish)**: DOCX/PPTX export, template system, cost analytics dashboard, keyboard shortcuts, performance optimization.

---

## Project Name Rationale

"SessionArchaeologist" — because we're excavating buried research narratives from compressed session artifacts, reconstructing the full story from fragmentary records, much like how archaeologists piece together history from layered strata of artifacts. Each compaction boundary is a stratum; each hot zone is a site worth careful excavation.
