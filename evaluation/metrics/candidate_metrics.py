"""Candidate relevance classification evaluation metrics.

Implements primary binary metrics (Precision, Recall, F1), sub-dimension accuracy,
and dedicated ambiguous-candidate handling statistics with strict exclusion of ambiguous
examples from primary binary metrics.
"""

from dataclasses import dataclass, field
from typing import Any

from app.services.relevance_service import _extract_verbatim_display_name
from evaluation.metrics.statistical import (
    ConfidenceInterval,
    compute_f1,
    compute_wilson_score_interval,
)
from evaluation.providers.base import CandidateBatchPredictionResult


@dataclass
class AmbiguityStatistics:
    """Statistics for ambiguous ground-truth candidate profiles."""

    total_ambiguous: int = 0
    percentage_of_total: float = 0.0
    accepted_by_model: int = 0
    rejected_by_model: int = 0
    model_low_confidence_count: int = 0
    acceptance_rate: float = 0.0


@dataclass
class DecisionPerformance:
    """Binary performance metrics for a classification decision layer."""

    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    precision_ci: ConfidenceInterval | None = None
    recall_ci: ConfidenceInterval | None = None


@dataclass
class CandidateMetricsReport:
    """Consolidated evaluation metrics for Candidate Relevance Classification."""

    total_candidates: int = 0
    unreviewed_excluded: int = 0
    reviewed_evaluated: int = 0

    # Primary Binary Evaluation (Ambiguous strictly excluded)
    model_level: DecisionPerformance = field(default_factory=DecisionPerformance)
    pipeline_level: DecisionPerformance = field(default_factory=DecisionPerformance)

    # Ambiguity Statistics
    ambiguity_stats: AmbiguityStatistics = field(default_factory=AmbiguityStatistics)

    # Sub-dimension Accuracies (on unambiguous candidates)
    individual_person_accuracy: float = 0.0
    name_support_accuracy: float = 0.0
    interest_support_accuracy: float = 0.0
    location_support_accuracy: float = 0.0

    # Operational metrics
    avg_latency_ms: float = 0.0
    total_tokens: int = 0
    warnings: list[str] = field(default_factory=list)


def evaluate_candidate_batch_predictions(
    batch_results: list[CandidateBatchPredictionResult],
    ground_truth_records: list[dict[str, Any]],
    require_human_reviewed: bool = False,
) -> CandidateMetricsReport:
    """Evaluate candidate relevance classifications against human-reviewed ground truth.

    Args:
        batch_results: Model prediction batch results from evaluation provider.
        ground_truth_records: List of curated candidate records.
        require_human_reviewed: If True, excludes records where status != 'reviewed'.

    Returns:
        CandidateMetricsReport with binary, ambiguous, and sub-dimension metrics.
    """
    report = CandidateMetricsReport(total_candidates=len(ground_truth_records))

    # Flatten predictions
    all_predictions = []
    total_latency = 0.0
    total_tokens = 0
    for batch in batch_results:
        total_latency += batch.latency_ms
        total_tokens += batch.token_usage.total_tokens
        all_predictions.extend(batch.predictions)

    report.avg_latency_ms = total_latency / len(batch_results) if batch_results else 0.0
    report.total_tokens = total_tokens

    # Pair predictions with ground truth
    pairs = []
    for pred in all_predictions:
        # Match by index or sequential ID
        idx = pred.candidate_index
        if idx < len(ground_truth_records):
            gt_rec = ground_truth_records[idx]
            annot = gt_rec.get("annotation", {})

            if require_human_reviewed and annot.get("status") != "reviewed":
                report.unreviewed_excluded += 1
                continue

            report.reviewed_evaluated += 1
            pairs.append((pred, gt_rec))

    if not pairs:
        if require_human_reviewed:
            report.warnings.append(
                "Zero human-reviewed candidate records found. Review annotations to compute primary metrics."
            )
        return report

    # 1. Process Ambiguous Candidates (Tracked separately; excluded from primary metrics)
    ambiguous_pairs = [
        (p, gt) for p, gt in pairs
        if gt["ground_truth"].get("overall_acceptability") == "ambiguous"
    ]
    unambiguous_pairs = [
        (p, gt) for p, gt in pairs
        if gt["ground_truth"].get("overall_acceptability") in ("positive", "negative")
    ]

    report.ambiguity_stats.total_ambiguous = len(ambiguous_pairs)
    report.ambiguity_stats.percentage_of_total = (
        len(ambiguous_pairs) / len(pairs) if pairs else 0.0
    )

    for pred, gt in ambiguous_pairs:
        c_item = pred.classification
        if c_item is not None:
            model_accepts = (
                c_item.is_individual_person
                and c_item.interest_supported
                and c_item.confidence.lower() in ("medium", "high")
            )
            if model_accepts:
                report.ambiguity_stats.accepted_by_model += 1
            else:
                report.ambiguity_stats.rejected_by_model += 1

            if c_item.confidence.lower() == "low":
                report.ambiguity_stats.model_low_confidence_count += 1
        else:
            report.ambiguity_stats.rejected_by_model += 1

    report.ambiguity_stats.acceptance_rate = (
        report.ambiguity_stats.accepted_by_model / len(ambiguous_pairs)
        if ambiguous_pairs else 0.0
    )

    # 2. Primary Binary Metrics on Unambiguous Candidates
    n_binary = len(unambiguous_pairs)
    person_matches = 0
    name_matches = 0
    interest_matches = 0
    location_matches = 0

    for pred, gt in unambiguous_pairs:
        c_item = pred.classification
        gt_target = gt["ground_truth"]
        is_gt_positive = gt_target.get("overall_acceptability") == "positive"

        raw_c = pred.raw_candidate

        # Model-Level Acceptance: LLM predicts individual + interest + medium/high confidence
        model_accepted = False
        if c_item is not None:
            model_accepted = (
                c_item.is_individual_person
                and c_item.interest_supported
                and c_item.confidence.lower() in ("medium", "high")
            )

        # Pipeline-Level Acceptance: Model accepted + verbatim name verified in code
        pipeline_accepted = False
        if model_accepted and c_item is not None:
            verbatim_name = _extract_verbatim_display_name(
                c_item.name_as_written, raw_c.title, raw_c.snippet
            )
            if verbatim_name is not None:
                pipeline_accepted = True

        # Model-level confusion matrix
        if is_gt_positive and model_accepted:
            report.model_level.true_positives += 1
        elif not is_gt_positive and not model_accepted:
            report.model_level.true_negatives += 1
        elif not is_gt_positive and model_accepted:
            report.model_level.false_positives += 1
        elif is_gt_positive and not model_accepted:
            report.model_level.false_negatives += 1

        # Pipeline-level confusion matrix
        if is_gt_positive and pipeline_accepted:
            report.pipeline_level.true_positives += 1
        elif not is_gt_positive and not pipeline_accepted:
            report.pipeline_level.true_negatives += 1
        elif not is_gt_positive and pipeline_accepted:
            report.pipeline_level.false_positives += 1
        elif is_gt_positive and not pipeline_accepted:
            report.pipeline_level.false_negatives += 1

        # Sub-dimension matches
        if c_item is not None:
            if (gt_target.get("is_individual_person") == "positive") == c_item.is_individual_person:
                person_matches += 1
            if (gt_target.get("interest_supported") == "positive") == c_item.interest_supported:
                interest_matches += 1
            if (gt_target.get("location_supported") == "positive") == c_item.location_supported:
                location_matches += 1

            # Name support check
            verbatim_name = _extract_verbatim_display_name(c_item.name_as_written, raw_c.title, raw_c.snippet)
            if (gt_target.get("name_supported") == "positive") == (verbatim_name is not None):
                name_matches += 1

    # Finalize model-level calculations
    _calculate_decision_metrics(report.model_level)
    # Finalize pipeline-level calculations
    _calculate_decision_metrics(report.pipeline_level)

    if n_binary > 0:
        report.individual_person_accuracy = person_matches / n_binary
        report.interest_support_accuracy = interest_matches / n_binary
        report.location_support_accuracy = location_matches / n_binary
        report.name_support_accuracy = name_matches / n_binary

    if n_binary < 30:
        report.warnings.append(
            f"Unambiguous candidate sample size N={n_binary} < 30. Metric confidence intervals are wide."
        )

    return report


def _calculate_decision_metrics(perf: DecisionPerformance) -> None:
    """Compute precision, recall, F1, FPR, FNR and confidence intervals."""
    tp = perf.true_positives
    fp = perf.false_positives
    tn = perf.true_negatives
    fn = perf.false_negatives

    denom_p = tp + fp
    denom_r = tp + fn
    denom_n = tn + fp

    perf.precision = tp / denom_p if denom_p else 0.0
    perf.recall = tp / denom_r if denom_r else 0.0
    perf.f1 = compute_f1(perf.precision, perf.recall)
    perf.false_positive_rate = fp / denom_n if denom_n else 0.0
    perf.false_negative_rate = fn / denom_r if denom_r else 0.0

    perf.precision_ci = compute_wilson_score_interval(tp, denom_p if denom_p else 1)
    perf.recall_ci = compute_wilson_score_interval(tp, denom_r if denom_r else 1)
