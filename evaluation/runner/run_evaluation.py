"""Offline evaluation runner CLI and orchestrator.

Loads datasets, executes evaluation providers (offline mock by default),
computes statistical metrics, and generates comparison reports with zero network access.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.schemas import QueryIntent
from app.schemas_internal import RawCandidate
from evaluation.metrics.candidate_metrics import (
    CandidateMetricsReport,
    evaluate_candidate_batch_predictions,
)
from evaluation.metrics.intent_metrics import (
    IntentMetricsReport,
    evaluate_intent_predictions,
)
from evaluation.providers.base import (
    CandidateBatchPredictionResult,
    EvaluationModelProvider,
    IntentPredictionResult,
)
from evaluation.providers.mock_provider import MockEvaluationProvider
from evaluation.runner.config import EvaluationConfig

logger = logging.getLogger(__name__)


class EvaluationRunner:
    """Orchestrator for offline LLM evaluation."""

    def __init__(self, config: EvaluationConfig | None = None) -> None:
        self.config = config or EvaluationConfig()
        self.config.validate_budget_safety()

    def load_intent_dataset(self) -> list[dict[str, Any]]:
        """Load intent records for the configured split."""
        path = self.config.datasets_dir / "intents" / f"{self.config.split}.json"
        if not path.exists():
            raise FileNotFoundError(f"Intent dataset file missing: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def load_candidate_dataset(self) -> list[dict[str, Any]]:
        """Load candidate records for the configured split."""
        path = self.config.datasets_dir / "candidates" / f"{self.config.split}.json"
        if not path.exists():
            raise FileNotFoundError(f"Candidate dataset file missing: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    async def run_intent_evaluation(
        self,
        provider: EvaluationModelProvider,
        dataset: list[dict[str, Any]],
    ) -> tuple[list[IntentPredictionResult], IntentMetricsReport]:
        """Execute intent predictions and compute metrics."""
        predictions = []
        for item in dataset:
            query = item["input_query"]
            pred = await provider.extract_intent(query)
            predictions.append(pred)

        metrics = evaluate_intent_predictions(
            predictions=predictions,
            ground_truth_records=dataset,
            require_human_reviewed=self.config.require_human_reviewed,
        )
        return predictions, metrics

    async def run_candidate_evaluation(
        self,
        provider: EvaluationModelProvider,
        dataset: list[dict[str, Any]],
    ) -> tuple[list[CandidateBatchPredictionResult], CandidateMetricsReport]:
        """Execute candidate batch predictions and compute metrics."""
        # Group candidates into batches of configured size
        raw_candidates = [
            RawCandidate(
                source_platform=item["platform"],
                canonical_url=item["url"],
                title=item["input"]["title"],
                snippet=item["input"]["snippet"],
                search_query=item.get("source_query", ""),
            )
            for item in dataset
        ]

        batch_size = self.config.candidate_batch_size
        batches = [
            raw_candidates[i : i + batch_size]
            for i in range(0, len(raw_candidates), batch_size)
        ]

        # Use canonical intent from dataset
        dummy_intent = QueryIntent(
            is_prospect_query=True,
            interest="Evaluation Target Domain",
            target_type="individual",
        )

        batch_results = []
        for batch in batches:
            res = await provider.classify_candidates(dummy_intent, batch)
            batch_results.append(res)

        metrics = evaluate_candidate_batch_predictions(
            batch_results=batch_results,
            ground_truth_records=dataset,
            require_human_reviewed=self.config.require_human_reviewed,
        )
        return batch_results, metrics

    async def run(
        self, provider: EvaluationModelProvider | None = None
    ) -> dict[str, Any]:
        """Execute complete offline evaluation and return summary report."""
        active_provider = provider or MockEvaluationProvider(model_id=self.config.model_id)

        intent_data = self.load_intent_dataset()
        candidate_data = self.load_candidate_dataset()

        _, intent_metrics = await self.run_intent_evaluation(active_provider, intent_data)
        _, candidate_metrics = await self.run_candidate_evaluation(active_provider, candidate_data)

        # Generate summary payload
        report_payload = {
            "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
            "model_id": active_provider.model_id,
            "split": self.config.split,
            "offline_mode": self.config.offline_mode,
            "budget_cap_usd": self.config.budget_cap_usd,
            "require_human_reviewed": self.config.require_human_reviewed,
            "intent_metrics": {
                "total_evaluated": intent_metrics.total_evaluated,
                "reviewed_evaluated": intent_metrics.reviewed_evaluated,
                "unreviewed_excluded": intent_metrics.unreviewed_excluded,
                "prospect_accuracy": round(intent_metrics.prospect_accuracy, 4),
                "prospect_precision": round(intent_metrics.prospect_precision, 4),
                "prospect_recall": round(intent_metrics.prospect_recall, 4),
                "prospect_f1": round(intent_metrics.prospect_f1, 4),
                "interest_semantic_accuracy": round(intent_metrics.interest_semantic_accuracy, 4),
                "location_accuracy": round(intent_metrics.location_accuracy, 4),
                "structured_validity_rate": round(intent_metrics.structured_validity_rate, 4),
                "hallucination_rate": round(intent_metrics.hallucination_rate, 4),
                "avg_latency_ms": round(intent_metrics.avg_latency_ms, 2),
                "total_tokens": intent_metrics.total_tokens,
                "warnings": intent_metrics.warnings,
            },
            "candidate_metrics": {
                "total_candidates": candidate_metrics.total_candidates,
                "reviewed_evaluated": candidate_metrics.reviewed_evaluated,
                "unreviewed_excluded": candidate_metrics.unreviewed_excluded,
                "ambiguity_stats": {
                    "total_ambiguous": candidate_metrics.ambiguity_stats.total_ambiguous,
                    "percentage_of_total": round(candidate_metrics.ambiguity_stats.percentage_of_total, 4),
                    "accepted_by_model": candidate_metrics.ambiguity_stats.accepted_by_model,
                    "rejected_by_model": candidate_metrics.ambiguity_stats.rejected_by_model,
                },
                "model_level": {
                    "precision": round(candidate_metrics.model_level.precision, 4),
                    "recall": round(candidate_metrics.model_level.recall, 4),
                    "f1": round(candidate_metrics.model_level.f1, 4),
                    "tp": candidate_metrics.model_level.true_positives,
                    "fp": candidate_metrics.model_level.false_positives,
                    "tn": candidate_metrics.model_level.true_negatives,
                    "fn": candidate_metrics.model_level.false_negatives,
                },
                "pipeline_level": {
                    "precision": round(candidate_metrics.pipeline_level.precision, 4),
                    "recall": round(candidate_metrics.pipeline_level.recall, 4),
                    "f1": round(candidate_metrics.pipeline_level.f1, 4),
                    "tp": candidate_metrics.pipeline_level.true_positives,
                    "fp": candidate_metrics.pipeline_level.false_positives,
                    "tn": candidate_metrics.pipeline_level.true_negatives,
                    "fn": candidate_metrics.pipeline_level.false_negatives,
                },
                "sub_dimension_accuracy": {
                    "individual_person": round(candidate_metrics.individual_person_accuracy, 4),
                    "name_support": round(candidate_metrics.name_support_accuracy, 4),
                    "interest_support": round(candidate_metrics.interest_support_accuracy, 4),
                    "location_support": round(candidate_metrics.location_support_accuracy, 4),
                },
                "avg_latency_ms": round(candidate_metrics.avg_latency_ms, 2),
                "total_tokens": candidate_metrics.total_tokens,
                "warnings": candidate_metrics.warnings,
            },
        }

        # Save report JSON
        self.config.reports_dir.mkdir(parents=True, exist_ok=True)
        report_file = self.config.reports_dir / f"eval_report_{self.config.split}_{active_provider.model_id}.json"
        report_file.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
        print(f"Generated evaluation report: {report_file.name}")

        return report_payload


def main() -> None:
    runner = EvaluationRunner()
    result = asyncio.run(runner.run())
    print("Evaluation run complete. Model:", result["model_id"])


if __name__ == "__main__":
    main()
