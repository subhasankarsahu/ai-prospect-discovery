"""LLM service interface and Gemini API implementation for query understanding."""

import asyncio
import json
import logging
from collections.abc import Sequence
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.schemas import QueryIntent
from app.schemas_internal import CandidateClassification, RawCandidate

logger = logging.getLogger(__name__)

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

GEMINI_QUERY_INTENT_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "is_prospect_query": {
            "type": "BOOLEAN",
            "description": "Whether the user query is looking to find people or organizations",
        },
        "interest": {
            "type": "STRING",
            "description": "Primary industry, skill, domain, or role of interest",
        },
        "audience": {
            "type": "STRING",
            "description": "Target audience segment or persona if specified",
        },
        "location": {
            "type": "OBJECT",
            "description": "Geographic constraints if present in the query",
            "properties": {
                "city": {"type": "STRING"},
                "state": {"type": "STRING"},
                "country": {"type": "STRING"},
            },
        },
        "target_type": {
            "type": "STRING",
            "description": "Type of target entity, e.g., individual, company, founder, creator",
        },
    },
    "required": ["is_prospect_query", "interest", "target_type"],
}

SYSTEM_INSTRUCTION = (
    "You are an intent extraction engine for a prospect discovery API. "
    "Convert natural-language search queries into structured JSON. "
    "Determine whether the query seeks people or organizations. "
    "Return JSON only conforming to the schema. "
    "Set is_prospect_query to false if the query is unrelated to discovering people or organizations."
)

GEMINI_CLASSIFICATION_SCHEMA: dict[str, Any] = {
    "type": "ARRAY",
    "description": "List of candidate relevance classifications",
    "items": {
        "type": "OBJECT",
        "properties": {
            "candidate_index": {
                "type": "INTEGER",
                "description": "Zero-based index of candidate within the batch",
            },
            "is_individual_person": {
                "type": "BOOLEAN",
                "description": "Whether the search result represents an individual human",
            },
            "name_as_written": {
                "type": "STRING",
                "description": "Person name as written verbatim in the candidate text",
            },
            "interest_supported": {
                "type": "BOOLEAN",
                "description": "Whether the candidate supports the requested interest",
            },
            "location_supported": {
                "type": "BOOLEAN",
                "description": "Whether candidate supports the requested location",
            },
            "confidence": {
                "type": "STRING",
                "enum": ["low", "medium", "high"],
                "description": "Confidence level in classification",
            },
            "reason": {
                "type": "STRING",
                "description": "One sentence explaining the classification",
            },
        },
        "required": [
            "candidate_index",
            "is_individual_person",
            "name_as_written",
            "interest_supported",
            "location_supported",
            "confidence",
            "reason",
        ],
    },
}

CLASSIFICATION_SYSTEM_INSTRUCTION = (
    "You are a relevance classification engine for a prospect discovery API. "
    "Determine whether each candidate search result represents an individual person "
    "relevant to the user's requested interest and domain.\n\n"
    "STRICT PROHIBITIONS:\n"
    "- Do NOT invent names. The name_as_written must appear verbatim in the candidate title or snippet.\n"
    "- Do NOT invent locations.\n"
    "- Do NOT infer an interest without direct evidence in the snippet or title.\n"
    "- Do NOT treat a company, organization, product, brand, or generic landing page as an individual.\n"
    "- Do NOT return URLs or replace candidate URLs.\n"
    "- Do NOT claim contact details that are not present in the supplied text.\n\n"
    "Return JSON only conforming strictly to the response schema."
)


class LLMServiceError(Exception):
    """Base exception for all LLM service failures."""


class LLMConfigurationError(LLMServiceError):
    """Raised when required LLM configuration is missing."""


class LLMTimeoutError(LLMServiceError):
    """Raised when an LLM provider request times out."""


class LLMRateLimitError(LLMServiceError):
    """Raised when an LLM provider rate limit (429) is encountered."""


class LLMResponseParsingError(LLMServiceError):
    """Raised when the LLM response is not valid JSON or fails schema validation."""


class BaseLLMService(Protocol):
    """Protocol interface defining operations required of an LLM provider."""

    async def extract_query_intent(self, query: str) -> QueryIntent:
        """Extract structured query intent from a natural language search query.

        Args:
            query: The user's search query string.

        Returns:
            Validated QueryIntent object.

        Raises:
            LLMServiceError: If intent extraction or network communication fails.
        """
        ...

    async def classify_candidates(
        self, intent: QueryIntent, candidates: list[RawCandidate]
    ) -> list[CandidateClassification]:
        """Classify candidate relevance against query intent.

        Args:
            intent: The validated search query intent.
            candidates: Batch of at most 20 raw candidate profiles.

        Returns:
            List of CandidateClassification objects from the LLM.

        Raises:
            LLMServiceError: If candidate classification fails.
        """
        ...


class GeminiLLMService:
    """Gemini API implementation of the LLM service interface."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the Gemini LLM service.

        Args:
            settings: Application settings containing credentials and configuration.
            client: Optional reusable HTTPX AsyncClient for connection pooling and testing.
        """
        self.settings = settings or get_settings()
        self._external_client = client

    def _build_payload(self, query: str) -> dict[str, Any]:
        """Construct the Gemini generateContent JSON request body.

        Args:
            query: User's search query.

        Returns:
            Dictionary matching the Gemini API generateContent schema.
        """
        return {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_INSTRUCTION}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": query}],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": GEMINI_QUERY_INTENT_SCHEMA,
                "temperature": 0.1,
            },
        }

    def _parse_candidate_response(self, response_data: dict[str, Any]) -> QueryIntent:
        """Parse and validate the JSON candidate text from Gemini response data.

        Args:
            response_data: Parsed JSON payload returned by Gemini.

        Returns:
            Validated QueryIntent model.

        Raises:
            LLMResponseParsingError: If candidate text is missing, invalid JSON, or invalid schema.
        """
        try:
            candidates = response_data.get("candidates", [])
            if not candidates:
                raise LLMResponseParsingError("Gemini response contained no candidates")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts or "text" not in parts[0]:
                raise LLMResponseParsingError("Gemini candidate contained no text parts")

            raw_text = parts[0]["text"]
            parsed_json = json.loads(raw_text)
            return QueryIntent.model_validate(parsed_json)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error("Failed to parse Gemini intent extraction response due to %s", type(exc).__name__)
            raise LLMResponseParsingError(
                "Invalid or malformed intent payload received from Gemini"
            ) from exc

    async def _execute_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        max_retries: int = 4,
    ) -> httpx.Response:
        """Execute HTTP request with exponential backoff for 429 and transient errors.

        Args:
            client: Active HTTPX client.
            url: Target Gemini API endpoint URL.
            headers: HTTP request headers including API key.
            payload: JSON request body.
            max_retries: Maximum number of retry attempts.

        Returns:
            Successful httpx.Response.

        Raises:
            LLMTimeoutError: If the request exceeds timeout.
            LLMRateLimitError: If rate limited (429) and retries exhausted.
            LLMServiceError: For other unrecoverable HTTP or transport errors.
        """
        attempt = 0
        backoff_seconds = 1.0

        while True:
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=float(self.settings.request_timeout_seconds),
                )

                if response.status_code == 200:
                    return response

                if response.status_code == 429:
                    attempt += 1
                    if attempt > max_retries:
                        logger.warning("Gemini API rate limit exceeded after %d retries", max_retries)
                        raise LLMRateLimitError("Gemini API rate limit exceeded (429)")

                    retry_after_header = response.headers.get("Retry-After")
                    sleep_time = backoff_seconds
                    if retry_after_header:
                        try:
                            retry_after_val = float(retry_after_header)
                            if retry_after_val > 10.0:
                                logger.warning(
                                    "Gemini Retry-After is %.2fs (exceeds 10s cap); aborting retry",
                                    retry_after_val,
                                )
                                raise LLMRateLimitError(
                                    f"Gemini API rate limit Retry-After ({retry_after_val}s) exceeds maximum allowed wait (10s)"
                                )
                            sleep_time = max(retry_after_val, 0.0)
                        except ValueError:
                            sleep_time = backoff_seconds

                    logger.info(
                        "Gemini rate limit hit; retrying attempt %d in %.2fs",
                        attempt,
                        sleep_time,
                    )
                    await asyncio.sleep(sleep_time)
                    backoff_seconds *= 2.0
                    continue

                if response.status_code >= 500:
                    attempt += 1
                    if attempt > max_retries:
                        logger.error("Gemini server error %d after retries", response.status_code)
                        raise LLMServiceError(f"Gemini server error: {response.status_code}")

                    retry_after_header = response.headers.get("Retry-After")
                    sleep_time = backoff_seconds
                    if retry_after_header:
                        try:
                            retry_after_val = float(retry_after_header)
                            if retry_after_val > 10.0:
                                logger.warning(
                                    "Gemini 5xx Retry-After is %.2fs (exceeds 10s cap); aborting retry",
                                    retry_after_val,
                                )
                                raise LLMServiceError(
                                    f"Gemini server error Retry-After ({retry_after_val}s) exceeds maximum allowed wait (10s)"
                                )
                            sleep_time = max(retry_after_val, 0.0)
                        except ValueError:
                            sleep_time = backoff_seconds

                    logger.info(
                        "Gemini server error %d; retrying attempt %d in %.2fs",
                        response.status_code,
                        attempt,
                        sleep_time,
                    )
                    await asyncio.sleep(sleep_time)
                    backoff_seconds *= 2.0
                    continue

                # Unrecoverable 4xx error (e.g., 400 Bad Request, 403 Forbidden)
                response.raise_for_status()

            except httpx.TimeoutException as exc:
                logger.error("Gemini API request timed out after %ds", self.settings.request_timeout_seconds)
                raise LLMTimeoutError("Gemini API request timed out") from exc
            except httpx.HTTPStatusError as exc:
                logger.error("Gemini API HTTP status error: %s", exc)
                raise LLMServiceError(f"Gemini API returned HTTP {exc.response.status_code}") from exc
            except httpx.RequestError as exc:
                attempt += 1
                if attempt > max_retries:
                    logger.error("Gemini network connection error after retries: %s", type(exc).__name__)
                    raise LLMServiceError(f"Gemini network error: {type(exc).__name__}") from exc
                logger.info("Transient network error (%s); retrying in %.2fs", type(exc).__name__, backoff_seconds)
                await asyncio.sleep(backoff_seconds)
                backoff_seconds *= 2.0

    async def extract_query_intent(self, query: str) -> QueryIntent:
        """Extract structured query intent using configured Gemini model.

        Args:
            query: The user's natural language search query.

        Returns:
            Validated QueryIntent instance.

        Raises:
            LLMConfigurationError: If GEMINI_API_KEY is missing.
            LLMTimeoutError: If Gemini request times out.
            LLMRateLimitError: If Gemini 429 rate limit is reached.
            LLMResponseParsingError: If Gemini response is invalid or missing required fields.
            LLMServiceError: For other API or network communication failures.
        """
        api_key = self.settings.gemini_api_key.strip()
        if not api_key:
            raise LLMConfigurationError("GEMINI_API_KEY is not configured in settings")

        url = f"{GEMINI_API_BASE_URL}/{self.settings.gemini_model}:generateContent"
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        payload = self._build_payload(query)

        if self._external_client is not None:
            response = await self._execute_with_retry(
                client=self._external_client,
                url=url,
                headers=headers,
                payload=payload,
            )
            return self._parse_candidate_response(response.json())

        async with httpx.AsyncClient() as client:
            response = await self._execute_with_retry(
                client=client,
                url=url,
                headers=headers,
                payload=payload,
            )
            return self._parse_candidate_response(response.json())

    def _build_classification_payload(
        self, intent: QueryIntent, candidates: Sequence[RawCandidate]
    ) -> dict[str, Any]:
        """Construct the Gemini generateContent JSON request body for relevance classification.

        Args:
            intent: User query intent.
            candidates: Batch of raw candidates to classify.

        Returns:
            Dictionary payload conforming to Gemini API schema.
        """
        loc_str = ""
        if intent.location:
            parts = [
                p.strip()
                for p in (intent.location.city, intent.location.state, intent.location.country)
                if p and p.strip()
            ]
            loc_str = ", ".join(parts)

        candidates_data = [
            {
                "candidate_index": idx,
                "title": cand.title,
                "snippet": cand.snippet,
            }
            for idx, cand in enumerate(candidates)
        ]

        user_content = (
            f"Query Intent:\n"
            f"- Interest: {intent.interest}\n"
            f"- Target Type: {intent.target_type}\n"
            f"- Location: {loc_str or 'None'}\n\n"
            f"Candidates to Classify:\n{json.dumps(candidates_data, indent=2)}"
        )

        return {
            "systemInstruction": {
                "parts": [{"text": CLASSIFICATION_SYSTEM_INSTRUCTION}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_content}],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": GEMINI_CLASSIFICATION_SCHEMA,
                "temperature": 0.1,
            },
        }

    def _parse_classification_response(
        self, response_data: dict[str, Any]
    ) -> list[CandidateClassification]:
        """Parse and validate JSON candidate classifications from Gemini response.

        Args:
            response_data: Parsed JSON payload returned by Gemini.

        Returns:
            List of validated CandidateClassification objects.

        Raises:
            LLMResponseParsingError: If classification response is missing or malformed.
        """
        try:
            candidates = response_data.get("candidates", [])
            if not candidates:
                raise LLMResponseParsingError("Gemini response contained no candidates")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts or "text" not in parts[0]:
                raise LLMResponseParsingError("Gemini candidate contained no text parts")

            raw_text = parts[0]["text"]
            parsed_json = json.loads(raw_text)
            if not isinstance(parsed_json, list):
                raise LLMResponseParsingError("Gemini classification response is not a list")

            return [CandidateClassification.model_validate(item) for item in parsed_json]
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error(
                "Failed to parse Gemini candidate classification response: %s",
                type(exc).__name__,
            )
            raise LLMResponseParsingError(
                "Invalid or malformed candidate classification payload received from Gemini"
            ) from exc

    async def classify_candidates(
        self, intent: QueryIntent, candidates: list[RawCandidate]
    ) -> list[CandidateClassification]:
        """Classify a batch of candidate profiles against query intent using Gemini.

        Args:
            intent: The validated search query intent.
            candidates: Batch of at most 20 raw candidate profiles.

        Returns:
            List of CandidateClassification objects.

        Raises:
            ValueError: If candidate batch size exceeds 20.
            LLMConfigurationError: If GEMINI_API_KEY is missing.
            LLMTimeoutError: If Gemini request times out.
            LLMRateLimitError: If Gemini 429 rate limit is reached.
            LLMResponseParsingError: If Gemini response is invalid or malformed.
            LLMServiceError: For other API or network communication failures.
        """
        if not candidates:
            return []

        if len(candidates) > 20:
            raise ValueError(
                f"Candidate batch size {len(candidates)} exceeds maximum allowed of 20"
            )

        api_key = self.settings.gemini_api_key.strip()
        if not api_key:
            raise LLMConfigurationError("GEMINI_API_KEY is not configured in settings")

        url = f"{GEMINI_API_BASE_URL}/{self.settings.gemini_model}:generateContent"
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        payload = self._build_classification_payload(intent, candidates)

        if self._external_client is not None:
            response = await self._execute_with_retry(
                client=self._external_client,
                url=url,
                headers=headers,
                payload=payload,
            )
            return self._parse_classification_response(response.json())

        async with httpx.AsyncClient() as client:
            response = await self._execute_with_retry(
                client=client,
                url=url,
                headers=headers,
                payload=payload,
            )
            return self._parse_classification_response(response.json())


def get_llm_service(settings: Settings | None = None) -> BaseLLMService:
    """Factory function providing the configured LLM service provider."""
    return GeminiLLMService(settings=settings)
