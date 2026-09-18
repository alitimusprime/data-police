import math

import polars as pl


def number(value):
    if value is None:
        return None
    result = float(value)
    return round(result, 6) if math.isfinite(result) else None


def profile_frame(frame: pl.DataFrame):
    count = frame.height
    columns = {}
    for name, dtype in frame.schema.items():
        series = frame[name]
        nonnull = series.drop_nulls()
        stats = {
            "type": str(dtype),
            "null_count": series.null_count(),
            "null_rate": series.null_count() / max(1, count),
            "distinct": nonnull.n_unique(),
        }
        if dtype.is_numeric():
            stats.update(
                {
                    "min": number(nonnull.min()),
                    "max": number(nonnull.max()),
                    "mean": number(nonnull.mean()),
                    "median": number(nonnull.median()),
                    "std": number(nonnull.std()),
                    "p05": number(nonnull.quantile(0.05)),
                    "p95": number(nonnull.quantile(0.95)),
                }
            )
            # A bounded deterministic sample is explicitly recorded as sampled, not full-population.
            if name in {"amount", "captured_amount", "quantity", "unit_price"}:
                stats["sample"] = [
                    number(v) for v in nonnull.sample(n=min(512, len(nonnull)), seed=17).to_list()
                ]
        elif dtype == pl.String:
            if stats["distinct"] <= 40:
                stats["distribution"] = {
                    str(row[name]): row["count"] for row in nonnull.value_counts().to_dicts()
                }
            if name.endswith("_at") or name == "date":
                stats.update({"min_timestamp": nonnull.min(), "max_timestamp": nonnull.max()})
        columns[name] = stats
    metrics = {}
    if "country_name" in frame.columns and "revenue" in frame.columns:
        for row in frame.to_dicts():
            metrics["revenue:" + str(row["country_name"])] = number(row["revenue"]) or 0
    if "reconciliation_delta" in frame.columns:
        metrics["reconciliation_failure_rate"] = frame.filter(
            pl.col("reconciliation_delta").abs() > 0.01
        ).height / max(1, count)
    if "revenue" in frame.columns:
        metrics["revenue_total"] = number(frame["revenue"].sum()) or 0
    return {
        "row_count": count,
        "column_count": frame.width,
        "duplicate_rate": (count - frame.unique().height) / max(1, count),
        "schema": {name: str(dtype) for name, dtype in frame.schema.items()},
        "columns": columns,
        "metrics": metrics,
    }
