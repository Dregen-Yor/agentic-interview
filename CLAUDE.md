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
# Development server
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

# Development server
npm run dev

# Build for production
npm run build

# Type checking
npm run type-check

# Unit tests
npm run test:unit
```

### Python Dependencies
```bash
# Install using uv (preferred)
uv sync

# Or using pip
pip install -r requirements.txt  # if exists, otherwise use pyproject.toml
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
- **Redis**: For Django Channels WebSocket layer (port 6379)
- **MongoDB**: For resume storage and vector search
- **Ollama**: Local embedding model server (port 11434)
- **TTS Service**: External text-to-speech API

### Environment Variables
Create `.env` file in project root:
```
DEEPSEEK_API_KEY=your_deepseek_key
GEMINI_API_KEY=your_gemini_key  # New: for security agent
MONGODB_URI=your_mongodb_connection_string
MONGODB_DB=your_database_name
MONGO_URI=your_mongodb_uri
MONGO_DATABASE_NAME=your_db_name
```

## Development Notes

### Running the Application
1. Start Redis server
2. Start MongoDB
3. Start Ollama with embedding model: `ollama run Q78KG/gte-Qwen2-7B-instruct:latest`
4. Run Django server: `python manage.py runserver`
5. Run Vue dev server: `cd frontend && npm run dev`

### Multi-Agent System Features
- **Intelligent Question Generation**: Context-aware questions based on resume and performance
- **Comprehensive Scoring**: Multi-dimensional evaluation with detailed feedback
- **Security Monitoring**: Real-time detection of manipulation attempts
- **Adaptive Workflow**: Dynamic interview length based on performance assessment
- **Detailed Analytics**: Complete interview transcripts and analysis

### Database Setup
- Django uses SQLite for session/auth data
- MongoDB stores resumes, users, interview results, and knowledge base with vector embeddings
- Vector search requires MongoDB Atlas or properly configured MongoDB with vector search capability

### WebSocket Communication
- Interview WebSocket: `ws://localhost:8000/ws/interview/{chat_id}/`
- Enhanced message types: `question`, `security_warning`, `interview_complete`
- Automatic session management and cleanup

### Authentication Flow
- JWT tokens stored in localStorage
- Route guards check authentication status
- Token validation on protected routes
- Login redirects preserve intended destination

### Backward Compatibility
The system maintains backward compatibility with existing frontend code:
- Old API endpoints continue to work with fallback mechanisms
- WebSocket protocol enhanced but compatible
- Session management preserved for HTTP-based interactions