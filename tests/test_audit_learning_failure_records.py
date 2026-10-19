"""Audit: no unbounded source consumption or lost learning failures."""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ezbean.knowledge_gate import DefinitionLibrary
from ezbean.learning_loop import EvidenceLearningLoop, SourceObservation

T = "2026-10-19T11:00:00Z"


class NoModel:
    def complete(self, context):
        raise RuntimeError("No model needed for investigator stream tests")


class Verifier:
    def check(self, concept, source):
        return True


class Endless:
    def __init__(self):
        self.yielded = 0

    def investigate(self, concept, question):
        while True:
            self.yielded += 1
            yield SourceObservation(
                "synthetic:" + str(self.yielded),
                "publisher_" + str(self.yielded),
                "42",
            )


class Interrupted:
    def investigate(self, concept, question):
        yield SourceObservation("local:1", "a", "42")
        raise RuntimeError("interrupted synthetic investigation")


class FailsVerification:
    def investigate(self, concept, question):
        yield SourceObservation("local:1", "a", "42")


class BrokenVerifier:
    def check(self, concept, source):
        raise RuntimeError("synthetic verifier unavailable")


def test_unbounded_investigator_is_consumed_only_to_existing_max_sources(tmp_path):
    db = DefinitionLibrary(tmp_path / "definitions.db")
    try:
        investigator = Endless()
        loop = EvidenceLearningLoop(
            db, investigator=investigator, verifier=Verifier(),
            max_sources=2,
        )
        outcome = loop.process(NoModel(), "test_bounded_stream", T)
        assert investigator.yielded == 2
        assert outcome.investigation_status == "committed_verified_revision"
        assert len(loop.history()) == 1
        assert len(loop.history()[0]["observations"]) == 2
    finally:
        db.close()


@pytest.mark.parametrize(
    "investigator,verifier,error_message",
    [
        (Interrupted(), Verifier(), "interrupted synthetic investigation"),
        (FailsVerification(), BrokenVerifier(), "synthetic verifier unavailable"),
    ],
)
def test_exception_preserves_partial_evidence_and_durable_error(
    tmp_path, investigator, verifier, error_message,
):
    path = tmp_path / "experiments.db"
    db = DefinitionLibrary(path)
    try:
        loop = EvidenceLearningLoop(
            db, investigator=investigator, verifier=verifier,
        )
        with pytest.raises(RuntimeError, match=error_message):
            loop.process(NoModel(), "fail_then_learn", T)
        history = loop.history()
        assert len(history) == 1
        assert history[0]["investigation_status"] == "investigation_error"
        assert history[0]["result_status"] == "experiment_error"
        assert history[0]["observations"][-1]["error_type"] == "RuntimeError"
        if isinstance(investigator, Interrupted):
            assert history[0]["observations"][0]["ref"] == "local:1"
        assert loop.compile_evidence()["cycles"] == 1
    finally:
        db.close()

    # The episode remains after reopening from an entirely new process handle.
    new_db = DefinitionLibrary(path)
    try:
        restarted = EvidenceLearningLoop(
            new_db, investigator=investigator, verifier=verifier,
        )
        assert restarted.history()[0]["result_status"] == "experiment_error"
        assert restarted.compile_evidence()["investigation_results"]["investigation_error"] == 1
    finally:
        new_db.close()
