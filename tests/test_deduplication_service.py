"""Unit tests for conservative, deterministic candidate deduplication."""

from app.schemas import SocialLink
from app.schemas_internal import RawCandidate, VerifiedCandidate
from app.services.deduplication_service import deduplicate_candidates


def _make_candidate(
    platform: str,
    url: str,
    name: str,
    location: str | None = None,
    snippet: str = "",
    contacts: list[SocialLink] | None = None,
) -> VerifiedCandidate:
    """Helper to construct verified candidate instances."""
    raw = RawCandidate(
        source_platform=platform,
        canonical_url=url,
        title=f"{name} on {platform}",
        snippet=snippet or f"{name} profile located in {location or 'Unknown'}.",
        search_query="query",
    )
    return VerifiedCandidate(
        raw_candidate=raw,
        verified_name=name,
        source_platform=platform,
        canonical_url=url,
        location=location,
        confidence="high",
        reason="Verified profile.",
        contacts=contacts or [],
    )


def test_rule_b_cross_platform_merge_same_person() -> None:
    """Verify Rule B merges same person across two platforms when handle, name, and location match."""
    # X and LinkedIn for "satyanadella" in "Redmond, WA"
    c_x = _make_candidate(
        platform="X",
        url="https://x.com/satyanadella",
        name="Satya Nadella",
        location="Redmond, WA",
    )
    c_li = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/satyanadella",
        name="Satya Nadella",
        location="Redmond, WA",
    )

    prospects = deduplicate_candidates([c_x, c_li])
    assert len(prospects) == 1
    assert prospects[0].primary_name == "Satya Nadella"
    assert len(prospects[0].verified_candidates) == 2
    platforms = {c.source_platform for c in prospects[0].verified_candidates}
    assert platforms == {"LinkedIn", "X"}


def test_prohibit_merge_same_name_different_cities() -> None:
    """Verify two people with the same name in different cities stay separate."""
    c_ny = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/michael-johnson-ny",
        name="Michael Johnson",
        location="New York, NY",
    )
    c_la = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/michael-johnson-la",
        name="Michael Johnson",
        location="Los Angeles, CA",
    )

    prospects = deduplicate_candidates([c_ny, c_la])
    assert len(prospects) == 2
    names = [p.primary_name for p in prospects]
    assert names == ["Michael Johnson", "Michael Johnson"]
    locs = {p.location for p in prospects}
    assert locs == {"New York, NY", "Los Angeles, CA"}


def test_prohibit_merge_same_name_different_handles() -> None:
    """Verify people with the same name but different handles do not merge."""
    c_x = _make_candidate(
        platform="X",
        url="https://x.com/mike_j123",
        name="Michael Johnson",
        location="Chicago, IL",
    )
    c_li = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/michael-j-456",
        name="Michael Johnson",
        location="Chicago, IL",
    )

    prospects = deduplicate_candidates([c_x, c_li])
    assert len(prospects) == 2


def test_prohibit_merge_same_name_and_handle_missing_location() -> None:
    """Verify that missing location prevents Rule B merge even if handle and name match."""
    c_x = _make_candidate(
        platform="X",
        url="https://x.com/alexsmith",
        name="Alex Smith",
        location=None,  # Missing location!
    )
    c_li = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/alexsmith",
        name="Alex Smith",
        location="Seattle, WA",
    )

    prospects = deduplicate_candidates([c_x, c_li])
    assert len(prospects) == 2


def test_rule_a_explicit_cross_profile_link_merges_verified() -> None:
    """Verify Rule A merges candidates when one page explicitly links to another verified candidate."""
    # Profile A snippet explicitly links to Profile B's canonical URL
    c_li = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/jane-custom-slug",
        name="Jane Doe",
        location="Austin, TX",
        snippet="Jane Doe's tech blog and Twitter: https://x.com/janedoe_austin",
    )
    c_x = _make_candidate(
        platform="X",
        url="https://x.com/janedoe_austin",
        name="Jane Doe",
        location="Austin, TX",
    )

    prospects = deduplicate_candidates([c_li, c_x])
    assert len(prospects) == 1
    assert len(prospects[0].verified_candidates) == 2
    assert any("Rule A" in r for r in prospects[0].merge_reasons)


def test_rule_a_unverified_linked_url_does_not_merge() -> None:
    """Verify an explicit link to an unverified URL does not create a fake merge."""
    # Profile A links to an external Twitter URL, but that Twitter URL was never discovered/verified
    c_li = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/solo-dev",
        name="Solo Dev",
        location="Boston, MA",
        snippet="Follow me on https://x.com/unverified_user",
    )

    prospects = deduplicate_candidates([c_li])
    assert len(prospects) == 1
    assert len(prospects[0].verified_candidates) == 1


def test_canonical_url_duplicate_grouping() -> None:
    """Verify multiple candidates with identical canonical URLs are grouped into one prospect."""
    c1 = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/sam-altman",
        name="Sam Altman",
        location="San Francisco, CA",
        contacts=[SocialLink(platform="Email", link="mailto:sam@openai.com")],
    )
    c2 = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/sam-altman",
        name="Sam Altman",
        location="San Francisco, CA",
        contacts=[SocialLink(platform="Phone", link="tel:+14155552671")],
    )

    prospects = deduplicate_candidates([c1, c2])
    assert len(prospects) == 1
    assert len(prospects[0].verified_candidates) == 2
    assert any("Canonical URL" in r for r in prospects[0].merge_reasons)


def test_deterministic_merge_regardless_of_order() -> None:
    """Verify that candidate input order does not alter the deduplicated outcome."""
    c_li = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/demishassabis",
        name="Demis Hassabis",
        location="London, UK",
    )
    c_x = _make_candidate(
        platform="X",
        url="https://x.com/demishassabis",
        name="Demis Hassabis",
        location="London, UK",
    )

    prospects_order_1 = deduplicate_candidates([c_li, c_x])
    prospects_order_2 = deduplicate_candidates([c_x, c_li])

    assert len(prospects_order_1) == 1
    assert len(prospects_order_2) == 1
    assert prospects_order_1[0].primary_name == prospects_order_2[0].primary_name
    assert (
        prospects_order_1[0].verified_candidates[0].canonical_url
        == prospects_order_2[0].verified_candidates[0].canonical_url
    )


def test_reject_transitive_merge_conflicting_locations() -> None:
    """CRITICAL: Transitive chain A-B-C with conflicting locations must not merge A and C."""
    # Cand A: Boston, LinkedIn
    c_a = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/alice-smith",
        name="Alice Smith",
        location="Boston, MA",
        snippet="Alice Smith tech lead. Check my Twitter: https://x.com/alicesmith",
    )
    # Cand B: No location, X (links to A and also mentions C's URL)
    c_b = _make_candidate(
        platform="X",
        url="https://x.com/alicesmith",
        name="Alice Smith",
        location=None,
        snippet="Alice Smith profile. Check my YouTube: https://youtube.com/@alicesmith_la",
    )
    # Cand C: Los Angeles, YouTube
    c_c = _make_candidate(
        platform="YouTube",
        url="https://youtube.com/@alicesmith_la",
        name="Alice Smith",
        location="Los Angeles, CA",
        snippet="Alice Smith in Los Angeles. Video creator.",
    )

    # A and B can merge (Boston + None), but uniting {A, B} with C would introduce conflicting locations!
    prospects = deduplicate_candidates([c_a, c_b, c_c])

    # Must produce 2 separate prospects, not 1!
    assert len(prospects) == 2

    # Group 1: Alice Smith in Boston (contains A and B)
    boston_prospect = next(p for p in prospects if p.location == "Boston, MA")
    assert len(boston_prospect.verified_candidates) == 2
    boston_platforms = {c.source_platform for c in boston_prospect.verified_candidates}
    assert boston_platforms == {"LinkedIn", "X"}

    # Group 2: Alice Smith in Los Angeles (contains C)
    la_prospect = next(p for p in prospects if p.location == "Los Angeles, CA")
    assert len(la_prospect.verified_candidates) == 1
    assert la_prospect.verified_candidates[0].source_platform == "YouTube"


def test_reject_transitive_merge_conflicting_names() -> None:
    """CRITICAL: A link from person A to person B must never merge two different people."""
    c_a = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/alice-smith",
        name="Alice Smith",
        location="Boston, MA",
        snippet="Alice Smith in Boston. Great collaboration with https://x.com/bobjones_sf",
    )
    c_b = _make_candidate(
        platform="X",
        url="https://x.com/bobjones_sf",
        name="Bob Jones",
        location="Boston, MA",
        snippet="Bob Jones tech insights.",
    )

    prospects = deduplicate_candidates([c_a, c_b])
    # Alice and Bob must remain separate prospects!
    assert len(prospects) == 2
    names = {p.primary_name for p in prospects}
    assert names == {"Alice Smith", "Bob Jones"}


def test_reject_merge_duplicate_platform_with_different_urls() -> None:
    """CRITICAL: An individual cannot have multiple different canonical URLs on the same platform."""
    c_li_1 = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/alice-primary",
        name="Alice Smith",
        location="Boston, MA",
        snippet="Alice Smith. Also on https://x.com/alicesmith",
    )
    c_x = _make_candidate(
        platform="X",
        url="https://x.com/alicesmith",
        name="Alice Smith",
        location="Boston, MA",
        snippet="Alice Smith. Secondary page: https://linkedin.com/in/alice-secondary",
    )
    c_li_2 = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/alice-secondary",
        name="Alice Smith",
        location="Boston, MA",
    )

    prospects = deduplicate_candidates([c_li_1, c_x, c_li_2])
    # {c_li_1, c_x} merge, but c_li_2 cannot merge into the same prospect because LinkedIn is already taken by c_li_1
    assert len(prospects) == 2


def test_avoid_url_substring_collision() -> None:
    """Verify that a URL that is a prefix/substring of another URL does not cause a false merge."""
    # Cand A links to https://x.com/alicesmith123 (a different person)
    c_a = _make_candidate(
        platform="LinkedIn",
        url="https://linkedin.com/in/alice-smith",
        name="Alice Smith",
        location="Boston, MA",
        snippet="Connect on https://x.com/alicesmith123",
    )
    # Cand B has handle "alicesmith", NOT "alicesmith123"
    c_b = _make_candidate(
        platform="X",
        url="https://x.com/alicesmith",
        name="Alice Smith",
        location="Boston, MA",
        snippet="Alice Smith on X.",
    )

    prospects = deduplicate_candidates([c_a, c_b])
    # Must NOT merge because the URL in evidence is alicesmith123, not alicesmith!
    assert len(prospects) == 2

