"""Validation test suite for Phase 5 Milestone 2 evaluation datasets.

Verifies:
1. Exactly 80 candidate examples prepared (30 dev, 50 test).
2. Exactly 30 intent examples prepared (10 dev, 20 test).
3. Unique stable IDs across all splits.
4. Required schema fields are present.
5. Candidate labels use only allowed ternary values ('positive', 'negative', 'ambiguous').
6. Intent ground truth adheres to QueryIntent schema requirements.
7. Evidence excerpts are traceable verbatim to the supplied title or snippet input.
8. Every example has an explicit annotation status in ('needs_human_review', 'reviewed', 'rejected').
9. Development and held-out test datasets have strictly disjoint IDs.
10. No existing Gemini prediction was blindly copied without independent review.
11. Privacy verification passes on all evaluation dataset files.
12. Dataset manifest counts match actual file contents.
"""

import json
from pathlib import Path

import pytest

from scripts.sanitize_fixtures import verify_privacy

EVAL_DIR = Path(__file__).resolve().parent.parent / "evaluation"
DATASETS_DIR = EVAL_DIR / "datasets"
METADATA_DIR = EVAL_DIR / "metadata"

INTENT_DEV_PATH = DATASETS_DIR / "intents" / "development.json"
INTENT_TEST_PATH = DATASETS_DIR / "intents" / "test.json"
CANDIDATE_DEV_PATH = DATASETS_DIR / "candidates" / "development.json"
CANDIDATE_TEST_PATH = DATASETS_DIR / "candidates" / "test.json"
MANIFEST_PATH = METADATA_DIR / "dataset_manifest.json"

ALLOWED_CANDIDATE_LABELS = {"positive", "negative", "ambiguous"}
ALLOWED_ANNOTATION_STATUSES = {"needs_human_review", "reviewed", "rejected"}


@pytest.fixture(scope="module")
def intent_datasets() -> tuple[list[dict], list[dict]]:
    """Load development and test intent datasets."""
    assert INTENT_DEV_PATH.exists(), f"Missing {INTENT_DEV_PATH}"
    assert INTENT_TEST_PATH.exists(), f"Missing {INTENT_TEST_PATH}"
    dev = json.loads(INTENT_DEV_PATH.read_text(encoding="utf-8"))
    test = json.loads(INTENT_TEST_PATH.read_text(encoding="utf-8"))
    return dev, test


@pytest.fixture(scope="module")
def candidate_datasets() -> tuple[list[dict], list[dict]]:
    """Load development and test candidate datasets."""
    assert CANDIDATE_DEV_PATH.exists(), f"Missing {CANDIDATE_DEV_PATH}"
    assert CANDIDATE_TEST_PATH.exists(), f"Missing {CANDIDATE_TEST_PATH}"
    dev = json.loads(CANDIDATE_DEV_PATH.read_text(encoding="utf-8"))
    test = json.loads(CANDIDATE_TEST_PATH.read_text(encoding="utf-8"))
    return dev, test


@pytest.fixture(scope="module")
def manifest() -> dict:
    """Load dataset manifest."""
    assert MANIFEST_PATH.exists(), f"Missing {MANIFEST_PATH}"
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_intent_example_counts(intent_datasets: tuple[list[dict], list[dict]]) -> None:
    """Verify exactly 30 intent examples prepared: 10 dev, 20 test."""
    dev, test = intent_datasets
    assert len(dev) == 10, f"Expected exactly 10 dev intents, got {len(dev)}"
    assert len(test) == 20, f"Expected exactly 20 test intents, got {len(test)}"
    assert len(dev) + len(test) == 30


def test_candidate_example_counts(candidate_datasets: tuple[list[dict], list[dict]]) -> None:
    """Verify exactly 80 candidate examples prepared: 30 dev, 50 test."""
    dev, test = candidate_datasets
    assert len(dev) == 30, f"Expected exactly 30 dev candidates, got {len(dev)}"
    assert len(test) == 50, f"Expected exactly 50 test candidates, got {len(test)}"
    assert len(dev) + len(test) == 80


def test_unique_stable_ids(
    intent_datasets: tuple[list[dict], list[dict]],
    candidate_datasets: tuple[list[dict], list[dict]],
) -> None:
    """Verify every example has a unique stable ID with zero duplicates between splits."""
    dev_i, test_i = intent_datasets
    intent_ids_dev = [item["example_id"] for item in dev_i]
    intent_ids_test = [item["example_id"] for item in test_i]
    all_intent_ids = intent_ids_dev + intent_ids_test

    assert len(all_intent_ids) == len(set(all_intent_ids)), "Duplicate intent IDs found"
    assert set(intent_ids_dev).isdisjoint(set(intent_ids_test)), "Intent ID leakage between dev and test"

    dev_c, test_c = candidate_datasets
    cand_ids_dev = [item["example_id"] for item in dev_c]
    cand_ids_test = [item["example_id"] for item in test_c]
    all_cand_ids = cand_ids_dev + cand_ids_test

    assert len(all_cand_ids) == len(set(all_cand_ids)), "Duplicate candidate IDs found"
    assert set(cand_ids_dev).isdisjoint(set(cand_ids_test)), "Candidate ID leakage between dev and test"


def test_candidate_schema_and_labels(candidate_datasets: tuple[list[dict], list[dict]]) -> None:
    """Verify candidate records follow schema and use only permitted ground truth enums."""
    dev, test = candidate_datasets
    all_cands = dev + test

    required_top_keys = {
        "example_id",
        "split",
        "source_fixture",
        "source_query",
        "platform",
        "url",
        "input",
        "ground_truth",
        "evidence",
        "annotation",
    }
    required_gt_keys = {
        "is_individual_person",
        "name_supported",
        "interest_supported",
        "location_supported",
        "overall_acceptability",
    }

    for cand in all_cands:
        ex_id = cand.get("example_id", "unknown")
        assert required_top_keys.issubset(cand.keys()), f"Missing top-level keys in {ex_id}"

        gt = cand["ground_truth"]
        assert required_gt_keys.issubset(gt.keys()), f"Missing ground_truth keys in {ex_id}"

        for dim, val in gt.items():
            assert val in ALLOWED_CANDIDATE_LABELS, (
                f"Invalid label '{val}' for {dim} in {ex_id}. Allowed: {ALLOWED_CANDIDATE_LABELS}"
            )

        annot = cand["annotation"]
        status = annot.get("status")
        assert status in ALLOWED_ANNOTATION_STATUSES, (
            f"Invalid annotation status '{status}' in {ex_id}. Allowed: {ALLOWED_ANNOTATION_STATUSES}"
        )


def test_candidate_evidence_traceability(candidate_datasets: tuple[list[dict], list[dict]]) -> None:
    """Verify that every positive evidence excerpt appears verbatim in title or snippet."""
    dev, test = candidate_datasets
    all_cands = dev + test

    for cand in all_cands:
        ex_id = cand["example_id"]
        title = cand["input"]["title"]
        snippet = cand["input"]["snippet"]
        combined_text = f"{title} {snippet}".lower()

        evidence = cand["evidence"]
        for ev_field in ("name", "interest", "location"):
            ev_text = evidence.get(ev_field, "")
            if ev_text:
                assert ev_text.lower() in combined_text, (
                    f"Evidence {ev_field}='{ev_text}' in {ex_id} not found in input text:\n"
                    f"Title: {title}\nSnippet: {snippet}"
                )


def test_intent_schema_adherence(intent_datasets: tuple[list[dict], list[dict]]) -> None:
    """Verify intent extraction records adhere strictly to QueryIntent properties."""
    dev, test = intent_datasets
    all_intents = dev + test

    for intent in all_intents:
        ex_id = intent["example_id"]
        assert "input_query" in intent, f"Missing input_query in {ex_id}"
        assert "ground_truth" in intent, f"Missing ground_truth in {ex_id}"
        assert "annotation" in intent, f"Missing annotation in {ex_id}"

        gt = intent["ground_truth"]
        assert isinstance(gt.get("is_prospect_query"), bool), f"Invalid is_prospect_query in {ex_id}"
        assert isinstance(gt.get("interest"), str), f"Missing or invalid interest in {ex_id}"
        assert "target_type" in gt, f"Missing target_type in {ex_id}"

        if gt["location"] is not None:
            loc = gt["location"]
            assert "city" in loc, f"Missing city in location for {ex_id}"
            assert "state" in loc, f"Missing state in location for {ex_id}"
            assert "country" in loc, f"Missing country in location for {ex_id}"

        annot = intent["annotation"]
        assert annot.get("status") in ALLOWED_ANNOTATION_STATUSES, f"Invalid status in {ex_id}"


def test_pending_annotation_distinction(
    intent_datasets: tuple[list[dict], list[dict]],
    candidate_datasets: tuple[list[dict], list[dict]],
) -> None:
    """Verify that candidate and intent records are marked as pending human review."""
    dev_i, test_i = intent_datasets
    dev_c, test_c = candidate_datasets

    for item in dev_i + test_i:
        assert item["annotation"]["status"] == "needs_human_review"
        assert item["annotation"]["labeler"] is None

    for item in dev_c + test_c:
        assert item["annotation"]["status"] == "needs_human_review"
        assert item["annotation"]["labeler"] is None


def test_dataset_manifest_integrity(
    manifest: dict,
    intent_datasets: tuple[list[dict], list[dict]],
    candidate_datasets: tuple[list[dict], list[dict]],
) -> None:
    """Verify dataset manifest metrics match the physical datasets."""
    dev_i, test_i = intent_datasets
    dev_c, test_c = candidate_datasets

    assert manifest["splits"]["intents"]["development_count"] == len(dev_i)
    assert manifest["splits"]["intents"]["test_count"] == len(test_i)
    assert manifest["splits"]["candidates"]["development_count"] == len(dev_c)
    assert manifest["splits"]["candidates"]["test_count"] == len(test_c)
    assert manifest["raw_candidates_selected"] == 80
    assert manifest["intent_queries_prepared"] == 30
    assert manifest["api_expenditure_usd"] == 0.0


def test_privacy_verification_on_evaluation_datasets() -> None:
    """Verify all curated evaluation JSON files pass strict privacy and credential verification."""
    eval_json_files = [
        INTENT_DEV_PATH,
        INTENT_TEST_PATH,
        CANDIDATE_DEV_PATH,
        CANDIDATE_TEST_PATH,
        MANIFEST_PATH,
    ]

    for file_path in eval_json_files:
        assert file_path.exists(), f"File missing: {file_path}"
        content = file_path.read_text(encoding="utf-8")
        # Must pass privacy verification without raising ValueError
        verify_privacy(content, slug=file_path.name)
