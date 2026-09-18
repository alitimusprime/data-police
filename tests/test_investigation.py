import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from data_police.config import settings
from data_police.db import session_scope
from data_police.investigation import investigate, provider_evidence
from data_police.models import Incident, WorkspaceState
from data_police.pipeline import create_run, execute_run


def test_provider_packet_excludes_failed_values_and_nested_details():
    evidence = [
        SimpleNamespace(
            id=7,
            facts={
                "dataset": "raw_orders",
                "observed": 0.4,
                "expected": "No null values",
                "kind": "quality_failure",
                "details": {
                    "failed_rows": 4,
                    "total_rows": 10,
                    "sample_values": ["private@example.test"],
                    "nested": {"token": "private-token"},
                    "baseline": {"private@example.test": 3},
                },
            },
        )
    ]
    packet = provider_evidence(evidence)
    serialized = json.dumps(packet)
    assert "private@example.test" not in serialized
    assert "private-token" not in serialized
    assert packet[0]["facts"]["details"] == {"failed_rows": 4, "total_rows": 10}


@pytest.mark.parametrize("unknown_id", [False, True])
def test_ai_output_cannot_replace_verified_facts_or_cite_unknown_evidence(
    live_provider, monkeypatch, unknown_id
):
    with session_scope() as session:
        session.get(WorkspaceState, "simulator").value = {"scenario": "invalid_values"}
    execute_run(create_run(key="ai-contract-test"))
    with session_scope() as session:
        incident_id = session.scalar(select(Incident.id))
        original = investigate(session, incident_id).report
    generated = dict(original)
    generated["verified"] = [{"text": "Invented fact must never become verified", "evidence_ids": []}]
    generated["inference"] = [
        {"text": "Check the source contract", "evidence_ids": [999999] if unknown_id else []}
    ]

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            assert "/chat/completions" in url
            assert "sample_values" not in json.dumps(kwargs["json"])
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {"choices": [{"message": {"content": json.dumps(generated)}}]},
            )

    monkeypatch.setattr("data_police.investigation.httpx.Client", Client)
    monkeypatch.setattr(settings, "llm_base_url", "https://provider.example.test/v1")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    with session_scope() as session:
        if unknown_id:
            with pytest.raises(ValueError, match="unknown evidence ID"):
                investigate(session, incident_id, use_llm=True)
        else:
            result = investigate(session, incident_id, use_llm=True)
            assert result.report["verified"] == original["verified"]
            assert result.provider == "configured_llm"
