# AI Prospect Discovery API

FastAPI-powered backend service for intelligent prospect discovery. The service translates natural language search requests into structured query intents, queries public web and developer platforms, extracts verified candidate profiles, and returns deduplicated prospect entities with verified social/platform links.

---

## Getting Started

### Prerequisites
- Python 3.11 or higher
- Git

### Installation & Environment Setup

1. **Clone the repository and navigate to the project root:**
   ```bash
   git clone <repo-url>
   cd ai-prospect-discovery
   ```

2. **Create and activate a virtual environment:**
   - **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - **Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Update `.env` with your API keys:
   - `LLM_PROVIDER`: Selected LLM provider (default: `gemini`).
   - `GEMINI_API_KEY`: Google Gemini API key.
   - `GEMINI_MODEL`: Gemini model identifier (default: `gemini-2.5-flash`).
   - `TAVILY_API_KEY`: Tavily search engine API key.
   - `REQUEST_TIMEOUT_SECONDS`: Outgoing HTTP timeout in seconds (default: `30`).

---

## Running the Application

Start the local development server with Uvicorn:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- **Interactive API Documentation (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative Docs (ReDoc):** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check Endpoint:** [http://localhost:8000/health](http://localhost:8000/health)

---

## Code Quality & Testing

In accordance with project rules, run linting and tests prior to making any commits:

```bash
# Check code formatting and linting
ruff check .

# Run test suite
pytest -v
```

---

## Architecture

The project follows a clean, modular design adhering to strict separation of concerns:

```
ai-prospect-discovery/
â”œâ”€â”€ app/
â”‚   â”œâ”€â”€ config.py           # Environment config loaded via pydantic-settings
â”‚   â”œâ”€â”€ main.py             # Route handlers and FastAPI application assembly
â”‚   â”œâ”€â”€ schemas.py          # Pydantic models for requests, responses, and domain entities
â”‚   â”œâ”€â”€ platforms/          # Independent platform adapters implementing a shared base interface
â”‚   â”œâ”€â”€ services/           # Business logic and external service orchestrators (LLM, discovery)
â”‚   â””â”€â”€ utils/              # Common validators, HTTP helpers, and deduplication utilities
â”œâ”€â”€ tests/                  # Pytest unit and integration test suite
â”œâ”€â”€ .env.example            # Environment configuration template
â”œâ”€â”€ requirements.txt       # Production dependencies
â”œâ”€â”€ requirements-dev.txt   # Development, testing, and linting dependencies
â””â”€â”€ AGENTS.md               # Mandatory architectural and code quality rules
```

### Request Lifecycle
1. **API Layer (`app/main.py`)**: Receives validated JSON requests and delegates directly to the service layer without embedding business logic.
2. **Service Layer (`app/services/`)**: Orchestrates query intent extraction via LLM, schedules concurrent platform queries, and merges candidate entities.
3. **Platform Adapters (`app/platforms/`)**: Self-contained connectors querying official public APIs or search engines with rate-limiting, timeouts, and backoff.
4. **Data Verification & Deduplication (`app/utils/`)**: Sanitizes and validates links and deduplicates prospects based on verified identity signals (e.g., matching handles, domains, and locations).

---

## Supported Platforms

*(Placeholder)*

Upcoming platform integrations will be documented here:
- **Platform A:** Interface definition and search capabilities.
- **Platform B:** Public profile extraction and link validation.
- **Platform C:** Entity enrichment and cross-referencing.

---

## LLM Comparison

*(Placeholder)*

Benchmarking and comparison across supported LLM providers will be detailed here:
- Provider accuracy on intent classification and entity extraction.
- Output token constraints and structured JSON adherence.
- Response latencies, cost per 1k discovery operations, and rate-limit considerations.
