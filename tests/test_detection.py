from types import SimpleNamespace

import polars as pl

from data_police.detection import detect, health_score
from data_police.lineage import distances, rank_candidates, related
from data_police.profiling import profile_frame
from data_police.quality import Evaluation


def test_cold_start_does_not_invent_baseline():
    p = profile_frame(pl.DataFrame({"x": range(100)}))
    assert detect(p, []) == []


def test_volume_drop_with_stable_baseline():
    p = profile_frame(pl.DataFrame({"x": range(100)}))
    current = profile_frame(pl.DataFrame({"x": range(35)}))
    assert any(a["kind"] == "volume" for a in detect(current, [p] * 10))


def test_country_value_change_is_not_schema_drift():
    p = profile_frame(pl.DataFrame({"country_code": ["PK"] * 30 + ["US"] * 70}))
    q = profile_frame(pl.DataFrame({"country_code": ["PAK"] * 30 + ["US"] * 70}))
    anomalies = detect(q, [p] * 10)
    assert any(a["kind"] == "distribution_drift" for a in anomalies)
    assert not any(a["kind"] == "schema_drift" for a in anomalies)


def test_removed_column_is_schema_drift_even_during_warmup():
    p = profile_frame(pl.DataFrame({"x": [1], "y": [2]}))
    q = profile_frame(pl.DataFrame({"x": [1]}))
    assert detect(q, [p])[0]["details"]["change"] == "removed"


def test_health_critical_cap():
    score, _ = health_score([("not_null", "critical", Evaluation(False, 0.001, "no nulls", 1, []))], [])
    assert score <= 59


def test_traversal_cycle_safe_and_directional():
    edges = [("a", "b"), ("b", "c"), ("c", "a"), ("c", "d")]
    assert distances("a", edges) == {"b": 1, "c": 2, "d": 3}
    assert not related("a", "unrelated", edges)


def test_ranking_prefers_upstream_evidence_and_sums():
    anomalies = [
        SimpleNamespace(id=1, dataset_id="raw", kind="quality_failure", severity="critical"),
        SimpleNamespace(id=2, dataset_id="fact", kind="null_spike", severity="critical"),
    ]
    ranking = rank_candidates(anomalies, [("raw", "fact")], {1: 1, 2: 2})
    assert ranking[0]["dataset_id"] == "raw"
    assert ranking[0]["score"] == sum(ranking[0]["contributions"].values())
