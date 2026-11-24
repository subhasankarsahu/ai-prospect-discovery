# AI Prospect Discovery API

FastAPI-powered backend service for intelligent prospect discovery. The service translates natural language search requests into structured query intents, queries public web and developer platforms, extracts verified candidate profiles, validates candidate relevance using LLM classification, enriches public contact signals, deduplicates identities, and returns verified prospect records with public platform links.

---

## Table of Contents

- [Overview & Purpose](#overview--purpose)
- [Technology Stack](#technology-stack)
- [Architecture & Component Responsibilities](#architecture--component-responsibilities)
- [Supported Platform Adapters & Limitations](#supported-platform-adapters--limitations)
- [Prerequisites & Installation](#prerequisites--installation)
- [Environment Configuration](#environment-configuration)
- [Running the Application](#running-the-application)
- [API Documentation](#api-documentation)
  - [Health Check (`GET /health`)](#health-check-get-health)
  - [Prospect Discovery (`POST /prospect-discovery`)](#prospect-discovery-post-prospect-discovery)
- [Example Requests & Responses](#example-requests--responses)
- [Error Handling & HTTP Status Codes](#error-handling--http-status-codes)
- [Code Quality & Testing](#code-quality--testing)
- [Privacy & Data Protection Policy](#privacy--data-protection-policy)
- [LLM Evaluation Suite (Phase 5)](#llm-evaluation-suite-phase-5)
- [Cloud Deployment (Render)](#cloud-deployment-render)
- [Known Limitations & Responsible Use](#known-limitations--responsible-use)

---

## Overview & Purpose

The **AI Prospect Discovery API** enables automated, privacy-conscious discovery of professional prospects and domain specialists across the public web. Rather than performing manual cross-platform searches or maintaining fragile web-scraping scripts, users provide natural language prompts (e.g., *"Digital marketing agency owners in New York"* or *"Startup founders in London"*).

The service handles the end-to-end discovery lifecycle:
1. **Natural Language Understanding**: Parses unstructured user prompts into structured query intents (`interest`, `audience`, `location`, `target_type`).
2. **Multi-Platform Search Orchestration**: Concurrently queries public search engine indexes across major platforms with rate limiting and retry backoff.
3. **Relevance Classification**: Employs LLM classification to verify that candidate search snippets represent individual human persons matching the requested domain and geography.
4. **Public Contact Signal Extraction**: Validates and normalizes public contact points (international phone numbers in E.164 format and business email addresses).
5. **Deterministic Deduplication**: Merges multi-platform profiles representing the same person using verified identity signals (Rule A: explicit cross-profile links; Rule B: identical name + verified location + matching handle/domain).
6. **Zero Fabrication**: Prohibits synthetic or hallucinated contacts; all returned profiles and URLs trace directly to verified public sources.

---

## Technology Stack

| Layer | Component | Version / Library | Purpose |
| :--- | :--- | :--- | :--- |
| **Runtime** | Python | 3.11+ | Modern async Python execution environment |
| **Framework** | FastAPI | `0.162.5` | High-performance asynchronous web API framework |
| **ASGI Server** | Uvicorn | `0.54.0` | Production ASGI web server implementation |
| **Data Validation** | Pydantic v2 | `2.14.4` | Strict request/response parsing and data schemas |
| **Settings** | Pydantic-Settings | `2.15.0` | Environment configuration loaded via `.env` |
| **HTTP Client** | HTTPX | `0.28.1` | Asynchronous HTTP client with connection pooling and timeouts |
| **HTML Parsing** | BeautifulSoup4 | `4.15.0` | Public snippet sanitization and text cleaning |
| **Phone Validation** | phonenumbers | `9.0.44` | Google libphonenumber Python port for strict E.164 parsing |
| **LLM Provider** | Google Gemini | `gemini-3.5-flash-lite` | Structured intent extraction and candidate relevance classification |
| **Search Engine** | Tavily Search API | REST API | Multi-platform public web search engine with domain scoping |
| **Testing** | Pytest & pytest-asyncio | `9.2.0` / `1.5.0` | Comprehensive unit, integration, and replay test suite |
| **Linter & Formatter** | Ruff | `0.17.6` | Fast static analysis and style enforcement |

---

## Architecture & Component Responsibilities

The codebase follows a modular architecture adhering to strict separation of concerns:

```
ai-prospect-discovery/
├── app/
│   ├── config.py           # Application settings loaded via pydantic-settings
│   ├── main.py             # FastAPI entry point, route definitions, and OpenAPI metadata
│   ├── schemas.py          # Public API schemas (DiscoveryRequest, DiscoveryResponse, Prospect, etc.)
│   ├── schemas_internal.py # Internal candidate classification, platform, and pipeline schemas
│   ├── platforms/          # Independent platform adapters implementing PlatformSource
│   │   ├── base.py         # PlatformSource abstract base interface
│   │   ├── linkedin.py     # LinkedIn profile adapter
│   │   ├── x.py            # X / Twitter profile adapter
│   │   ├── youtube.py      # YouTube channel adapter
│   │   ├── instagram.py    # Instagram profile adapter
│   │   ├── threads.py      # Threads profile adapter
│   │   └── facebook.py     # Facebook profile and page adapter
│   ├── services/           # Core business logic and external service orchestrators
│   │   ├── discovery_service.py     # Main coordinator for multi-platform discovery
│   │   ├── llm_service.py           # Gemini LLM provider for intent and candidate classification
│   │   ├── search_service.py        # Tavily search service with retry budget and caching
│   │   ├── cache_service.py         # Local disk search cache with SHA-256 keys and TTL
│   │   ├── relevance_service.py     # Candidate classification and verification
│   │   ├── profile_extractor.py     # Contact extraction (phones, emails, cross-links)
│   │   ├── deduplication_service.py # Rules A & B identity deduplication engine
│   │   └── prospect_service.py      # Final Prospect model assembly
│   └── utils/              # Shared validators, HTTP helpers, and phone/URL normalizers
│       └── validators.py   # Strict regex, libphonenumber, and URL validators
├── evaluation/             # Phase 5 offline LLM evaluation framework & datasets
│   ├── datasets/           # 30 intent queries and 80 candidate profiles (dev/test splits)
│   ├── ground_truth/       # Human annotation guides and ambiguity policies
│   ├── metrics/            # Intent, candidate, and Wilson score statistical metrics
│   ├── providers/          # Model providers (offline mock double and Google Gemini adapter)
│   ├── review/             # Tabular review tools (CSV/JSON) and human review ingestion
│   ├── runner/             # Offline CLI evaluation orchestrator with $0 budget enforcement
│   └── reports/            # 17-section model comparison report template
├── tests/                  # Pytest test suite (286 automated tests)
├── tests/fixtures/         # Sanitized offline fixture recordings for deterministic replay
├── render.yaml             # Render Blueprint specification for cloud web service deployment
├── .python-version         # Declared Python runtime version (3.11)
├── .env.example            # Environment configuration template
├── requirements.txt       # Production dependencies
├── requirements-dev.txt   # Development and testing dependencies
└── AGENTS.md               # Mandatory architectural and code quality rules
```

### Component Responsibilities
- **API Routing (`app/main.py`)**: Receives validated HTTP JSON requests and delegates directly to `app/services/discovery_service.py`. Contains no business logic.
- **Intent Extraction (`app/services/llm_service.py`)**: Translates queries into structured `QueryIntent` records using Google Gemini with structured JSON output enforcement. Non-prospect queries are detected and resolved early.
- **Platform Search (`app/services/search_service.py`)**: Queries Tavily with domain filtering, concurrency limits (maximum 3 concurrent platform queries), retry budgets, and disk caching.
- **Candidate Classification (`app/services/relevance_service.py`)**: Evaluates candidate snippets with Gemini to verify individual persona status, location support, and domain alignment.
- **Contact Extraction (`app/services/profile_extractor.py`)**: Scans snippets for email addresses and phone numbers. Emails are checked against disposable/placeholder lists; phone numbers are parsed and formatted using `phonenumbers`.
- **Deduplication Engine (`app/services/deduplication_service.py`)**: Merges multiple platform records into unified prospect entities using:
  - **Rule A (Explicit Linkage)**: Profiles linked by explicit cross-platform URLs in their public bio.
  - **Rule B (Signal Matching)**: Same person name + confirmed matching city/country + matching public handle or domain.
  - **Anti-Collapsing Guards**: Conflicting locations, conflicting names, or multiple distinct URLs on the same platform are strictly prevented from merging.

---

## Supported Platform Adapters & Limitations

The discovery pipeline integrates with six major public platforms through modular adapters inheriting from `PlatformSource`:

| Platform | Adapter Module | Target Profile Patterns | Extraction Capabilities | Platform Limitations |
| :--- | :--- | :--- | :--- | :--- |
| **LinkedIn** | `app.platforms.linkedin` | `linkedin.com/in/{username}` | Discovers public profile vanity paths, professional titles, and names. | Login walls restrict full profile text; extraction relies on publicly indexed Google/Tavily snippet text. |
| **X (Twitter)** | `app.platforms.x` | `x.com/{handle}`, `twitter.com/{handle}` | Extracts user handles, display names, and bio descriptions; filters status/tweet URLs. | Character limits on public bios; frequent absence of explicit geographic location in short bios. |
| **YouTube** | `app.platforms.youtube` | `youtube.com/@{handle}`, `youtube.com/channel/{id}` | Discovers custom handles, channel names, and public channel descriptions. | Channel descriptions often describe video programming rather than owner personal credentials; geographic data is rare. |
| **Instagram** | `app.platforms.instagram` | `instagram.com/{handle}` | Extracts public username and profile description; filters `/p/`, `/reel/`, and `/explore/`. | High prevalence of private accounts; public search snippets frequently truncate profile descriptions. |
| **Threads** | `app.platforms.threads` | `threads.net/@{handle}` | Discovers public Threads user handles and short bio snippets. | Newer platform with lower indexation density in web search engines compared to older platforms. |
| **Facebook** | `app.platforms.facebook` | `facebook.com/{page}`, `facebook.com/profile.php?id={id}` | Normalizes vanity and canonical numeric profile paths; preserves numeric IDs for cross-linking. | Strict privacy gates on personal profiles; high mixture of business pages, community groups, and personal accounts. |

> [!NOTE]
> **External Platform Availability & Access Restrictions**: All discovery relies exclusively on public, search-engine-indexed metadata. The API does not bypass login walls, scrape private profiles, or violate platform access restrictions. As a result, changes in search engine crawl frequency, third-party platform robots.txt policies, or regional access constraints may affect candidate yield for specific queries.

---

## Prerequisites & Installation

### Prerequisites
- **Python 3.11** or higher
- **Git**
- Optional: Google Gemini API key and Tavily Search API key (for live online discovery; not required for health check or offline test suites)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/subhasankarsahu/ai-prospect-discovery.git
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

---

## Environment Configuration

Configuration is loaded from environment variables using `pydantic-settings`. Create a `.env` file in the root directory:

```bash
cp .env.example .env
```

### Configuration Variables

| Variable Name | Type | Default Value | Required? | Description |
| :--- | :--- | :--- | :--- | :--- |
| `LLM_PROVIDER` | string | `gemini` | Optional | Active LLM provider identifier (`gemini`). |
| `GEMINI_API_KEY` | string | `""` | **Required for live queries** | Google Gemini API key for intent extraction and candidate verification. Optional for `/health` and offline test replay. |
| `GEMINI_MODEL` | string | `gemini-3.5-flash-lite` | Optional | Model identifier to use with the Gemini provider. |
| `TAVILY_API_KEY` | string | `""` | **Required for live queries** | Tavily Search API key for multi-platform querying. Optional for `/health` and offline test replay. |
| `REQUEST_TIMEOUT_SECONDS` | integer | `30` | Optional | Default outgoing HTTP timeout in seconds for LLM and search calls. |
| `SEARCH_CACHE_ENABLED` | boolean | `true` | Optional | Enable local disk caching for search responses to prevent duplicate calls. |
| `SEARCH_CACHE_DIR` | string | `.cache/search` | Optional | Local filesystem directory path for cached search responses. |
| `PHONE_DEFAULT_REGION` | string | `US` | Optional | Default two-letter ISO country code used for national phone number parsing when no country prefix is supplied. |

---

## Running the Application

### Local Development Server

Start the local server using Uvicorn:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Interactive Documentation & Health Probe
Once running, access the following local endpoints in your browser:
- **Interactive Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check Endpoint:** [http://localhost:8000/health](http://localhost:8000/health)

---

## API Documentation

### Health Check (`GET /health`)
Lightweight liveness and readiness probe for container orchestrators, load balancers, and hosting providers.

- **URL:** `/health`
- **Method:** `GET`
- **Authentication:** None required
- **Success Response (HTTP 200):**
  ```json
  {
    "status": "healthy"
  }
  ```

---

### Prospect Discovery (`POST /prospect-discovery`)
Primary discovery endpoint. Translates natural language queries, queries platforms, verifies candidates, and returns deduplicated prospects.

- **URL:** `/prospect-discovery`
- **Method:** `POST`
- **Content-Type:** `application/json`

#### Request Schema (`DiscoveryRequest`)

| Field | Type | Required? | Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `query` | string | **Yes** | Min length: 1; Non-whitespace | The natural language prospect discovery search query. |

#### Response Schema (`DiscoveryResponse`)

| Field | Type | Description |
| :--- | :--- | :--- |
| `success` | boolean | Indicates whether the overall discovery operation completed successfully. |
| `query` | string | The original search query processed. |
| `total_prospects` | integer | The total count of verified prospects returned in this response. |
| `prospects` | array[`Prospect`] | List of discovered, verified, and deduplicated prospect entities. |

#### Prospect Entity Schema (`Prospect`)

| Field | Type | Description |
| :--- | :--- | :--- |
| `name` | string | Verified personal or organization name of the prospect. |
| `location` | string \| object \| null | Verified location string or structured location object (`city`, `state`, `country`). |
| `social_link` | array[`SocialLink`] | List of verified public profile links across supported platforms. |

#### Social Link Schema (`SocialLink`)

| Field | Type | Description |
| :--- | :--- | :--- |
| `platform` | string | Name of the platform (e.g., `LinkedIn`, `X`, `YouTube`, `Instagram`, `Threads`, `Facebook`). |
| `link` | string | Direct, normalized HTTPS URL to the public profile. |

---

## Example Requests & Responses

### 1. Successful Prospect Discovery

**Request:**
```http
POST /prospect-discovery HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "query": "Startup founders in London"
}
```

**Response (HTTP 200 OK):**
```json
{
  "success": true,
  "query": "Startup founders in London",
  "total_prospects": 2,
  "prospects": [
    {
      "name": "Jane Doe",
      "location": "London, United Kingdom",
      "social_link": [
        {
          "platform": "LinkedIn",
          "link": "https://linkedin.com/in/janedoe"
        },
        {
          "platform": "X",
          "link": "https://x.com/janedoe"
        }
      ]
    },
    {
      "name": "Alex Smith",
      "location": "London, United Kingdom",
      "social_link": [
        {
          "platform": "LinkedIn",
          "link": "https://linkedin.com/in/alexsmith"
        }
      ]
    }
  ]
}
```

---

### 2. Non-Prospect Query Intent

When the LLM determines the query is not seeking people or organizations (e.g., factual queries or general information), the API returns successfully with zero prospects without wasting platform search calls.

**Request:**
```http
POST /prospect-discovery HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "query": "What is the capital of France?"
}
```

**Response (HTTP 200 OK):**
```json
{
  "success": true,
  "query": "What is the capital of France?",
  "total_prospects": 0,
  "prospects": []
}
```

---

### 3. Validation Failure (Empty Query)

When the query is empty or whitespace-only, Pydantic rejects the request with HTTP 422.

**Request:**
```http
POST /prospect-discovery HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "query": "   "
}
```

**Response (HTTP 422 Unprocessable Entity):**
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "query"],
      "msg": "Value error, Query cannot be empty or whitespace only",
      "input": "   "
    }
  ]
}
```

---

## Error Handling & HTTP Status Codes

The API maps internal conditions to standard HTTP status codes:

| HTTP Status | Reason / Exception | Detail / Description |
| :--- | :--- | :--- |
| **`200 OK`** | Success | Query processed successfully. Returned even when zero candidates match. |
| **`422 Unprocessable Entity`** | `ValidationError` | Missing `query` field, empty string, whitespace-only query, or malformed JSON. |
| **`429 Too Many Requests`** | `LLMRateLimitError` or `SearchRateLimitError` | Downstream Gemini API or Tavily Search API rate limit exceeded. |
| **`502 Bad Gateway`** | `LLMResponseParsingError` or `SearchServiceError` | Upstream provider returned invalid JSON, malformed response, or service failure. |
| **`503 Service Unavailable`** | `LLMConfigurationError` or `SearchConfigurationError` | Upstream API key missing or service misconfigured. |
| **`504 Gateway Timeout`** | `LLMTimeoutError` or `SearchTimeoutError` | Upstream Gemini or Tavily request exceeded configured timeout budget. |

---

## Code Quality & Testing

The repository maintains a strict testing regime with **286 automated tests** that run completely offline without external network calls.

```bash
# Run Ruff linting and formatting verification
ruff check .

# Run complete test suite
pytest -v
```

### Test Architecture
- **Offline Determinism**: Network calls are mocked or replayed from sanitized JSON fixtures in `tests/fixtures/`.
- **Async Testing**: Utilizes `httpx.AsyncClient` with `httpx.ASGITransport(app=app)` rather than synchronous test shims, avoiding deprecation warnings and testing the true ASGI pipeline.
- **Privacy Verification**: Automated tests verify that all committed fixtures and evaluation datasets remain 100% free of unredacted personal phone numbers and emails.

---

## Privacy & Data Protection Policy

To protect individual privacy and adhere to data protection standards:
- **Automated Contact Redaction**: All raw search snippets committed to repository test fixtures are sanitized: personal emails and phone numbers are replaced with `REDACTED`.
- **Public Profiles Only**: Only publicly discoverable vanity profile URLs and verbatim public display names are retained to test parsing and deduplication.
- **Local Storage Exclusion**: Unredacted live search recordings remain strictly inside the gitignored `.cache/fixtures/` directory and are never committed or published.

---

## LLM Evaluation Suite (Phase 5)

An independent offline evaluation harness is provided in `evaluation/` to benchmark LLM performance on the two core AI tasks:
1. **Query Intent Extraction**: Translating search queries into structured `QueryIntent` records.
2. **Candidate Relevance Classification**: Determining whether candidate profiles represent individual human persons matching the requested interest and geography.

### Curated Ground-Truth Datasets
- **Intent Queries (30 total)**: 10 development queries (`evaluation/datasets/intents/development.json`) and 20 held-out test queries (`evaluation/datasets/intents/test.json`).
- **Candidate Profiles (80 total across 7 platforms)**: 30 development profiles (`evaluation/datasets/candidates/development.json`) and 50 held-out test profiles (`evaluation/datasets/candidates/test.json`).

### Evaluation Highlights
- **Strict $0 Budget Guard**: Default configuration enforces `budget_cap_usd = 0.0`. Live inference is blocked unless explicitly authorized.
- **Ambiguity Isolation**: Ambiguous profiles are strictly excluded from binary precision/recall/F1 metrics and tracked in an uncertainty report.
- **Statistical Confidence Intervals**: Computes 95% Wilson score confidence intervals with automated small-sample warnings ($N < 30$).
- **CLI Runner**:
  ```bash
  python -m evaluation.runner.run_evaluation
  ```

See [evaluation/README.md](file:///c:/Users/subha/Downloads/ai-prospect-discovery/evaluation/README.md) for full evaluation documentation.

---

## Cloud Deployment (Render)

The application is fully prepared for zero-configuration cloud deployment on **[Render](https://render.com)** as a Python Web Service.

### Deployment Specifications
- **Service Type:** Web Service
- **Environment:** Python 3.11+ (declared in `.python-version` and `render.yaml`)
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Health Check Path:** `/health`
- **Port:** Uses Render's dynamic `$PORT` environment variable (never hardcoded)

---

### Option A: Blueprint Deployment via `render.yaml` (Recommended)

1. Push this repository to your GitHub account.
2. In the **Render Dashboard**, click **New +** and select **Blueprint**.
3. Connect your GitHub repository `ai-prospect-discovery`.
4. Render will detect `render.yaml` and configure the Web Service automatically.
5. In the environment setup prompt, provide your secret API keys:
   - `GEMINI_API_KEY`: Your Google Gemini API key.
   - `TAVILY_API_KEY`: Your Tavily Search API key.
6. Click **Apply**. Render will build and deploy the application.

---

### Option B: Manual Web Service Setup via Render Dashboard

If configuring manually without Blueprints:

1. Click **New +** → **Web Service**.
2. Connect your GitHub repository `ai-prospect-discovery` on branch `main`.
3. Set the following configuration:
   - **Name:** `ai-prospect-discovery`
   - **Language:** `Python 3`
   - **Branch:** `main`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Expand **Advanced** and set **Health Check Path** to `/health`.
5. Under **Environment Variables**, add:
   - `PYTHON_VERSION`: `3.11.10`
   - `LLM_PROVIDER`: `gemini`
   - `GEMINI_MODEL`: `gemini-3.5-flash-lite`
   - `GEMINI_API_KEY`: *[Your secret Google Gemini API key]*
   - `TAVILY_API_KEY`: *[Your secret Tavily Search API key]*
   - `REQUEST_TIMEOUT_SECONDS`: `30`
   - `PHONE_DEFAULT_REGION`: `US`
6. Click **Create Web Service**.

---

### Deployment Verification Checklist
Once deployed on Render, verify your live deployment:
1. **Health Check:** `curl https://<your-render-subdomain>.onrender.com/health` returns `{"status": "healthy"}`.
2. **Interactive Docs:** Visit `https://<your-render-subdomain>.onrender.com/docs` to inspect Swagger UI.
3. **Live Discovery Query:**
   ```bash
   curl -X POST "https://<your-render-subdomain>.onrender.com/prospect-discovery" \
        -H "Content-Type: application/json" \
        -d '{"query": "Digital marketing agency owners in New York"}'
   ```
4. **Validation Test:** Sending `{"query": " "}` returns HTTP 422 with validation details.

---

## Known Limitations & Responsible Use

- **Search Engine Snippet Density**: The pipeline classifies candidate relevance using public search snippets. When a search snippet lacks explicit geographic or role markers, the pipeline conservatively omits unverified fields.
- **Third-Party Platform Policies**: The service respects platform anti-scraping policies and only processes publicly indexed search engine results. It never circumvents login barriers or scrapes private accounts.
- **Zero Fabrication**: When a phone number or email cannot be verified from search metadata, it is omitted. The service never synthesizes synthetic contact details.
- **Rate Limits & API Budgets**: Live production queries depend on upstream Gemini and Tavily rate limits and quotas. For heavy workloads, configure appropriate concurrency limits or enterprise tiers.
- **Responsible Outreach**: Discovered prospects should be contacted strictly in compliance with applicable regional privacy and electronic messaging laws (e.g., CAN-SPAM, GDPR, PECR).
