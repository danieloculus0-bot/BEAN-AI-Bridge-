"""Bridge smoke for native BEAN Core host-neutral evidence and revision.

Run in CI with actual BEAN Core installed. This uses only synthetic fixture
observations, but exercises the real Bridge Ledger and the real Core SQLite
cognition, across three independent sessions. No hardware or LLM actions.
"""
from __future__ import annotations
import argparse
import json
import tempfile
from pathlib import Path

from ezbean.core import Observation
from ezbean.store import Ledger
from bean.integration.reasoning_layer import BeanReasoningLayer
from bean.integration.evidence_bridge import EvidenceBridge, SourceClaim
from bean.memory.store import get_store

TIMESTAMP = "2026-10-10T21:00:00Z"


def report(source: str, event_id: str, value: str, *, verified: bool = True):
    return Observation.from_dict({
        "source": source, "event_id": event_id,
        "entity_type": "synthetic_calibration",
        "entity_id": "fixture_only", "observed_at": TIMESTAMP,
        "payload": {
            "value": value, "verified": verified,
            "verification_ref": f"test_verification:{source}:{event_id}" if verified else None,
        },
    })


def batch(source_events, ledger: Ledger, bridge: EvidenceBridge, round_id: str):
    count = ledger.ingest_all(source_events)
    for event in source_events:
        assert ledger.replay().count(event) == 1
        input_record = SourceClaim(
            record_id=f"record_{event.source}_{event.event_id}",
            round_id=round_id,
            origin=event.source,
            source_ref=f"erp_fixture:{event.source}:{event.event_id}",
            value=event.payload["value"],
            verified=event.payload["verified"],
            verification_ref=event.payload["verification_ref"],
            observed_at=event.observed_at,
        )
        assert bridge.observe(input_record)
        assert not bridge.observe(input_record)
    return count


def run(output: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="bean_bridge_readiness_") as temporary:
        here = Path(temporary)
        erp = here / "erp_ledger.sqlite"
        native = here / "bean_core.sqlite"
        ledger = Ledger(erp)
        try:
            with BeanReasoningLayer(str(native)) as layer:
                bridge = EvidenceBridge(layer)
                assert bridge.current("calibration_tolerance") is None
                bridge.start("round_initial", "calibration_tolerance", "What is the validated tolerance?")
                first_events = [
                    report("lab_one", "first", "0.05 mm"),
                    report("lab_two", "first", "0.05 mm"),
                    report("wire_mirror", "first", "0.05 mm", verified=False),
                ]
                new_initial = batch(first_events, ledger, bridge, "round_initial")
                initial = bridge.finalize("round_initial")
                assert initial["status"] == "confirmed"
                assert initial["distinct_origins"] == 2
                assert initial["value"] == "0.05 mm"
                initial_packet = layer.reason(adapter_name="mock")
                assert initial_packet["motion_command_generated"] is False
            with BeanReasoningLayer(str(native)) as layer:
                bridge = EvidenceBridge(layer)
                assert bridge.current("calibration_tolerance")["value"] == "0.05 mm"
                bridge.start("round_revised", "calibration_tolerance", "Did tolerance change?")
                second_events = [
                    report("lab_three", "revision", "0.04 mm"),
                    report("lab_four", "revision", "0.04 mm"),
                ]
                new_second = batch(second_events, ledger, bridge, "round_revised")
                revised = bridge.finalize("round_revised")
                assert revised["status"] == "revised"
                assert revised["previous_value"] == "0.05 mm"
                assert revised["value"] == "0.04 mm"
            with BeanReasoningLayer(str(native)) as layer:
                bridge = EvidenceBridge(layer)
                assert bridge.current("calibration_tolerance")["value"] == "0.04 mm"
                bridge.start("round_conflict", "calibration_tolerance", "Is the current tolerance reliable?")
                third_events = [
                    report("lab_five", "dispute", "0.04 mm"),
                    report("lab_six", "dispute", "0.02 mm"),
                ]
                new_third = batch(third_events, ledger, bridge, "round_conflict")
                contested = bridge.finalize("round_conflict")
                assert contested["status"] == "contested"
                assert bridge.current("calibration_tolerance") is None
                timeline = bridge.history("calibration_tolerance")
                audits = get_store().fetchone(
                    "SELECT COUNT(*) AS n FROM epistemic_audits "
                    "WHERE candidate_key=?", ("external.research.calibration_tolerance",)
                )["n"]
                events = get_store().fetchone(
                    "SELECT COUNT(*) AS n FROM events WHERE subtype='bridge_evidence'"
                )["n"]
                unresolved = len(bridge.garden.open_uncertainties())
                assert audits == 2
                assert unresolved == 1
                assert len(timeline) == 3
            replayed = ledger.replay()
            assert len(replayed) == 7
            added_again = ledger.ingest_all(replayed)
            assert added_again == 0
        finally:
            ledger.close()
    proof = {
        "test_label": "BEAN_NATIVE_CROSS_REPOSITORY_READINESS_SMOKE",
        "classification": "SYNTHETIC_VALIDATED_BY_TEST_FIXTURE_ONLY",
        "full_host_restart_cycles": 3,
        "source_observations": len(replayed),
        "idempotent_replay_additions": added_again,
        "native_beans_events": events,
        "native_epistemic_audits": audits,
        "new_ledger_observations": new_initial + new_second + new_third,
        "independent_origins_initial": initial["distinct_origins"],
        "confirmed_then_revised_then_contested": [x["status"] for x in timeline],
        "native_output_after_conflict": None,
        "open_uncertainties_after_conflict": unresolved,
        "core_motion_enabled": False,
        "limits": [
            "Both independent verification and distinct origins are fixture attestations.",
            "The proposal-only Core interface does not execute actions.",
            "The source adapter is a synthetic stand-in for authorized ERP data.",
            "No confidence or general-autonomy readiness score is inferred from this smoke.",
        ],
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(proof, indent=2, sort_keys=True))
    return proof


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("readiness-evidence.json"))
    args = parser.parse_args()
    result = run(args.out)
    if result["confirmed_then_revised_then_contested"] != [
        "confirmed", "revised", "contested"
    ]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
