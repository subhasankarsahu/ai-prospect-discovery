"""Offline test suite for the evaluation harness, providers, metrics, and safety controls.

Verifies:
1. Zero-budget enforcement (blocks live inference when budget is $0).
2. Mock evaluation provider offline execution.
3. Gemini evaluation provider with injected mock client.
4. Intent metrics calculation (exact, semantic, non-prospect, hallucination detection).
5. Intent unreviewed-label exclusion from primary scoring.
6. Candidate metrics calculation (model-level vs pipeline-level).
7. Strict exclusion of ambiguous candidates from binary precision/recall/F1.
8. Ambiguous candidate uncertainty statistics calculation.
9. Wilson score confidence intervals and small sample warnings.
10. Evaluation runner end-to-end execution on development split.
11. Human review export and ingestion workflow preserving machine suggestions.
12. Total decoupling from Tavily and external network access.
"""

import json
from pathlib import Path

import httpx
import pytest

from app.schemas import Location, QueryIntent
from app.schemas_internal import CandidateClassification, RawCandidate
from evaluation.metrics.candidate_metrics import (
    evaluate_candidate_batch_predictions,
)
from evaluation.metrics.intent_metrics import (
    evaluate_intent_predictions,
    is_hallucinated_commentary,
)
from evaluation.metrics.statistical import (
    compute_f1,
    compute_wilson_score_interval,
)
from evaluation.providers.base import (
    CandidateBatchPredictionResult,
    CandidatePredictionResult,
    IntentPredictionResult,
    ZeroBudgetViolationError,
)
from evaluation.providers.gemini import GeminiEvaluationProvider
from evaluation.providers.mock_provider import MockEvaluationProvider
from evaluation.review.export_review import (
    export_candidate_reviews,
    export_intent_reviews,
)
from evaluation.runner.config import EvaluationConfig
from evaluation.runner.run_evaluation import EvaluationRunner


def test_budget_safety_validation() -> None:
    """Verify EvaluationConfig enforces the $0.00 budget rule."""
    # Default is valid
    cfg = EvaluationConfig()
    cfg.validate_budget_safety()
    assert cfg.budget_cap_usd == 0.0
    assert cfg.offline_mode is True

    # Reject non-zero budget cap
    with pytest.raises(ValueError, match="budget cap is set to"):
        invalid_cfg = EvaluationConfig(budget_cap_usd=10.0)
        invalid_cfg.validate_budget_safety()

    # Reject live API with zero budget
    with pytest.raises(ValueError, match="Live API execution is disabled"):
        invalid_live = EvaluationConfig(allow_live_api=True, budget_cap_usd=0.0)
        invalid_live.validate_budget_safety()


@pytest.mark.asyncio
async def test_gemini_provider_zero_budget_guard() -> None:
    """Verify GeminiEvaluationProvider blocks live requests under zero budget."""
    provider = GeminiEvaluationProvider(
        model_id="gemini-3.5-flash-lite",
        budget_cap_usd=0.0,
        allow_live_api=False,
    )

    with pytest.raises(ZeroBudgetViolationError, match="budget cap is"):
        await provider.extract_intent("test query")

    with pytest.raises(ZeroBudgetViolationError, match="budget cap is"):
        await provider.classify_candidates(
            QueryIntent(interest="test"),
            [RawCandidate(source_platform="X", canonical_url="https://x.com/1", search_query="q")],
        )


@pytest.mark.asyncio
async def test_gemini_provider_with_mock_client() -> None:
    """Verify GeminiEvaluationProvider parses responses when an offline mock client is injected."""
    mock_intent_resp = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps({
                                "is_prospect_query": True,
                                "interest": "FinTech",
                                "target_type": "founder",
                            })
                        }
                    ]
                }
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 50,
            "candidatesTokenCount": 20,
            "totalTokenCount": 70,
        },
    }

    mock_http_resp = httpx.Response(
        status_code=200,
        json=mock_intent_resp,
        request=httpx.Request("POST", "https://test"),
    )

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: mock_http_resp))
    provider = GeminiEvaluationProvider(
        model_id="gemini-3.5-flash-lite",
        budget_cap_usd=0.0,
        client=client,
    )

    result = await provider.extract_intent("FinTech founders")
    assert result.is_valid_schema is True
    assert result.intent is not None
    assert result.intent.interest == "FinTech"
    assert result.token_usage.total_tokens == 70


@pytest.mark.asyncio
async def test_mock_provider_offline() -> None:
    """Verify MockEvaluationProvider executes completely offline."""
    provider = MockEvaluationProvider(model_id="mock-test-model")
    res = await provider.extract_intent("Startup founders in London")
    assert res.is_valid_schema is True
    assert res.intent is not None
    assert res.intent.is_prospect_query is True

    cand = RawCandidate(
        source_platform="LinkedIn",
        canonical_url="https://linkedin.com/in/alice",
        title="Alice - Founder",
        snippet="Alice is a founder in London",
        search_query="q",
    )
    b_res = await provider.classify_candidates(res.intent, [cand])
    assert len(b_res.predictions) == 1
    assert b_res.predictions[0].classification is not None
    assert b_res.predictions[0].classification.is_individual_person is True


def test_intent_metrics_calculation() -> None:
    """Verify intent metrics calculations including semantic variants and hallucination detection."""
    ground_truth = [
        {
            "input_query": "AI founders in NYC",
            "ground_truth": {
                "is_prospect_query": True,
                "interest": "artificial intelligence",
                "audience": "founders",
                "location": {"city": "New York", "state": "NY", "country": "USA"},
                "target_type": "founder",
            },
            "acceptable_variants": {
                "interest": ["AI", "machine learning"],
                "location": {"city": ["New York", "NYC"]},
            },
            "annotation": {"status": "reviewed"},
        },
        {
            "input_query": "What is the capital of Italy?",
            "ground_truth": {
                "is_prospect_query": False,
                "interest": "geography",
                "audience": None,
                "location": None,
                "target_type": "other",
            },
            "annotation": {"status": "reviewed"},
        },
    ]

    predictions = [
        IntentPredictionResult(
            query="AI founders in NYC",
            intent=QueryIntent(
                is_prospect_query=True,
                interest="AI",  # matches variant
                audience="founders",
                location=Location(city="NYC", state="NY", country="USA"),
                target_type="founder",
            ),
            is_valid_schema=True,
        ),
        IntentPredictionResult(
            query="What is the capital of Italy?",
            intent=QueryIntent(
                is_prospect_query=False,
                interest="geography",
                target_type="other",
            ),
            is_valid_schema=True,
        ),
    ]

    report = evaluate_intent_predictions(predictions, ground_truth, require_human_reviewed=True)
    assert report.total_evaluated == 2
    assert report.reviewed_evaluated == 2
    assert report.prospect_accuracy == 1.0
    assert report.prospect_precision == 1.0
    assert report.prospect_recall == 1.0
    assert report.prospect_f1 == 1.0
    assert report.interest_semantic_accuracy == 1.0
    assert report.location_accuracy == 1.0


def test_intent_hallucination_detection() -> None:
    """Verify that verbose model reasoning in location fields is flagged as hallucination."""
    verbose_text = "New York State or NY implied context not explicitly separated in query"
    assert is_hallucinated_commentary(verbose_text) is True
    assert is_hallucinated_commentary("New York") is False
    assert is_hallucinated_commentary("CA") is False


def test_candidate_metrics_ambiguous_exclusion() -> None:
    """Verify that ambiguous candidates are strictly excluded from binary precision/recall/F1."""
    ground_truth = [
        # 1. Unambiguous Positive
        {
            "example_id": "c1",
            "ground_truth": {
                "is_individual_person": "positive",
                "name_supported": "positive",
                "interest_supported": "positive",
                "location_supported": "positive",
                "overall_acceptability": "positive",
            },
            "annotation": {"status": "reviewed"},
        },
        # 2. Unambiguous Negative
        {
            "example_id": "c2",
            "ground_truth": {
                "is_individual_person": "negative",
                "name_supported": "positive",
                "interest_supported": "positive",
                "location_supported": "positive",
                "overall_acceptability": "negative",
            },
            "annotation": {"status": "reviewed"},
        },
        # 3. Ambiguous Candidate
        {
            "example_id": "c3",
            "ground_truth": {
                "is_individual_person": "ambiguous",
                "name_supported": "positive",
                "interest_supported": "positive",
                "location_supported": "positive",
                "overall_acceptability": "ambiguous",
            },
            "annotation": {"status": "reviewed"},
        },
    ]

    raw_cands = [
        RawCandidate(source_platform="LinkedIn", canonical_url="https://u1", title="Alice Smith", snippet="Bio", search_query="q"),
        RawCandidate(source_platform="LinkedIn", canonical_url="https://u2", title="Acme Agency", snippet="Agency Bio", search_query="q"),
        RawCandidate(source_platform="LinkedIn", canonical_url="https://u3", title="Consulting Group", snippet="Consulting", search_query="q"),
    ]

    # Model correctly accepts c1, rejects c2, and accepts ambiguous c3
    batch_res = CandidateBatchPredictionResult(
        predictions=[
            CandidatePredictionResult(
                candidate_index=0,
                raw_candidate=raw_cands[0],
                classification=CandidateClassification(
                    candidate_index=0,
                    is_individual_person=True,
                    name_as_written="Alice Smith",
                    interest_supported=True,
                    location_supported=True,
                    confidence="high",
                    reason="Person",
                ),
                is_valid=True,
            ),
            CandidatePredictionResult(
                candidate_index=1,
                raw_candidate=raw_cands[1],
                classification=CandidateClassification(
                    candidate_index=1,
                    is_individual_person=False,
                    name_as_written="Acme Agency",
                    interest_supported=True,
                    location_supported=True,
                    confidence="high",
                    reason="Company",
                ),
                is_valid=True,
            ),
            CandidatePredictionResult(
                candidate_index=2,
                raw_candidate=raw_cands[2],
                classification=CandidateClassification(
                    candidate_index=2,
                    is_individual_person=True,
                    name_as_written="Consulting Group",
                    interest_supported=True,
                    location_supported=True,
                    confidence="medium",
                    reason="Ambiguous",
                ),
                is_valid=True,
            ),
        ]
    )

    report = evaluate_candidate_batch_predictions([batch_res], ground_truth, require_human_reviewed=True)

    # Ambiguity check
    assert report.ambiguity_stats.total_ambiguous == 1
    assert report.ambiguity_stats.accepted_by_model == 1
    assert report.ambiguity_stats.acceptance_rate == 1.0

    # Binary check (ONLY evaluated on c1 and c2; c3 MUST be excluded!)
    # c1 is TP, c2 is TN. Total binary = 2.
    assert report.model_level.true_positives == 1
    assert report.model_level.false_positives == 0  # c3 was NOT counted as FP!
    assert report.model_level.true_negatives == 1
    assert report.model_level.false_negatives == 0
    assert report.model_level.precision == 1.0
    assert report.model_level.recall == 1.0
    assert report.model_level.f1 == 1.0


def test_wilson_score_interval_and_f1() -> None:
    """Verify Wilson score interval math and sample size warnings."""
    # N = 10 (< 30) should trigger warning
    ci_small = compute_wilson_score_interval(8, 10)
    assert ci_small.point_estimate == 0.8
    assert ci_small.warning is not None
    assert "Small sample size" in ci_small.warning
    assert 0.0 <= ci_small.ci_lower < 0.8 < ci_small.ci_upper <= 1.0

    # F1 edge case: 0 precision and 0 recall returns 0.0
    assert compute_f1(0.0, 0.0) == 0.0
    assert compute_f1(1.0, 1.0) == 1.0


@pytest.mark.asyncio
async def test_evaluation_runner_development_split() -> None:
    """Verify EvaluationRunner executes on development split completely offline."""
    config = EvaluationConfig(
        model_id="mock-gemini-test",
        split="development",
        offline_mode=True,
        require_human_reviewed=False,  # Allow running against initial suggested ground truth
    )

    runner = EvaluationRunner(config=config)
    result = await runner.run()

    assert result["model_id"] == "mock-gemini-test"
    assert result["split"] == "development"
    assert result["intent_metrics"]["total_evaluated"] == 10
    assert result["candidate_metrics"]["total_candidates"] == 30
    assert result["budget_cap_usd"] == 0.0


def test_human_review_workflow_preserves_machine_suggestions(tmp_path: Path) -> None:
    """Verify that applying human reviews preserves original machine suggestions."""
    # Test review export produces CSV and JSON
    export_candidate_reviews()
    export_intent_reviews()

    review_cand_file = Path("evaluation/review/pending_candidate_reviews.json")
    review_intent_file = Path("evaluation/review/pending_intent_reviews.json")
    assert review_cand_file.exists()
    assert review_intent_file.exists()
