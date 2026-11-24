"""Unit tests for contact extraction and strict page ownership guarantees."""

from app.schemas_internal import RawCandidate, VerifiedCandidate
from app.services.profile_extractor import (
    enrich_candidate_contacts,
    extract_page_scoped_contacts,
)


def _make_verified_candidate(idx: int, title: str, snippet: str) -> VerifiedCandidate:
    """Helper to build sample VerifiedCandidate objects."""
    raw = RawCandidate(
        source_platform="LinkedIn",
        canonical_url=f"https://linkedin.com/in/person-{idx}",
        title=title,
        snippet=snippet,
        search_query="query",
    )
    return VerifiedCandidate(
        raw_candidate=raw,
        verified_name=f"Person {idx}",
        source_platform="LinkedIn",
        canonical_url=f"https://linkedin.com/in/person-{idx}",
        location="San Francisco",
        confidence="high",
        reason="Verified profile.",
        contacts=[],
    )


def test_extract_valid_email() -> None:
    """Verify legitimate email addresses are extracted and formatted as mailto links."""
    cand = _make_verified_candidate(
        1,
        title="Dr. John Doe",
        snippet="Contact Dr. John Doe at john.doe@ai-biotech.org for collaboration.",
    )
    contacts = extract_page_scoped_contacts(cand)

    assert len(contacts) == 1
    assert contacts[0].platform == "Email"
    assert contacts[0].link == "mailto:john.doe@ai-biotech.org"


def test_reject_placeholder_and_malformed_emails() -> None:
    """Verify placeholder domains and invalid email formats are not extracted."""
    cand = _make_verified_candidate(
        1,
        title="John Doe",
        snippet="Reach me at user@example.com, test@test.com, or user@domain.com.",
    )
    contacts = extract_page_scoped_contacts(cand)
    assert len(contacts) == 0


def test_extract_valid_whatsapp_links() -> None:
    """Verify valid WhatsApp URLs (wa.me and api.whatsapp.com) are extracted and canonicalized."""
    cand = _make_verified_candidate(
        1,
        title="Jane Smith",
        snippet="Chat on WhatsApp at https://wa.me/14155552671 or api.whatsapp.com/send?phone=14155552671.",
    )
    contacts = extract_page_scoped_contacts(cand)

    # Both links point to the same phone number -> exactly 1 unique WhatsApp contact
    assert len(contacts) == 1
    assert contacts[0].platform == "WhatsApp"
    assert contacts[0].link == "https://wa.me/14155552671"


def test_reject_lookalike_and_invalid_whatsapp() -> None:
    """Verify lookalike domains and invalid WhatsApp URLs are rejected."""
    cand = _make_verified_candidate(
        1,
        title="Bob Smith",
        snippet="Visit https://wa.me.attacker.com/12345 or https://fake-whatsapp.com/send?phone=123.",
    )
    contacts = extract_page_scoped_contacts(cand)
    assert len(contacts) == 0


def test_deduplicate_multiple_identical_contacts() -> None:
    """Verify duplicate mentions of the same contact on a page produce a single SocialLink."""
    cand = _make_verified_candidate(
        1,
        title="Alice",
        snippet="Email alice@lab.org. Inquiries to ALICE@LAB.ORG. WhatsApp wa.me/14155552671.",
    )
    contacts = extract_page_scoped_contacts(cand)

    assert len(contacts) == 2
    platforms = [c.platform for c in contacts]
    assert "Email" in platforms
    assert "WhatsApp" in platforms
    email_contact = next(c for c in contacts if c.platform == "Email")
    assert email_contact.link == "mailto:alice@lab.org"


def test_strict_page_ownership_isolation() -> None:
    """CRITICAL: Verify contacts from page A are never attached to candidate B."""
    cand_a = _make_verified_candidate(
        1,
        title="Alice Johnson Profile A",
        snippet="Alice Johnson. Contact: alice@stanford.edu or wa.me/14155550001.",
    )
    cand_b = _make_verified_candidate(
        2,
        title="Alice Johnson Profile B",
        snippet="Alice Johnson is an AI Researcher in SF.",
    )

    enriched = enrich_candidate_contacts([cand_a, cand_b])

    # Candidate A must have its contacts
    assert len(enriched[0].contacts) == 2
    assert any(c.link == "mailto:alice@stanford.edu" for c in enriched[0].contacts)
    assert any(c.link == "https://wa.me/14155550001" for c in enriched[0].contacts)

    # Candidate B must have ZERO contacts because its own page contained none
    assert len(enriched[1].contacts) == 0


def test_strict_page_ownership_distinct_contacts_per_page() -> None:
    """Verify multiple candidates each retain only the contacts found on their respective pages."""
    cand_a = _make_verified_candidate(
        1,
        title="Founder One",
        snippet="Founder One: founder1@startup-one.io.",
    )
    cand_b = _make_verified_candidate(
        2,
        title="Founder Two",
        snippet="Founder Two: founder2@startup-two.io.",
    )

    enriched = enrich_candidate_contacts([cand_a, cand_b])

    assert len(enriched[0].contacts) == 1
    assert enriched[0].contacts[0].link == "mailto:founder1@startup-one.io"

    assert len(enriched[1].contacts) == 1
    assert enriched[1].contacts[0].link == "mailto:founder2@startup-two.io"
