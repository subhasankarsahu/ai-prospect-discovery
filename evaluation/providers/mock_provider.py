"""Offline mock evaluation provider.

Enables deterministic offline testing of the evaluation harness, metric calculation,
and report generation with zero network access and $0 budget expenditure.
"""

from app.schemas import QueryIntent
from app.schemas_internal import CandidateClassification, RawCandidate
from evaluation.providers.base import (
    CandidateBatchPredictionResult,
    CandidatePredictionResult,
    EvaluationModelProvider,
    IntentPredictionResult,
    TokenUsage,
)


class MockEvaluationProvider(EvaluationModelProvider):
    """Deterministic offline mock provider for evaluation harness testing."""

    def __init__(
        self,
        model_id: str = "mock-gemini-evaluator",
        intent_map: dict[str, QueryIntent] | None = None,
        classification_map: dict[str, CandidateClassification] | None = None,
        latency_ms: float = 45.0,
        token_usage: TokenUsage | None = None,
    ) -> None:
        self.model_id = model_id
        self.intent_map = intent_map or {}
        self.classification_map = classification_map or {}
        self.latency_ms = latency_ms
        self.token_usage = token_usage or TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)

    async def extract_intent(self, query: str) -> IntentPredictionResult:
        """Return scripted or heuristic intent prediction."""
        if query in self.intent_map:
            return IntentPredictionResult(
                query=query,
                intent=self.intent_map[query],
                raw_response="{}",
                is_valid_json=True,
                is_valid_schema=True,
                latency_ms=self.latency_ms,
                token_usage=self.token_usage,
            )

        # Fallback heuristic prediction
        is_prospect = not any(q in query.lower() for q in ["capital of", "how to", "weather", "stock price", "history of"])
        intent = QueryIntent(
            is_prospect_query=is_prospect,
            interest=query.split()[0] if query else "general",
            target_type="individual" if is_prospect else "other",
        )
        return IntentPredictionResult(
            query=query,
            intent=intent,
            raw_response="{}",
            is_valid_json=True,
            is_valid_schema=True,
            latency_ms=self.latency_ms,
            token_usage=self.token_usage,
        )

    async def classify_candidates(
        self, intent: QueryIntent, candidates: list[RawCandidate]
    ) -> CandidateBatchPredictionResult:
        """Return scripted or heuristic candidate classifications."""
        predictions = []
        for idx, cand in enumerate(candidates):
            lookup_key = f"{cand.source_platform}:{cand.title}"
            if lookup_key in self.classification_map:
                c_obj = self.classification_map[lookup_key]
                predictions.append(
                    CandidatePredictionResult(
                        candidate_index=idx,
                        raw_candidate=cand,
                        classification=c_obj,
                        is_valid=True,
                    )
                )
            else:
                # Default heuristic: individual if title has '-' or looks like a person
                title_lower = cand.title.lower()
                is_org = any(w in title_lower for w in ["league", "association", "center", "titans", "agency", "seo", "commanders", "ventures", "magazine"])
                name_words = cand.title.split("-")[0].strip() if "-" in cand.title else cand.title.split("|")[0].strip()

                c_obj = CandidateClassification(
                    candidate_index=idx,
                    is_individual_person=not is_org,
                    name_as_written=name_words,
                    interest_supported=True,
                    location_supported=True,
                    confidence="high" if not is_org else "low",
                    reason="Mock heuristic classification",
                )
                predictions.append(
                    CandidatePredictionResult(
                        candidate_index=idx,
                        raw_candidate=cand,
                        classification=c_obj,
                        is_valid=True,
                    )
                )

        return CandidateBatchPredictionResult(
            predictions=predictions,
            raw_response="[]",
            is_valid_json=True,
            latency_ms=self.latency_ms,
            token_usage=self.token_usage,
        )
