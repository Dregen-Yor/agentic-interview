# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered interview platform: Django backend (ASGI/WebSocket) + Vue 3 frontend + multi-agent system for automated interview orchestration.

## Common Commands

### Backend
```bash
# ASGI server (supports HTTP + WebSocket)
daphne -b 0.0.0.0 -p 8000 interview_backend.asgi:application

# HTTP-only dev server (no WebSocket support)
python manage.py runserver

# Database migrations (Django ORM / SQLite only)
python manage.py makemigrations && python manage.py migrate

# Initialize vector search indexes in MongoDB
python init.py

# Install Python dependencies (uv preferred)
uv sync
```

### Frontend
```bash
cd frontend
npm install
npm run dev          # Dev server with HMR
npm run build        # Production build (includes type-check)
npm run build-only   # Build without type-check
npm run type-check   # TypeScript validation only
npm run test:unit    # Vitest (framework configured, no test files yet)
```

## Architecture

### Dual-Channel API

The system exposes two parallel communication channels:

| Channel | Entry Point | Coordinator | LLM (Question/Scoring) | LLM (Security/Summary) |
|---------|------------|-------------|------------------------|------------------------|
| **WebSocket** (primary) | `consumers.py` → per-connection coordinator | Independent instance | `chatgpt_model` (gpt-5-mini) | `chatgpt_model` |
| **HTTP** (legacy compat) | `views.py` → global singleton coordinator | Shared `_global_coordinator` | `kimi_model` (kimi-k2) | `gemini_model` (gemini-2.5-flash) |

WebSocket endpoint: `ws://<host>:8000/ws/interview/<chat_id>/`

### Multi-Agent Pipeline

Each interview answer flows through this pipeline (orchestrated by `coordinator.py`):

```
Interview Start
  → ResumeParser       (LLM-driven resume → structured_profile, cached in session)

User Answer
  → SecurityAgent    (regex fast-check + LLM deep analysis → continue/warning/block)
  → ScoringAgent     (5-dimension scoring, readiness check)
  → Memory update    (record Q&A, scores, context)
  → QuestionGeneratorAgent  (next question, resume-anchored, may invoke RAG tool)
  → [After 5-6 rounds] SummaryAgent  (final report + hiring recommendation)
```

**Interview lifecycle**: 5-6 rounds. Early termination possible after round 4. Force-end at round 6. Security violations trigger immediate termination via separate path (`_finalize_interview_with_security_termination`).

### Agent Internals

All agents inherit from `BaseAgent` (`interview/agents/base_agent.py`), implementing `get_system_prompt()` and `process()`.

- **QuestionGeneratorAgent**: 4 question types (math_logic / technical / behavioral / experience), max 2 per type. Integrates LangChain tool calling for RAG search. Receives `parsed_profile` (not raw `resume_data`) and uses resume-anchored questioning rules to tie questions to specific resume items and weak dimensions.
- **ScoringAgent**: 5 dimensions totaling 10 points — math_logic(1-4), reasoning_rigor(1-2), communication(1-2), collaboration(0-1), growth_potential(0-1). Grades: A≥8.5, B≥7.0, C≥5.0, D<5.0.
- **SecurityAgent**: Dual-layer detection — fast regex pattern matching for known attack patterns, then LLM analysis. Three risk levels: low→continue, medium→warning, high→block.
- **SummaryAgent**: Generates comprehensive report with 5-dimension analysis, saves to MongoDB.

**Common pattern**: All agents include `_fix_common_json_issues()` to repair malformed LLM JSON output (markdown fencing, trailing commas, unescaped quotes).

### Resume Parsing & Anchored Questioning

Inspired by *Beyond the Resumé*, the system pre-processes resumes before the interview starts:

1. **`interview/rubrics.py`** — Pure data module defining 5 scoring dimensions with LOW/MEDIUM/HIGH level descriptors.
2. **`interview/agents/resume_parser.py`** — `ResumeParser` (standalone class, not a BaseAgent subclass) calls LLM once at interview start to produce a `structured_profile`:
   - Per-item: category, summary, inferred involvement/motivation, knowledge gaps, KSD, dimension signals
   - Aggregate: dimension signal levels, weakest/strongest dimensions, suggested probe items
   - Fallback: on LLM failure, returns all-MEDIUM profile so downstream degrades gracefully
3. **Integration flow**: `coordinator.start_interview()` → `ResumeParser.parse()` → result cached in `session.parsed_profile` and persisted in `conversation_memories.context.parsed_profile` → passed to `QuestionGeneratorAgent.process()` via `input_data["parsed_profile"]`
4. **QuestionGeneratorAgent** injects profile into prompt: formats items as compact text, highlights weak dimensions, suggests probe targets. System prompt includes "Resume-Anchored Questioning Rules" requiring new-topic questions to reference specific resume items.

**Note**: `QuestionGeneratorAgent.process()` no longer receives `resume_data` — all resume context flows through `parsed_profile`.

### Data Layer

**Dual-database strategy** — Django ORM models.py is intentionally empty:
- **SQLite** (Django): auth, sessions, admin (framework internals only)
- **MongoDB**: All business data, accessed via `RetrievalSystem` (`interview/tools/rag_tools.py`)

MongoDB collections: `users`, `resumes`, `problem` (knowledge base + 1024-dim vectors), `result`, `interview_memories`

Vector search uses Aliyun `text-embedding-v4` (not Ollama). RAG exposed as LangChain `@tool` for agent tool-calling.

### Frontend Architecture

Vue 3 + TypeScript + Composition API, Element Plus UI, Pinia state management.

Key routes (auth-guarded via JWT verification against `/api/verify/`):
- `/face2facetest` — Main interview view (WebSocket-based)
- `/interviewresult` — Score and report display
- `/resumerewriter` — Resume editing

Auth store (`stores/auth.ts`) manages JWT in localStorage with axios interceptors.

**Note**: Several features are stubbed/disabled — face verification (auto-passes), TTS audio (commented out), speech recognition via Xfyun ASR (`utils/xfyun-asr.ts` implemented but not wired in), spoken language test page (placeholder).

### API Endpoints

**Interview**: `POST /api/` (process answer), `GET /api/interview/status/`, `POST /api/interview/end/`

**Users** (`interview/users.py`): `POST /api/create/`, `POST /api/check/` (login→JWT), `POST /api/verify/`, `GET /api/resume/`, `POST /api/resume/update/`, `GET /api/result/`

## Environment Setup

### Required Services
- **Redis** (port 6379): Django Channels WebSocket layer
- **MongoDB**: Business data + vector search (Atlas or local with vector search capability)

### Environment Variables (`.env` in project root)
```bash
# MongoDB
MONGODB_URI=your_mongodb_uri
MONGODB_DB=your_db_name

# LLM API Keys & Base URLs
GPT_API_KEY=...          # For ChatGPT/Gemini/Kimi (via proxy)
GPT_BASE_URL=...
ALIYUN_API_KEY=...       # For Qwen + text-embedding-v4
ALIYUN_BASE_URL=...
DOUBAO_API_KEY=...       # For Doubao (ByteDance)
DOUBAO_BASE_URL=...
```

### LLM Models (`interview/llm.py`)
All configured via `langchain_openai.ChatOpenAI` with 30s timeout:
- `chatgpt_model` — gpt-5-mini (via proxy)
- `qwen_model` — qwen-plus (Aliyun)
- `gemini_model` — gemini-2.5-flash (via proxy)
- `doubao_model` — doubao-seed-1-6 (ByteDance, thinking disabled)
- `kimi_model` — kimi-k2-0711-preview (via proxy)

## Development Notes

- **No linter/formatter configured** for either Python or TypeScript
- **No test coverage**: backend `tests.py` is empty, frontend has Vitest configured but no test files
- **Frontend hardcodes** backend URL `101.76.218.89:8000` in multiple places (auth store, views)
- `RetrievalSystem` in `tools/rag_tools.py` is the unified data access layer — all MongoDB operations go through it
- Coordinator owns all data persistence to avoid duplicate saves from individual agents
