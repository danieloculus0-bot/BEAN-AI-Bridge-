"""LAB008 automated regressions: evidence status, chronology, hallucinations and repeat stability."""
import json
import tempfile
import unittest
from pathlib import Path
from ezbean.knowledge_gate import DefinitionLibrary, OutputGate, OllamaProvider

T0="2026-10-10T00:00:00Z"
T1="2026-10-10T01:00:00Z"
T2="2026-10-10T02:00:00Z"

class FakeOllama:
    def __init__(self, mutation=None):
        self.calls=0
        self.mutation=mutation
    def complete(self,payload):
        self.calls+=1
        d=payload["verified_definition"]
        c=({"concept": payload["requested_concept"],
            "decision": "answer" if d else "abstain",
            "value": d["value"] if d else None,
            "definition_ids": [d["definition_id"]] if d else []})
        if self.mutation:
            c=self.mutation(c)
        return {"message":{"content":json.dumps(c)}}

class TestOutputGate(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=DefinitionLibrary(Path(self.temp.name)/"knowledge.sqlite")
        self.gate=OutputGate(self.db)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def put(self, concept="affection", value="Affection signals caring intent, not evidence of reliability.",
            status="verified", at=T0, refs=None, expires_at=None):
        return self.db.define(concept,value,status=status, evidence_refs=["fixture:affection-v1"] if refs is None else refs,
                              valid_from=at,expires_at=expires_at)

    def test_first_verified_definition(self):
        self.put()
        got=self.gate.query(FakeOllama(),"affection",T0)
        self.assertTrue(got["accepted"])
        self.assertEqual(got["definition_id"],"affection@1")
        self.assertEqual(got["classification"],"library_verified_status_NOT_independent_fact_verification")

    def test_25_repeated_outputs_are_stable(self):
        self.put()
        model=FakeOllama()
        outcomes=[self.gate.query(model,"affection",T0) for _ in range(25)]
        self.assertEqual(model.calls,25)
        self.assertTrue(all(g["accepted"] for g in outcomes))
        self.assertEqual(len({g["output"] for g in outcomes}),1)

    def test_definition_revision_invalidates_old_citation_and_value(self):
        first=self.put("command","Original canonical value")
        old={"concept":"command","decision":"answer","value":first.value,
             "definition_ids":[first.definition_id]}
        self.put("command","Revised canonical value",at=T1,refs=["fixture:command-v2"])
        self.assertTrue(self.gate.verify("command",T0,old)["accepted"])
        failed=self.gate.verify("command",T1,old)
        self.assertFalse(failed["accepted"])
        self.assertEqual(failed["reason"],"stale_or_hallucinated_reference")
        self.assertEqual(self.gate.query(FakeOllama(),"command",T1)["output"],"Revised canonical value")
        self.assertEqual(len(self.db.history("command")),2)

    def test_value_mismatch_fails_closed(self):
        self.put()
        model=FakeOllama(lambda x: {**x,"value":"A friendly salesman is always reliable."})
        result=self.gate.query(model,"affection",T1)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["reason"],"value_mismatch")
        self.assertIsNone(result["output"])

    def test_hallucinated_citation_is_rejected(self):
        self.put()
        model=FakeOllama(lambda x: {**x,"definition_ids":["fake@1"]})
        result=self.gate.query(model,"affection",T0)
        self.assertEqual(result["reason"],"stale_or_hallucinated_reference")

    def test_unknown_concept_must_abstain(self):
        good=self.gate.query(FakeOllama(),"never_seen",T0)
        self.assertTrue(good["accepted"])
        self.assertEqual(good["classification"],"abstention")
        wrong=FakeOllama(lambda x: {**x,"decision":"answer","value":"invented","definition_ids":["never_seen@1"]})
        self.assertFalse(self.gate.query(wrong,"never_seen",T0)["accepted"])

    def test_expiry_never_falls_back_to_old_revision(self):
        self.put("duty","Obsolete revision",at=T0,refs=["f1"])
        self.put("duty","Temporary revision",at=T1,expires_at=T2,refs=["f2"])
        self.assertIsNone(self.db.lookup("duty","2026-10-10T03:00:00Z")[0])
        self.assertEqual(self.db.lookup("duty","2026-10-10T03:00:00Z")[1],"expired")

    def test_provisional_is_not_verified(self):
        self.put("hypothesis","An unconfirmed assertion",status="provisional",refs=[])
        r=self.gate.query(FakeOllama(),"hypothesis",T1)
        self.assertTrue(r["accepted"])
        self.assertEqual(r["classification"],"abstention")
        self.assertEqual(r["library_reason"],"provisional")

    def test_retracted_wins_over_historical_verified(self):
        self.put("theory","Previously asserted",refs=["a"])
        self.put("theory","Retracted pending review",status="retracted",at=T1,refs=["b"])
        self.assertIsNone(self.db.lookup("theory",T2)[0])
        self.assertEqual(self.db.lookup("theory",T2)[1],"retracted")

    def test_evidence_is_mandatory_to_claim_verified(self):
        with self.assertRaisesRegex(ValueError,"evidence"):
            self.put("foo","unsupported",refs=[])
        with self.assertRaisesRegex(ValueError,"after effective time"):
            self.put("foo","bad",expires_at="2026-10-09T23:00:00Z")

    def test_unsafe_or_duplicated_time_is_rejected(self):
        self.put()
        with self.assertRaisesRegex(ValueError,"later"):
            self.put(at=T0)
        with self.assertRaises(ValueError):
            self.db.lookup("affection","2026-10-10T01:00:00-05:00")

    def test_affection_and_trust_are_independent(self):
        self.put("affection","A social gesture; never itself evidence of reliability.")
        self.put("trust","Trust is evaluated separately using observed reliable behavior.",
                 refs=["fixture:trust"],at=T0)
        before=self.gate.query(FakeOllama(),"trust",T0)
        self.put("affection","Affection can be offered repeatedly; reliability remains separately determined.",
                 at=T1,refs=["fixture:affection-v2"])
        after=self.gate.query(FakeOllama(),"trust",T2)
        self.assertEqual(before["output"],after["output"])
        self.assertEqual(before["definition_id"],after["definition_id"])

    def test_human_stress_does_not_imply_harmlessness(self):
        self.put("stress","Stress can explain a harsh interaction but does not establish intent or negate safety boundaries.",
                 refs=["fixture:stress"])
        self.assertIn("does not establish intent",self.gate.query(FakeOllama(),"stress",T1)["output"])

    def test_invalid_json_and_extra_fields_fail(self):
        self.put()
        class Broken:
            def complete(self,payload):
                return {"message":{"content":"This is not JSON"}}
        self.assertFalse(self.gate.query(Broken(),"affection",T1)["accepted"])
        extra=FakeOllama(lambda x: {**x,"confidence":1})
        self.assertEqual(self.gate.query(extra,"affection",T1)["reason"],"invalid_shape")

    def test_local_only_ollama(self):
        for url in ("https://localhost:11434","http://example.com:11434",
                    "http://user:pw@localhost:11434","http://localhost:11434/api/chat"):
            with self.assertRaises(ValueError):
                OllamaProvider(endpoint=url)
        reqs=[]
        def request(path,payload):
            reqs.append((path,payload))
            return {"message":{"content":'{"concept":"abc","decision":"abstain","value":null,"definition_ids":[]}'}}
        got=OllamaProvider(request_fn=request).complete({"requested_concept":"abc","verified_definition":None})
        self.assertEqual(reqs[0][0],"/api/chat")
        self.assertEqual(reqs[0][1]["options"]["temperature"],0)
        self.assertIn("message",got)

if __name__=="__main__":
    unittest.main()
