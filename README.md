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
   - `GEMINI_MODEL`: Gemini model identifier (default: `gemini-3.5-flash-lite`).
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

### Testing Notes
The test suite utilizes `httpx.AsyncClient` with `httpx.ASGITransport(app=app)` rather than Starlette's synchronous `TestClient`. In modern Starlette releases, importing `starlette.testclient` without `httpx2` triggers an import-time `StarletteDeprecationWarning`. Testing natively with `httpx.AsyncClient` eliminates this deprecation warning, avoids unnecessary third-party shim dependencies, and accurately exercises FastAPI's asynchronous ASGI interface.

---

## Privacy, Data Protection & Test Fixtures

### Redaction and Privacy Policy
To respect privacy and comply with strict data protection requirements, all fixture files committed to this repository undergo automated sanitization:
- **Private Contact Information Redacted**: All email addresses and phone numbers discovered in search snippets or metadata are strictly replaced with `REDACTED`. WhatsApp contact links containing phone numbers are likewise redacted.
- **No Publishing of Personal Contact Data**: The repository prohibits publishing private contact information (such as personal email addresses or phone numbers) of individuals discovered via public search queries.
- **Retention of Public Profile URLs and Names**: Public profile URLs (e.g. LinkedIn, X/Twitter, YouTube, Threads, Instagram, and canonical Facebook profile paths) and verbatim public names are retained exclusively to validate profile parsing, normalization, relevance classification, and deduplication logic during automated testing.
- **Local Gitignored Raw Recordings**: All raw, unredacted recordings captured during live pipeline validation reside strictly in the local, gitignored `.cache/fixtures/` directory and are never committed or published.

---

## Architecture & Project Structure

The project follows a clean, modular design adhering to strict separation of concerns:

```
ai-prospect-discovery/
├── app/
│   ├── config.py           # Environment config loaded via pydantic-settings
│   ├── main.py             # Route handlers and FastAPI application assembly
│   ├── schemas.py          # Pydantic models for requests, responses, and domain entities
│   ├── schemas_internal.py # Internal candidate classification & pipeline schemas
│   ├── platforms/          # Independent platform adapters implementing a shared base interface
│   ├── services/           # Business logic and external service orchestrators (LLM, discovery)
│   └── utils/              # Common validators, HTTP helpers, and deduplication utilities
├── evaluation/             # Independent offline LLM evaluation framework & datasets
│   ├── datasets/           # Curated ground-truth datasets (intents & candidates)
│   ├── ground_truth/       # Annotation guides & ambiguity classification policies
│   ├── metrics/            # Intent, candidate, and Wilson score statistical metrics
│   ├── providers/          # Model providers (offline mock double and Google Gemini)
│   ├── review/             # Review export, CSV/JSON tabular viewers, and review application
│   ├── runner/             # Offline CLI evaluation runner and configuration
│   └── reports/            # Model comparison report templates and evaluation outputs
├── tests/                  # Pytest unit, integration, and offline evaluation test suite
├── tests/fixtures/         # Sanitized offline fixture recordings for pipeline replay
├── .env.example            # Environment configuration template
├── requirements.txt       # Production dependencies
├── requirements-dev.txt   # Development, testing, and linting dependencies
└── AGENTS.md               # Mandatory architectural and code quality rules
```

### Request Lifecycle
1. **API Layer (`app/main.py`)**: Receives validated JSON requests and delegates directly to the service layer without embedding business logic.
2. **Service Layer (`app/services/`)**: Orchestrates query intent extraction via LLM, schedules concurrent platform queries, and merges candidate entities.
3. **Platform Adapters (`app/platforms/`)**: Self-contained connectors querying official public APIs or search engines with rate-limiting, timeouts, and backoff.
4. **Data Verification & Deduplication (`app/utils/`)**: Sanitizes and validates links and deduplicates prospects based on verified identity signals (e.g., matching handles, domains, and locations).

---

## Supported Platforms

The discovery pipeline integrates with six major public platforms through modular platform adapters implementing `PlatformSource`:

1. **LinkedIn (`app/platforms/linkedin.py`)**:
   - Discovers public `linkedin.com/in/...` profiles.
   - Normalizes vanity and canonical profile URLs.
   - Extracts public professional headlines, names, and titles from public snippets.
2. **X / Twitter (`app/platforms/x.py`)**:
   - Identifies public user profile pages (`x.com/...` and `twitter.com/...`).
   - Distinguishes profile URLs from status tweets and media paths.
   - Extracts public display names, screen handles, and bio descriptions.
3. **YouTube (`app/platforms/youtube.py`)**:
   - Extracts YouTube channel pages, custom handles (`youtube.com/@...`), and canonical channel IDs (`youtube.com/channel/...`).
   - Extracts public channel titles and descriptions.
4. **Instagram (`app/platforms/instagram.py`)**:
   - Discovers public Instagram user profiles (`instagram.com/...`).
   - Filters non-profile paths (explore, reels, p/) and normalizes profile handles.
5. **Threads (`app/platforms/threads.py`)**:
   - Targets public Threads profiles (`threads.net/@...`).
   - Parses public handles and bio snippets.
6. **Facebook (`app/platforms/facebook.py`)**:
   - Canonicalizes public Facebook profiles and pages (`facebook.com/...` and `facebook.com/profile.php?id=...`).
   - Preserves identity-defining numeric ID parameters for verified profile cross-referencing.

---

## LLM Evaluation Suite (Phase 5)

An independent offline evaluation framework is provided in `evaluation/` to benchmark and compare Large Language Models across the two primary AI tasks in the pipeline:
1. **Query Intent Extraction**: Translating natural language queries into structured `QueryIntent` instances (`is_prospect_query`, `interest`, `audience`, `location`, `target_type`).
2. **Candidate Relevance Classification**: Classifying whether search result candidates represent individual human persons matching the requested interest and geography.

### Curated Ground-Truth Datasets
- **Intent Queries (30 total)**:
  - `development.json`: 10 queries (8 prospect queries, 2 non-prospect queries).
  - `test.json`: 20 held-out queries (16 prospect queries, 4 non-prospect queries).
- **Candidate Profiles (80 total across 7 platforms)**:
  - Sourced from 140 raw search results across 4 populated Phase 4 fixtures (`cricket_lovers_ahmedabad`, `digital_marketing_owners_new_york`, `football_lovers_washington_dc`, `startup_founders_london`).
  - `development.json`: 30 candidate profiles.
  - `test.json`: 50 held-out candidate profiles.

### Key Evaluation Features
- **Strict $0 Budget Guard**: Default configuration enforces `budget_cap_usd = 0.0`. Live inference is blocked unless explicitly authorized, protecting against accidental API usage.
- **Ambiguity Policy**: Ambiguous candidates are strictly excluded from primary binary metrics (precision, recall, F1) to prevent metric distortion, and are tracked separately in an uncertainty report.
- **Wilson Score Confidence Intervals**: All accuracy and rate metrics compute 95% Wilson score confidence intervals, with automated small-sample warnings when $N < 30$.
- **Human Review Tools**: Scripts (`evaluation/review/export_review.py` and `apply_review.py`) support tabular CSV and JSON review workflows while strictly preserving original machine suggestions.

### Running Offline Evaluation
To execute an offline evaluation run using deterministic mock doubles:

```bash
python -m evaluation.runner.run_evaluation
```

Detailed framework documentation and annotation guides are available in [evaluation/README.md](file:///c:/Users/subha/Downloads/ai-prospect-discovery/evaluation/README.md) and [model_comparison_template.md](file:///c:/Users/subha/Downloads/ai-prospect-discovery/evaluation/reports/model_comparison_template.md).

---

## Known Limitations

- **Search Engine & LLM Rate Limits**: Downstream search engine (Tavily) and LLM endpoints have rate limits and per-minute quotas. The service implements backoff, retries, and local disk caching to mitigate transient throttling.
- **Search Snippet Text Density**: Candidate relevance classification relies on public search engine snippets. When a search snippet lacks explicit geographic or persona markers, the pipeline relies on conservative heuristics or marks attributes unverified.
- **Zero-Budget Default**: No live LLM calls or Tavily API calls are executed during development and testing unless API credentials are provided and live execution is explicitly enabled. Offline replay fixtures provide complete test coverage without network calls.
- **Search Result Variance**: Search engine results for broad natural language queries may evolve as web crawlers update their indices over time.
