"""Conservative, deterministic deduplication and cross-platform identity resolution."""

import logging
import re
from collections.abc import Sequence

from app.schemas_internal import DeduplicatedProspect, VerifiedCandidate
from app.utils.normalizers import canonical_url, extract_handle, normalize_name

logger = logging.getLogger(__name__)

URL_EXTRACT_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:[a-zA-Z0-9_\-\.]+\.[a-zA-Z]{2,})/[^\s,;\"'<>]+"
)


def _extract_canonical_urls_from_text(text: str) -> set[str]:
    """Find all potential profile URLs in evidence text and normalize them to canonical form."""
    found: set[str] = set()
    for match in URL_EXTRACT_PATTERN.findall(text):
        link = match.strip().rstrip(".)],;")
        if not link.startswith(("http://", "https://")):
            link = "https://" + link
        canon = canonical_url(link)
        if canon:
            found.add(canon.lower())
    return found


def _explicit_cross_profile_link(cand_a: VerifiedCandidate, cand_b: VerifiedCandidate) -> bool:
    """Check if either candidate's page text explicitly links to the other's verified profile URL.

    Rule A requirements:
    1. Platforms must be different.
    2. Normalized names must match (links to different people are never identity proofs).
    3. Non-empty locations must not conflict.
    4. Exact canonical profile URL of one candidate must appear in the other's evidence text.

    Args:
        cand_a: First verified candidate.
        cand_b: Second verified candidate.

    Returns:
        True if an explicit cross-profile link exists in evidence; False otherwise.
    """
    if cand_a.source_platform.lower() == cand_b.source_platform.lower():
        return False

    name_a = normalize_name(cand_a.verified_name)
    name_b = normalize_name(cand_b.verified_name)
    if not name_a or not name_b or name_a != name_b:
        return False

    if cand_a.location and cand_b.location:
        loc_a = normalize_name(cand_a.location)
        loc_b = normalize_name(cand_b.location)
        if loc_a != loc_b:
            return False

    urls_in_a = _extract_canonical_urls_from_text(
        f"{cand_a.raw_candidate.title} {cand_a.raw_candidate.snippet}"
    )
    urls_in_b = _extract_canonical_urls_from_text(
        f"{cand_b.raw_candidate.title} {cand_b.raw_candidate.snippet}"
    )

    url_a = cand_a.canonical_url.lower()
    url_b = cand_b.canonical_url.lower()

    return (url_b in urls_in_a) or (url_a in urls_in_b)


def _strong_identity_match(cand_a: VerifiedCandidate, cand_b: VerifiedCandidate) -> bool:
    """Check if two candidates on different platforms meet Rule B for identity merging.

    Rule B requirements (ALL must hold):
    1. Platforms must be different.
    2. Normalized handle must be non-empty and identical on both platforms.
    3. Normalized names must match.
    4. Locations must both be non-empty and match.

    Args:
        cand_a: First verified candidate.
        cand_b: Second verified candidate.

    Returns:
        True if Rule B is completely satisfied; False otherwise.
    """
    # Rule B is for cross-platform matching
    if cand_a.source_platform.lower() == cand_b.source_platform.lower():
        return False

    handle_a = extract_handle(cand_a.canonical_url, cand_a.source_platform)
    handle_b = extract_handle(cand_b.canonical_url, cand_b.source_platform)

    # 1. Matching non-empty handle
    if not handle_a or not handle_b or handle_a != handle_b:
        return False

    # 2. Matching normalized name
    name_a = normalize_name(cand_a.verified_name)
    name_b = normalize_name(cand_b.verified_name)
    if not name_a or not name_b or name_a != name_b:
        return False

    # 3. Matching non-empty location (missing location strictly prevents Rule B merge)
    if not cand_a.location or not cand_b.location:
        return False

    loc_a = normalize_name(cand_a.location)
    loc_b = normalize_name(cand_b.location)
    return bool(loc_a and loc_b and loc_a == loc_b)


def _can_unify_candidate_sets(
    set_a: Sequence[VerifiedCandidate],
    set_b: Sequence[VerifiedCandidate],
) -> bool:
    """Verify that merging two candidate groups will not introduce conflicting identity evidence.

    Guarantees:
    1. Name consistency: All candidates across both groups have compatible normalized names.
    2. Location consistency: Candidates with non-empty locations must not have conflicting locations.
    3. Platform uniqueness: A single individual cannot have two distinct canonical profile URLs
       on the same platform.

    Args:
        set_a: First candidate set.
        set_b: Second candidate set.

    Returns:
        True if the sets can be safely unified; False if any conflict is detected.
    """
    all_candidates = list(set_a) + list(set_b)

    # 1. Name consistency: all candidates must share the same normalized name
    names = {normalize_name(c.verified_name) for c in all_candidates if c.verified_name}
    if len(names) > 1:
        return False

    # 2. Location consistency: any non-empty locations must match
    locations = {
        normalize_name(c.location)
        for c in all_candidates
        if c.location and c.location.strip()
    }
    if len(locations) > 1:
        return False

    # 3. Platform uniqueness: no two different canonical URLs on the same platform
    platform_urls: dict[str, str] = {}
    for c in all_candidates:
        plat = c.source_platform.lower()
        canon_url = c.canonical_url.lower()
        if plat in platform_urls and platform_urls[plat] != canon_url:
            return False
        platform_urls[plat] = canon_url

    return True


def deduplicate_candidates(
    candidates: Sequence[VerifiedCandidate],
) -> list[DeduplicatedProspect]:
    """Group duplicate canonical URLs and merge cross-platform identities conservatively.

    Deduplication executes in two deterministic phases:
    1. Group candidates with identical canonical profile URLs.
    2. Merge distinct platform profiles only when Rule A (explicit verified link) or
       Rule B (matching handle + matching name + matching location) is satisfied,
       verifying that the union creates no conflicting names, locations, or duplicate platforms.

    Args:
        candidates: Sequence of verified candidates with page-scoped contacts.

    Returns:
        List of DeduplicatedProspect objects in deterministic order.
    """
    if not candidates:
        return []

    # Phase 1: Canonical URL grouping
    url_groups: dict[str, list[VerifiedCandidate]] = {}
    for cand in candidates:
        url = cand.canonical_url
        if url not in url_groups:
            url_groups[url] = []
        url_groups[url].append(cand)

    # Build initial URL-level prospect records, sorted deterministically by canonical URL
    initial_prospects: list[DeduplicatedProspect] = []
    for canon_url in sorted(url_groups.keys()):
        group_cands = url_groups[canon_url]
        primary_name = group_cands[0].verified_name
        loc = next((c.location for c in group_cands if c.location), None)

        reasons: list[str] = []
        if len(group_cands) > 1:
            reasons.append(f"Canonical URL duplicate grouping ({canon_url})")

        initial_prospects.append(
            DeduplicatedProspect(
                primary_name=primary_name,
                location=loc,
                verified_candidates=group_cands,
                merge_reasons=reasons,
            )
        )

    # Phase 2: Cross-platform identity merging using Disjoint Set Union (Union-Find)
    n = len(initial_prospects)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            # Deterministic: smaller index becomes parent
            if root_i < root_j:
                parent[root_j] = root_i
            else:
                parent[root_i] = root_j

    merge_reasons_map: dict[tuple[int, int], str] = {}

    for i in range(n):
        for j in range(i + 1, n):
            root_i = find(i)
            root_j = find(j)
            if root_i == root_j:
                continue

            p_a = initial_prospects[i]
            p_b = initial_prospects[j]

            # Check all pairwise candidate relationships between groups
            matched = False
            reason = ""

            for cand_a in p_a.verified_candidates:
                for cand_b in p_b.verified_candidates:
                    if _explicit_cross_profile_link(cand_a, cand_b):
                        matched = True
                        reason = (
                            f"Rule A: Explicit verified link between {cand_a.canonical_url} "
                            f"and {cand_b.canonical_url}"
                        )
                        break
                    if _strong_identity_match(cand_a, cand_b):
                        matched = True
                        h = extract_handle(cand_a.canonical_url, cand_a.source_platform)
                        reason = (
                            f"Rule B: Matching handle '{h}', name '{cand_a.verified_name}', "
                            f"and location '{cand_a.location}' across platforms"
                        )
                        break
                if matched:
                    break

            if matched:
                # Transitive merge safety check: verify the proposed union has no conflicting identity evidence
                cands_in_i = [
                    c
                    for idx in range(n)
                    if find(idx) == root_i
                    for c in initial_prospects[idx].verified_candidates
                ]
                cands_in_j = [
                    c
                    for idx in range(n)
                    if find(idx) == root_j
                    for c in initial_prospects[idx].verified_candidates
                ]

                if _can_unify_candidate_sets(cands_in_i, cands_in_j):
                    union(i, j)
                    merge_reasons_map[(min(i, j), max(i, j))] = reason
                else:
                    logger.info(
                        "Rejecting merge between candidate groups %d and %d due to conflicting group identity evidence",
                        i,
                        j,
                    )

    # Assemble components deterministically
    clusters: dict[int, list[int]] = {}
    for idx in range(n):
        root = find(idx)
        if root not in clusters:
            clusters[root] = []
        clusters[root].append(idx)

    deduped_results: list[DeduplicatedProspect] = []

    for root in sorted(clusters.keys()):
        member_indices = clusters[root]
        first_prospect = initial_prospects[member_indices[0]]

        all_candidates: list[VerifiedCandidate] = []
        all_reasons: list[str] = list(first_prospect.merge_reasons)
        resolved_location = first_prospect.location

        for idx in member_indices:
            p = initial_prospects[idx]
            all_candidates.extend(p.verified_candidates)
            if not resolved_location and p.location:
                resolved_location = p.location
            if idx != member_indices[0]:
                pair_key = (min(member_indices[0], idx), max(member_indices[0], idx))
                if pair_key in merge_reasons_map:
                    all_reasons.append(merge_reasons_map[pair_key])

        # Sort candidates deterministically by platform name then canonical URL
        all_candidates.sort(key=lambda c: (c.source_platform, c.canonical_url))

        deduped_results.append(
            DeduplicatedProspect(
                primary_name=first_prospect.primary_name,
                location=resolved_location,
                verified_candidates=all_candidates,
                merge_reasons=all_reasons,
            )
        )

    # Sort final prospects deterministically by primary name then first canonical URL
    deduped_results.sort(
        key=lambda p: (
            p.primary_name.lower(),
            p.verified_candidates[0].canonical_url if p.verified_candidates else "",
        )
    )

    logger.info(
        "Deduplication complete: %d initial candidate records resolved to %d distinct prospects",
        len(candidates),
        len(deduped_results),
    )
    return deduped_results

