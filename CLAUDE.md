# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AI-powered interview platform with a full-stack architecture:
- **Backend**: Django application with WebSocket support for real-time communication
- **Frontend**: Vue 3 + TypeScript SPA with Vite build system
- **AI Components**: Multi-agent system with specialized agents for different interview tasks

## Common Commands

### Backend (Django)
```bash
# Development server with ASGI support
daphne -b 0.0.0.0 -p 8000 interview_backend.asgi:application

# Alternative: Basic development server (HTTP only, no WebSocket)
python manage.py runserver

# Database migrations
python manage.py makemigrations
python manage.py migrate

# Django shell
python manage.py shell

# Create superuser
python manage.py createsuperuser
```

### Frontend (Vue.js)
```bash
cd frontend

# Install dependencies
npm install

# Development server (with hot reload)
npm run dev

# Build for production (includes type checking)
npm run build

# Build only (without type checking)
npm run build-only

# Type checking only
npm run type-check

# Unit tests (Vitest)
npm run test:unit

# Preview production build
npm run preview
```

### Python Dependencies
```bash
# Install using uv (preferred, uses Tsinghua mirror)
uv sync

# Or install from pyproject.toml
pip install -e .
```

## Architecture Overview

### Multi-Agent Interview System
The system now uses a sophisticated multi-agent architecture with specialized agents:

1. **Question Generator Agent** (`interview/agents/question_generator.py`)
   - Generates contextual interview questions based on resume and previous responses
   - Integrates with RAG system for technical questions
   - Adapts difficulty based on candidate performance

2. **Scoring Agent** (`interview/agents/scoring_agent.py`)
   - Evaluates candidate responses across multiple dimensions
   - Provides detailed feedback and scoring rationale
   - Determines when sufficient information is gathered for final decision

3. **Security Agent** (`interview/agents/security_agent.py`)
   - Detects prompt injection and system manipulation attempts
   - Monitors for inappropriate content and gaming attempts
   - Provides session-level security analysis

4. **Summary Agent** (`interview/agents/summary_agent.py`)
   - Generates comprehensive interview summaries
   - Makes final hiring recommendations
   - Provides detailed candidate analysis and feedback

5. **Multi-Agent Coordinator** (`interview/agents/coordinator.py`)
   - Orchestrates the entire interview workflow
   - Manages agent interactions and state transitions
   - Handles session lifecycle and cleanup

### Backend Structure
- **Django Project**: `interview_backend/` - Main Django configuration
- **Interview App**: `interview/` - Core interview functionality
  - `agents/` - Multi-agent system components
    - `base_agent.py` - Abstract base class for all agents
    - `memory.py` - Advanced interview memory management
    - `retrieval.py` - RAG and database retrieval system
  - `consumers.py` - WebSocket consumer using multi-agent system
  - `views.py` - HTTP API with backward compatibility
  - `models.py` - Database models
- **Database**: SQLite for Django models, MongoDB for resume/user data and vector search

### Frontend Structure
- **Vue 3 + TypeScript** with Composition API
- **Router**: Vue Router with authentication guards
- **State Management**: Pinia stores (`auth.ts`, `counter.ts`)
- **UI Components**: Element Plus UI library + custom components
- **Views**: Route-based views for different interview stages

### Key Integration Points
- **WebSocket Communication**: Real-time multi-agent interview management
- **HTTP API**: Backward-compatible REST endpoints
- **Authentication**: JWT-based with token verification
- **File Upload**: Resume processing and storage
- **TTS Integration**: Text-to-speech via external service (`http://101.76.216.150:9880/`)

### New API Endpoints
- `GET /api/interview/status/` - Get current interview session status
- `POST /api/interview/end/` - Manually end interview session
- `POST /api/` - Enhanced interview endpoint with multi-agent support

## Environment Dependencies

### Required Services
- **Redis**: For Django Channels WebSocket layer (port 6379) - `redis-server`
- **MongoDB**: For resume storage and vector search - `mongod`
- **Ollama**: Local embedding model server (port 11434) - `ollama run Q78KG/gte-Qwen2-7B-instruct:latest`
- **TTS Service**: External text-to-speech API (`http://101.76.216.150:9880/`)

### Environment Variables
Create `.env` file in project root:
```bash
# AI API Keys
DEEPSEEK_API_KEY=your_deepseek_key
GEMINI_API_KEY=your_gemini_key

# MongoDB Configuration
MONGO_URI=your_mongodb_uri
MONGO_DATABASE_NAME=your_db_name
```

### Service Startup Sequence
For full functionality, start services in this order:
```bash
# 1. Start Redis
redis-server

# 2. Start MongoDB  
mongod

# 3. Start Ollama embedding model
ollama run Q78KG/gte-Qwen2-7B-instruct:latest

# 4. Start Django backend
daphne -b 0.0.0.0 -p 8000 interview_backend.asgi:application

# 5. Start Vue frontend (separate terminal)
cd frontend && npm run dev
```

## Development Notes

### Multi-Agent System Architecture
Key components for understanding the interview workflow:

- **BaseAgent** (`interview/agents/base_agent.py`): Abstract base class defining common interface
- **Coordinator** (`interview/agents/coordinator.py`): Orchestrates agent interactions and state
- **Memory System** (`interview/agents/memory.py`): Manages interview context and history
- **Retrieval System** (`interview/agents/retrieval.py`): RAG integration for knowledge queries

### WebSocket Communication Protocol
- **Endpoint**: `ws://localhost:8000/ws/interview/{chat_id}/`
- **Message Types**: `question`, `security_warning`, `interview_complete`  
- **Session Management**: Automatic cleanup and state management

### Database Architecture
- **Django Models**: SQLite database for session/auth data (standard Django ORM)
- **MongoDB Collections**: Resume storage, user data, interview results, knowledge base with vector embeddings
- **Vector Search**: Requires MongoDB Atlas or local MongoDB with vector search capability

### Agent Development Pattern
To create custom agents, inherit from BaseAgent:

```python
from interview.agents.base_agent import BaseAgent
from typing import Dict, Any

class CustomAgent(BaseAgent):
    def get_system_prompt(self) -> str:
        return "Your system prompt here"
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        # Processing logic
        return {"result": "output"}
```

### Authentication & Security
- **JWT Tokens**: Stored in localStorage, validated on protected routes
- **Security Agent**: Real-time detection of prompt injection and manipulation attempts
- **Session Isolation**: Each interview session independently managed
- **CORS**: Currently configured for development (allow all origins)