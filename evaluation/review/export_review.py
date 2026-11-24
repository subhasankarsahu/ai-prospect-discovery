"""Human review export utility for Phase 5 ground-truth datasets.

Exports pending intent and candidate annotations into review-friendly formats (CSV and JSON)
for inspection and approval by the project owner without overwriting machine suggestions.
"""

import csv
import json
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATASETS_DIR = ROOT_DIR / "evaluation" / "datasets"
REVIEW_DIR = ROOT_DIR / "evaluation" / "review"


def export_candidate_reviews() -> None:
    """Export all 80 candidate annotations into candidate review CSV and JSON."""
    dev_path = DATASETS_DIR / "candidates" / "development.json"
    test_path = DATASETS_DIR / "candidates" / "test.json"

    candidates: list[dict[str, Any]] = []
    if dev_path.exists():
        candidates.extend(json.loads(dev_path.read_text(encoding="utf-8")))
    if test_path.exists():
        candidates.extend(json.loads(test_path.read_text(encoding="utf-8")))

    # 1. Export JSON with separate suggested vs reviewer fields
    review_items = []
    for c in candidates:
        review_items.append({
            "example_id": c["example_id"],
            "split": c["split"],
            "source_fixture": c["source_fixture"],
            "platform": c["platform"],
            "url": c["url"],
            "input": {
                "title": c["input"]["title"],
                "snippet": c["input"]["snippet"],
            },
            "machine_suggestion": {
                "is_individual_person": c["ground_truth"]["is_individual_person"],
                "name_supported": c["ground_truth"]["name_supported"],
                "interest_supported": c["ground_truth"]["interest_supported"],
                "location_supported": c["ground_truth"]["location_supported"],
                "overall_acceptability": c["ground_truth"]["overall_acceptability"],
                "evidence": c.get("evidence", {}),
            },
            "human_review": {
                "status": c["annotation"].get("status", "needs_human_review"),
                "approved_is_individual_person": None,
                "approved_name_supported": None,
                "approved_interest_supported": None,
                "approved_location_supported": None,
                "approved_overall_acceptability": None,
                "reviewer_name": None,
                "reviewed_at": None,
                "notes": c["annotation"].get("notes", ""),
            },
        })

    json_out = REVIEW_DIR / "pending_candidate_reviews.json"
    json_out.write_text(json.dumps(review_items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {len(review_items)} candidate reviews to {json_out.name}")

    # 2. Export CSV for quick tabular spreadsheet inspection
    csv_out = REVIEW_DIR / "pending_candidate_reviews.csv"
    with csv_out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "example_id",
            "split",
            "source_fixture",
            "platform",
            "title",
            "snippet",
            "suggested_person",
            "suggested_name",
            "suggested_interest",
            "suggested_location",
            "suggested_overall",
            "evidence_name",
            "evidence_interest",
            "evidence_location",
            "decision_status (needs_human_review/reviewed/rejected)",
            "approved_overall (positive/negative/ambiguous)",
            "reviewer_name",
            "review_notes",
        ])
        for c in candidates:
            gt = c["ground_truth"]
            ev = c.get("evidence", {})
            an = c.get("annotation", {})
            writer.writerow([
                c["example_id"],
                c["split"],
                c["source_fixture"],
                c["platform"],
                c["input"]["title"].replace("\n", " "),
                c["input"]["snippet"].replace("\n", " "),
                gt.get("is_individual_person"),
                gt.get("name_supported"),
                gt.get("interest_supported"),
                gt.get("location_supported"),
                gt.get("overall_acceptability"),
                ev.get("name", ""),
                ev.get("interest", ""),
                ev.get("location", ""),
                an.get("status", "needs_human_review"),
                "",  # approved_overall initially blank
                "",  # reviewer_name initially blank
                an.get("notes", "").replace("\n", " "),
            ])
    print(f"Exported candidate review CSV to {csv_out.name}")


def export_intent_reviews() -> None:
    """Export all 30 intent annotations into intent review CSV and JSON."""
    dev_path = DATASETS_DIR / "intents" / "development.json"
    test_path = DATASETS_DIR / "intents" / "test.json"

    intents: list[dict[str, Any]] = []
    if dev_path.exists():
        intents.extend(json.loads(dev_path.read_text(encoding="utf-8")))
    if test_path.exists():
        intents.extend(json.loads(test_path.read_text(encoding="utf-8")))

    review_items = []
    for item in intents:
        review_items.append({
            "example_id": item["example_id"],
            "split": item["split"],
            "input_query": item["input_query"],
            "machine_suggestion": item["ground_truth"],
            "acceptable_variants": item.get("acceptable_variants", {}),
            "human_review": {
                "status": item["annotation"].get("status", "needs_human_review"),
                "approved_is_prospect_query": None,
                "approved_interest": None,
                "approved_audience": None,
                "approved_location": None,
                "approved_target_type": None,
                "reviewer_name": None,
                "reviewed_at": None,
                "notes": item["annotation"].get("notes", ""),
            },
        })

    json_out = REVIEW_DIR / "pending_intent_reviews.json"
    json_out.write_text(json.dumps(review_items, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {len(review_items)} intent reviews to {json_out.name}")

    csv_out = REVIEW_DIR / "pending_intent_reviews.csv"
    with csv_out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "example_id",
            "split",
            "input_query",
            "suggested_is_prospect",
            "suggested_interest",
            "suggested_audience",
            "suggested_city",
            "suggested_state",
            "suggested_country",
            "suggested_target_type",
            "decision_status (needs_human_review/reviewed/rejected)",
            "reviewer_name",
            "review_notes",
        ])
        for item in intents:
            gt = item["ground_truth"]
            loc = gt.get("location") or {}
            an = item.get("annotation", {})
            writer.writerow([
                item["example_id"],
                item["split"],
                item["input_query"],
                gt.get("is_prospect_query"),
                gt.get("interest"),
                gt.get("audience"),
                loc.get("city"),
                loc.get("state"),
                loc.get("country"),
                gt.get("target_type"),
                an.get("status", "needs_human_review"),
                "",
                an.get("notes", "").replace("\n", " "),
            ])
    print(f"Exported intent review CSV to {csv_out.name}")


def main() -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    export_candidate_reviews()
    export_intent_reviews()
    print("Human review export complete.")


if __name__ == "__main__":
    main()
