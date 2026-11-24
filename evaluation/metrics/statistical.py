"""Statistical utilities for metric calculations and confidence intervals.

Provides proportion statistics, Wilson score confidence intervals, and small-sample warnings.
"""

import math
from dataclasses import dataclass


@dataclass
class ConfidenceInterval:
    """Confidence interval range for a proportion metric."""

    point_estimate: float
    ci_lower: float
    ci_upper: float
    sample_size: int
    confidence_level: float = 0.95
    warning: str | None = None


def compute_wilson_score_interval(
    successes: int,
    total: int,
    confidence_level: float = 0.95,
) -> ConfidenceInterval:
    """Calculate Wilson score interval for a binomial proportion.

    Args:
        successes: Number of successful outcomes (e.g. true positives, correct predictions).
        total: Total number of trials.
        confidence_level: Desired confidence level (default: 0.95, z ≈ 1.96).

    Returns:
        ConfidenceInterval with point estimate, lower and upper bounds, and sample warning.
    """
    if total <= 0:
        return ConfidenceInterval(
            point_estimate=0.0,
            ci_lower=0.0,
            ci_upper=0.0,
            sample_size=0,
            confidence_level=confidence_level,
            warning="Sample size is zero; confidence interval cannot be computed.",
        )

    p_hat = successes / total

    # z-value for standard normal distribution
    if math.isclose(confidence_level, 0.95):
        z = 1.95996
    elif math.isclose(confidence_level, 0.99):
        z = 2.57583
    elif math.isclose(confidence_level, 0.90):
        z = 1.64485
    else:
        z = 1.95996

    z2 = z * z
    n = float(total)

    denominator = 1.0 + z2 / n
    center_adjusted = (p_hat + z2 / (2.0 * n)) / denominator
    margin = (z / denominator) * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z2 / (4.0 * n * n)))

    lower = max(0.0, center_adjusted - margin)
    upper = min(1.0, center_adjusted + margin)

    warning = None
    if total < 30:
        warning = f"Small sample size warning: N={total} < 30. Confidence intervals are wide and metrics should be interpreted cautiously."

    return ConfidenceInterval(
        point_estimate=p_hat,
        ci_lower=lower,
        ci_upper=upper,
        sample_size=total,
        confidence_level=confidence_level,
        warning=warning,
    )


def compute_f1(precision: float, recall: float) -> float:
    """Compute harmonic mean F1 score from precision and recall."""
    if (precision + recall) <= 0.0:
        return 0.0
    return (2.0 * precision * recall) / (precision + recall)
