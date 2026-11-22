# DocChat Technical Architecture

This document provides a detailed technical overview of the DocChat system architecture, design decisions, and implementation details.

## Table of Contents

- [System Overview](#system-overview)
- [Architecture Diagram](#architecture-diagram)
- [Technology Stack](#technology-stack)
- [Database Schema](#database-schema)
- [API Design](#api-design)
- [Authentication Flow](#authentication-flow)
- [Document Processing Pipeline](#document-processing-pipeline)
- [Chat & RAG Implementation](#chat--rag-implementation)
- [Voice Features](#voice-features)
- [Security Considerations](#security-considerations)
- [Performance Optimizations](#performance-optimizations)

## System Overview

DocChat is a full-stack web application that implements a Retrieval-Augmented Generation (RAG) system for conversational AI over document collections. The architecture follows modern best practices with a clear separation between frontend, backend, and data layers.

### Design Principles

1. **Single Responsibility**: Each component has a clear, focused purpose
2. **Layered Architecture**: Separation of concerns (presentation, business logic, data access)
3. **RESTful API**: Standard HTTP methods and status codes
4. **Stateless Backend**: JWT tokens for authentication, no server-side sessions
5. **Security First**: Input validation, rate limiting, secure password storage

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Browser                          │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              React SPA (Port 8000)                       │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────┐   │  │
│  │  │  Login  │  │Documents│  │ Agents  │  │   Chat   │   │  │
│  │  │  Page   │  │  Page   │  │  Page   │  │   Page   │   │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └──────────┘   │  │
│  │                                                          │  │
│  │  ┌──────────────────────────────────────────────────┐   │  │
│  │  │         API Client (Axios + JWT Interceptors)    │   │  │
│  │  └──────────────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTPS/REST API
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Port 8000)                  │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │                     API Routers                        │    │
│  │  /auth  /documents  /agents  /chat  /voice            │    │
│  └─────────────────┬──────────────────────────────────────┘    │
│                    │                                            │
│  ┌─────────────────▼──────────────────────────────────────┐    │
│  │                  Service Layer                         │    │
│  │  - DocumentService  - ChatService                      │    │
│  │  - AgentService     - VoiceService                     │    │
│  └─────────────────┬──────────────────────────────────────┘    │
│                    │                                            │
│  ┌─────────────────▼──────────────────────────────────────┐    │
│  │              SQLAlchemy Models/ORM                     │    │
│  └─────────────────┬──────────────────────────────────────┘    │
└────────────────────┼────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                          │
│                                                                 │
│  Tables: users, documents, chunks, embeddings, agents,         │
│          agent_documents, chat_sessions, chat_messages         │
└─────────────────────────────────────────────────────────────────┘

External Services:
┌──────────────────┐
│   OpenAI API     │ ← Used for embeddings, chat completion, TTS, STT
└──────────────────┘
```

## Technology Stack

### Frontend
- **React 19**: Latest React with concurrent features
- **TypeScript**: Type safety and better IDE support
- **Vite**: Fast build tool and development server
- **React Router v6**: Client-side routing
- **Tailwind CSS**: Utility-first CSS framework
- **Axios**: HTTP client with interceptors

### Backend
- **FastAPI**: Modern Python web framework with automatic OpenAPI docs
- **SQLAlchemy**: SQL toolkit and ORM
- **Alembic**: Database migration tool
- **Pydantic**: Data validation using Python type hints
- **python-jose**: JWT token generation and validation
- **Passlib + Bcrypt**: Secure password hashing
- **SlowAPI**: Rate limiting middleware
- **PyPDF2**: PDF text extraction
- **OpenAI Python SDK**: API client for AI services

### Database
- **PostgreSQL 14+**: Relational database with JSON support for embeddings

### Deployment
- **Uvicorn**: ASGI server for FastAPI
- **Single-server architecture**: FastAPI serves both API and built React app

## Database Schema

### Entity Relationship Diagram

```
┌──────────────┐
│    users     │
├──────────────┤
│ id (PK)      │
│ phone_number │◄──┐
│ name         │   │
│ hashed_pwd   │   │
│ is_active    │   │
│ created_at   │   │
└──────────────┘   │
                   │
       ┌───────────┼───────────┐
       │           │           │
       │           │           │
┌──────▼───────┐   │   ┌───────▼──────┐
│  documents   │   │   │    agents    │
├──────────────┤   │   ├──────────────┤
│ id (PK)      │   │   │ id (PK)      │
│ user_id (FK) │───┘   │ user_id (FK) │
│ original_name│       │ name         │
│ file_path    │◄──┐   │ ai_model     │
│ file_size    │   │   │ system_prompt│
│ upload_date  │   │   │ created_at   │
│ is_processed │   │   └───────┬──────┘
└──────┬───────┘   │           │
       │           │    ┌──────▼──────────────┐
       │           │    │  agent_documents    │
       │           └────┤  (junction table)   │
       │                ├─────────────────────┤
       │                │ agent_id (PK, FK)   │
       │                │ document_id (PK, FK)│
       │                └─────────────────────┘
       │
┌──────▼──────┐
│   chunks    │
├─────────────┤
│ id (PK)     │
│ document_id │
│ text        │
│ chunk_index │
└──────┬──────┘
       │
       │
┌──────▼──────┐
│ embeddings  │
├─────────────┤
│ id (PK)     │
│ chunk_id(FK)│
│ vector(JSON)│
└─────────────┘

┌──────────────────┐
│  chat_sessions   │
├──────────────────┤
│ id (PK)          │
│ owner_id (FK)    │
│ document_id (FK) │
│ title            │
│ created_at       │
└────────┬─────────┘
         │
┌────────▼─────────┐
│  chat_messages   │
├──────────────────┤
│ id (PK)          │
│ session_id (FK)  │
│ role             │
│ content          │
│ created_at       │
└──────────────────┘
```

### Key Design Decisions

1. **User Phone Number as Identifier**: Unique constraint on phone numbers for login
2. **Cascade Deletes**: When a user is deleted, all their documents, agents, and sessions are automatically deleted
3. **Many-to-Many Agent-Document**: Agents can access multiple documents, documents can be linked to multiple agents
4. **JSON Storage for Embeddings**: PostgreSQL JSON column stores vector arrays (1536 floats for OpenAI embeddings)
5. **Indexed Foreign Keys**: All foreign keys have indexes for efficient joins
6. **Composite Indexes**: Performance-critical query patterns have composite indexes

## API Design

### RESTful Endpoints

#### Authentication (`/auth`)
- `POST /auth/register` - Create new user account
- `POST /auth/login` - Authenticate and receive JWT token
- `GET /auth/me` - Get current user profile (requires auth)

#### Documents (`/documents`)
- `GET /documents/` - List user's documents
- `POST /documents/upload` - Upload and process PDF
- `GET /documents/{id}` - Get document details with chunk count
- `DELETE /documents/{id}` - Delete document

#### Agents (`/agents`)
- `GET /agents/` - List user's agents
- `POST /agents/` - Create new agent
- `GET /agents/{id}` - Get agent details
- `PUT /agents/{id}` - Update agent (name, system prompt)
- `DELETE /agents/{id}` - Delete agent
- `POST /agents/{id}/documents` - Link documents to agent

#### Chat (`/chat`)
- `POST /chat/` - Send message and get AI response
- `GET /chat/sessions` - List chat sessions
- `POST /chat/sessions` - Create chat session
- `GET /chat/sessions/{id}` - Get session with messages
- `POST /chat/sessions/{id}/messages` - Add message to session
- `DELETE /chat/sessions/{id}` - Delete session

#### Voice (`/voice`)
- `POST /voice/transcribe` - Convert audio to text (STT)
- `POST /voice/speak` - Convert text to audio (TTS)
- `POST /voice/chat-speak` - Combined voice chat with audio response

### API Response Format

**Success Response**:
```json
{
  "status": "success",
  "data": { ... }
}
```

**Error Response**:
```json
{
  "detail": "Error message",
  "status_code": 400
}
```

## Authentication Flow

```
1. User Registration/Login
   ├─► Frontend sends phone + password
   ├─► Backend validates credentials
   ├─► Password hashed with bcrypt (12 rounds)
   ├─► JWT token generated (expires in 30 days)
   └─► Token returned to client

2. Authenticated Requests
   ├─► Frontend stores token in localStorage
   ├─► Axios interceptor adds "Authorization: Bearer <token>" header
   ├─► Backend validates JWT signature
   ├─► User ID extracted from token
   └─► Request processed with user context

3. Token Expiration
   ├─► Backend returns 401 Unauthorized
   ├─► Frontend intercepts 401 response
   ├─► User redirected to login page
   └─► Old token cleared from localStorage
```

### JWT Token Structure
```json
{
  "sub": "phone_number",
  "exp": 1234567890
}
```

## Document Processing Pipeline

```
1. Upload (POST /documents/upload)
   ├─► Validate file type (PDF only)
   ├─► Validate file size (<10MB)
   ├─► Save file to disk with unique filename
   └─► Create Document record (is_processed=False)

2. Text Extraction
   ├─► Open PDF with PyPDF2
   ├─► Extract text from all pages
   ├─► Clean and normalize text
   └─► Handle extraction errors gracefully

3. Chunking
   ├─► Split text into overlapping chunks
   ├─► Chunk size: ~500 tokens
   ├─► Overlap: ~50 tokens for context
   └─► Create Chunk records with indices

4. Embedding Generation (if OPENAI_API_KEY set)
   ├─► Call OpenAI embedding API (model: text-embedding-ada-002)
   ├─► Generate 1536-dimensional vectors
   ├─► Store vectors as JSON in Embedding records
   └─► Mark Document as is_processed=True

5. Error Handling
   ├─► If OpenAI API fails: Log warning, skip embeddings
   ├─► If extraction fails: Return error to user
   └─► Partial failures: Save what succeeded, flag document
```

## Chat & RAG Implementation

### Retrieval-Augmented Generation Flow

```
1. User sends message to agent
   │
2. Retrieve agent's linked documents
   │
3. For each document's chunks:
   ├─► Get chunk embeddings from database
   ├─► Generate query embedding (user message)
   ├─► Calculate cosine similarity
   └─► Rank chunks by similarity

4. Select top K chunks (default: 5)
   │
5. Build prompt with context:
   ├─► System prompt (agent's personality)
   ├─► Retrieved document chunks
   └─► User's question

6. Call OpenAI Chat Completion API
   ├─► Model: gpt-4 or gpt-3.5-turbo
   ├─► Temperature: 0.7
   └─► Max tokens: 1000

7. Return response with sources
   └─► Answer + chunk IDs + similarity scores
```

### Cosine Similarity Calculation

```python
def cosine_similarity(vec1, vec2):
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = sqrt(sum(a * a for a in vec1))
    magnitude2 = sqrt(sum(b * b for b in vec2))
    return dot_product / (magnitude1 * magnitude2)
```

## Voice Features

### Speech-to-Text (Transcription)
- **API**: OpenAI Whisper API
- **Input**: Audio file (WebM format from browser)
- **Output**: Transcribed text + detected language
- **Max size**: 25MB
- **Timeout**: 60 seconds

### Text-to-Speech (Synthesis)
- **API**: OpenAI TTS API
- **Input**: Text string (max 4096 chars)
- **Voice options**: alloy, echo, fable, onyx, nova, shimmer
- **Output**: Audio blob (MP3)
- **Timeout**: 120 seconds

### Voice Chat Flow
1. Record audio in browser
2. Send to `/voice/chat-speak`
3. Backend transcribes audio
4. Process as regular chat message
5. Generate response with TTS
6. Return text + audio to frontend
7. Auto-play audio in conversation mode

## Security Considerations

### Authentication & Authorization
- **Password Requirements**: Min 12 chars, uppercase, lowercase, digit, special char
- **Password Storage**: Bcrypt hashing with salt (12 rounds)
- **JWT Security**: HS256 algorithm, 30-day expiration
- **Authorization**: All endpoints verify user ownership of resources

### Input Validation
- **Pydantic Schemas**: Type validation for all API inputs
- **File Upload**: Type checking (PDF only), size limits (10MB)
- **SQL Injection**: SQLAlchemy ORM prevents injection attacks
- **XSS Protection**: React escapes all rendered content

### Rate Limiting
- **Implementation**: SlowAPI middleware
- **Limits**: 30 requests/minute for chat, 10/minute for uploads
- **Key**: IP address

### CORS Configuration
- **Allowed Origins**: Configurable via environment variable
- **Credentials**: Allowed for authenticated requests
- **Methods**: GET, POST, PUT, DELETE, OPTIONS, PATCH

## Performance Optimizations

### Database Indexes
1. **Composite Index**: `(user_id, is_processed)` on documents
   - **Query**: `SELECT * FROM documents WHERE user_id = ? AND is_processed = true`
   - **Impact**: 80% faster (450ms → 90ms)

2. **Date Index**: `(upload_date)` on documents
   - **Query**: Date range and sorting queries
   - **Impact**: 70% faster

3. **Session Index**: `(owner_id, created_at)` on chat_sessions
   - **Query**: `SELECT * FROM chat_sessions WHERE owner_id = ? ORDER BY created_at DESC`
   - **Impact**: 70% faster with pagination

### Caching Strategies
- **Frontend**: Browser caches static assets (JS, CSS)
- **Embeddings**: Stored in database, not regenerated
- **Agent Context**: Documents linked once, reused across chat sessions

### Async Operations
- FastAPI async endpoints for I/O operations
- Non-blocking OpenAI API calls
- Concurrent document processing (if needed)

### Frontend Optimizations
- **Code Splitting**: Vite automatically splits bundles
- **Lazy Loading**: Route-based code splitting with React.lazy
- **Memoization**: React.memo for expensive components
- **Debouncing**: Search inputs debounced to reduce API calls

---

## Future Scalability Considerations

1. **Horizontal Scaling**: Add load balancer, multiple backend instances
2. **Vector Database**: Migrate embeddings to Pinecone/Weaviate for better performance
3. **Caching Layer**: Redis for frequently accessed data
4. **Queue System**: Celery/RQ for asynchronous document processing
5. **CDN**: Serve static assets from CDN
6. **Database Replication**: Read replicas for analytics queries

---

**Last Updated**: November 2024  
**DocChat Version**: 1.0.0


---

## Customer Support Bot & Voice Architecture

The support bot runs one **support engine** behind two front doors. The React text chat calls it over REST. A **LiveKit voice agent** worker talks to the customer over WebRTC. Both use the same tools and NLP code, and both log every customer turn for the evaluation metrics.

```
 Browser (React)                                 FastAPI backend
 ┌──────────────────────┐   POST /support/chat   ┌───────────────────────────────────────────┐
 │ Support page (text)  │ ─────────────────────► │ app/support/engine.py   handle_turn()     │
 │                      │                        │   1. nlp.analyze()  intent/NER/sentiment  │
 │ "Call support" ──┐   │ POST /voice/livekit-   │   2. escalation rule → support_tickets    │
 │                  │   │ token (JWT auth)       │   3. LLM + tools.py (orders, returns,     │
 │                  │   │ ─────────────────────► │      FAQ search, escalate)                │
 └──────────────────┼───┘  {server_url, token}   │   4. chat_messages + message_analysis     │
                    │                            └───────────────────────────────────────────┘
                    │ WebRTC audio                                  ▲ same tools.py / nlp.py / DB
                    ▼                                               │
          ┌───────────────────┐  dispatch "support-agent"  ┌────────┴──────────────────────────┐
          │  LiveKit Cloud    │ ─────────────────────────► │ voice_agent/agent.py (worker)     │
          │  room support-*   │ ◄───────────────────────── │ OpenAI STT → LLM (+tools) → TTS   │
          └───────────────────┘     agent audio + text     │ Silero VAD, turn logging, latency │
                                                           └───────────────────────────────────┘
```

### Call flow
1. The customer clicks **Call support**. `POST /voice/livekit-token` creates a `chat_sessions` row with `channel="voice"`. It then signs a LiveKit access token for a new room `support-{user_id}-{id}`. The token's room configuration **dispatches the `support-agent` worker**, and its metadata carries `{user_id, session_id}`. The LiveKit API secret never leaves the backend.
2. The browser joins with `livekit-client` / `@livekit/components-react` and publishes the microphone. The worker joins the same room.
3. Each customer turn is processed as follows:
   - Silero VAD and OpenAI speech-to-text (`gpt-4o-mini-transcribe`) produce the transcript.
   - `on_user_turn_completed` runs the NLP analysis and escalation rule and writes to the database. If escalation fires, a note is added to the LLM context.
   - The LLM (`gpt-4o-mini`) calls the support tools, which are scoped to `user_id`.
   - OpenAI text-to-speech (`gpt-4o-mini-tts`) speaks the reply.
4. Transcripts reach the browser as LiveKit text streams (`useTranscriptions`). The worker also measures **response time**, from the end of the customer's speech to the agent starting to speak, and stores it in `message_analysis.response_time_ms`.

### Support data model
| Table | Purpose |
|---|---|
| `products`, `orders`, `order_items` | Catalog and customer orders (seeded by `backend/seed_ecommerce.py`) |
| `return_requests` | Returns created by the bot (30-day window, delivered orders only) |
| `support_tickets` | Escalations, prioritised by sentiment (urgent ≤ −0.8, high ≤ −0.5) |
| `message_analysis` | Per customer turn: intent, confidence, classifier, entities, sentiment, response time, escalated |
| `feedback` | Post-conversation rating (1–5), resolved yes/no, comment |
| `chat_sessions.channel` | `text` / `voice` for support conversations (`NULL` for DocChat document chats) |

### Support endpoints
| Method | Path | Description |
|---|---|---|
| POST | `/support/chat` | Send a message (creates a session if `session_id` is null) |
| GET | `/support/sessions/{id}` | Conversation with per-turn intent/sentiment |
| GET | `/support/orders` | Current customer's orders |
| POST | `/support/feedback` | Satisfaction form |
| GET / PATCH | `/support/tickets[/{id}]` | Human-agent escalation queue |
| GET | `/support/metrics` | Evaluation metrics |
| POST | `/voice/livekit-token` | LiveKit room token + agent dispatch |
