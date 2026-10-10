"""Integrated learning-loop tests: no model self-certification, real BEAN cognition."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ezbean.knowledge_gate import DefinitionLibrary
from ezbean.learning_loop import EvidenceLearningLoop, SourceObservation, CoreEvidenceJournal
from experiments.learning_loop.run_lab009 import (
    T0, T1, T2, FixedWrongModel, SyntheticSourceInvestigator,
    SyntheticIndependentVerifier, TRUTH, run,
)


class RepeatingInvestigator:
    def __init__(self, observations):
        self.observations = observations
        self.requests = 0

    def investigate(self, concept, question):
        self.requests += 1
        return self.observations


class AlwaysPassVerifier:
    def __init__(self):
        self.checks = 0

    def check(self, concept, observation):
        self.checks += 1
        return True


class FakeCorrectProvider:
    def complete(self, context):
        definition = context["verified_definition"]
        if definition:
            payload = {
                "concept": context["requested_concept"], "decision": "answer",
                "value": definition["value"], "definition_ids": [definition["definition_id"]],
            }
        else:
            payload = {"concept": context["requested_concept"], "decision": "abstain",
                       "value": None, "definition_ids": []}
        return {"message": {"content": json.dumps(payload)}}


class LearningLoopCases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.lib = DefinitionLibrary(self.path / "library.db")

    def tearDown(self):
        self.lib.close()
        self.temp.cleanup()

    def test_bad_model_never_certifies_itself(self):
        investigator = SyntheticSourceInvestigator()
        verifier = SyntheticIndependentVerifier()
        model = FixedWrongModel()
        loop = EvidenceLearningLoop(self.lib, investigator=investigator, verifier=verifier)
        r = loop.process(model, "sensor_tolerance", T1)
        self.assertEqual(r.investigation_status, "committed_verified_revision")
        self.assertFalse(r.model_accepted)
        self.assertEqual(r.system_answer, TRUTH["sensor_tolerance"])
        self.assertEqual(r.distinct_origins, 2)
        self.assertEqual(r.confirmed_sources, 3)
        self.assertEqual(len(self.lib.history("sensor_tolerance")), 1)
        self.assertEqual(loop.history()[0]["cycle_id"], r.cycle_id)

    def test_new_evidence_can_correct_stale_verified_definition(self):
        self.lib.define("calibration_code", "HX-00621", status="verified",
                        evidence_refs=["synthetic:old"], valid_from=T0)
        loop = EvidenceLearningLoop(self.lib, investigator=SyntheticSourceInvestigator(),
                                    verifier=SyntheticIndependentVerifier())
        r = loop.process(FakeCorrectProvider(), "calibration_code", T1, refresh=True)
        self.assertTrue(r.model_accepted)  # Model accepted *old* library snapshot!
        self.assertEqual(r.investigation_status, "committed_verified_revision")
        self.assertEqual(r.system_answer, "HX-00742")
        self.assertEqual([v.value for v in self.lib.history("calibration_code")],
                         ["HX-00621", "HX-00742"])
        self.assertEqual(self.lib.lookup("calibration_code", T0)[0].value, "HX-00621")
        self.assertEqual(self.lib.lookup("calibration_code", T2)[0].value, "HX-00742")

    def test_rechecking_correct_value_keeps_history_append_only(self):
        investigator = SyntheticSourceInvestigator()
        loop = EvidenceLearningLoop(self.lib, investigator=investigator,
                                    verifier=SyntheticIndependentVerifier())
        loop.process(FixedWrongModel(), "sensor_tolerance", T1)
        r = loop.process(FakeCorrectProvider(), "sensor_tolerance", T2, refresh=True)
        self.assertEqual(r.investigation_status, "corroborated_no_revision")
        self.assertEqual(len(self.lib.history("sensor_tolerance")), 1)
        self.assertEqual(investigator.requests[-1]["concept"], "sensor_tolerance")

    def test_two_conflicting_verified_origins_block_new_definition(self):
        self.lib.define("unresolved_safety", "unknown-old", status="verified",
                        evidence_refs=["synthetic:older"], valid_from=T0)
        loop = EvidenceLearningLoop(self.lib, investigator=SyntheticSourceInvestigator(),
                                    verifier=SyntheticIndependentVerifier())
        r = loop.process(FixedWrongModel(), "unresolved_safety", T1)
        self.assertEqual(r.investigation_status, "conflicting_verified_evidence")
        self.assertEqual(r.result_status, "unresolved")
        self.assertIsNone(r.system_answer)
        self.assertEqual(len(self.lib.history("unresolved_safety")), 1)

    def test_duplicate_origins_never_certify_a_new_claim(self):
        observations = [
            SourceObservation("ref:1", "one_publisher", "42"),
            SourceObservation("ref:2", "one_publisher", "42"),
            SourceObservation("ref:1", "one_publisher", "42"),
        ]
        verifier = AlwaysPassVerifier()
        loop = EvidenceLearningLoop(self.lib, investigator=RepeatingInvestigator(observations),
                                    verifier=verifier)
        r = loop.process(FixedWrongModel(), "concept_two", T1)
        self.assertEqual(r.investigation_status, "insufficient_verified_evidence")
        self.assertEqual(r.distinct_origins, 1)
        self.assertEqual(verifier.checks, 2)
        self.assertIsNone(r.system_answer)

    def test_unverified_or_model_provided_guesses_never_become_knowledge(self):
        observations = [
            SourceObservation("ref:1", "a", "INVENTED_BY_PROVIDER"),
            SourceObservation("ref:2", "b", "INVENTED_BY_PROVIDER"),
        ]
        class Deny:
            def check(self, concept, source): return False
        loop = EvidenceLearningLoop(self.lib, investigator=RepeatingInvestigator(observations),
                                    verifier=Deny())
        r = loop.process(FixedWrongModel(), "concept_three", T1)
        self.assertEqual(r.investigation_status, "insufficient_verified_evidence")
        self.assertEqual(self.lib.history("concept_three"), [])

    def test_invalid_verifier_return_is_rejected_not_promoted(self):
        class Dishonest:
            def check(self, c, s): return "verified"
        inv = RepeatingInvestigator([SourceObservation("ref:a", "first", "22")])
        loop = EvidenceLearningLoop(self.lib, investigator=inv, verifier=Dishonest())
        with self.assertRaises(TypeError):
            loop.process(FixedWrongModel(), "concept_four", T1)
        self.assertEqual(self.lib.history("concept_four"), [])

    def test_future_time_required_for_a_new_revision(self):
        self.lib.define("sensor_tolerance", "old", status="verified",
                        evidence_refs=["fixture:old"], valid_from=T1)
        loop = EvidenceLearningLoop(self.lib, investigator=SyntheticSourceInvestigator(),
                                    verifier=SyntheticIndependentVerifier())
        r = loop.process(FixedWrongModel(), "sensor_tolerance", T1, refresh=True)
        self.assertEqual(r.investigation_status, "requires_later_effective_time")
        self.assertEqual(self.lib.history("sensor_tolerance")[-1].value, "old")

    def test_learning_cycles_durable_after_reopen(self):
        loop = EvidenceLearningLoop(self.lib, investigator=SyntheticSourceInvestigator(),
                                    verifier=SyntheticIndependentVerifier())
        r = loop.process(FixedWrongModel(), "sensor_tolerance", T1)
        self.lib.close()
        new_db = DefinitionLibrary(self.path / "library.db")
        try:
            new_loop = EvidenceLearningLoop(new_db, investigator=SyntheticSourceInvestigator(),
                                            verifier=SyntheticIndependentVerifier())
            self.assertEqual(new_loop.history()[0]["cycle_id"], r.cycle_id)
            self.assertEqual(new_db.lookup("sensor_tolerance", T2)[0].value,
                             TRUTH["sensor_tolerance"])
        finally:
            new_db.close()
            # tearDown closes the original instance a second time; SQLite's
            # close operation is idempotent.


class LiveCoreTest(unittest.TestCase):
    def test_full_real_core_and_holdout_replay(self):
        with tempfile.TemporaryDirectory(prefix="bean_learning_test_") as tmp:
            report = run(Path(tmp) / "lab009.json")
            self.assertEqual(report["heldout_metrics"]["system_correct_after"], 3)
            self.assertEqual(report["heldout_metrics"]["model_accepted_after"], 0)
            self.assertEqual(report["heldout_metrics"]["baseline_correct"], 0)
            self.assertGreater(report["ledger"]["native_bean_events"], 0)
            self.assertGreater(report["ledger"]["native_bean_epistemic_audits"], 0)
            self.assertTrue(report["ledger"]["canonical_origin_visible"])
            self.assertFalse(report["ledger"]["body_output_enabled"])
            self.assertEqual(report["pre_restart_learning"][2]["result_status"], "unresolved")
            self.assertEqual(len(report["ledger"]["definition_revisions"]["unresolved_safety"]), 0)
            self.assertGreaterEqual(report["ledger"]["cycles_after_restart"], 6)
            self.assertTrue((Path(tmp) / "lab009.json").exists())


if __name__ == "__main__":
    unittest.main()
