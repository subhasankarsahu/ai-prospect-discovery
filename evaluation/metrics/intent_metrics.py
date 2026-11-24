"""Query intent extraction evaluation metrics.

Evaluates predicted QueryIntent objects against human-reviewed ground truth with support
for semantic variants, hallucination detection, and unreviewed label exclusion.
"""

from dataclasses import dataclass, field
from typing import Any

from evaluation.metrics.statistical import (
    ConfidenceInterval,
    compute_f1,
    compute_wilson_score_interval,
)
from evaluation.providers.base import IntentPredictionResult


@dataclass
class IntentMetricsReport:
    """Consolidated evaluation metrics for Query Intent Extraction."""

    total_evaluated: int = 0
    reviewed_evaluated: int = 0
    unreviewed_excluded: int = 0

    # Prospect Query Classification (Binary)
    prospect_tp: int = 0
    prospect_fp: int = 0
    prospect_tn: int = 0
    prospect_fn: int = 0
    prospect_accuracy: float = 0.0
    prospect_precision: float = 0.0
    prospect_recall: float = 0.0
    prospect_f1: float = 0.0
    prospect_f1_ci: ConfidenceInterval | None = None

    # Field-Level Accuracies
    interest_exact_accuracy: float = 0.0
    interest_semantic_accuracy: float = 0.0
    audience_accuracy: float = 0.0
    location_accuracy: float = 0.0
    target_type_accuracy: float = 0.0

    # Quality & Reliability
    structured_validity_rate: float = 0.0
    hallucination_rate: float = 0.0
    avg_latency_ms: float = 0.0
    total_tokens: int = 0

    warnings: list[str] = field(default_factory=list)


def is_semantic_match(predicted: str | None, canonical: str | None, acceptable_variants: list[str] | None = None) -> bool:
    """Check if predicted string matches canonical string or any acceptable semantic variant."""
    if predicted is None and canonical is None:
        return True
    if predicted is None or canonical is None:
        return False

    pred_clean = predicted.strip().lower()
    canon_clean = canonical.strip().lower()

    if pred_clean == canon_clean:
        return True

    # Check variants
    if acceptable_variants:
        for var in acceptable_variants:
            if var and var.strip().lower() == pred_clean:
                return True
            # Also check substring match for multi-word domain variants
            if var and var.strip().lower() in pred_clean:
                return True

    return False


def is_hallucinated_commentary(text: str | None) -> bool:
    """Detect if field contains model conversational reasoning or meta-commentary."""
    if not text:
        return False
    lower = text.lower()
    # Check for sentence punctuation and meta phrases observed in audit
    if len(text) > 40:
        return True
    suspicious_phrases = [
        "implied context",
        "according to",
        "not explicitly",
        "specified as a whole",
        "as a result",
        "note that",
    ]
    return any(p in lower for p in suspicious_phrases)


def evaluate_intent_predictions(
    predictions: list[IntentPredictionResult],
    ground_truth_records: list[dict[str, Any]],
    require_human_reviewed: bool = False,
) -> IntentMetricsReport:
    """Compute comprehensive intent extraction metrics.

    Args:
        predictions: List of IntentPredictionResult from model provider.
        ground_truth_records: List of curated ground truth records with acceptable variants.
        require_human_reviewed: If True, excludes records where status != 'reviewed'.

    Returns:
        IntentMetricsReport containing detailed metric calculations.
    """
    gt_by_query = {rec["input_query"].strip().lower(): rec for rec in ground_truth_records}

    report = IntentMetricsReport(total_evaluated=len(predictions))
    total_latency = 0.0
    total_tokens = 0
    valid_structures = 0
    hallucinations = 0

    evaluated_records = []

    for pred in predictions:
        total_latency += pred.latency_ms
        total_tokens += pred.token_usage.total_tokens
        if pred.is_valid_schema and pred.intent is not None:
            valid_structures += 1

        lookup_key = pred.query.strip().lower()
        if lookup_key not in gt_by_query:
            continue

        gt_rec = gt_by_query[lookup_key]
        annot = gt_rec.get("annotation", {})

        if require_human_reviewed and annot.get("status") != "reviewed":
            report.unreviewed_excluded += 1
            continue

        report.reviewed_evaluated += 1
        evaluated_records.append((pred, gt_rec))

    report.structured_validity_rate = (
        valid_structures / len(predictions) if predictions else 0.0
    )
    report.avg_latency_ms = (
        total_latency / len(predictions) if predictions else 0.0
    )
    report.total_tokens = total_tokens

    if not evaluated_records:
        if require_human_reviewed:
            report.warnings.append(
                "Zero human-reviewed intent records found. Annotations must be reviewed to compute primary metrics."
            )
        return report

    n = len(evaluated_records)
    interest_exact_matches = 0
    interest_semantic_matches = 0
    audience_matches = 0
    location_matches = 0
    target_type_matches = 0

    for pred, gt_rec in evaluated_records:
        gt = gt_rec["ground_truth"]
        variants = gt_rec.get("acceptable_variants", {})

        pred_intent = pred.intent
        if pred_intent is None:
            # Model failed to parse
            if gt["is_prospect_query"]:
                report.prospect_fn += 1
            else:
                report.prospect_tn += 1
            continue

        # 1. Prospect Query Detection
        actual_is_prospect = gt["is_prospect_query"]
        pred_is_prospect = pred_intent.is_prospect_query

        if actual_is_prospect and pred_is_prospect:
            report.prospect_tp += 1
        elif not actual_is_prospect and not pred_is_prospect:
            report.prospect_tn += 1
        elif not actual_is_prospect and pred_is_prospect:
            report.prospect_fp += 1
        elif actual_is_prospect and not pred_is_prospect:
            report.prospect_fn += 1

        # 2. Interest Match
        canon_interest = gt.get("interest")
        pred_interest = pred_intent.interest
        if pred_interest and canon_interest and pred_interest.strip().lower() == canon_interest.strip().lower():
            interest_exact_matches += 1
            interest_semantic_matches += 1
        elif is_semantic_match(pred_interest, canon_interest, variants.get("interest")):
            interest_semantic_matches += 1

        # 3. Audience Match
        canon_aud = gt.get("audience")
        pred_aud = pred_intent.audience
        if is_semantic_match(pred_aud, canon_aud, variants.get("audience")):
            audience_matches += 1

        # 4. Target Type Match
        canon_target = gt.get("target_type")
        pred_target = pred_intent.target_type
        if is_semantic_match(pred_target, canon_target, variants.get("target_type")):
            target_type_matches += 1

        # 5. Location Match
        gt_loc = gt.get("location")
        pred_loc = pred_intent.location

        if gt_loc is None and pred_loc is None:
            location_matches += 1
        elif gt_loc is not None and pred_loc is not None:
            city_ok = is_semantic_match(pred_loc.city, gt_loc.get("city"), variants.get("location", {}).get("city"))
            state_ok = is_semantic_match(pred_loc.state, gt_loc.get("state"), variants.get("location", {}).get("state"))
            country_ok = is_semantic_match(pred_loc.country, gt_loc.get("country"), variants.get("location", {}).get("country"))

            # Check for verbose commentary in state (hallucination audit)
            if is_hallucinated_commentary(pred_loc.state) or is_hallucinated_commentary(pred_loc.city):
                hallucinations += 1
                state_ok = False

            if city_ok and (state_ok or gt_loc.get("state") is None) and country_ok:
                location_matches += 1

    # Binary metrics
    denom_p = report.prospect_tp + report.prospect_fp
    denom_r = report.prospect_tp + report.prospect_fn
    total_class = report.prospect_tp + report.prospect_fp + report.prospect_tn + report.prospect_fn

    report.prospect_accuracy = (report.prospect_tp + report.prospect_tn) / total_class if total_class else 0.0
    report.prospect_precision = report.prospect_tp / denom_p if denom_p else 0.0
    report.prospect_recall = report.prospect_tp / denom_r if denom_r else 0.0
    report.prospect_f1 = compute_f1(report.prospect_precision, report.prospect_recall)
    report.prospect_f1_ci = compute_wilson_score_interval(report.prospect_tp, denom_p if denom_p else 1)

    # Component rates
    report.interest_exact_accuracy = interest_exact_matches / n
    report.interest_semantic_accuracy = interest_semantic_matches / n
    report.audience_accuracy = audience_matches / n
    report.location_accuracy = location_matches / n
    report.target_type_accuracy = target_type_matches / n
    report.hallucination_rate = hallucinations / n

    if n < 30:
        report.warnings.append(f"Intent dataset size N={n} < 30. Metrics have wide confidence intervals.")

    return report
