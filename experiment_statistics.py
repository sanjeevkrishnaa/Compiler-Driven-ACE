"""Dependency-free statistics for repeated compiler/ACE experiments."""

from __future__ import annotations

from math import sqrt
from statistics import fmean, stdev


# Two-sided 95% Student-t critical values for 1..30 degrees of freedom.
_T95 = (
    None, 12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306,
    2.262157, 2.228139, 2.200985, 2.178813, 2.160369, 2.144787,
    2.131450, 2.119905, 2.109816,
    2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056,
    2.052, 2.048, 2.045, 2.042,
)


def summarize(values: list[float]) -> dict[str, float | int | None]:
    """Return n, mean, sample SD, SE, and a two-sided 95% t interval."""
    clean = [float(value) for value in values]
    if not clean:
        return {"n": 0, "mean": None, "sample_sd": None, "standard_error": None,
                "ci95_low": None, "ci95_high": None}
    mean = fmean(clean)
    if len(clean) == 1:
        return {"n": 1, "mean": mean, "sample_sd": None, "standard_error": None,
                "ci95_low": None, "ci95_high": None}
    sd = stdev(clean)
    se = sd / sqrt(len(clean))
    df = len(clean) - 1
    critical = _T95[df] if df < len(_T95) else 1.96
    margin = critical * se
    return {"n": len(clean), "mean": mean, "sample_sd": sd,
            "standard_error": se, "ci95_low": mean - margin,
            "ci95_high": mean + margin}


def interval_from_summary(mean: float, sample_sd: float, n: int) -> tuple[float, float]:
    """Calculate a 95% t interval from reported mean, sample SD, and n."""
    if n < 2:
        raise ValueError("a confidence interval requires at least two samples")
    if sample_sd < 0:
        raise ValueError("sample SD cannot be negative")
    df = n - 1
    critical = _T95[df] if df < len(_T95) else 1.96
    margin = critical * sample_sd / sqrt(n)
    return mean - margin, mean + margin
