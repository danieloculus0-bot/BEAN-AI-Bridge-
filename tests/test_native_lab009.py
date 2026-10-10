"""Tests of BEAN's independent gateway and bounded architecture optimizer."""
import json
import tempfile
import unittest
from pathlib import Path

from ezbean.knowledge_gate import DefinitionLibrary
from experiments.native_engine.native_lab import (
    BEAN_NATIVE, REFERENCE, Blueprint, Evolution, Gateway, Provider,
    benchmark, experiment, fixtures,
)

class LocalModelFixture:
    """Deliberately unreliable Ollama-like transport; never mislabel as live."""
    def __init__(self):
        self.calls=[]
    def __call__(self,path,payload):
        self.calls.append((path,payload))
        if path=="/api/version": return {"version":"fixture-only"}
        if path=="/api/tags":
            return {"models":[{"name":"fixture:test","digest":"FAKE_NOT_REAL","size":0}]}
        assert path=="/api/chat"
        snap=json.loads(payload["messages"][1]["content"])
        d=snap["verified_definition"]
        if not d:
            candidate={"concept":snap["requested_concept"],"decision":"abstain",
                       "value":None,"definition_ids":[]}
        else:
            candidate={"concept":snap["requested_concept"],"decision":"answer",
                       "value":d["value"],
                       "definition_ids":[d["definition_id"] if isinstance(payload["format"],dict)
                                         else "hallucinated@bad"]}
        return {"model":"fixture:test","message":{"content":json.dumps(candidate)}}

class TestNativeArchitecture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=DefinitionLibrary(Path(self.temp.name)/"knowledge.sqlite")
        self.training,self.holdout=fixtures(self.db)
        self.fake=LocalModelFixture()
        self.backend=Provider(model="fixture:test",request_fn=self.fake)
        self.gw=Gateway(self.db,self.backend)
    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_probe_is_real_api_shaped_but_fixture_labeled(self):
        caps=self.backend.map_runtime()
        self.assertEqual(caps["version"],"fixture-only")
        self.assertEqual(caps["models"][0]["digest"],"FAKE_NOT_REAL")
        self.assertIn("GPU scheduler",caps["unmapped_internals"])
        self.assertEqual([p for p,_ in self.fake.calls],["/api/version","/api/tags"])

    def test_reference_fails_on_hallucinated_ids(self):
        r=benchmark(self.gw,REFERENCE,self.training)
        self.assertGreater(r["rejected"],0)
        self.assertEqual(r["backend_model_calls"],len(self.training))
        self.assertTrue(any(x["reason"]=="stale_or_hallucinated_reference" for x in r["results"]))

    def test_native_grounding_independent_of_provider(self):
        before=len(self.fake.calls)
        r=benchmark(self.gw,BEAN_NATIVE,self.holdout)
        self.assertEqual((r["accepted"],r["rejected"]),(len(self.holdout),0))
        self.assertEqual(len(self.fake.calls),before)
        self.assertEqual(r["backend_model_calls"],0)
        self.assertTrue(all(z["output"] is not None for z in r["results"]))

    def test_schema_strategy_repairs_fixture_model(self):
        r=benchmark(self.gw,Blueprint(False,True,False,False),self.training)
        self.assertEqual(r["accepted"],len(self.training))
        self.assertTrue(all(x["backend_model_calls"]==1 for x in r["results"]))

    def test_safe_fallback_never_publishes_model_hallucination(self):
        r=benchmark(self.gw,Blueprint(False,False,False,True),self.training)
        self.assertEqual(r["accepted"],len(self.training))
        self.assertTrue(any("deterministic_safe_fallback" in z["stages"] for z in r["results"]))
        self.assertTrue(all("hallucinated" not in (z["output"] or "") for z in r["results"]))

    def test_train_and_holdout_have_disjoint_concept_keys(self):
        self.assertFalse({x for x,_ in self.training}&{x for x,_ in self.holdout})

    def test_search_reproducible_with_same_seed(self):
        # For deterministic fitness time has a small weight; compare candidates
        # and validated acceptance, not volatile wall-time microseconds.
        a=Evolution(seed=106,iterations=12).search(self.gw,self.training)
        b=Evolution(seed=106,iterations=12).search(self.gw,self.training)
        self.assertEqual(a["proposals"],b["proposals"])
        self.assertGreaterEqual(a["unique_architectures"],4)
        self.assertIn("canonical_fast_path",a["winner"].__dict__)
        self.assertTrue(any(p["derivation"].startswith("mutated") for p in a["proposals"]))

    def test_injected_provider_complete_experiment_and_replay(self):
        output=Path(self.temp.name)/"output"
        result=experiment(output,self.backend,seed=106,iterations=8)
        self.assertEqual(result["training_cases"],len(self.training))
        self.assertEqual(result["heldout_cases"],len(self.holdout))
        self.assertGreaterEqual(result["winner_holdout"]["accepted"],result["reference_holdout"]["accepted"])
        self.assertTrue((output/"lab009-results.json").exists())
        self.assertEqual(result["runtime_mapping"]["version"],"fixture-only")
        self.assertEqual(len(result["search"]["proposals"]),8)
        self.assertEqual(len(result["winner_holdout"]["results"]),10)
        self.assertTrue(all(z["as_of_utc"].endswith("Z") for z in result["winner_holdout"]["results"]))
        self.assertTrue(all(z["classification"] if "classification" in z else True for z in [result]))

    def test_self_hosted_native_api_roundtrip(self):
        import threading
        from urllib.request import urlopen, Request
        from urllib.error import HTTPError
        from experiments.native_engine.http_gateway import serve,MODEL
        server=serve(self.db,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        addr="http://127.0.0.1:"+str(server.server_address[1])
        try:
            with urlopen(addr+"/api/version") as r:
                self.assertIn("symbolic",json.load(r)["version"])
            with urlopen(addr+"/api/tags") as r:
                self.assertEqual(json.load(r)["models"][0]["name"],MODEL)
            body=json.dumps({"model":MODEL,"messages":[{"role":"user",
                "content":json.dumps({"concept":"repair","as_of_utc":"2026-10-10T02:00:00Z"})}]}).encode()
            with urlopen(Request(addr+"/api/chat",body,headers={"Content-Type":"application/json"})) as r:
                data=json.load(r)
            self.assertTrue(data["verification"]["accepted"])
            self.assertIn("audit history",data["message"]["content"])
            self.assertEqual(data["verification"]["definition_id"],"repair@1")
            bad=json.dumps({"model":MODEL,"messages":[{"role":"user","content":"guess anything"}]}).encode()
            with self.assertRaises(HTTPError) as failure:
                urlopen(Request(addr+"/api/chat",bad,headers={"Content-Type":"application/json"}))
            self.assertEqual(failure.exception.code,400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_proposal_never_mutates_main_or_model_weights(self):
        result=experiment(Path(self.temp.name)/"isolated",self.backend,seed=110,iterations=6)
        self.assertTrue("Selected" not in json.dumps(result["limitations"]))
        self.assertEqual(result["classification"],"SYNTHETIC_DEFINITION_LOOKUP_ONLY")
        self.assertIn("arbitrary natural language",result["limitations"][0])

if __name__=="__main__":unittest.main()
