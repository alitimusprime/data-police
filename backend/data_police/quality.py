import re
from dataclasses import dataclass

import polars as pl


RULE_KINDS = {"not_null", "unique", "accepted", "range", "pattern", "reference", "schema", "volume"}


@dataclass
class Evaluation:
    passed: bool
    observed: float
    expected: str
    failed_count: int
    sample: list
    status: str = "evaluated"


def validate_rule(kind, column, params):
    if kind not in RULE_KINDS:
        raise ValueError("Unsupported rule type")
    if kind not in {"schema", "volume"} and not column:
        raise ValueError("This rule requires a column")
    if kind == "accepted" and (
        not isinstance(params.get("values"), list) or not params["values"] or len(params["values"]) > 100
    ):
        raise ValueError("Accepted values requires a nonempty list of at most 100 values")
    if kind == "range":
        if "min" not in params and "max" not in params:
            raise ValueError("Range requires min or max")
        for field in ("min", "max"):
            if field in params and not isinstance(params[field], (int, float)):
                raise ValueError("Range bounds must be numbers")
        if params.get("min", float("-inf")) > params.get("max", float("inf")):
            raise ValueError("Range min must not exceed max")
    if kind == "pattern":
        pattern = params.get("pattern", "")
        if not isinstance(pattern, str) or not 1 <= len(pattern) <= 200:
            raise ValueError("Pattern length must be 1 to 200")
        try:
            re.compile(pattern)
            # Polars uses a linear-time regex engine without catastrophic backtracking.
            pl.Series(["test"]).str.contains(pattern)
        except Exception:
            raise ValueError("Unsupported or invalid regular expression") from None
    if kind == "reference" and not all(
        isinstance(params.get(k), str) and params[k] for k in ("dataset", "column")
    ):
        raise ValueError("Reference rules require a dataset and column")
    if kind == "schema" and not (
        isinstance(params.get("columns"), list)
        and all(isinstance(x, str) for x in params["columns"])
        and params["columns"]
    ):
        raise ValueError("Schema rules require a nonempty columns list")
    if kind == "schema" and "types" in params:
        if not isinstance(params["types"], dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in params["types"].items()
        ):
            raise ValueError("Schema types must map column names to type strings")
    if kind == "volume":
        lower, upper = params.get("min", 1), params.get("max", 10**12)
        if type(lower) is not int or type(upper) is not int or lower < 0 or upper < lower:
            raise ValueError("Volume bounds must be nonnegative integers with min <= max")


def evaluate(rule, frame, references):
    kind, col, params = rule.kind, rule.column, rule.params
    count = frame.height
    if kind == "schema":
        missing = sorted(set(params["columns"]) - set(frame.columns))
        mismatched = {
            k: v
            for k, v in params.get("types", {}).items()
            if k in frame.schema and str(frame.schema[k]) != v
        }
        bad = len(missing) + len(mismatched)
        return Evaluation(
            bad == 0, bad, "Required columns and configured types must match", bad, missing + list(mismatched)
        )
    if kind == "volume":
        lower, upper = params.get("min", 1), params.get("max", 10**12)
        return Evaluation(
            lower <= count <= upper,
            count,
            f"{lower} <= rows <= {upper}",
            0 if lower <= count <= upper else count,
            [],
        )
    if col not in frame.columns:
        return Evaluation(False, 1, f"Column {col} must exist", count, [], "error")
    column = pl.col(col)
    if kind == "not_null":
        mask, expected = column.is_null(), "Null rate must equal 0"
    elif kind == "unique":
        # Count extra occurrences, not every member of a duplicate group.
        bad = count - frame[col].n_unique()
        return Evaluation(bad == 0, bad / max(count, 1), "Duplicate excess must equal 0", bad, [])
    elif kind == "accepted":
        mask, expected = (
            (~column.is_in(params["values"])).fill_null(True),
            f"Value must be one of {params['values']}",
        )
    elif kind == "range":
        numeric = column.cast(pl.Float64, strict=False)
        mask = (
            numeric.is_null()
            | (numeric < params.get("min", float("-inf")))
            | (numeric > params.get("max", float("inf")))
        )
        expected = f"Value within [{params.get('min', '-inf')}, {params.get('max', 'inf')}]"
    elif kind == "pattern":
        mask, expected = (
            (~column.cast(pl.String).str.contains(params["pattern"])).fill_null(True),
            "Value must match the configured pattern",
        )
    elif kind == "reference":
        ref = references.get(params["dataset"])
        if ref is None or params["column"] not in ref.columns:
            return Evaluation(False, 1, "Reference dataset and column must be available", count, [], "error")
        values = ref[params["column"]].drop_nulls().implode()
        mask, expected = (
            (~column.is_in(values)).fill_null(True),
            f"Value must exist in {params['dataset']}.{params['column']}",
        )
    else:
        raise ValueError("Unknown rule")
    failed = frame.filter(mask)
    # Do not persist row payloads or customer information in evidence.
    samples = (
        []
        if "email" in (col or "").lower() or "customer" in (col or "").lower()
        else failed.select(col).head(5).to_series().to_list()
    )
    return Evaluation(failed.height == 0, failed.height / max(count, 1), expected, failed.height, samples)
