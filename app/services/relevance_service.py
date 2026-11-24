"""Candidate relevance classification service with strict code-side evidence verification."""

import logging
from collections.abc import Sequence

from app.schemas import QueryIntent
from app.schemas_internal import RawCandidate, VerifiedCandidate
from app.services.llm_service import (
    BaseLLMService,
    LLMConfigurationError,
    LLMRateLimitError,
    LLMResponseParsingError,
    LLMServiceError,
    LLMTimeoutError,
    get_llm_service,
)

logger = logging.getLogger(__name__)

MAX_CLASSIFICATION_BATCH_SIZE = 20


def _extract_verbatim_display_name(name_as_written: str, title: str, snippet: str) -> str | None:
    """Find and extract the exact-cased display name verbatim from title or snippet.

    Args:
        name_as_written: Name string supplied by LLM.
        title: Raw candidate page title.
        snippet: Raw candidate search snippet.

    Returns:
        Exact substring with original casing if found; None otherwise.
    """
    clean_name = name_as_written.strip()
    if not clean_name:
        return None

    lower_name = clean_name.lower()
    lower_title = title.lower()
    lower_snippet = snippet.lower()

    # Search title first
    pos = lower_title.find(lower_name)
    if pos != -1:
        return title[pos : pos + len(clean_name)]

    # Search snippet second
    pos = lower_snippet.find(lower_name)
    if pos != -1:
        return snippet[pos : pos + len(clean_name)]

    return None


def _find_verbatim_fragment(fragment: str | None, title: str, snippet: str) -> str | None:
    """Extract a fragment verbatim with exact casing as it appears in title or snippet."""
    if not fragment or not isinstance(fragment, str):
        return None
    frag_clean = fragment.strip()
    if not frag_clean:
        return None

    frag_lower = frag_clean.lower()
    # Check title first
    pos = title.lower().find(frag_lower)
    if pos != -1:
        return title[pos : pos + len(frag_clean)]

    # Check snippet
    pos = snippet.lower().find(frag_lower)
    if pos != -1:
        return snippet[pos : pos + len(frag_clean)]

    return None


def _extract_verified_location(intent: QueryIntent, title: str, snippet: str) -> str | None:
    """Verify that location components appear in the candidate title or snippet.

    Extracts verbatim evidence text from the candidate, ensuring no location is
    inferred without direct evidence in the snippet or title.

    Args:
        intent: Query intent containing optional geographic constraints.
        title: Candidate title.
        snippet: Candidate snippet.

    Returns:
        Verified location string if present in candidate evidence; None otherwise.
    """
    if not intent.location:
        return None

    loc_parts: list[str] = []

    if intent.location.city:
        matched_city = _find_verbatim_fragment(intent.location.city, title, snippet)
        if matched_city:
            loc_parts.append(matched_city)

    if intent.location.state:
        matched_state = _find_verbatim_fragment(intent.location.state, title, snippet)
        if matched_state:
            loc_parts.append(matched_state)

    if intent.location.country:
        matched_country = _find_verbatim_fragment(intent.location.country, title, snippet)
        if matched_country:
            loc_parts.append(matched_country)

    return ", ".join(loc_parts) if loc_parts else None


async def classify_and_verify_candidates(
    intent: QueryIntent,
    candidates: Sequence[RawCandidate],
    llm_service: BaseLLMService | None = None,
) -> list[VerifiedCandidate]:
    """Classify raw search candidates in batches of <=20 and verify evidence on code side.

    Enforces that:
    1. Candidate indexes are integers in batch bounds.
    2. Duplicates for the same candidate index are rejected.
    3. Person name appears verbatim in title or snippet; rejected if absent.
    4. Only accepted when is_individual_person=True, interest_supported=True,
       and confidence is medium or high.
    5. Original candidate URL and source platform are preserved.
    6. Batch failures do not discard results from successful batches.

    Args:
        intent: The validated search query intent.
        candidates: Sequence of raw candidate search results.
        llm_service: Optional LLM service instance.

    Returns:
        List of verified, evidence-backed candidate objects.

    Raises:
        LLMConfigurationError: On missing API keys.
        LLMRateLimitError: If all classification batches are rate limited.
        LLMTimeoutError: If all classification batches time out.
        LLMServiceError: If all classification batches fail unrecoverably.
    """
    if not candidates:
        return []

    service = llm_service or get_llm_service()
    candidate_list = list(candidates)
    verified_candidates: list[VerifiedCandidate] = []

    batches: list[list[RawCandidate]] = [
        candidate_list[i : i + MAX_CLASSIFICATION_BATCH_SIZE]
        for i in range(0, len(candidate_list), MAX_CLASSIFICATION_BATCH_SIZE)
    ]

    failed_batches = 0
    last_error: Exception | None = None

    for batch_idx, batch in enumerate(batches):
        try:
            raw_classifications = await service.classify_candidates(intent, batch)
        except LLMConfigurationError:
            raise
        except (LLMRateLimitError, LLMTimeoutError, LLMResponseParsingError, LLMServiceError) as exc:
            logger.warning(
                "Classification batch %d/%d failed due to %s: %s",
                batch_idx + 1,
                len(batches),
                type(exc).__name__,
                exc,
            )
            failed_batches += 1
            last_error = exc
            continue

        seen_indices: set[int] = set()

        for item in raw_classifications:
            # 1. candidate_index must be an integer within batch bounds
            if not isinstance(item.candidate_index, int):
                logger.warning("Ignoring classification item with non-integer candidate_index")
                continue

            idx = item.candidate_index
            if idx < 0 or idx >= len(batch):
                logger.warning("Ignoring classification item with out-of-range index: %d", idx)
                continue

            # 2. Reject duplicate classification entries for the same index
            if idx in seen_indices:
                logger.warning("Rejecting duplicate classification entry for candidate_index %d", idx)
                continue
            seen_indices.add(idx)

            # 3. Acceptance criteria: individual person, supported interest, confidence medium/high
            if not item.is_individual_person:
                continue
            if not item.interest_supported:
                continue
            if item.confidence.lower() not in ("medium", "high"):
                continue

            cand = batch[idx]

            # 4. Mandatory verbatim name check in title or snippet
            verbatim_name = _extract_verbatim_display_name(
                item.name_as_written, cand.title, cand.snippet
            )
            if not verbatim_name:
                logger.info(
                    "Rejecting candidate %s: claimed name '%s' not found verbatim in title or snippet",
                    cand.canonical_url,
                    item.name_as_written,
                )
                continue

            # 5. Extract verified location only if supported and present in evidence
            verified_loc: str | None = None
            if item.location_supported:
                verified_loc = _extract_verified_location(intent, cand.title, cand.snippet)

            verified_candidates.append(
                VerifiedCandidate(
                    raw_candidate=cand,
                    verified_name=verbatim_name,
                    source_platform=cand.source_platform,
                    canonical_url=cand.canonical_url,
                    location=verified_loc,
                    confidence=item.confidence.lower(),
                    reason=item.reason,
                    contacts=[],
                )
            )

    # If all batches failed and 0 candidates were verified, propagate the failure
    if failed_batches == len(batches) and not verified_candidates and last_error is not None:
        logger.error("All %d relevance classification batches failed", len(batches))
        raise last_error

    logger.info(
        "Candidate relevance classification complete: %d verified candidates from %d raw candidates across %d batches (%d batches failed)",
        len(verified_candidates),
        len(candidate_list),
        len(batches),
        failed_batches,
    )
    return verified_candidates
