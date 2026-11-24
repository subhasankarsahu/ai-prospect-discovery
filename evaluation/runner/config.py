"""Configuration model for the LLM evaluation runner.

Controls dataset splits, model selection (Google Gemini only), offline-mode enforcement,
and zero-budget expenditure safeguards.
"""

from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


@dataclass
class EvaluationConfig:
    """Evaluation runner execution settings."""

    # Model configuration (Google Gemini only)
    model_id: str = "gemini-3.5-flash-lite"
    alternative_model_id: str | None = None

    # Dataset partition control
    # Defaults strictly to 'development' to prevent accidental held-out test leakage
    split: str = "development"

    # Execution and Budget Safeguards
    offline_mode: bool = True
    budget_cap_usd: float = 0.0
    allow_live_api: bool = False

    # Annotation Integrity
    require_human_reviewed: bool = True

    # Processing batching
    candidate_batch_size: int = 15

    # Pricing metadata for cost estimation (manually supplied; defaults to 0.0)
    pricing_input_per_million: float = 0.0
    pricing_output_per_million: float = 0.0

    # Directory paths
    datasets_dir: Path = field(default_factory=lambda: ROOT_DIR / "evaluation" / "datasets")
    reports_dir: Path = field(default_factory=lambda: ROOT_DIR / "evaluation" / "reports")

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate inference cost in USD based on configured pricing metadata."""
        cost_in = (prompt_tokens / 1_000_000.0) * self.pricing_input_per_million
        cost_out = (completion_tokens / 1_000_000.0) * self.pricing_output_per_million
        return cost_in + cost_out

    def validate_budget_safety(self) -> None:
        """Enforce $0 budget restriction."""
        if self.budget_cap_usd > 0.0:
            raise ValueError(
                f"Evaluation budget cap is set to ${self.budget_cap_usd:.2f}, but the mandatory project budget is $0.00."
            )
        if self.allow_live_api and self.budget_cap_usd <= 0.0:
            raise ValueError(
                "Live API execution is disabled under $0.00 budget. Keep offline_mode=True."
            )
