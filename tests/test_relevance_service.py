"""Unit tests for candidate relevance classification and evidence verification."""

from unittest.mock import AsyncMock

import pytest

from app.schemas import Location, QueryIntent
from app.schemas_internal import CandidateClassification, RawCandidate
from app.services.llm_service import (
    BaseLLMService,
    LLMRateLimitError,
    LLMResponseParsingError,
)
from app.services.relevance_service import classify_and_verify_candidates


@pytest.fixture
def sample_intent() -> QueryIntent:
    """Fixture returning sample query intent."""
    return QueryIntent(
        is_prospect_query=True,
        interest="Machine Learning",
        target_type="researcher",
        location=Location(city="Seattle", country="USA"),
    )


def _make_candidate(idx: int, title: str, snippet: str) -> RawCandidate:
    """Helper to create dummy raw candidates."""
    return RawCandidate(
        source_platform="LinkedIn",
        canonical_url=f"https://linkedin.com/in/user-{idx}",
        title=title,
        snippet=snippet,
        search_query="ml researcher seattle",
    )


@pytest.mark.asyncio
async def test_relevance_accepts_supported_individual(sample_intent: QueryIntent) -> None:
    """Verify that a candidate meeting all criteria with name verbatim in evidence is accepted."""
    cand = _make_candidate(
        1,
        title="Dr. Alice Smith - Principal ML Researcher",
        snippet="Alice Smith is leading machine learning research in Seattle, USA.",
    )

    mock_llm = AsyncMock(spec=BaseLLMService)
    mock_llm.classify_candidates.return_value = [
        CandidateClassification(
            candidate_index=0,
            is_individual_person=True,
            name_as_written="Alice Smith",
            interest_supported=True,
            location_supported=True,
            confidence="high",
            reason="Alice Smith is an ML researcher based in Seattle.",
        )
    ]

    verified = await classify_and_verify_candidates(sample_intent, [cand], mock_llm)
    assert len(verified) == 1
    assert verified[0].verified_name == "Alice Smith"
    assert verified[0].canonical_url == "https://linkedin.com/in/user-1"
    assert verified[0].source_platform == "LinkedIn"
    assert verified[0].location == "Seattle, USA"
    assert verified[0].confidence == "high"


@pytest.mark.asyncio
async def test_relevance_rejects_hallucinated_name(sample_intent: QueryIntent) -> None:
    """Verify candidate is rejected if name_as_written is absent from title and snippet."""
    cand = _make_candidate(
        1,
        title="Machine Learning Research Laboratory",
        snippet="Leading artificial intelligence and deep learning group.",
    )

    mock_llm = AsyncMock(spec=BaseLLMService)
    mock_llm.classify_candidates.return_value = [
        CandidateClassification(
            candidate_index=0,
            is_individual_person=True,
            name_as_written="Bob Hallucinated",
            interest_supported=True,
            location_supported=False,
            confidence="high",
            reason="Presumed lead researcher.",
        )
    ]

    verified = await classify_and_verify_candidates(sample_intent, [cand], mock_llm)
    assert len(verified) == 0


@pytest.mark.asyncio
async def test_relevance_rejects_low_confidence(sample_intent: QueryIntent) -> None:
    """Verify that low confidence candidates are rejected."""
    cand = _make_candidate(
        1,
        title="Charlie Brown profile",
        snippet="Charlie Brown mentions computer science.",
    )

    mock_llm = AsyncMock(spec=BaseLLMService)
    mock_llm.classify_candidates.return_value = [
        CandidateClassification(
            candidate_index=0,
            is_individual_person=True,
            name_as_written="Charlie Brown",
            interest_supported=True,
            location_supported=False,
            confidence="low",
            reason="Uncertain if actually doing ML research.",
        )
    ]

    verified = await classify_and_verify_candidates(sample_intent, [cand], mock_llm)
    assert len(verified) == 0


@pytest.mark.asyncio
async def test_relevance_rejects_organization(sample_intent: QueryIntent) -> None:
    """Verify that company, organization, or generic pages are rejected."""
    cand = _make_candidate(
        1,
        title="Seattle ML Institute",
        snippet="Seattle ML Institute focuses on applied AI algorithms.",
    )

    mock_llm = AsyncMock(spec=BaseLLMService)
    mock_llm.classify_candidates.return_value = [
        CandidateClassification(
            candidate_index=0,
            is_individual_person=False,
            name_as_written="Seattle ML Institute",
            interest_supported=True,
            location_supported=True,
            confidence="high",
            reason="This is an organization, not an individual.",
        )
    ]

    verified = await classify_and_verify_candidates(sample_intent, [cand], mock_llm)
    assert len(verified) == 0


@pytest.mark.asyncio
async def test_relevance_rejects_unsupported_interest(sample_intent: QueryIntent) -> None:
    """Verify candidate is rejected if their profile does not support the requested interest."""
    cand = _make_candidate(
        1,
        title="David Miller - Real Estate Agent",
        snippet="David Miller is a top realtor serving Seattle homes.",
    )

    mock_llm = AsyncMock(spec=BaseLLMService)
    mock_llm.classify_candidates.return_value = [
        CandidateClassification(
            candidate_index=0,
            is_individual_person=True,
            name_as_written="David Miller",
            interest_supported=False,
            location_supported=True,
            confidence="high",
            reason="David Miller is a real estate agent, unrelated to ML.",
        )
    ]

    verified = await classify_and_verify_candidates(sample_intent, [cand], mock_llm)
    assert len(verified) == 0


@pytest.mark.asyncio
async def test_relevance_ignores_out_of_range_index(sample_intent: QueryIntent) -> None:
    """Verify classification entries with out-of-range indexes are ignored."""
    cand = _make_candidate(
        1,
        title="Dr. Eva Green - ML Scientist",
        snippet="Eva Green works on ML models.",
    )

    mock_llm = AsyncMock(spec=BaseLLMService)
    mock_llm.classify_candidates.return_value = [
        CandidateClassification(
            candidate_index=99,  # Out of range!
            is_individual_person=True,
            name_as_written="Eva Green",
            interest_supported=True,
            location_supported=False,
            confidence="high",
            reason="Valid candidate but wrong index.",
        )
    ]

    verified = await classify_and_verify_candidates(sample_intent, [cand], mock_llm)
    assert len(verified) == 0


@pytest.mark.asyncio
async def test_relevance_rejects_duplicate_index(sample_intent: QueryIntent) -> None:
    """Verify duplicate classification items for the same index do not duplicate candidates."""
    cand = _make_candidate(
        1,
        title="Frank Castle - ML Engineer",
        snippet="Frank Castle develops algorithms.",
    )

    mock_llm = AsyncMock(spec=BaseLLMService)
    mock_llm.classify_candidates.return_value = [
        CandidateClassification(
            candidate_index=0,
            is_individual_person=True,
            name_as_written="Frank Castle",
            interest_supported=True,
            location_supported=False,
            confidence="high",
            reason="First entry.",
        ),
        CandidateClassification(
            candidate_index=0,  # Duplicate!
            is_individual_person=True,
            name_as_written="Frank Castle",
            interest_supported=True,
            location_supported=False,
            confidence="high",
            reason="Duplicate entry.",
        ),
    ]

    verified = await classify_and_verify_candidates(sample_intent, [cand], mock_llm)
    assert len(verified) == 1


@pytest.mark.asyncio
async def test_relevance_splits_into_batches_of_20(sample_intent: QueryIntent) -> None:
    """Verify that >20 candidates are split into separate batches of at most 20."""
    candidates = [
        _make_candidate(i, f"Researcher {i}", f"Researcher {i} does Machine Learning research.")
        for i in range(25)
    ]

    mock_llm = AsyncMock(spec=BaseLLMService)

    async def mock_classify(intent, batch):
        return [
            CandidateClassification(
                candidate_index=idx,
                is_individual_person=True,
                name_as_written=f"Researcher {batch[idx].title.split()[-1]}",
                interest_supported=True,
                location_supported=False,
                confidence="high",
                reason="Match.",
            )
            for idx in range(len(batch))
        ]

    mock_llm.classify_candidates.side_effect = mock_classify

    verified = await classify_and_verify_candidates(sample_intent, candidates, mock_llm)

    assert mock_llm.classify_candidates.call_count == 2
    # First batch had 20, second batch had 5
    first_call_batch = mock_llm.classify_candidates.call_args_list[0].args[1]
    second_call_batch = mock_llm.classify_candidates.call_args_list[1].args[1]
    assert len(first_call_batch) == 20
    assert len(second_call_batch) == 5
    assert len(verified) == 25


@pytest.mark.asyncio
async def test_relevance_partial_batch_failure_preserves_successful_batches(
    sample_intent: QueryIntent,
) -> None:
    """Verify that a failure in one batch does not erase successful results from other batches."""
    candidates = [
        _make_candidate(i, f"Researcher {i}", f"Researcher {i} works on Machine Learning.")
        for i in range(25)
    ]

    mock_llm = AsyncMock(spec=BaseLLMService)
    call_count = 0

    async def mock_classify(intent, batch):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First batch (20 candidates) succeeds
            return [
                CandidateClassification(
                    candidate_index=idx,
                    is_individual_person=True,
                    name_as_written=f"Researcher {batch[idx].title.split()[-1]}",
                    interest_supported=True,
                    location_supported=False,
                    confidence="high",
                    reason="Match.",
                )
                for idx in range(len(batch))
            ]
        # Second batch fails
        raise LLMResponseParsingError("Malformed response in second batch")

    mock_llm.classify_candidates.side_effect = mock_classify

    verified = await classify_and_verify_candidates(sample_intent, candidates, mock_llm)

    # 20 from the first batch preserved
    assert len(verified) == 20


@pytest.mark.asyncio
async def test_relevance_all_batches_fail_raises_error(sample_intent: QueryIntent) -> None:
    """Verify that if all classification batches fail, the exception is raised."""
    cand = _make_candidate(1, "Researcher", "Snippet")
    mock_llm = AsyncMock(spec=BaseLLMService)
    mock_llm.classify_candidates.side_effect = LLMRateLimitError("Rate limit")

    with pytest.raises(LLMRateLimitError):
        await classify_and_verify_candidates(sample_intent, [cand], mock_llm)


@pytest.mark.asyncio
async def test_relevance_location_not_accepted_without_text_evidence(sample_intent: QueryIntent) -> None:
    """Verify that location is rejected if not in candidate text, even if LLM claimed location_supported=True."""
    # Candidate text does NOT mention Seattle or USA
    cand = _make_candidate(
        1,
        title="Alice Smith - ML Lead",
        snippet="Alice Smith is leading machine learning research.",
    )
    mock_llm = AsyncMock(spec=BaseLLMService)
    mock_llm.classify_candidates.return_value = [
        CandidateClassification(
            candidate_index=0,
            is_individual_person=True,
            name_as_written="Alice Smith",
            interest_supported=True,
            location_supported=True,  # LLM erroneously claims location is supported
            confidence="high",
            reason="Location assumed from query.",
        )
    ]

    verified = await classify_and_verify_candidates(sample_intent, [cand], mock_llm)
    assert len(verified) == 1
    # Location must be None because it does not appear in candidate evidence!
    assert verified[0].location is None


@pytest.mark.asyncio
async def test_relevance_location_verbatim_evidence_preserved(sample_intent: QueryIntent) -> None:
    """Verify that location casing and text are sliced verbatim from candidate evidence."""
    cand = _make_candidate(
        1,
        title="Alice Smith - ML Lead",
        snippet="Alice Smith is leading ML research in SEATTLE, USA.",
    )
    mock_llm = AsyncMock(spec=BaseLLMService)
    mock_llm.classify_candidates.return_value = [
        CandidateClassification(
            candidate_index=0,
            is_individual_person=True,
            name_as_written="Alice Smith",
            interest_supported=True,
            location_supported=True,
            confidence="high",
            reason="Verified profile.",
        )
    ]

    verified = await classify_and_verify_candidates(sample_intent, [cand], mock_llm)
    assert len(verified) == 1
    # Preserves verbatim casing from candidate evidence snippet
    assert verified[0].location == "SEATTLE, USA"

