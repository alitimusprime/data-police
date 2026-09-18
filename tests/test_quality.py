from types import SimpleNamespace

import polars as pl
import pytest

from data_police.profiling import profile_frame
from data_police.quality import evaluate, validate_rule


def rule(kind, column="x", params=None):
    return SimpleNamespace(kind=kind, column=column, params=params or {})


def test_nulls():
    result = evaluate(rule("not_null"), pl.DataFrame({"x": [1, None, 3]}), {})
    assert result.failed_count == 1
    assert result.observed == pytest.approx(1 / 3)


def test_duplicates_counts_excess_not_group_members():
    result = evaluate(rule("unique"), pl.DataFrame({"x": [1, 1, 1, 2]}), {})
    assert result.failed_count == 2
    assert result.observed == 0.5


@pytest.mark.parametrize(
    "kind,params,values,bad",
    [
        ("range", {"min": 0, "max": 10}, [-1, 3, 14, None], 3),
        ("accepted", {"values": ["PK", "US"]}, ["PK", "PAK", None], 2),
        ("pattern", {"pattern": "^[A-Z]{2}$"}, ["PK", "PAK", "1"], 2),
    ],
)
def test_rule_categories(kind, params, values, bad):
    assert evaluate(rule(kind, params=params), pl.DataFrame({"x": values}), {}).failed_count == bad


def test_missing_column_is_error_not_success():
    result = evaluate(rule("not_null"), pl.DataFrame({"other": [1]}), {})
    assert not result.passed and result.status == "error"


def test_reference_null_and_invalid():
    frame = pl.DataFrame({"x": [1, 2, None]})
    result = evaluate(
        rule("reference", params={"dataset": "ref", "column": "key"}),
        frame,
        {"ref": pl.DataFrame({"key": [1]})},
    )
    assert result.failed_count == 2


def test_schema_removed():
    assert not evaluate(rule("schema", params={"columns": ["x", "y"]}), pl.DataFrame({"x": [1]}), {}).passed


def test_profile_empty_and_mixed():
    frame = pl.DataFrame({"x": [1, None, 3], "country_code": ["PK", "PK", "US"]})
    result = profile_frame(frame)
    assert result["row_count"] == 3
    assert result["columns"]["x"]["mean"] == 2
    assert result["columns"]["country_code"]["distribution"] == {"PK": 2, "US": 1}
    assert profile_frame(pl.DataFrame(schema={"x": pl.Int64}))["row_count"] == 0


@pytest.mark.parametrize(
    "kind,column,params",
    [
        ("python", "x", {}),
        ("range", "x", {}),
        ("range", "x", {"min": 5, "max": 2}),
        ("accepted", "x", {"values": []}),
        ("not_null", None, {}),
        ("pattern", "x", {"pattern": "["}),
    ],
)
def test_rule_validation_rejects_invalid_input(kind, column, params):
    with pytest.raises(ValueError):
        validate_rule(kind, column, params)
