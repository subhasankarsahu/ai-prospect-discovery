"""End-to-end replay tests and edge-case test suite.

Replays the 5 sanitized fixture sets through the actual application pipeline,
mocking ONLY the external HTTP boundaries (Tavily search API and Gemini LLM API).
Exercises all internal components:
- Query intent parsing
- Platform query building
- Search result parsing and normalization
- Profile validation
- Candidate relevance classification
- Contact extraction
- Deduplication (Rules A & B)
- Response assembly
- FastAPI routing and Pydantic validation
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.main import app
from app.schemas import DiscoveryResponse, Location, QueryIntent
from app.schemas_internal import (
    CandidateClassification,
    RawCandidate,
    TavilySearchResult,
)
from app.services.llm_service import (
    LLMConfigurationError,
    LLMRateLimitError,
    LLMResponseParsingError,
    LLMServiceError,
    LLMTimeoutError,
)
from app.services.search_service import SearchRateLimitError, SearchServiceError
from app.utils.validators import validate_profile_url

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

ASSESSMENT_SLUGS = [
    "football_lovers_washington_dc",
    "digital_marketing_owners_new_york",
    "startup_founders_london",
    "cricket_lovers_ahmedabad",
    "restaurant_owners_dubai",
]

PERMITTED_PLATFORMS = {
    "LinkedIn",
    "X",
    "YouTube",
    "Instagram",
    "Threads",
    "Facebook",
    "Email",
    "WhatsApp",
}


def load_fixture(slug: str) -> dict[str, Any]:
    """Load sanitized JSON fixture from tests/fixtures/."""
    fixture_path = FIXTURES_DIR / f"{slug}.json"
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture file missing: {fixture_path}")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


class ReplayLLMService:
    """Mock LLM Service supplying exact recorded intents and classifications."""

    def __init__(self, fixture: dict[str, Any]) -> None:
        self.fixture = fixture
        self.classification_batches = fixture.get("classification_calls", [])
        self.batch_index = 0

    async def extract_query_intent(self, query: str) -> QueryIntent:
        intent_data = self.fixture.get("intent")
        if not intent_data:
            # Fallback if query intent was non-prospect or empty
            return QueryIntent(
                is_prospect_query=False,
                interest=query,
                target_type="individual",
            )
        return QueryIntent.model_validate(intent_data)

    async def classify_candidates(
        self, intent: QueryIntent, candidates: list[RawCandidate]
    ) -> list[CandidateClassification]:
        if self.batch_index < len(self.classification_batches):
            batch = self.classification_batches[self.batch_index]
            self.batch_index += 1
            raw_classifications = batch.get("classifications", [])
            return [
                CandidateClassification.model_validate(c)
                for c in raw_classifications
            ]
        # Return fallback classifications if more batches than recorded
        return []


def create_search_replay_side_effect(fixture: dict[str, Any]):
    """Create a search function that matches search calls from the fixture."""
    recorded_calls = fixture.get("search_calls", [])

    async def replay_search(query: str, include_domains: list[str] | None = None) -> list[TavilySearchResult]:
        # Attempt exact or domain-based match
        target_domains = set(include_domains) if include_domains else set()
        for call in recorded_calls:
            call_domains = set(call.get("include_domains") or [])
            if target_domains == call_domains:
                return [TavilySearchResult(**r) for r in call.get("results", [])]
            if call.get("query") == query:
                return [TavilySearchResult(**r) for r in call.get("results", [])]
        # If no match or empty search
        return []

    return replay_search


# =====================================================================
# PART A: FIVE ASSESSMENT REPLAY TESTS
# =====================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", ASSESSMENT_SLUGS)
async def test_assessment_query_offline_replay(slug: str) -> None:
    """Replay each of the 5 assessment queries offline and verify all 9 required criteria."""
    fixture = load_fixture(slug)
    query_text = fixture["query"]
    replay_llm = ReplayLLMService(fixture)
    replay_search = create_search_replay_side_effect(fixture)

    with patch(
        "app.services.discovery_service.get_llm_service",
        return_value=replay_llm,
    ), patch(
        "app.services.search_service.TavilySearchService.search",
        side_effect=replay_search,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/prospect-discovery",
                json={"query": query_text},
            )

            # 1. HTTP response is successful (200 OK)
            assert response.status_code == 200, f"Expected 200 for {slug}, got {response.status_code}: {response.text}"
            data = response.json()

            # 2. success is true
            assert data.get("success") is True, f"Expected success=True for {slug}"

            # 3. total_prospects == len(prospects)
            prospects = data.get("prospects", [])
            assert data.get("total_prospects") == len(prospects), f"Mismatch in total_prospects for {slug}"

            # Validate each returned prospect
            for prospect in prospects:
                # 4. Every returned prospect has a non-empty social_link array
                links = prospect.get("social_link", [])
                assert len(links) > 0, f"Prospect {prospect.get('name')} in {slug} has empty social_link array"

                for link_obj in links:
                    platform = link_obj.get("platform")
                    url = link_obj.get("link")

                    # 5. Every social link uses a permitted platform
                    assert platform in PERMITTED_PLATFORMS, f"Invalid platform {platform} in {slug}"

                    # 6 & 7. Every social link passes validate_profile_url or valid mailto/wa.me
                    if platform == "Email":
                        assert url.startswith("mailto:"), f"Email link must start with mailto: {url}"
                    elif platform == "WhatsApp":
                        assert "wa.me/" in url or "whatsapp.com" in url, f"Invalid WhatsApp link: {url}"
                    else:
                        validated = validate_profile_url(url)
                        assert validated is not None, f"Malformed/invalid profile URL survived in {slug}: {url}"

                # 8. No internal processing metadata leaks into public response
                allowed_keys = {"name", "location", "social_link"}
                leaked_keys = set(prospect.keys()) - allowed_keys
                assert not leaked_keys, f"Internal metadata leaked into prospect in {slug}: {leaked_keys}"

            # 9. Serialized response conforms to public DiscoveryResponse schema
            validated_response = DiscoveryResponse.model_validate(data)
            assert validated_response.query == query_text


# =====================================================================
# PART B: REQUIRED EDGE-CASE TESTS
# =====================================================================


@pytest.mark.asyncio
async def test_edge_case_input_validation() -> None:
    """Edge Case 1: Empty query, whitespace query, and invalid JSON return 422."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Empty query
        res1 = await client.post("/prospect-discovery", json={"query": ""})
        assert res1.status_code == 422

        # Whitespace-only query
        res2 = await client.post("/prospect-discovery", json={"query": "   \n\t  "})
        assert res2.status_code == 422

        # Invalid JSON request body
        res3 = await client.post(
            "/prospect-discovery",
            content=b"not-json-content",
            headers={"Content-Type": "application/json"},
        )
        assert res3.status_code == 422


@pytest.mark.asyncio
async def test_edge_case_gemini_failures() -> None:
    """Edge Case 2: Gemini failures map to correct HTTP statuses (502, 503, 504, 429)."""
    failure_cases = [
        (LLMTimeoutError("Gemini timed out"), 504),
        (LLMRateLimitError("Rate limit exceeded"), 429),
        (LLMConfigurationError("Missing key"), 503),
        (LLMResponseParsingError("Invalid JSON"), 502),
        (LLMServiceError("Server error 500"), 502),
    ]

    for exception_instance, expected_status in failure_cases:
        with patch(
            "app.services.llm_service.GeminiLLMService.extract_query_intent",
            side_effect=exception_instance,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                res = await client.post(
                    "/prospect-discovery",
                    json={"query": "Founders in Seattle"},
                )
                assert res.status_code == expected_status, (
                    f"Expected {expected_status} for {type(exception_instance).__name__}, got {res.status_code}"
                )


@pytest.mark.asyncio
async def test_edge_case_complete_tavily_failure() -> None:
    """Edge Case 3: Complete Tavily search yielding zero results follows the successful empty-result contract."""
    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="Healthcare",
        target_type="individual",
    )

    # 1. Tavily search returns empty results for every platform
    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
        return_value=mock_intent,
    ), patch(
        "app.services.search_service.TavilySearchService.search",
        return_value=[],
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/prospect-discovery",
                json={"query": "Doctors in Boston"},
            )
            # API must not return HTTP 500; must follow successful empty-result contract
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            assert data["total_prospects"] == 0
            assert data["prospects"] == []

    # 2. When all platforms experience upstream service errors, verify API returns 502 (never 500)
    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
        return_value=mock_intent,
    ), patch(
        "app.services.search_service.TavilySearchService.search",
        side_effect=SearchServiceError("Tavily service completely unreachable"),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/prospect-discovery",
                json={"query": "Doctors in Boston"},
            )
            assert res.status_code == 502
            assert res.status_code != 500


@pytest.mark.asyncio
async def test_edge_case_partial_platform_failure() -> None:
    """Edge Case 4: Partial platform failure allows surviving platforms to contribute prospects."""
    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="Software",
        location=Location(city="Austin", country="USA"),
        target_type="individual",
    )

    # LinkedIn fails, but X succeeds
    async def partial_search(query: str, include_domains: list[str] | None = None) -> list[TavilySearchResult]:
        if include_domains and "linkedin.com" in include_domains:
            raise SearchServiceError("LinkedIn search temporarily rate limited")
        if include_domains and ("x.com" in include_domains or "twitter.com" in include_domains):
            return [
                TavilySearchResult(
                    url="https://x.com/austin_dev",
                    title="Austin Dev (@austin_dev)",
                    snippet="Senior software engineer living in Austin, USA.",
                )
            ]
        return []

    mock_classification = [
        CandidateClassification(
            candidate_index=0,
            is_individual_person=True,
            name_as_written="Austin Dev",
            interest_supported=True,
            location_supported=True,
            confidence="high",
            reason="Individual software engineer in Austin.",
        )
    ]

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
        return_value=mock_intent,
    ), patch(
        "app.services.llm_service.GeminiLLMService.classify_candidates",
        new_callable=AsyncMock,
        return_value=mock_classification,
    ), patch(
        "app.services.search_service.TavilySearchService.search",
        side_effect=partial_search,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/prospect-discovery",
                json={"query": "Software engineers in Austin USA"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            assert data["total_prospects"] == 1
            assert data["prospects"][0]["name"] == "Austin Dev"
            assert data["prospects"][0]["social_link"][0]["platform"] == "X"


@pytest.mark.asyncio
async def test_edge_case_duplicate_profiles_across_platforms() -> None:
    """Edge Case 5: Duplicate candidates across platforms deduplicate using Phase 3 rules."""
    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="AI",
        location=Location(city="Seattle", country="USA"),
        target_type="individual",
    )

    # Return same person on LinkedIn and X with explicit handle matching
    async def multi_platform_search(query: str, include_domains: list[str] | None = None) -> list[TavilySearchResult]:
        if include_domains and "linkedin.com" in include_domains:
            return [
                TavilySearchResult(
                    url="https://linkedin.com/in/sarah-ai-expert",
                    title="Sarah Connor - AI Researcher - LinkedIn",
                    snippet="AI Researcher in Seattle, USA. Also on X: https://x.com/sarah_ai",
                )
            ]
        if include_domains and ("x.com" in include_domains or "twitter.com" in include_domains):
            return [
                TavilySearchResult(
                    url="https://x.com/sarah_ai",
                    title="Sarah Connor (@sarah_ai) on X",
                    snippet="Building AI models in Seattle, USA.",
                )
            ]
        return []

    mock_classifications = [
        CandidateClassification(
            candidate_index=0,
            is_individual_person=True,
            name_as_written="Sarah Connor",
            interest_supported=True,
            location_supported=True,
            confidence="high",
            reason="AI Researcher in Seattle.",
        ),
        CandidateClassification(
            candidate_index=1,
            is_individual_person=True,
            name_as_written="Sarah Connor",
            interest_supported=True,
            location_supported=True,
            confidence="high",
            reason="AI researcher on X in Seattle.",
        ),
    ]

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
        return_value=mock_intent,
    ), patch(
        "app.services.llm_service.GeminiLLMService.classify_candidates",
        new_callable=AsyncMock,
        return_value=mock_classifications,
    ), patch(
        "app.services.search_service.TavilySearchService.search",
        side_effect=multi_platform_search,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/prospect-discovery",
                json={"query": "AI researchers in Seattle"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["success"] is True
            # Deduplication should merge them into exactly 1 distinct prospect with both links
            assert data["total_prospects"] == 1
            prospect = data["prospects"][0]
            assert prospect["name"] == "Sarah Connor"
            platforms = {link["platform"] for link in prospect["social_link"]}
            assert "LinkedIn" in platforms
            assert "X" in platforms


@pytest.mark.asyncio
async def test_edge_case_invalid_search_result_urls() -> None:
    """Edge Case 6: Malformed, internal, or non-profile URLs are filtered out."""
    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="Fintech",
        target_type="individual",
    )

    async def bad_url_search(query: str, include_domains: list[str] | None = None) -> list[TavilySearchResult]:
        return [
            TavilySearchResult(
                url="http://attacker.com/malicious",
                title="Bad URL 1",
                snippet="Not allowed",
            ),
            TavilySearchResult(
                url="https://127.0.0.1:8000/in/test",
                title="Bad URL 2",
                snippet="Internal IP",
            ),
            TavilySearchResult(
                url="https://linkedin.com/jobs/view/12345",
                title="Job Posting",
                snippet="Job posting not profile",
            ),
        ]

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
        return_value=mock_intent,
    ), patch(
        "app.services.search_service.TavilySearchService.search",
        side_effect=bad_url_search,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/prospect-discovery",
                json={"query": "Fintech executives"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["total_prospects"] == 0
            assert data["prospects"] == []


@pytest.mark.asyncio
async def test_edge_case_missing_contact_information() -> None:
    """Edge Case 7: Candidates with missing emails/phones return without fabricated contacts."""
    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="Robotics",
        location=Location(city="Denver", country="USA"),
        target_type="individual",
    )

    async def search_no_contact(query: str, include_domains: list[str] | None = None) -> list[TavilySearchResult]:
        if include_domains and "linkedin.com" in include_domains:
            return [
                TavilySearchResult(
                    url="https://linkedin.com/in/alex-robotics",
                    title="Alex Rivera - Robotics Engineer - LinkedIn",
                    snippet="Lead robotics architect in Denver, Colorado. No direct phone or email published.",
                )
            ]
        return []

    mock_classification = [
        CandidateClassification(
            candidate_index=0,
            is_individual_person=True,
            name_as_written="Alex Rivera",
            interest_supported=True,
            location_supported=True,
            confidence="high",
            reason="Individual robotics engineer in Denver.",
        )
    ]

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
        return_value=mock_intent,
    ), patch(
        "app.services.llm_service.GeminiLLMService.classify_candidates",
        new_callable=AsyncMock,
        return_value=mock_classification,
    ), patch(
        "app.services.search_service.TavilySearchService.search",
        side_effect=search_no_contact,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/prospect-discovery",
                json={"query": "Robotics engineers in Denver"},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["total_prospects"] == 1
            prospect = data["prospects"][0]
            assert prospect["name"] == "Alex Rivera"

            # Verify no invented contact platforms
            contact_platforms = [link["platform"] for link in prospect["social_link"] if link["platform"] in ("Email", "WhatsApp")]
            assert len(contact_platforms) == 0, f"Fabricated contact platform found: {contact_platforms}"


@pytest.mark.asyncio
async def test_edge_case_rate_limiting() -> None:
    """Edge Case 8: Upstream rate limit (429) triggers proper error mapping."""
    # Test upstream Tavily 429
    mock_intent = QueryIntent(
        is_prospect_query=True,
        interest="Biotech",
        target_type="individual",
    )

    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        new_callable=AsyncMock,
        return_value=mock_intent,
    ), patch(
        "app.services.search_service.TavilySearchService.search",
        side_effect=SearchRateLimitError("Tavily rate limit exceeded (429)"),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/prospect-discovery",
                json={"query": "Biotech researchers in Boston"},
            )
            # TavilySearchService 429 strictly dominates, returning mapped HTTP 429
            assert res.status_code == 429
            assert "rate limit" in res.json().get("detail", "").lower()

    # Test upstream Gemini 429
    with patch(
        "app.services.llm_service.GeminiLLMService.extract_query_intent",
        side_effect=LLMRateLimitError("Gemini rate limit 429"),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post(
                "/prospect-discovery",
                json={"query": "Biotech researchers in Boston"},
            )
            # LLM 429 maps to HTTP 429
            assert res.status_code == 429
            assert "rate limit" in res.json().get("detail", "").lower()
