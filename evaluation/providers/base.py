"""Base interface and data models for model evaluation providers.

Strictly Google-only; provides evaluation-scoped abstraction without modifying production code.
"""

from dataclasses import dataclass, field
from typing import Protocol

from app.schemas import QueryIntent
from app.schemas_internal import CandidateClassification, RawCandidate


class ZeroBudgetViolationError(RuntimeError):
    """Raised when an external network request is attempted with a zero budget."""


class EvaluationProviderError(Exception):
    """Base exception for evaluation provider failures."""


@dataclass
class TokenUsage:
    """Token consumption metadata."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class IntentPredictionResult:
    """Outcome of an intent extraction prediction."""

    query: str
    intent: QueryIntent | None = None
    raw_response: str = ""
    is_valid_json: bool = False
    is_valid_schema: bool = False
    error_message: str | None = None
    latency_ms: float = 0.0
    token_usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass
class CandidatePredictionResult:
    """Outcome of candidate relevance classification for a single candidate."""

    candidate_index: int
    raw_candidate: RawCandidate
    classification: CandidateClassification | None = None
    is_valid: bool = False
    error_message: str | None = None


@dataclass
class CandidateBatchPredictionResult:
    """Outcome of candidate relevance classification for a batch of candidates."""

    predictions: list[CandidatePredictionResult] = field(default_factory=list)
    raw_response: str = ""
    is_valid_json: bool = False
    latency_ms: float = 0.0
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    error_message: str | None = None


class EvaluationModelProvider(Protocol):
    """Protocol interface for an evaluation model provider."""

    model_id: str

    async def extract_intent(self, query: str) -> IntentPredictionResult:
        """Extract structured query intent."""
        ...

    async def classify_candidates(
        self, intent: QueryIntent, candidates: list[RawCandidate]
    ) -> CandidateBatchPredictionResult:
        """Classify relevance for a batch of raw candidates."""
        ...
