import math
from statistics import median

from scipy.spatial.distance import jensenshannon
from scipy.stats import ks_2samp


MIN_BASELINE = 8


def robust_bounds(values, relative_floor=0.25, absolute_floor=1):
    center = median(values)
    mad = median(abs(v - center) for v in values)
    tolerance = max(6 * 1.4826 * mad, abs(center) * relative_floor, absolute_floor)
    return center, max(0, center - tolerance), center + tolerance


def detect(current, history):
    anomalies = []

    def add(kind, column, observed, expected, method, details, severity="warning"):
        anomalies.append(
            {
                "kind": kind,
                "column": column or "",
                "severity": severity,
                "title": f"{kind.replace('_', ' ').capitalize()}{' · ' + column if column else ''}",
                "observed": observed,
                "expected": expected,
                "method": method,
                "details": details,
            }
        )

    if history:
        previous = history[-1]
        for col in sorted(set(previous["schema"]) | set(current["schema"])):
            before, after = previous["schema"].get(col), current["schema"].get(col)
            if before != after:
                # Null-only inference is not asserted as a physical database type migration.
                add(
                    "schema_drift",
                    col,
                    None,
                    f"Observed type: {before}",
                    "Observed schema diff",
                    {
                        "before": before,
                        "after": after,
                        "change": "added"
                        if before is None
                        else "removed"
                        if after is None
                        else "type_changed",
                    },
                    "critical" if after is None else "warning",
                )
    if len(history) < MIN_BASELINE:
        return anomalies
    baseline = history[-12:]
    _, lo, hi = robust_bounds([h["row_count"] for h in baseline])
    if not lo <= current["row_count"] <= hi:
        add(
            "volume",
            "",
            current["row_count"],
            f"{lo:.0f} to {hi:.0f} rows",
            "Median ± 6 scaled MAD; 25% floor",
            {"baseline_runs": len(baseline), "lower": lo, "upper": hi},
            "critical",
        )
    base_duplicates = median(h["duplicate_rate"] for h in baseline)
    if current["duplicate_rate"] > base_duplicates + 0.05:
        add(
            "duplicates",
            "",
            current["duplicate_rate"],
            f"Duplicate rate <= {base_duplicates + 0.05:.2%}",
            "Baseline + 5 percentage points",
            {"baseline": base_duplicates},
            "critical",
        )
    if current["row_count"] >= 30:
        for col, stats in current["columns"].items():
            old = [h["columns"][col] for h in baseline if col in h["columns"]]
            if len(old) < MIN_BASELINE:
                continue
            normal_null = median(s["null_rate"] for s in old)
            if stats["null_rate"] > normal_null + 0.08:
                add(
                    "null_spike",
                    col,
                    stats["null_rate"],
                    f"Null rate <= {normal_null + 0.08:.2%}",
                    "Baseline + 8 percentage points",
                    {"baseline": normal_null},
                    "critical",
                )
            if (
                col in {"country_code", "payment_method", "status", "category", "segment"}
                and "distribution" in stats
            ):
                prior = {}
                for row in old:
                    for key, value in row.get("distribution", {}).items():
                        prior[key] = prior.get(key, 0) + value
                keys = sorted(set(prior) | set(stats["distribution"]))
                if keys and sum(prior.values()) > 0 and sum(stats["distribution"].values()) > 0:
                    # Squared base-2 JS distance is bounded divergence in [0, 1].
                    divergence = float(
                        jensenshannon(
                            [prior.get(k, 0) for k in keys],
                            [stats["distribution"].get(k, 0) for k in keys],
                            base=2,
                        )
                        ** 2
                    )
                    if math.isfinite(divergence) and divergence > 0.12:
                        add(
                            "distribution_drift",
                            col,
                            divergence,
                            "JS divergence <= 0.12",
                            "Jensen-Shannon divergence, base 2",
                            {
                                "baseline_counts": prior,
                                "current_counts": stats["distribution"],
                                "baseline_runs": len(old),
                            },
                        )
            if "sample" in stats and len(stats["sample"]) >= 30:
                values = [v for row in old for v in row.get("sample", []) if v is not None]
                samples = [v for v in stats["sample"] if v is not None]
                if len(values) >= 30 and len(samples) >= 30:
                    result = ks_2samp(values, samples)
                    if result.statistic > 0.30 and result.pvalue < 0.01:
                        add(
                            "numeric_drift",
                            col,
                            float(result.statistic),
                            "KS effect size <= 0.30 or p >= 0.01",
                            "Two-sample KS on bounded samples",
                            {
                                "p_value": float(result.pvalue),
                                "effect_size": float(result.statistic),
                                "baseline_n": len(values),
                                "current_n": len(samples),
                            },
                        )
    metric_keys = set().union(*(h.get("metrics", {}) for h in baseline))
    for key in metric_keys:
        if not key.startswith("revenue:") or key == "revenue:Unmatched":
            continue
        values = [h.get("metrics", {}).get(key, 0) for h in baseline]
        center, lo, hi = robust_bounds(values, 0.40, 100)
        value = current.get("metrics", {}).get(key, 0)
        if not lo <= value <= hi:
            add(
                "business_metric",
                key,
                value,
                f"{lo:.2f} to {hi:.2f}",
                "Country revenue robust baseline",
                {"baseline": center, "delta_pct": round((value - center) / max(center, 1) * 100, 2)},
                "critical",
            )
    return anomalies


def health_score(quality_results, anomalies):
    components = {
        k: 100.0
        for k in ("freshness", "completeness", "validity", "uniqueness", "schema", "volume", "distribution")
    }
    categories = {"not_null": "completeness", "unique": "uniqueness", "schema": "schema", "volume": "volume"}
    cap = 100
    for kind, severity, result in quality_results:
        if not result.passed:
            category = categories.get(kind, "validity")
            score = 0 if result.status == "error" else max(0, 100 * (1 - min(1, result.observed)))
            components[category] = min(components[category], score)
            if severity == "critical":
                cap = min(cap, 59)
    categories = {
        "schema_drift": "schema",
        "volume": "volume",
        "duplicates": "uniqueness",
        "null_spike": "completeness",
        "distribution_drift": "distribution",
        "numeric_drift": "distribution",
        "freshness": "freshness",
        "business_metric": "validity",
        "pipeline_failure": "freshness",
    }
    for anomaly in anomalies:
        components[categories.get(anomaly["kind"], "validity")] = min(
            components[categories.get(anomaly["kind"], "validity")], 30
        )
        cap = min(cap, 49 if anomaly["severity"] == "critical" else 79)
    weights = {
        "freshness": 0.20,
        "completeness": 0.15,
        "validity": 0.15,
        "uniqueness": 0.10,
        "schema": 0.15,
        "volume": 0.10,
        "distribution": 0.15,
    }
    score = round(min(cap, sum(components[k] * weights[k] for k in weights)), 1)
    return score, components
