"""Unit tests for prospect assembly service and public schema validation."""

from app.schemas import DiscoveryResponse, SocialLink
from app.schemas_internal import DeduplicatedProspect, RawCandidate, VerifiedCandidate
from app.services.prospect_service import assemble_discovery_response


def _make_candidate(
    platform: str,
    name: str,
    url: str,
    location: str | None = None,
    contacts: list[SocialLink] | None = None,
) -> VerifiedCandidate:
    return VerifiedCandidate(
        raw_candidate=RawCandidate(
            source_platform=platform,
            canonical_url=url,
            title=f"{name} Profile",
            snippet=f"{name} based in {location or 'unknown'}",
            search_query="test query",
        ),
        verified_name=name,
        source_platform=platform,
        canonical_url=url,
        location=location,
        confidence="high",
        reason="Verified profile.",
        contacts=contacts or [],
    )


def test_assemble_empty_prospects() -> None:
    """Verify empty input produces a valid DiscoveryResponse with total_prospects=0."""
    response = assemble_discovery_response("quantum computing researchers", [])

    assert isinstance(response, DiscoveryResponse)
    assert response.success is True
    assert response.query == "quantum computing researchers"
    assert response.total_prospects == 0
    assert response.prospects == []


def test_assemble_single_prospect_with_contacts_and_casing() -> None:
    """Verify verbatim name casing, location, profile link, and contacts are preserved."""
    cand = _make_candidate(
        platform="LinkedIn",
        name="Dr. Jane Smith-O'Connor",
        url="https://linkedin.com/in/jane-smith",
        location="San Francisco, CA",
        contacts=[
            SocialLink(platform="Email", link="mailto:jane@stanford.edu"),
            SocialLink(platform="WhatsApp", link="https://wa.me/14155552671"),
            SocialLink(platform="Phone", link="tel:+14155552671"),
        ],
    )
    group = DeduplicatedProspect(
        primary_name="Dr. Jane Smith-O'Connor",
        location="San Francisco, CA",
        verified_candidates=[cand],
    )

    response = assemble_discovery_response("ai researchers", [group])

    assert response.total_prospects == 1
    assert len(response.prospects) == 1

    prospect = response.prospects[0]
    # Exact casing preserved
    assert prospect.name == "Dr. Jane Smith-O'Connor"
    assert prospect.location == "San Francisco, CA"

    # Social links sorted by platform: Email, LinkedIn, Phone, WhatsApp
    platforms = [sl.platform for sl in prospect.social_link]
    assert platforms == ["Email", "LinkedIn", "Phone", "WhatsApp"]

    links_dict = {sl.platform: sl.link for sl in prospect.social_link}
    assert links_dict["Email"] == "mailto:jane@stanford.edu"
    assert links_dict["LinkedIn"] == "https://linkedin.com/in/jane-smith"
    assert links_dict["Phone"] == "tel:+14155552671"
    assert links_dict["WhatsApp"] == "https://wa.me/14155552671"


def test_assemble_omit_location_when_missing() -> None:
    """Verify location is None when candidate group has no location evidence."""
    cand = _make_candidate(
        platform="X",
        name="Alex River",
        url="https://x.com/ariver",
        location=None,
    )
    group = DeduplicatedProspect(
        primary_name="Alex River",
        location=None,
        verified_candidates=[cand],
    )

    response = assemble_discovery_response("developers", [group])
    assert response.prospects[0].location is None


def test_assemble_social_link_deduplication_and_sorting() -> None:
    """Verify duplicate profile links and contacts across candidates in a group are deduplicated."""
    cand_li = _make_candidate(
        platform="LinkedIn",
        name="Bob Builder",
        url="https://linkedin.com/in/bob-builder",
        location="London",
        contacts=[SocialLink(platform="Email", link="mailto:bob@build.co.uk")],
    )
    cand_x = _make_candidate(
        platform="X",
        name="Bob Builder",
        url="https://x.com/bob_builder",
        location="London",
        contacts=[
            # Duplicate email with different platform casing
            SocialLink(platform="email", link="mailto:bob@build.co.uk"),
        ],
    )
    group = DeduplicatedProspect(
        primary_name="Bob Builder",
        location="London",
        verified_candidates=[cand_li, cand_x],
    )

    response = assemble_discovery_response("construction experts", [group])
    prospect = response.prospects[0]

    # Email must appear only once
    email_links = [sl for sl in prospect.social_link if sl.platform.lower() == "email"]
    assert len(email_links) == 1
    assert email_links[0].link == "mailto:bob@build.co.uk"

    # Total 3 links: Email, LinkedIn, X
    assert len(prospect.social_link) == 3
    assert [sl.platform for sl in prospect.social_link] == ["Email", "LinkedIn", "X"]


def test_assemble_prospect_deterministic_sorting() -> None:
    """Verify prospects are sorted deterministically by primary_name (case-insensitive) and link."""
    group_c = DeduplicatedProspect(
        primary_name="Charlie Davis",
        location="Austin",
        verified_candidates=[_make_candidate("X", "Charlie Davis", "https://x.com/cdavis")],
    )
    group_a = DeduplicatedProspect(
        primary_name="alice Adams",
        location="Boston",
        verified_candidates=[_make_candidate("LinkedIn", "alice Adams", "https://linkedin.com/in/alice")],
    )
    group_b = DeduplicatedProspect(
        primary_name="Bob Brown",
        location="Chicago",
        verified_candidates=[_make_candidate("YouTube", "Bob Brown", "https://youtube.com/@bobbrown")],
    )

    response = assemble_discovery_response("founders", [group_c, group_a, group_b])
    names = [p.name for p in response.prospects]
    # alice Adams, Bob Brown, Charlie Davis
    assert names == ["alice Adams", "Bob Brown", "Charlie Davis"]


def test_assemble_public_schema_cleanliness_no_leaks() -> None:
    """CRITICAL: Verify serialized response strictly adheres to DiscoveryResponse schema without internal metadata."""
    cand = _make_candidate(
        platform="LinkedIn",
        name="Elena Rostova",
        url="https://linkedin.com/in/elena-rostova",
        location="Zurich",
        contacts=[SocialLink(platform="Email", link="mailto:elena@ethz.ch")],
    )
    group = DeduplicatedProspect(
        primary_name="Elena Rostova",
        location="Zurich",
        verified_candidates=[cand],
    )

    response = assemble_discovery_response("robotics researchers", [group])
    dumped = response.model_dump()

    # Must only contain the public fields
    assert set(dumped.keys()) == {"success", "query", "total_prospects", "prospects"}

    prospect_dumped = dumped["prospects"][0]
    assert set(prospect_dumped.keys()) == {"name", "location", "social_link"}

    for link_dumped in prospect_dumped["social_link"]:
        assert set(link_dumped.keys()) == {"platform", "link"}

    # Confirm json serialization has no internal fields
    json_str = response.model_dump_json()
    assert "confidence" not in json_str
    assert "reason" not in json_str
    assert "candidate_index" not in json_str
    assert "raw_candidate" not in json_str
    assert "snippet" not in json_str
