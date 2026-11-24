"""Unit and integration tests for API routes."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.main import app
from app.schemas import Location, QueryIntent
from app.services.llm_service import (
    LLMConfigurationError,
    LLMRateLimitError,
    LLMResponseParsingError,
    LLMTimeoutError,
)


@pytest.mark.asyncio
async def test_root_redirect() -> None:
    """Verify GET / redirects to /docs with status 307."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/docs"


@pytest.mark.asyncio
async def test_health_route() -> None:
    """Verify GET /health returns 200 with status 'healthy'."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_prospect_discovery_route_success() -> None:
    """Verify POST /prospect-discovery returns 200 with valid discovery intent and discovery search."""
    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="AI Engineering",
        target_type="individual",
    )

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
    ) as mock_extract, patch(
        "app.services.discovery_service.discover_raw_candidates",
        new_callable=AsyncMock,
    ) as mock_raw:
        mock_extract.return_value = mock_intent
        mock_raw.return_value = []

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            payload = {"query": "AI founders in San Francisco"}
            response = await client.post("/prospect-discovery", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["query"] == "AI founders in San Francisco"
            assert data["total_prospects"] == 0
            assert data["prospects"] == []


@pytest.mark.asyncio
async def test_prospect_discovery_route_non_prospect() -> None:
    """Verify POST /prospect-discovery gracefully handles non-prospect queries."""
    mock_intent = QueryIntent(
        is_prospect_query=False,
        interest="Weather updates",
        target_type="other",
    )

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
    ) as mock_extract:
        mock_extract.return_value = mock_intent

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            payload = {"query": "What is the weather today?"}
            response = await client.post("/prospect-discovery", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["query"] == "What is the weather today?"
            assert data["total_prospects"] == 0
            assert data["prospects"] == []


@pytest.mark.asyncio
async def test_prospect_discovery_empty_query() -> None:
    """Verify POST /prospect-discovery rejects empty string query with 422."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/prospect-discovery", json={"query": ""})
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_prospect_discovery_whitespace_query() -> None:
    """Verify POST /prospect-discovery rejects whitespace-only query with 422."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/prospect-discovery", json={"query": "   \n\t  "})
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_prospect_discovery_rate_limit_429() -> None:
    """Verify POST /prospect-discovery returns 429 when LLM rate limit is reached."""
    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
    ) as mock_extract:
        mock_extract.side_effect = LLMRateLimitError("Rate limit exceeded")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/prospect-discovery", json={"query": "FinTech leaders"})
            assert response.status_code == 429
            assert "rate limit exceeded" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_prospect_discovery_timeout_504() -> None:
    """Verify POST /prospect-discovery returns 504 on LLM timeout."""
    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
    ) as mock_extract:
        mock_extract.side_effect = LLMTimeoutError("Call timed out")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/prospect-discovery", json={"query": "FinTech leaders"})
            assert response.status_code == 504
            assert "timed out" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_prospect_discovery_parsing_error_502() -> None:
    """Verify POST /prospect-discovery returns 502 on malformed LLM response."""
    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
    ) as mock_extract:
        mock_extract.side_effect = LLMResponseParsingError("Malformed response")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/prospect-discovery", json={"query": "FinTech leaders"})
            assert response.status_code == 502
            assert "failed to parse" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_prospect_discovery_unconfigured_503() -> None:
    """Verify POST /prospect-discovery returns 503 when API key is missing."""
    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
    ) as mock_extract:
        mock_extract.side_effect = LLMConfigurationError("Missing API key")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/prospect-discovery", json={"query": "FinTech leaders"})
            assert response.status_code == 503
            assert "not properly configured" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_prospect_discovery_route_search_rate_limit_429() -> None:
    """Verify route returns 429 when all search platforms are rate-limited."""
    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="Crypto",
        target_type="individual",
    )
    from fastapi import HTTPException

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
    ) as mock_extract, patch(
        "app.services.discovery_service.discover_raw_candidates",
        new_callable=AsyncMock,
    ) as mock_raw:
        mock_extract.return_value = mock_intent
        mock_raw.side_effect = HTTPException(status_code=429, detail="Search provider rate limit exceeded")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/prospect-discovery", json={"query": "Crypto founders"})
            assert response.status_code == 429
            assert "rate limit exceeded" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_prospect_discovery_route_search_timeout_504() -> None:
    """Verify route returns 504 when search platforms time out."""
    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="Cloud",
        target_type="individual",
    )
    from fastapi import HTTPException

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
    ) as mock_extract, patch(
        "app.services.discovery_service.discover_raw_candidates",
        new_callable=AsyncMock,
    ) as mock_raw:
        mock_extract.return_value = mock_intent
        mock_raw.side_effect = HTTPException(status_code=504, detail="Search provider request timed out")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/prospect-discovery", json={"query": "Cloud engineers"})
            assert response.status_code == 504
            assert "timed out" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_prospect_discovery_route_full_pipeline_success() -> None:
    """Verify full end-to-end route execution resolves verified, deduplicated prospect."""
    from app.schemas_internal import CandidateClassification, RawCandidate

    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="Robotics",
        target_type="individual",
        location=Location(city="Boston", state="MA"),
    )

    raw_candidates = [
        RawCandidate(
            source_platform="LinkedIn",
            canonical_url="https://linkedin.com/in/alice-robotics",
            title="Alice Smith - Robotics Lead",
            snippet="Alice Smith leading robotics in Boston, MA. Email alice@robotics.org.",
            search_query="Robotics lead",
        ),
        RawCandidate(
            source_platform="X",
            canonical_url="https://x.com/alice_robotics",
            title="Alice Smith (@alice_robotics)",
            snippet="Robotics researcher in Boston, MA. Profile: https://linkedin.com/in/alice-robotics.",
            search_query="Robotics lead",
        ),
    ]

    classifications = [
        CandidateClassification(
            candidate_index=0,
            is_individual_person=True,
            name_as_written="Alice Smith",
            interest_supported=True,
            location_supported=True,
            confidence="high",
            reason="Verified profile.",
        ),
        CandidateClassification(
            candidate_index=1,
            is_individual_person=True,
            name_as_written="Alice Smith",
            interest_supported=True,
            location_supported=True,
            confidence="high",
            reason="Verified profile.",
        ),
    ]

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
    ) as mock_extract, patch(
        "app.services.discovery_service.discover_raw_candidates",
        new_callable=AsyncMock,
    ) as mock_raw, patch(
        "app.services.llm_service.GeminiLLMService.classify_candidates",
        new_callable=AsyncMock,
    ) as mock_classify:
        mock_extract.return_value = mock_intent
        mock_raw.return_value = raw_candidates
        mock_classify.return_value = classifications

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/prospect-discovery", json={"query": "Robotics leads in Boston"})
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["total_prospects"] == 1
            prospect = data["prospects"][0]
            assert prospect["name"] == "Alice Smith"
            assert prospect["location"] == "Boston, MA"
            platforms = [sl["platform"] for sl in prospect["social_link"]]
            assert "Email" in platforms
            assert "LinkedIn" in platforms
            assert "X" in platforms


@pytest.mark.asyncio
async def test_prospect_discovery_route_classification_rate_limit_429() -> None:
    """Verify route returns 429 when candidate classification hits LLM rate limit."""
    from app.schemas_internal import RawCandidate

    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="Robotics",
        target_type="individual",
        location=Location(city="Boston", state="MA"),
    )
    raw_cand = RawCandidate(
        source_platform="LinkedIn",
        canonical_url="https://linkedin.com/in/candidate",
        title="Candidate Profile",
        snippet="Candidate in Boston",
        search_query="test",
    )

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
    ) as mock_extract, patch(
        "app.services.discovery_service.discover_raw_candidates",
        new_callable=AsyncMock,
    ) as mock_raw, patch(
        "app.services.llm_service.GeminiLLMService.classify_candidates",
        new_callable=AsyncMock,
    ) as mock_classify:
        mock_extract.return_value = mock_intent
        mock_raw.return_value = [raw_cand]
        mock_classify.side_effect = LLMRateLimitError("Rate limit exceeded")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/prospect-discovery", json={"query": "Robotics"})
            assert response.status_code == 429
            assert "rate limit exceeded" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_prospect_discovery_route_classification_timeout_504() -> None:
    """Verify route returns 504 when candidate classification times out."""
    from app.schemas_internal import RawCandidate

    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="Robotics",
        target_type="individual",
        location=Location(city="Boston", state="MA"),
    )
    raw_cand = RawCandidate(
        source_platform="LinkedIn",
        canonical_url="https://linkedin.com/in/candidate",
        title="Candidate Profile",
        snippet="Candidate in Boston",
        search_query="test",
    )

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
    ) as mock_extract, patch(
        "app.services.discovery_service.discover_raw_candidates",
        new_callable=AsyncMock,
    ) as mock_raw, patch(
        "app.services.llm_service.GeminiLLMService.classify_candidates",
        new_callable=AsyncMock,
    ) as mock_classify:
        mock_extract.return_value = mock_intent
        mock_raw.return_value = [raw_cand]
        mock_classify.side_effect = LLMTimeoutError("Classification timed out")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/prospect-discovery", json={"query": "Robotics"})
            assert response.status_code == 504
            assert "timed out" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_prospect_discovery_route_classification_parsing_502() -> None:
    """Verify route returns 502 when candidate classification returns malformed JSON."""
    from app.schemas_internal import RawCandidate

    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="Robotics",
        target_type="individual",
        location=Location(city="Boston", state="MA"),
    )
    raw_cand = RawCandidate(
        source_platform="LinkedIn",
        canonical_url="https://linkedin.com/in/candidate",
        title="Candidate Profile",
        snippet="Candidate in Boston",
        search_query="test",
    )

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
    ) as mock_extract, patch(
        "app.services.discovery_service.discover_raw_candidates",
        new_callable=AsyncMock,
    ) as mock_raw, patch(
        "app.services.llm_service.GeminiLLMService.classify_candidates",
        new_callable=AsyncMock,
    ) as mock_classify:
        mock_extract.return_value = mock_intent
        mock_raw.return_value = [raw_cand]
        mock_classify.side_effect = LLMResponseParsingError("Malformed classification JSON")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/prospect-discovery", json={"query": "Robotics"})
            assert response.status_code == 502
            assert "failed to parse" in response.json()["detail"].lower()


