"""Human review ingestion utility.

Applies human-approved ground-truth labels from a completed review file (JSON or CSV)
to the evaluation dataset while strictly preserving the original machine suggestions
in separate fields (`machine_suggestion`, `machine_evidence`).
"""

import json
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATASETS_DIR = ROOT_DIR / "evaluation" / "datasets"
REVIEW_DIR = ROOT_DIR / "evaluation" / "review"


def apply_candidate_reviews(review_json_path: Path | None = None) -> int:
    """Apply human-reviewed labels from review JSON to candidates development and test datasets."""
    path = review_json_path or (REVIEW_DIR / "pending_candidate_reviews.json")
    if not path.exists():
        raise FileNotFoundError(f"Review file not found: {path}")

    reviews: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    reviews_by_id = {r["example_id"]: r for r in reviews}

    updated_count = 0

    for split in ("development", "test"):
        dataset_file = DATASETS_DIR / "candidates" / f"{split}.json"
        if not dataset_file.exists():
            continue

        records = json.loads(dataset_file.read_text(encoding="utf-8"))
        for item in records:
            ex_id = item["example_id"]
            if ex_id in reviews_by_id:
                rev = reviews_by_id[ex_id]
                hr = rev.get("human_review", {})
                status = hr.get("status")

                if status in ("reviewed", "rejected"):
                    # Preserve machine suggestion if not already preserved
                    if "machine_suggestion" not in item:
                        item["machine_suggestion"] = dict(item["ground_truth"])
                    if "machine_evidence" not in item:
                        item["machine_evidence"] = dict(item.get("evidence", {}))

                    # Update human-approved values if specified
                    for dim in ("is_individual_person", "name_supported", "interest_supported", "location_supported", "overall_acceptability"):
                        approved_val = hr.get(f"approved_{dim}")
                        if approved_val:
                            item["ground_truth"][dim] = approved_val

                    item["annotation"]["status"] = status
                    item["annotation"]["labeler"] = hr.get("reviewer_name")
                    item["annotation"]["reviewed_at"] = hr.get("reviewed_at")
                    if hr.get("notes"):
                        item["annotation"]["notes"] = hr.get("notes")
                    updated_count += 1

        dataset_file.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    return updated_count


def apply_intent_reviews(review_json_path: Path | None = None) -> int:
    """Apply human-reviewed labels from review JSON to intent development and test datasets."""
    path = review_json_path or (REVIEW_DIR / "pending_intent_reviews.json")
    if not path.exists():
        raise FileNotFoundError(f"Review file not found: {path}")

    reviews: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    reviews_by_id = {r["example_id"]: r for r in reviews}

    updated_count = 0

    for split in ("development", "test"):
        dataset_file = DATASETS_DIR / "intents" / f"{split}.json"
        if not dataset_file.exists():
            continue

        records = json.loads(dataset_file.read_text(encoding="utf-8"))
        for item in records:
            ex_id = item["example_id"]
            if ex_id in reviews_by_id:
                rev = reviews_by_id[ex_id]
                hr = rev.get("human_review", {})
                status = hr.get("status")

                if status in ("reviewed", "rejected"):
                    # Preserve machine suggestion
                    if "machine_suggestion" not in item:
                        item["machine_suggestion"] = dict(item["ground_truth"])

                    if hr.get("approved_is_prospect_query") is not None:
                        item["ground_truth"]["is_prospect_query"] = hr["approved_is_prospect_query"]
                    if hr.get("approved_interest") is not None:
                        item["ground_truth"]["interest"] = hr["approved_interest"]
                    if hr.get("approved_audience") is not None:
                        item["ground_truth"]["audience"] = hr["approved_audience"]
                    if hr.get("approved_location") is not None:
                        item["ground_truth"]["location"] = hr["approved_location"]
                    if hr.get("approved_target_type") is not None:
                        item["ground_truth"]["target_type"] = hr["approved_target_type"]

                    item["annotation"]["status"] = status
                    item["annotation"]["labeler"] = hr.get("reviewer_name")
                    item["annotation"]["reviewed_at"] = hr.get("reviewed_at")
                    if hr.get("notes"):
                        item["annotation"]["notes"] = hr.get("notes")
                    updated_count += 1

        dataset_file.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    return updated_count


if __name__ == "__main__":
    c_updated = apply_candidate_reviews()
    i_updated = apply_intent_reviews()
    print(f"Applied human reviews: {c_updated} candidates, {i_updated} intents.")
