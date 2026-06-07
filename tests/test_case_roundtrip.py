"""
Phase 1 gate — the Case entity round-trips through Cognee and accretes fields.

Run: uv run pytest tests/test_case_roundtrip.py -q
"""
from __future__ import annotations

import cognee_client as cognee
from ontology import AccountRole, Action, Case


def test_case_write_read_update(tmp_path, monkeypatch):
    # Isolate the JSON store to a temp file so we don't clobber a real run.
    import importlib
    monkeypatch.setattr(cognee, "_STORE_PATH", tmp_path / "store.json", raising=False)
    cognee._store = cognee._LocalStore()
    cognee.reset_store()

    # Agent 1 writes a Case.
    case = Case(
        account="AC-9999",
        role=AccountRole.RELAY,
        signals={"under_threshold": True, "relay_depth": 1},
        is_candidate=True,
        decoy_suspect=False,
        dist_stats={"amount_p50": 650.0},
        detect_reason="relay node forwarding under-threshold amounts",
    )
    cognee.write_case(case)

    got = cognee.read_case("AC-9999")
    assert got is not None
    assert got["role"] == "relay"            # enum serialized to value
    assert got["is_candidate"] is True
    assert got.get("p_mule") is None         # not set yet

    # Agent 2 accretes probability fields.
    cognee.update_case_fields("AC-9999", {
        "p_mule": 0.97,
        "credible_interval": [0.94, 0.99],
    })
    got2 = cognee.read_case("AC-9999")
    assert got2["p_mule"] == 0.97
    assert got2["credible_interval"] == [0.94, 0.99]

    # Agent 3 accretes an action (enum value serialized).
    cognee.update_case_fields("AC-9999", {"action": Action.ESCALATE})
    assert cognee.read_case("AC-9999")["action"] == "ESCALATE"

    # read_cases(candidates_only=True) finds it.
    cands = cognee.read_cases(candidates_only=True)
    assert any(c["account"] == "AC-9999" for c in cands)
