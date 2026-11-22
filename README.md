# DocChat - AI-Powered Document Assistant

DocChat is a full-stack web application that allows users to upload PDF documents, process them using AI, and have intelligent conversations about their content. Built as a capstone project, it demonstrates modern web development practices with production-ready architecture.

## What It Does

Upload your PDF documents, and DocChat will extract, chunk, and create semantic embeddings of the content. Then, chat with an AI assistant that can answer questions about your documents using natural language. The system uses retrieval-augmented generation (RAG) to provide accurate, context-aware responses with source citations.

## Key Features

- **Document Management**: Upload PDFs (up to 10MB), automatic text extraction and processing
- **AI Chat Interface**: Conversational interface with context-aware responses and source citations
- **Agent System**: Create AI agents linked to specific document collections
- **Voice Features**: Voice input (speech-to-text) and voice output (text-to-speech)
- **Authentication**: Secure phone/password authentication with JWT tokens
- **Real-time Processing**: Semantic search using OpenAI embeddings for accurate retrieval

## Technology Stack

**Frontend**
- React 19 with TypeScript
- Vite for fast development and optimized builds
- Tailwind CSS for modern, responsive UI
- React Router for navigation
- Axios for API communication

**Backend**
- FastAPI (Python) for high-performance REST API
- SQLAlchemy ORM with PostgreSQL database
- Alembic for database migrations
- OpenAI API for embeddings and chat completion
- JWT authentication with bcrypt password hashing
- Rate limiting and security middleware

**Infrastructure**
- Single-server deployment (FastAPI serves both API and frontend)
- PostgreSQL for data persistence
- RESTful API architecture

## Quick Start

### Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer
- PostgreSQL 14 or newer
- OpenAI API key (optional for development)

### 1. Clone and Setup

```bash
git clone <repository-url>
cd DocChat
```

### 2. Configure Environment

```bash
# Backend environment
cp backend/.env.example backend/.env
# Edit backend/.env and set:
# - DATABASE_URL (PostgreSQL connection string)
# - SECRET_KEY (generate a secure random string)
# - OPENAI_API_KEY (your OpenAI API key)

# Frontend environment
cp frontend/.env.example frontend/.env
# Keep VITE_API_BASE_URL empty for single-server deployment
```

### 3. Install Dependencies

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 4. Run the Application

**Option A: One-command startup** (recommended)
```bash
./start_production.sh
```

**Option B: Manual startup**
```bash
# Build frontend
cd frontend
npm run build

# Run backend (serves both API and frontend)
cd ../backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Option C: Local development** (hot reload, SQLite, no PostgreSQL needed)
```powershell
# backend/.env: DATABASE_URL=sqlite:///./docchat.db
# Terminal 1 - backend API on port 5003
cd backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 5003

# Terminal 2 - frontend on http://localhost:5173
# (frontend/.env.development proxies /api -> http://localhost:5003)
cd frontend
npm run dev
```

### 5. Access the Application

Open your browser to `http://localhost:8000`

**Test Account**
- Phone: `9876543210`
- Password: `Test123456!@`

## Customer Support Bot (Capstone)

On top of DocChat, the project includes an **e-commerce customer support bot** for a demo store called *ShopEase*. It can be used by text chat or by live voice call through **LiveKit**. It answers FAQs, tracks orders, processes returns and cancellations, and escalates to human agents.

| Requirement | Implementation |
|---|---|
| FAQs, order tracking, returns, routing to humans | Tool-calling engine in [backend/app/support/](backend/app/support/) with 7 tools scoped to the logged-in customer. FAQ answers come from the embedded [data/faq.md](backend/data/faq.md). |
| Intent recognition | Structured-output LLM classifier (9 intents), plus a TF-IDF + logistic-regression baseline in [intent_baseline.py](backend/app/support/intent_baseline.py) that is also the offline fallback. |
| Named entity extraction | Regex for order numbers (including spoken forms like "order 10023"), email, phone and amounts, merged with LLM entities (product, reason, date). |
| Product/order database | `products`, `orders`, `order_items`, `return_requests` tables, filled by `seed_ecommerce.py`. |
| Voice / web interaction | React **Support** page (text chat) plus a **LiveKit** voice agent worker ([backend/voice_agent/agent.py](backend/voice_agent/agent.py)) using OpenAI speech-to-text, LLM and text-to-speech. |
| Sentiment analysis and escalation | A sentiment score is computed for every turn. Sentiment ≤ −0.7, asking for a human, or 3 out-of-scope turns opens a prioritised ticket on the **Tickets** page. |
| Evaluation metrics | **Metrics** page: intent accuracy, manual appropriateness scores, response time (text and voice), and satisfaction from the post-chat feedback form. |

### Setup

1. **LiveKit credentials.** In the [LiveKit Cloud](https://cloud.livekit.io) project, open Settings → API Keys, then add these to `backend/.env`. This file is git-ignored; never put the secret in the frontend.
   ```
   LIVEKIT_URL=wss://<your-project>.livekit.cloud
   LIVEKIT_API_KEY=...
   LIVEKIT_API_SECRET=...
   ```
2. **Install and seed.** Run these from `backend/` with the venv active:
   ```bash
   pip install -r voice_agent/requirements.txt      # backend deps + livekit-agents
   alembic upgrade head                              # Postgres; SQLite tables are created automatically
   python seed_ecommerce.py                          # demo customer, products, orders, FAQ
   python -m voice_agent.agent download-files        # one-time: voice activity detection model
   ```
   The demo customer logs in with phone `9876543210` and password `Test123456!@`. To give your own account demo orders, run `python seed_ecommerce.py --phone <your phone>`.
3. **Run the three processes.** On Windows, run `.\start_dev.ps1` from the project folder. It opens one window for each process and then opens the browser. To start them by hand, run each in its own terminal:
   ```powershell
   cd backend;  .\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 5003   # API
   cd backend;  .\venv\Scripts\python.exe -m voice_agent.agent dev                       # LiveKit voice agent
   cd frontend; npm run dev                                                              # http://localhost:5173
   ```
4. Open **Support** in the navbar. Chat, or click **Call support** and allow the microphone.

**Before a demo**, run `python seed_ecommerce.py --reset` to undo cancellations and returns. Add `--clear-logs` to also wipe conversations, tickets and feedback so the metrics start fresh.

### Demo script
- "Where is my order ORD-10023?" returns the shipped status, the carrier and the expected delivery date.
- "I want to return the headphones from ORD-10021, they stopped working" leads the bot to confirm, then create a return.
- "Can I return the shoes from ORD-10022?" is refused because the order is outside the 30-day window.
- "Cancel ORD-10024" cancels the order (it is still in *placed* status). Cancelling ORD-10023 is refused because it has shipped.
- "What's your refund timeline for UPI?" is answered from the FAQ.
- "This is ridiculous, I want a person!" opens an urgent ticket that appears on the **Tickets** page.

### Evaluation
```bash
cd backend
python eval/evaluate_intents.py          # intent accuracy: LLM vs TF-IDF baseline on held-out test set
python eval/export_for_review.py --n 50  # sample real turns for manual appropriateness scoring
```
- **Intent accuracy** uses [eval/intent_dataset.csv](backend/eval/intent_dataset.csv): 216 labelled utterances with 9 intents and an 80/20 train/test split. Results go to `eval/results/intent_eval.json`. The latest run scored **94.4%** for the LLM (`gpt-4o-mini`) and **75.0%** for the TF-IDF baseline, on 36 test utterances.
- **Response appropriateness:** reviewers score `correct`, `helpful` and `polite` from 1 to 5 in `eval/results/appropriateness_review.csv`, then save it as `appropriateness_reviewed.csv`.
- **Average response time** is logged for every turn. For text it is measured from request to reply. For voice it is measured from the end of the customer's speech to the agent starting to speak.
- **User satisfaction** comes from the feedback form shown after every chat and call.

## How to Use

1. **Login**: Use the test account or register a new account (requires strong password)
2. **Upload Documents**: Go to Documents page and upload PDF files
3. **Create an Agent**: Navigate to Agents page, create an agent, and link your documents
4. **Start Chatting**: Select an agent and start asking questions about your documents
5. **View Sources**: See which document chunks were used to generate each response

## Project Structure

```
DocChat/
├── backend/              # FastAPI application
│   ├── app/
│   │   ├── routers/     # API endpoints (auth, documents, chat, agents, voice)
│   │   ├── services/    # Business logic layer
│   │   ├── models.py    # Database models
│   │   ├── schemas.py   # Pydantic schemas for validation
│   │   └── main.py      # Application entry point
│   ├── alembic/         # Database migrations
│   └── tests/           # Unit and integration tests
├── frontend/            # React application
│   ├── src/
│   │   ├── components/  # Reusable UI components
│   │   ├── pages/       # Page components
│   │   ├── services/    # API client
│   │   └── hooks/       # Custom React hooks
│   └── dist/            # Production build output
└── start_production.sh  # Startup script
```

## API Documentation

When the application is running, interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Testing

```bash
# Run backend tests
cd backend
pytest

# Run frontend linting
cd frontend
npm run lint
```

## Additional Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)**: Detailed technical architecture, database schema, and design decisions
- **[DEPLOYMENT.md](DEPLOYMENT.md)**: Production deployment guide for cloud platforms
- **[backend/SECURITY.md](backend/SECURITY.md)**: Security features and best practices
- **[backend/PERFORMANCE_OPTIMIZATIONS.md](backend/PERFORMANCE_OPTIMIZATIONS.md)**: Performance tuning details
- **[backend/TEST_SUITE_README.md](backend/TEST_SUITE_README.md)**: Testing documentation

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused on login | Ensure PostgreSQL is running and `DATABASE_URL` is correct |
| Document upload fails | Check `OPENAI_API_KEY` is set (or leave empty for dev mode) |
| 405 Method Not Allowed in chat | Make sure frontend is rebuilt with `npm run build` |
| Blank page after build | Check browser console and verify backend is serving `/assets` |

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Capstone Project Information

**Project**: Customer Support Bot for an e-commerce platform, built on DocChat  
**Focus**: Full-stack web development with AI integration  
**Technologies**: FastAPI, React, PostgreSQL, OpenAI API, LiveKit Agents, scikit-learn  
**Key Features**: Intent recognition, entity extraction, sentiment-based escalation, order/return tools, LiveKit voice agent, evaluation dashboard

---

**DocChat** - Making documents conversational with AI
