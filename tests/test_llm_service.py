"""Unit tests for the Gemini LLM service implementation."""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.config import Settings
from app.schemas import QueryIntent
from app.schemas_internal import RawCandidate
from app.services.llm_service import (
    GeminiLLMService,
    LLMConfigurationError,
    LLMRateLimitError,
    LLMResponseParsingError,
    LLMTimeoutError,
)


@pytest.fixture
def mock_settings() -> Settings:
    """Fixture returning settings configured for testing."""
    return Settings(
        llm_provider="gemini",
        gemini_api_key="test-gemini-key",
        gemini_model="gemini-2.5-flash",
        request_timeout_seconds=5,
    )


def build_gemini_candidate_payload(json_str: str) -> dict:
    """Helper to wrap a raw JSON string into Gemini's generateContent response envelope."""
    return {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json_str}],
                    "role": "model",
                },
                "finishReason": "STOP",
            }
        ]
    }


@pytest.mark.asyncio
async def test_extract_query_intent_success(mock_settings: Settings) -> None:
    """Verify successful extraction of QueryIntent from Gemini response."""
    expected_intent_data = {
        "is_prospect_query": True,
        "interest": "AI Engineering",
        "audience": "Founders",
        "location": {"city": "San Francisco", "state": "CA", "country": "USA"},
        "target_type": "individual",
    }
    gemini_body = build_gemini_candidate_payload(json.dumps(expected_intent_data))

    mock_resp = httpx.Response(
        status_code=200,
        json=gemini_body,
        request=httpx.Request("POST", "https://test"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        service = GeminiLLMService(settings=mock_settings)
        intent = await service.extract_query_intent("AI founders in San Francisco")

        assert intent.is_prospect_query is True
        assert intent.interest == "AI Engineering"
        assert intent.audience == "Founders"
        assert intent.location is not None
        assert intent.location.city == "San Francisco"
        assert intent.target_type == "individual"
        assert mock_post.await_count == 1


@pytest.mark.asyncio
async def test_extract_query_intent_non_prospect(mock_settings: Settings) -> None:
    """Verify handling when query is not seeking people or organizations."""
    intent_data = {
        "is_prospect_query": False,
        "interest": "weather forecast",
        "audience": None,
        "location": {"city": "London", "country": "UK"},
        "target_type": "other",
    }
    gemini_body = build_gemini_candidate_payload(json.dumps(intent_data))

    mock_resp = httpx.Response(
        status_code=200,
        json=gemini_body,
        request=httpx.Request("POST", "https://test"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        service = GeminiLLMService(settings=mock_settings)
        intent = await service.extract_query_intent("What is the weather in London?")

        assert intent.is_prospect_query is False
        assert intent.interest == "weather forecast"


@pytest.mark.asyncio
async def test_extract_query_intent_missing_api_key() -> None:
    """Verify LLMConfigurationError is raised when GEMINI_API_KEY is empty."""
    empty_settings = Settings(gemini_api_key="")
    service = GeminiLLMService(settings=empty_settings)

    with pytest.raises(LLMConfigurationError, match="GEMINI_API_KEY is not configured"):
        await service.extract_query_intent("test query")


@pytest.mark.asyncio
async def test_extract_query_intent_malformed_json(mock_settings: Settings) -> None:
    """Verify LLMResponseParsingError is raised when candidate text is not valid JSON."""
    gemini_body = build_gemini_candidate_payload("not-a-valid-json-string {")

    mock_resp = httpx.Response(
        status_code=200,
        json=gemini_body,
        request=httpx.Request("POST", "https://test"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        service = GeminiLLMService(settings=mock_settings)

        with pytest.raises(LLMResponseParsingError, match="Invalid or malformed intent payload"):
            await service.extract_query_intent("test query")


@pytest.mark.asyncio
async def test_extract_query_intent_empty_candidates(mock_settings: Settings) -> None:
    """Verify LLMResponseParsingError is raised when Gemini returns no candidates."""
    mock_resp = httpx.Response(
        status_code=200,
        json={"candidates": []},
        request=httpx.Request("POST", "https://test"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        service = GeminiLLMService(settings=mock_settings)

        with pytest.raises(LLMResponseParsingError, match="no candidates"):
            await service.extract_query_intent("test query")


@pytest.mark.asyncio
async def test_extract_query_intent_timeout(mock_settings: Settings) -> None:
    """Verify LLMTimeoutError is raised when HTTP request times out."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ReadTimeout("Request timed out")
        service = GeminiLLMService(settings=mock_settings)

        with pytest.raises(LLMTimeoutError, match="timed out"):
            await service.extract_query_intent("test query")


@pytest.mark.asyncio
async def test_extract_query_intent_rate_limit_exceeds_cap(mock_settings: Settings) -> None:
    """Verify LLMRateLimitError is raised immediately when Retry-After exceeds 10s."""
    mock_429 = httpx.Response(
        status_code=429,
        headers={"Retry-After": "60"},
        request=httpx.Request("POST", "https://test"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_post.return_value = mock_429
        service = GeminiLLMService(settings=mock_settings)

        with pytest.raises(LLMRateLimitError, match="exceeds maximum allowed wait"):
            await service.extract_query_intent("test query")

        # Must not sleep for 60s
        mock_sleep.assert_not_called()
        assert mock_post.await_count == 1


@pytest.mark.asyncio
async def test_extract_query_intent_rate_limit_exhausted(mock_settings: Settings) -> None:
    """Verify LLMRateLimitError is raised when rate limits persist across retries."""
    mock_429 = httpx.Response(
        status_code=429,
        headers={"Retry-After": "0"},
        request=httpx.Request("POST", "https://test"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.return_value = mock_429
        service = GeminiLLMService(settings=mock_settings)

        with pytest.raises(LLMRateLimitError, match="rate limit exceeded"):
            await service.extract_query_intent("test query")


@pytest.mark.asyncio
async def test_extract_query_intent_rate_limit_retry_success(mock_settings: Settings) -> None:
    """Verify recovery after an initial 429 response when the retry succeeds."""
    intent_data = {
        "is_prospect_query": True,
        "interest": "FinTech founders",
        "target_type": "individual",
    }
    mock_429 = httpx.Response(
        status_code=429,
        headers={"Retry-After": "0"},
        request=httpx.Request("POST", "https://test"),
    )
    mock_200 = httpx.Response(
        status_code=200,
        json=build_gemini_candidate_payload(json.dumps(intent_data)),
        request=httpx.Request("POST", "https://test"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_post.side_effect = [mock_429, mock_200]
        service = GeminiLLMService(settings=mock_settings)

        intent = await service.extract_query_intent("FinTech founders")
        assert intent.is_prospect_query is True
        assert intent.interest == "FinTech founders"
        assert mock_post.await_count == 2


@pytest.mark.asyncio
async def test_classify_candidates_success(mock_settings: Settings) -> None:
    """Verify GeminiLLMService.classify_candidates formats request and parses response."""
    classification_data = [
        {
            "candidate_index": 0,
            "is_individual_person": True,
            "name_as_written": "Alice Smith",
            "interest_supported": True,
            "location_supported": True,
            "confidence": "high",
            "reason": "Alice is an ML researcher.",
        }
    ]
    mock_200 = httpx.Response(
        status_code=200,
        json=build_gemini_candidate_payload(json.dumps(classification_data)),
        request=httpx.Request("POST", "https://test"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_200
        service = GeminiLLMService(settings=mock_settings)

        intent = QueryIntent(interest="Machine Learning", target_type="researcher")
        cand = RawCandidate(
            source_platform="LinkedIn",
            canonical_url="https://linkedin.com/in/alice",
            title="Alice Smith - Researcher",
            snippet="Bio",
            search_query="q",
        )

        results = await service.classify_candidates(intent, [cand])
        assert len(results) == 1
        assert results[0].candidate_index == 0
        assert results[0].name_as_written == "Alice Smith"
        assert results[0].confidence == "high"

        # Verify header sends API key without exposing in URL
        assert mock_post.call_args.kwargs["headers"]["x-goog-api-key"] == "test-gemini-key"
        assert "key=" not in str(mock_post.call_args.args[0])


@pytest.mark.asyncio
async def test_classify_candidates_exceeds_batch_limit_raises_value_error(
    mock_settings: Settings,
) -> None:
    """Verify ValueError is raised if candidate batch size exceeds 20."""
    service = GeminiLLMService(settings=mock_settings)
    intent = QueryIntent(interest="AI", target_type="researcher")
    candidates = [
        RawCandidate(
            source_platform="LinkedIn",
            canonical_url=f"https://linkedin.com/in/{i}",
            title="Title",
            snippet="Snippet",
            search_query="q",
        )
        for i in range(21)
    ]

    with pytest.raises(ValueError, match="exceeds maximum allowed of 20"):
        await service.classify_candidates(intent, candidates)


@pytest.mark.asyncio
async def test_classify_candidates_malformed_json_raises_parsing_error(
    mock_settings: Settings,
) -> None:
    """Verify LLMResponseParsingError is raised on malformed classification JSON."""
    mock_200 = httpx.Response(
        status_code=200,
        json=build_gemini_candidate_payload("NOT VALID JSON"),
        request=httpx.Request("POST", "https://test"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_200
        service = GeminiLLMService(settings=mock_settings)
        intent = QueryIntent(interest="AI", target_type="researcher")
        cand = RawCandidate(
            source_platform="LinkedIn",
            canonical_url="https://linkedin.com/in/1",
            title="Title",
            snippet="Snippet",
            search_query="q",
        )

        with pytest.raises(LLMResponseParsingError, match="malformed"):
            await service.classify_candidates(intent, [cand])
