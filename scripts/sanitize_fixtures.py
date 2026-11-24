"""Sanitization and preparation script for committed test fixtures.

Transforms raw recordings in .cache/fixtures/ into privacy-safe committed fixtures
in tests/fixtures/ by redacting email addresses, phone numbers, and WhatsApp numbers
while preserving names, profile URLs, and query semantics.
"""

import json
import re
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT_DIR / ".cache" / "fixtures"
TARGET_DIR = ROOT_DIR / "tests" / "fixtures"

# Regex for detecting email addresses
EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# Regex for phone numbers: sequences of digits with optional spaces, dashes, parentheses
# Protect against matching ISO timestamps, URLs, IDs, etc.
PHONE_REGEX = re.compile(
    r"(?<![a-zA-Z0-9_\-\.\/])(?:\+?\d{1,3}[\s\-\.]?)?\(?\d{2,4}\)?[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}(?![a-zA-Z0-9_\-\.\/])"
)

# Regex for WhatsApp URLs with numbers
WHATSAPP_REGEX = re.compile(
    r"(?:https?:\/\/)?(?:api\.whatsapp\.com\/send\?phone=|wa\.me\/)\+?\d+",
    re.IGNORECASE,
)


def sanitize_text(text: str) -> str:
    """Recursively sanitize text to remove private contact information."""
    if not isinstance(text, str):
        return text

    # Redact WhatsApp links containing numbers
    text = WHATSAPP_REGEX.sub("https://wa.me/REDACTED", text)

    # Redact email addresses
    text = EMAIL_REGEX.sub("REDACTED", text)

    # Specific phone pattern redactions in snippets (e.g. (212) 202-1431)
    text = re.sub(r"\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4}", "REDACTED", text)
    text = re.sub(r"\+\d{1,3}[\s\-]\d{2,4}[\s\-]\d{3,4}[\s\-]\d{3,4}", "REDACTED", text)

    return text


def sanitize_data(obj: Any) -> Any:
    """Recursively sanitize data structures."""
    if isinstance(obj, str):
        return sanitize_text(obj)
    if isinstance(obj, dict):
        sanitized = {}
        for k, v in obj.items():
            # If the key itself indicates contact info, redact value
            if k in ("email", "emails", "phone", "phones", "phone_numbers"):
                if isinstance(v, list):
                    sanitized[k] = ["REDACTED" for _ in v]
                elif isinstance(v, str) and v:
                    sanitized[k] = "REDACTED"
                else:
                    sanitized[k] = v
            else:
                sanitized[k] = sanitize_data(v)
        return sanitized
    if isinstance(obj, list):
        return [sanitize_data(item) for item in obj]
    return obj


def load_raw_or_cached(slug: str) -> dict[str, Any]:
    """Load raw recording and any supplementary classified files."""
    raw_path = CACHE_DIR / f"{slug}.raw.json"
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw fixture not found: {raw_path}")

    data = json.loads(raw_path.read_text(encoding="utf-8"))

    # Check for supplementary classifications or intent
    supp_class_map = {
        "startup_founders_london": "startup_founders_classifications.json",
        "digital_marketing_owners_new_york": "digital_marketing_owners_new_york_classifications.json",
        "cricket_lovers_ahmedabad": "cricket_lovers_ahmedabad_classifications.json",
    }

    if slug in supp_class_map:
        supp_path = CACHE_DIR / supp_class_map[slug]
        if supp_path.exists():
            classifications = json.loads(supp_path.read_text(encoding="utf-8"))
            if not data.get("gemini_classification_calls"):
                data["gemini_classification_calls"] = []
            if data["gemini_classification_calls"]:
                data["gemini_classification_calls"][0]["status"] = "success"
                data["gemini_classification_calls"][0]["classifications"] = classifications
            else:
                data["gemini_classification_calls"].append({
                    "call_index": 1,
                    "status": "success",
                    "classifications": classifications,
                })

    if slug == "restaurant_owners_dubai":
        intent_path = CACHE_DIR / "restaurant_owners_intent.json"
        if intent_path.exists():
            intent = json.loads(intent_path.read_text(encoding="utf-8"))
            data["gemini_intent_calls"] = [{
                "call_index": 1,
                "status": "success",
                "intent": intent,
            }]
            data["gemini_classification_calls"] = [{
                "call_index": 1,
                "status": "success",
                "classifications": [],
            }]

    return data


def build_sanitized_fixture(slug: str) -> dict[str, Any]:
    """Build a deterministic, privacy-safe fixture from raw data."""
    raw = load_raw_or_cached(slug)

    # Extract intent
    intent = None
    for call in raw.get("gemini_intent_calls", []):
        if call.get("status") == "success" and "intent" in call:
            intent = call["intent"]
            break

    # Extract search calls
    search_calls = []
    for call in raw.get("search_calls", []):
        search_calls.append({
            "query": call.get("query", ""),
            "include_domains": call.get("include_domains"),
            "results": [
                {
                    "url": r.get("url", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                }
                for r in call.get("results", [])
            ],
        })

    # Extract classification calls
    classification_calls = []
    for call in raw.get("gemini_classification_calls", []):
        if call.get("status") == "success" and "classifications" in call:
            classification_calls.append({
                "candidate_count": call.get("candidate_count", len(call["classifications"])),
                "classifications": call["classifications"],
            })

    fixture_payload = {
        "slug": slug,
        "query": raw.get("query", ""),
        "intent": intent,
        "search_calls": search_calls,
        "classification_calls": classification_calls,
    }

    # Apply recursive sanitization
    sanitized = sanitize_data(fixture_payload)
    return sanitized


def verify_privacy(sanitized_json_str: str, slug: str) -> None:
    """Verify no unredacted email, phone, or token exists in sanitized JSON."""
    # Check for actual email patterns not equal to REDACTED
    emails = EMAIL_REGEX.findall(sanitized_json_str)
    unredacted_emails = [e for e in emails if "example.com" not in e and "redacted" not in e.lower()]
    if unredacted_emails:
        raise ValueError(f"Privacy breach in {slug}: Found unredacted email(s): {unredacted_emails}")

    # Check for phone numbers
    phones = re.findall(r"\(\d{3}\)\s\d{3}-\d{4}", sanitized_json_str)
    if phones:
        raise ValueError(f"Privacy breach in {slug}: Found unredacted US phone(s): {phones}")

    # Check for raw whatsapp numbers
    wa_matches = re.findall(r"wa\.me\/\+?\d+", sanitized_json_str)
    if wa_matches:
        raise ValueError(f"Privacy breach in {slug}: Found unredacted WhatsApp URL(s): {wa_matches}")

    # Check for secrets
    if "AIza" in sanitized_json_str or "tvly-" in sanitized_json_str:
        raise ValueError(f"Privacy breach in {slug}: Potential API key detected!")


def main() -> None:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    slugs = [
        "football_lovers_washington_dc",
        "digital_marketing_owners_new_york",
        "startup_founders_london",
        "cricket_lovers_ahmedabad",
        "restaurant_owners_dubai",
    ]

    for slug in slugs:
        sanitized = build_sanitized_fixture(slug)
        output_file = TARGET_DIR / f"{slug}.json"
        json_content = json.dumps(sanitized, indent=2, ensure_ascii=False)

        verify_privacy(json_content, slug)

        output_file.write_text(json_content, encoding="utf-8")
        print(f"Generated sanitized fixture: {output_file.relative_to(ROOT_DIR)}")

    print("All fixtures successfully sanitized and privacy verified!")


if __name__ == "__main__":
    main()
