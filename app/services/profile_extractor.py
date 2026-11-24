"""Contact detail extraction from candidate profile text with strict page ownership."""

import logging
import re
from urllib.parse import parse_qsl, urlsplit

from app.schemas import SocialLink
from app.schemas_internal import VerifiedCandidate
from app.utils.validators import validate_email, validate_phone

logger = logging.getLogger(__name__)

# Pattern to locate candidate email strings in snippet text
EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+"
)

# Pattern to find potential WhatsApp URLs in snippet text
WHATSAPP_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?(?:wa\.me|api\.whatsapp\.com)/[^\s,;\"'<>]+"
)

# Pattern for potential phone numbers in snippet text
PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,4}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}\b"
)


def _extract_valid_emails(text: str) -> list[str]:
    """Find and validate all email addresses in text.

    Args:
        text: Raw text string (title and snippet).

    Returns:
        List of normalized lowercase unique valid emails.
    """
    seen: set[str] = set()
    valid_emails: list[str] = []

    for match in EMAIL_PATTERN.findall(text):
        clean = validate_email(match)
        if clean and clean not in seen:
            seen.add(clean)
            valid_emails.append(clean)

    return valid_emails


def _extract_valid_whatsapp_links(text: str) -> list[str]:
    """Find, validate, and canonicalize WhatsApp links from text.

    Args:
        text: Raw text string (title and snippet).

    Returns:
        List of canonical WhatsApp URL strings (e.g. 'https://wa.me/14155552671').
    """
    seen: set[str] = set()
    valid_links: list[str] = []

    for match in WHATSAPP_URL_PATTERN.findall(text):
        url = match.strip().rstrip(".)],;")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            parsed = urlsplit(url)
        except ValueError:
            continue

        hostname = (parsed.hostname or "").lower()
        # Enforce exact allowed WhatsApp domains
        if hostname != "wa.me" and hostname != "api.whatsapp.com":
            continue

        digits = ""
        if hostname == "wa.me":
            # https://wa.me/<number>
            path_part = parsed.path.strip("/")
            digits = re.sub(r"\D", "", path_part)
        elif hostname == "api.whatsapp.com":
            # https://api.whatsapp.com/send?phone=<number>
            params = dict(parse_qsl(parsed.query))
            phone_val = params.get("phone", "")
            digits = re.sub(r"\D", "", phone_val)

        # Standard international phone number length between 7 and 15 digits
        if 7 <= len(digits) <= 15:
            canonical_wa = f"https://wa.me/{digits}"
            if canonical_wa not in seen:
                seen.add(canonical_wa)
                valid_links.append(canonical_wa)

    return valid_links


def _extract_valid_phones(text: str, default_region: str = "US") -> list[str]:
    """Find, validate, and format standalone phone numbers in text.

    Excludes digits embedded within URLs or email addresses.

    Args:
        text: Raw text string (title and snippet).
        default_region: Two-letter ISO region code to interpret national numbers.

    Returns:
        List of formatted E.164 phone numbers (e.g. '+14155552671').
    """
    # Strip URLs and emails so digits inside links (e.g. wa.me/14155552671) are not matched
    cleaned = WHATSAPP_URL_PATTERN.sub(" ", text)
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = EMAIL_PATTERN.sub(" ", cleaned)

    seen: set[str] = set()
    valid_phones: list[str] = []

    for match in PHONE_PATTERN.findall(cleaned):
        e164 = validate_phone(match, default_region=default_region)
        if e164 and e164 not in seen:
            seen.add(e164)
            valid_phones.append(e164)

    return valid_phones


def extract_page_scoped_contacts(candidate: VerifiedCandidate) -> list[SocialLink]:
    """Extract validated contacts found strictly on this candidate's own page.

    Contacts found on page A belong exclusively to page A and are never transferred
    or attached to another candidate.

    Args:
        candidate: VerifiedCandidate whose snippet and title are scanned.

    Returns:
        List of SocialLink objects for email, WhatsApp, and standalone phone numbers.
    """
    evidence_text = f"{candidate.raw_candidate.title} {candidate.raw_candidate.snippet}"
    contacts: list[SocialLink] = []
    seen_contacts: set[tuple[str, str]] = set()

    # 1. Emails
    for email in _extract_valid_emails(evidence_text):
        link = f"mailto:{email}"
        key = ("Email", link)
        if key not in seen_contacts:
            seen_contacts.add(key)
            contacts.append(SocialLink(platform="Email", link=link))

    # 2. WhatsApp links
    for wa_url in _extract_valid_whatsapp_links(evidence_text):
        key = ("WhatsApp", wa_url)
        if key not in seen_contacts:
            seen_contacts.add(key)
            contacts.append(SocialLink(platform="WhatsApp", link=wa_url))

    # 3. Standalone phone numbers (formatted as tel:<E.164>)
    for phone_e164 in _extract_valid_phones(evidence_text):
        link = f"tel:{phone_e164}"
        key = ("Phone", link)
        if key not in seen_contacts:
            seen_contacts.add(key)
            contacts.append(SocialLink(platform="Phone", link=link))

    return contacts


def enrich_candidate_contacts(candidates: list[VerifiedCandidate]) -> list[VerifiedCandidate]:
    """Extract and attach page-scoped contacts to each verified candidate.

    Guarantees strict page ownership: contact details are attached only to the candidate
    whose own canonical URL and evidence text contained them.

    Args:
        candidates: Sequence of VerifiedCandidate objects.

    Returns:
        Same sequence with candidate.contacts populated.
    """
    for cand in candidates:
        cand.contacts = extract_page_scoped_contacts(cand)

    return candidates
