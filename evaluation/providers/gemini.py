"""Google Gemini evaluation provider adapter.

Provides model-configurable inference harness for Google Gemini models with strict
offline-first safeguards and $0 API budget enforcement.
"""

import json
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.schemas import QueryIntent
from app.schemas_internal import CandidateClassification, RawCandidate
from app.services.llm_service import (
    CLASSIFICATION_SYSTEM_INSTRUCTION,
    GEMINI_CLASSIFICATION_SCHEMA,
    GEMINI_QUERY_INTENT_SCHEMA,
    SYSTEM_INSTRUCTION,
)
from evaluation.providers.base import (
    CandidateBatchPredictionResult,
    CandidatePredictionResult,
    EvaluationModelProvider,
    IntentPredictionResult,
    TokenUsage,
    ZeroBudgetViolationError,
)

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiEvaluationProvider(EvaluationModelProvider):
    """Evaluation provider for Google Gemini models."""

    def __init__(
        self,
        model_id: str = "gemini-3.5-flash-lite",
        budget_cap_usd: float = 0.0,
        client: httpx.AsyncClient | None = None,
        allow_live_api: bool = False,
    ) -> None:
        """Initialize the Gemini evaluation provider.

        Args:
            model_id: Exact Google Gemini model identifier.
            budget_cap_usd: Budget cap in USD. Strictly 0.0 by default.
            client: Optional injected HTTPX client or mock transport for offline testing.
            allow_live_api: Explicit flag required to attempt live network access.
        """
        self.model_id = model_id
        self.budget_cap_usd = budget_cap_usd
        self.allow_live_api = allow_live_api
        self._client = client
        self.settings = get_settings()

    def _check_budget_guard(self) -> None:
        """Enforce zero-budget safety safeguard."""
        if not self.allow_live_api and self._client is None:
            raise ZeroBudgetViolationError(
                f"Live inference for model '{self.model_id}' blocked: budget cap is ${self.budget_cap_usd:.2f} "
                "and live inference is disabled. Use mock provider or injected test doubles for offline testing."
            )
        if self.budget_cap_usd <= 0.0 and self.allow_live_api:
            raise ZeroBudgetViolationError(
                f"Budget violation: Cannot execute live requests with budget_cap_usd=${self.budget_cap_usd:.2f}."
            )

    def _build_intent_payload(self, query: str) -> dict[str, Any]:
        """Construct Gemini generateContent JSON payload for intent extraction."""
        return {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": query}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": GEMINI_QUERY_INTENT_SCHEMA,
                "temperature": 0.0,
            },
        }

    def _build_classification_payload(
        self, intent: QueryIntent, candidates: list[RawCandidate]
    ) -> dict[str, Any]:
        """Construct Gemini generateContent JSON payload for candidate classification."""
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
            "systemInstruction": {"parts": [{"text": CLASSIFICATION_SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": user_content}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": GEMINI_CLASSIFICATION_SCHEMA,
                "temperature": 0.0,
            },
        }

    def _parse_token_usage(self, response_data: dict[str, Any]) -> TokenUsage:
        """Extract token usage metadata from Gemini response if present."""
        usage_meta = response_data.get("usageMetadata", {})
        return TokenUsage(
            prompt_tokens=usage_meta.get("promptTokenCount", 0),
            completion_tokens=usage_meta.get("candidatesTokenCount", 0),
            total_tokens=usage_meta.get("totalTokenCount", 0),
        )

    async def extract_intent(self, query: str) -> IntentPredictionResult:
        """Extract intent using configured Gemini model."""
        self._check_budget_guard()

        url = f"{GEMINI_API_BASE_URL}/{self.model_id}:generateContent"
        headers = {
            "x-goog-api-key": self.settings.gemini_api_key.strip(),
            "Content-Type": "application/json",
        }
        payload = self._build_intent_payload(query)

        start_time = time.perf_counter()
        raw_text = ""
        token_usage = TokenUsage()

        try:
            client = self._client or httpx.AsyncClient()
            try:
                resp = await client.post(url, headers=headers, json=payload, timeout=15.0)
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                resp_json = resp.json()
            finally:
                if self._client is None:
                    await client.aclose()

            token_usage = self._parse_token_usage(resp_json)
            candidates = resp_json.get("candidates", [])
            if not candidates or "content" not in candidates[0]:
                return IntentPredictionResult(
                    query=query,
                    error_message="Gemini returned no candidates",
                    latency_ms=elapsed_ms,
                    token_usage=token_usage,
                )

            parts = candidates[0]["content"].get("parts", [])
            if not parts or "text" not in parts[0]:
                return IntentPredictionResult(
                    query=query,
                    error_message="Gemini candidate contained no text parts",
                    latency_ms=elapsed_ms,
                    token_usage=token_usage,
                )

            raw_text = parts[0]["text"]
            parsed_json = json.loads(raw_text)
            intent = QueryIntent.model_validate(parsed_json)

            return IntentPredictionResult(
                query=query,
                intent=intent,
                raw_response=raw_text,
                is_valid_json=True,
                is_valid_schema=True,
                latency_ms=elapsed_ms,
                token_usage=token_usage,
            )

        except json.JSONDecodeError as exc:
            return IntentPredictionResult(
                query=query,
                raw_response=raw_text,
                is_valid_json=False,
                is_valid_schema=False,
                error_message=f"JSONDecodeError: {exc}",
                latency_ms=(time.perf_counter() - start_time) * 1000.0,
                token_usage=token_usage,
            )
        except ValidationError as exc:
            return IntentPredictionResult(
                query=query,
                raw_response=raw_text,
                is_valid_json=True,
                is_valid_schema=False,
                error_message=f"ValidationError: {exc}",
                latency_ms=(time.perf_counter() - start_time) * 1000.0,
                token_usage=token_usage,
            )
        except (httpx.HTTPError, KeyError, ValueError, RuntimeError) as exc:
            return IntentPredictionResult(
                query=query,
                error_message=f"{type(exc).__name__}: {exc}",
                latency_ms=(time.perf_counter() - start_time) * 1000.0,
                token_usage=token_usage,
            )

    async def classify_candidates(
        self, intent: QueryIntent, candidates: list[RawCandidate]
    ) -> CandidateBatchPredictionResult:
        """Classify candidate batch using configured Gemini model."""
        if not candidates:
            return CandidateBatchPredictionResult()

        self._check_budget_guard()

        url = f"{GEMINI_API_BASE_URL}/{self.model_id}:generateContent"
        headers = {
            "x-goog-api-key": self.settings.gemini_api_key.strip(),
            "Content-Type": "application/json",
        }
        payload = self._build_classification_payload(intent, candidates)

        start_time = time.perf_counter()
        raw_text = ""
        token_usage = TokenUsage()

        try:
            client = self._client or httpx.AsyncClient()
            try:
                resp = await client.post(url, headers=headers, json=payload, timeout=20.0)
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                resp_json = resp.json()
            finally:
                if self._client is None:
                    await client.aclose()

            token_usage = self._parse_token_usage(resp_json)
            cand_items = resp_json.get("candidates", [])
            if not cand_items or "content" not in cand_items[0]:
                return CandidateBatchPredictionResult(
                    error_message="Gemini returned no candidates in classification response",
                    latency_ms=elapsed_ms,
                    token_usage=token_usage,
                )

            parts = cand_items[0]["content"].get("parts", [])
            if not parts or "text" not in parts[0]:
                return CandidateBatchPredictionResult(
                    error_message="Gemini candidate contained no text parts",
                    latency_ms=elapsed_ms,
                    token_usage=token_usage,
                )

            raw_text = parts[0]["text"]
            parsed_list = json.loads(raw_text)
            if not isinstance(parsed_list, list):
                return CandidateBatchPredictionResult(
                    raw_response=raw_text,
                    is_valid_json=True,
                    error_message="Classification JSON is not a list",
                    latency_ms=elapsed_ms,
                    token_usage=token_usage,
                )

            predictions = []
            parsed_by_index: dict[int, CandidateClassification] = {}

            for item in parsed_list:
                try:
                    c_obj = CandidateClassification.model_validate(item)
                    parsed_by_index[c_obj.candidate_index] = c_obj
                except ValidationError:
                    continue

            for idx, raw_c in enumerate(candidates):
                if idx in parsed_by_index:
                    predictions.append(
                        CandidatePredictionResult(
                            candidate_index=idx,
                            raw_candidate=raw_c,
                            classification=parsed_by_index[idx],
                            is_valid=True,
                        )
                    )
                else:
                    predictions.append(
                        CandidatePredictionResult(
                            candidate_index=idx,
                            raw_candidate=raw_c,
                            classification=None,
                            is_valid=False,
                            error_message="Candidate index missing in model output",
                        )
                    )

            return CandidateBatchPredictionResult(
                predictions=predictions,
                raw_response=raw_text,
                is_valid_json=True,
                latency_ms=elapsed_ms,
                token_usage=token_usage,
            )

        except json.JSONDecodeError as exc:
            return CandidateBatchPredictionResult(
                raw_response=raw_text,
                is_valid_json=False,
                error_message=f"JSONDecodeError: {exc}",
                latency_ms=(time.perf_counter() - start_time) * 1000.0,
                token_usage=token_usage,
            )
        except (httpx.HTTPError, KeyError, ValueError, RuntimeError) as exc:
            return CandidateBatchPredictionResult(
                error_message=f"{type(exc).__name__}: {exc}",
                latency_ms=(time.perf_counter() - start_time) * 1000.0,
                token_usage=token_usage,
            )
