"""LAB 009: closed-loop, reproducible evidence learning with real BEAN Core.

Three distinct stages:
  1. broken LLM outputs and stale or missing library entries;
  2. host-supplied, independently checked synthetic source observations;
  3. a different set of requests at a later time, plus a previously unseen
     concept. Accuracy is scored against a private fixture oracle.

No external facts are authenticated and no model weights are updated.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from ezbean.knowledge_gate import DefinitionLibrary
from ezbean.learning_loop import SourceObservation, EvidenceLearningLoop, CoreEvidenceJournal

T0 = "2026-10-10T00:00:00Z"
T1 = "2026-10-10T02:00:00Z"
T2 = "2026-10-10T04:00:00Z"

# The oracle is in the evaluator and is never sent to the language provider.
TRUTH = {
    "sensor_tolerance": "±0.05 V measured at 25 C",
    "calibration_code": "HX-00742",
    "novel_capacitance": "47 nF",
}


class FixedWrongModel:
    """A demonstrably unchanged model that hallucinates a citation each call."""

    def __init__(self):
        self.calls = 0

    def complete(self, prompt):
        self.calls += 1
        return {"message": {"content": json.dumps({
            "concept": prompt["requested_concept"],
            "decision": "answer",
            "value": "UNSUPPORTED_MODEL_GUESS",
            "definition_ids": ["invented@1"],
        })}}


class SyntheticSourceInvestigator:
    """Produces source reports but does not decide whether any are reliable."""

    def __init__(self, *, conflicting: bool = False):
        self.conflicting = conflicting
        self.requests = []

    def investigate(self, concept: str, question: str) -> list[SourceObservation]:
        self.requests.append({"concept": concept, "question": question})
        if concept == "unresolved_safety":
            return [
                SourceObservation("synthetic:unresolved:left", "origin_left", "safe"),
                SourceObservation("synthetic:unresolved:right", "origin_right", "unsafe"),
            ]
        if concept not in TRUTH:
            return []
        return [
            SourceObservation(f"synthetic:{concept}:lab", f"lab_{concept}", TRUTH[concept]),
            SourceObservation(f"synthetic:{concept}:inspection", f"inspection_{concept}", TRUTH[concept]),
            # A third-party duplicate may be recorded but never increase provenance count.
            SourceObservation(f"synthetic:{concept}:mirror", f"inspection_{concept}", TRUTH[concept]),
        ]


class SyntheticIndependentVerifier:
    """Fixture-only checking adapter; the model cannot query its hidden map."""

    def __init__(self):
        self.checks = 0

    def check(self, concept: str, observation: SourceObservation) -> bool:
        self.checks += 1
        if concept == "unresolved_safety":
            return observation.ref in {
                "synthetic:unresolved:left", "synthetic:unresolved:right"
            }
        # A source is approved only if the expected exact reference, claimed
        # value and correct declared origin all match trusted fixture evidence.
        expected_origins = {f"lab_{concept}", f"inspection_{concept}"}
        return (
            concept in TRUTH and
            observation.value == TRUTH[concept] and
            observation.origin in expected_origins and
            observation.ref.startswith(f"synthetic:{concept}:")
        )


def run(output: Path, *, base_dir: Path | None = None) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bean_lab009_") as sandbox:
        working = base_dir if base_dir is not None else Path(sandbox)
        working.mkdir(parents=True, exist_ok=True)
        library_path = working / "evidence_library.sqlite"
        core_path = working / "native_bean_core.sqlite"
        model = FixedWrongModel()
        investigator = SyntheticSourceInvestigator()
        verifier = SyntheticIndependentVerifier()
        lib = DefinitionLibrary(library_path)
        if not lib.history("calibration_code"):
            lib.define("calibration_code", "HX-00621",
                       status="verified", evidence_refs=["synthetic:obsolete:v1"],
                       valid_from=T0)
        native = CoreEvidenceJournal(str(core_path))
        loop = EvidenceLearningLoop(lib, investigator=investigator, verifier=verifier,
                                    journal=native)

        # Prior to new evidence, old key is stale and other concepts absent.
        baseline = {
            c: (lib.lookup(c, T1)[0].value if lib.lookup(c, T1)[0] else None)
            for c in ("sensor_tolerance", "calibration_code", "novel_capacitance")
        }

        investigated = [
            asdict(loop.process(model, "sensor_tolerance", T1)),
            asdict(loop.process(model, "calibration_code", T1, refresh=True)),
            asdict(loop.process(model, "unresolved_safety", T1)),
        ]
        unresolved = investigated[-1]

        # Close and reopen both durable databases: no in-memory trick.
        packet_before_restart = native.context()
        native_events_before = len(native.recorded)
        native.close()
        lib.close()
        lib = DefinitionLibrary(library_path)
        native = CoreEvidenceJournal(str(core_path))
        loop = EvidenceLearningLoop(lib, investigator=investigator, verifier=verifier,
                                    journal=native)

        # Held out in time: questions arrive at T2, with one novel concept
        # never used in the first learning episodes.
        evaluation_concepts = ["sensor_tolerance", "calibration_code", "novel_capacitance"]
        before_correct = sum(baseline[c] == TRUTH[c] for c in evaluation_concepts)
        heldout = [
            asdict(loop.process(model, "sensor_tolerance", T2)),
            asdict(loop.process(model, "calibration_code", T2)),
            asdict(loop.process(model, "novel_capacitance", T2)),
        ]
        after_correct = sum(r["system_answer"] == TRUTH[r["concept"]] for r in heldout)
        model_correct = sum(bool(r["model_accepted"]) for r in heldout)
        final_history = loop.history()
        native_packet = native.context()
        native_records = native.store.fetchone(
            "SELECT COUNT(*) AS n FROM events WHERE subtype='research_learning_loop'"
        )["n"]
        native_audits = native.store.fetchone(
            "SELECT COUNT(*) AS n FROM epistemic_audits WHERE candidate_key LIKE 'research.loop.%'"
        )["n"]
        pending = len(native.garden.open_uncertainties())
        definitions = {
            c: [asdict(x) for x in lib.history(c)]
            for c in evaluation_concepts + ["unresolved_safety"]
        }
        native.close()
        lib.close()

    report = {
        "label": "BEAN_LAB009_BOUNDED_EXPERIENCE_LEARNING_NATIVE_CORE",
        "classification": "SYNTHETIC_EVIDENCE_NO_AUTHENTICATED_LIVE_SOURCES",
        "baseline": baseline,
        "pre_restart_learning": investigated,
        "post_restart_heldout": heldout,
        "heldout_metrics": {
            "cases": len(heldout), "baseline_correct": before_correct,
            "system_correct_after": after_correct,
            "model_accepted_after": model_correct,
            "system_accuracy_before": before_correct / len(heldout),
            "system_accuracy_after": after_correct / len(heldout),
            "model_success_after": model_correct / len(heldout),
        },
        "ledger": {
            "cycles_after_restart": len(final_history),
            "definition_revisions": definitions,
            "native_bean_events": native_records,
            "native_bean_epistemic_audits": native_audits,
            "open_uncertainties_after_reboot": pending,
            "native_event_count_pre_restart": native_events_before,
            "native_packet_pre_restart": packet_before_restart["packet_id"],
            "native_packet_post_restart": native_packet["packet_id"],
            "canonical_origin_visible": bool(native_packet["origin"].get("version")),
            "body_output_enabled": native_packet["body_output_status"]["enabled"],
        },
        "investigation_budget": {"verifier_checks": verifier.checks,
                                 "investigation_requests": len(investigator.requests)},
        "limits": [
            "All evidence is synthetic and truth is known only to the fixture verifier.",
            "Model weights do not change. Improved system accuracy is deterministic knowledge retrieval, not LLM learning.",
            "The trusted verifier is provided by the host; live source authenticity, independence and ownership require separate validation.",
            "The held-out requests are later-time and include a novel concept, but reuse synthetic source-generation rules.",
            "This is a bounded research batch, not a permanent running process.",
            "A recorded uncertainty may be reopened by future observations, not terminally discarded.",
        ],
    }
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "label": report["label"], "metrics": report["heldout_metrics"],
        "native_events": native_records, "native_epistemic_audits": native_audits,
        "native_origin_visible": report["ledger"]["canonical_origin_visible"],
        "unresolved_status": unresolved["result_status"],
        "model_calls": model.calls,
    }, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("lab009-evidence.json"))
    args = parser.parse_args()
    result = run(args.out)
    metrics = result["heldout_metrics"]
    if (metrics["system_correct_after"] <= metrics["baseline_correct"]
            or not result["ledger"]["native_bean_events"]
            or not result["ledger"]["native_bean_epistemic_audits"]
            or result["ledger"]["body_output_enabled"]):
        raise SystemExit("Missing measured improvement, durable evidence or safety boundary")


if __name__ == "__main__":
    main()
