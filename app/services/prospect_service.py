"""Assembly and validation service for final public discovery responses."""

import logging
from collections.abc import Sequence

from app.schemas import DiscoveryResponse, Prospect, SocialLink
from app.schemas_internal import DeduplicatedProspect

logger = logging.getLogger(__name__)


def assemble_discovery_response(
    query: str,
    prospect_groups: Sequence[DeduplicatedProspect],
) -> DiscoveryResponse:
    """Transform internal deduplicated prospect groups into a validated public DiscoveryResponse.

    Performs deterministic ordering, contact assembly, social link deduplication,
    and schema validation. Guarantees that internal pipeline artifacts are never
    leaked to the public response.

    Args:
        query: Original search query.
        prospect_groups: Deduplicated and identity-clustered candidate groups.

    Returns:
        Validated DiscoveryResponse object conforming strictly to the public API schema.
    """
    prospects: list[Prospect] = []

    for group in prospect_groups:
        # 1. Primary Name: preserve original verbatim casing
        name = group.primary_name.strip()
        if not name:
            # Fallback to first non-empty verified candidate name if primary_name was blank
            for cand in group.verified_candidates:
                if cand.verified_name.strip():
                    name = cand.verified_name.strip()
                    break

        if not name:
            logger.warning("Skipping prospect group with completely empty name.")
            continue

        # 2. Location: omit (None) if missing or whitespace-only
        location: str | None = None
        if group.location and group.location.strip():
            location = group.location.strip()

        # 3. Social Links: profile URLs + verified page-scoped contacts
        raw_links: list[SocialLink] = []
        for cand in group.verified_candidates:
            # Candidate profile link
            if cand.canonical_url and cand.source_platform:
                raw_links.append(
                    SocialLink(
                        platform=cand.source_platform,
                        link=cand.canonical_url,
                    )
                )
            # Page-scoped verified contacts (Email, WhatsApp, Phone)
            raw_links.extend(cand.contacts)

        # Deduplicate social links by (platform.lower(), link)
        seen_links: set[tuple[str, str]] = set()
        deduped_links: list[SocialLink] = []
        for sl in raw_links:
            key = (sl.platform.strip().lower(), sl.link.strip())
            if key not in seen_links:
                seen_links.add(key)
                deduped_links.append(
                    SocialLink(
                        platform=sl.platform.strip(),
                        link=sl.link.strip(),
                    )
                )

        # Deterministic sorting of social links: alphabetical by platform, breaking ties by link
        sorted_links = sorted(
            deduped_links,
            key=lambda item: (item.platform.lower(), item.link),
        )

        prospects.append(
            Prospect(
                name=name,
                location=location,
                social_link=sorted_links,
            )
        )

    # Deterministic result ordering: primary_name ascending (case-insensitive),
    # breaking ties by the first social link URL
    sorted_prospects = sorted(
        prospects,
        key=lambda p: (
            p.name.lower(),
            p.social_link[0].link if p.social_link else "",
        ),
    )

    total = len(sorted_prospects)
    # Validate invariant
    if len(sorted_prospects) != total:
        msg = f"Invariant violation: len(prospects)={len(sorted_prospects)} != total={total}"
        raise ValueError(msg)

    response = DiscoveryResponse(
        success=True,
        query=query,
        total_prospects=total,
        prospects=sorted_prospects,
    )

    logger.info(
        "Assembled discovery response for query %r: %d prospects resolved.",
        query,
        total,
    )
    return response
