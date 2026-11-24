# Project Rules: AI Prospect Discovery API

## Stack
- Python 3.11+, FastAPI, Uvicorn, Pydantic v2, HTTPX (async), BeautifulSoup4
- LLM: one provider behind an interface in services/llm_service.py
- Tests: pytest. Lint/format: ruff.

## Code Quality (mandatory)
- Type hints on all functions. Pydantic models for every request, response, and internal data object.
- Each platform is an independent module in app/platforms/ implementing the same base interface.
- No business logic in main.py. Routes call services; services call platforms.
- No bare `except:`. Catch specific exceptions and log them with context.
- Every external call has a timeout and retry/backoff. Respect rate-limit (429) responses.
- Config only through environment variables (pydantic-settings). Never hardcode keys.
- Small functions with single responsibility. Docstrings on public classes and functions.
- Run `ruff check` and `pytest` before every commit. Do not commit failing code.

## Data Integrity (mandatory)
- Never fabricate names, URLs, emails, or phone numbers. If a field is not verified from a source, leave it out.
- Only use official APIs or public search results. Never bypass authentication or scrape private/login-only content.
- Validate emails and phone numbers with explicit validators before including them.
- Deduplicate by verified identity signals (same name + location + matching handle or domain). Never merge two people just because their names are similar.
- Keep the source URL for every link internally, for verification.

## Git Workflow (mandatory)
- Make small, focused commits. One logical change per commit.
- Use Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- Commit after each completed step, not in one large batch at the end.
- Never commit `.env`, API keys, or `.venv/`. Keep `.gitignore` up to date.

## Working Method
- Before starting a task, check for and follow any relevant skills or instructions available in this project and environment.
- Plan the change in a short list, then implement it, then run lint and tests.
- If something is unclear, ask before writing a large amount of code.
- Explain any non-obvious decision in a short comment or in the README.