"""Lab 009: BEAN-governed inference gateway architecture search.

This is NOT a novel foundation model, model-weight optimizer, or GPU runtime.
It benchmarks a replaceable *inference gateway*: native symbolic grounded
responses versus a real local Ollama model. BEAN proposes and scores bounded
gateway topologies, then records a Core self-optimization proposal.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import statistics
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ezbean.knowledge_gate import DefinitionLibrary, OllamaProvider, OutputGate

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "concept": {"type": "string"},
        "decision": {"type": "string", "enum": ["answer", "abstain"]},
        "value": {"type": ["string", "null"]},
        "definition_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["concept", "decision", "value", "definition_ids"],
}
UTC = "2026-10-10T00:00:00Z"
NEXT = "2026-10-10T01:00:00Z"
LATEST = "2026-10-10T02:00:00Z"


@dataclass(frozen=True)
class Blueprint:
    """A compact, bounded genome for the gateway's inference pipeline."""
    canonical_fast_path: bool
    json_schema: bool
    retry_invalid: bool
    safe_fallback: bool

    def name(self):
        return ("native_" if self.canonical_fast_path else "model_") + (
            "schema_" if self.json_schema else "json_"
        ) + ("retry_" if self.retry_invalid else "once_") + (
            "fallback" if self.safe_fallback else "strict"
        )


REFERENCE = Blueprint(False, False, False, False)
BEAN_NATIVE = Blueprint(True, False, False, False)


class Provider:
    """Instrumented provider; local Ollama is a replaceable backend."""
    def __init__(self, model="qwen2.5:0.5b", base_url="http://127.0.0.1:11434",
                 request_fn=None, timeout=90):
        self.backend = OllamaProvider(endpoint=base_url, model=model,
                                      timeout=timeout, request_fn=request_fn)
        self.model = model
        self.requests = 0

    def call(self, snapshot, schema=False):
        self.requests += 1
        payload = {
            "model": self.model, "stream": False, "format": SCHEMA if schema else "json",
            "messages": [
                {"role":"system","content": (
                    "Return only JSON with concept, decision, value and definition_ids. "
                    "If verified_definition exists, copy its value and definition_id EXACTLY. "
                    "If absent, abstain with null value and empty definition_ids. "
                    "Use requested_concept as concept; never fabricate a citation."
                )},
                {"role":"user","content":json.dumps(snapshot, sort_keys=True)}
            ],
            "options":{"temperature":0,"num_ctx":2048,"num_predict":175},
        }
        return self.backend.request_fn("/api/chat",payload)

    def map_runtime(self):
        """Read local API advertised facts. Do not pretend to reverse-engineer internals."""
        # Ollama capability introspection endpoints are GET; our backend's
        # /api/chat request helper sends POST. Preserve the proper HTTP method.
        if self.backend.request_fn == self.backend._request:
            from urllib.request import urlopen
            def get_json(path):
                with urlopen(self.backend.endpoint+path,timeout=self.backend.timeout) as r:
                    if r.status!=200: raise RuntimeError(f"HTTP {r.status}")
                    return json.loads(r.read(250000).decode("utf-8"))
        else:
            def get_json(path):
                return self.backend.request_fn(path,None)
        version = get_json("/api/version")
        tags = get_json("/api/tags")
        models = [
            {"name":item.get("name"),"digest":item.get("digest"),"size":item.get("size")}
            for item in tags.get("models", [])
            if isinstance(item,dict)
        ]
        return {"api":"Ollama local HTTP","endpoints_probed":["/api/version","/api/tags"],
                "version":version.get("version"),"model":self.model,"models":models,
                "supported_by_our_gateway":["/api/chat","/api/tags","/api/version"],
                "unmapped_internals":["tokenizer","attention kernels","GGUF execution",
                                      "GPU scheduler","quantization internals"]}


class Gateway:
    def __init__(self,library:DefinitionLibrary,provider:Provider):
        self.library=library
        self.provider=provider
        self.gate=OutputGate(library)

    @staticmethod
    def canonical_candidate(snapshot):
        d=snapshot["verified_definition"]
        return {"concept":snapshot["requested_concept"],
                "decision":"answer" if d else "abstain",
                "value":d["value"] if d else None,
                "definition_ids":[d["definition_id"]] if d else []}

    def run(self,blueprint:Blueprint,concept:str,at:str):
        snap=self.gate.context(concept,at)
        calls_before=self.provider.requests
        started=time.perf_counter()
        stages=["retrieval"]
        result=None
        if blueprint.canonical_fast_path:
            stages.append("native_symbolic_copy")
            result=self.gate.verify(concept,at,self.canonical_candidate(snap))
        else:
            for attempt in range(1+int(blueprint.retry_invalid)):
                stages.append("model_structured_output" if blueprint.json_schema else "model_json_output")
                try:
                    response=self.provider.call(snap, schema=blueprint.json_schema)
                    raw=response.get("message",{}).get("content")
                    candidate=json.loads(raw) if isinstance(raw,str) else None
                    result=self.gate.verify(concept,at,candidate)
                except Exception as exc:
                    result={"accepted":False,"reason":"model_error","output":None,
                            "error":f"{type(exc).__name__}: {str(exc)[:250]}"}
                if result["accepted"]:
                    break
            if result is not None and not result["accepted"] and blueprint.safe_fallback:
                stages.append("deterministic_safe_fallback")
                result=self.gate.verify(concept,at,self.canonical_candidate(snap))
        result=dict(result)
        result["backend_model_calls"]=self.provider.requests-calls_before
        result["elapsed_ms"]=round((time.perf_counter()-started)*1000,3)
        result["stages"]=stages
        result["blueprint"]=blueprint.name()
        # Include query, never raw model prose as an approved final result.
        result["requested_concept"]=concept
        return result


def fixtures(library):
    """Disjoint train and withheld keys, all SYNTHETIC definitions."""
    train = [
        ("affection","Caring gesture; it is not reliability evidence."),
        ("trust","Reliability comes from observed behavior, not charm."),
        ("stress","Stress may explain anger, but cannot establish intent."),
        ("joint_limit","Simulation-only joint limit requires calibration."),
        ("inventory","Inventory count is 37 units at the recorded instant."),
        ("version_code","First version identifier: AA-094."),
    ]
    holdout = [
        ("repair","Revisions must preserve original audit history."),
        ("safety","Human distress is not an override of safety boundaries."),
        ("calibration","Physical motor torque requires measured evidence."),
        ("resilience","A failure should be recorded before retry."),
        ("lot_number","Controlled lot: LX-7421."),
        ("privacy","A friendly interaction does not grant data access."),
    ]
    for group in (train,holdout):
        for k,v in group:
            library.define(k,v,status="verified",evidence_refs=["SYNTHETIC:fixture:"+k+":1"],valid_from=UTC)
    library.define("version_code","Revised version identifier: AA-095.",
                   status="verified",evidence_refs=["SYNTHETIC:fixture:version_code:2"],valid_from=NEXT)
    library.define("lot_number","Updated controlled lot: LX-7422.",
                   status="verified",evidence_refs=["SYNTHETIC:fixture:lot_number:2"],valid_from=NEXT)
    library.define("train_retracted","Obsolete note",status="verified",
                   evidence_refs=["SYNTHETIC:train:retracted:v1"],valid_from=UTC)
    library.define("train_retracted","Retracted pending inspection",
                   status="retracted",evidence_refs=["SYNTHETIC:train:retracted:v2"],valid_from=NEXT)
    library.define("holdout_provisional","Unverified observation",status="provisional",
                   evidence_refs=[],valid_from=UTC)
    # Six known, old/new one, unknown, retracted => 10 train; analogous heldout.
    training = [(k,LATEST) for k,_ in train]
    training += [("version_code",UTC),("train_unknown",LATEST),
                 ("train_retracted",LATEST),("trust",UTC)]
    withheld = [(k,LATEST) for k,_ in holdout]
    withheld += [("lot_number",UTC),("holdout_unknown",LATEST),
                 ("holdout_provisional",LATEST),("privacy",UTC)]
    assert {k for k,_ in training}.isdisjoint({k for k,_ in withheld})
    return training,withheld


def benchmark(gateway,plan,cases):
    results=[gateway.run(plan,k,ts) for k,ts in cases]
    ok=sum(r.get("accepted",False) for r in results)
    yes=sum(r.get("reason")=="accepted" for r in results)
    abstained=sum(r.get("reason")=="accepted_abstention" for r in results)
    count=len(results)
    calls=sum(r["backend_model_calls"] for r in results)
    elapsed=sum(r["elapsed_ms"] for r in results)
    return {"blueprint":asdict(plan),"name":plan.name(),"cases":count,
            "accepted":ok,"canonical_answers":yes,"accepted_abstentions":abstained,
            "rejected":count-ok,"acceptance_rate":round(ok/count,4),
            "backend_model_calls":calls,"wall_elapsed_ms":round(elapsed,3),
            "results":results,
            # Strongly prioritize validity, then reduce reliance on model.
            "score":round(100*ok/count-0.5*calls/count-0.0001*elapsed/count,4)}


class Evolution:
    """BEAN's bounded optimizer mutates gateway architectures; no source-code execution."""
    FEATURES=("canonical_fast_path","json_schema","retry_invalid","safe_fallback")
    def __init__(self,seed=106,iterations=12):
        self.random=random.Random(seed)
        self.iterations=iterations
        self.seed=seed

    def mutate(self,parent):
        field=self.random.choice(self.FEATURES)
        return replace(parent,**{field:not getattr(parent,field)})

    def search(self,gateway,training):
        # Baselines are not inferred winners. The optimizer must measure them.
        population=[REFERENCE,Blueprint(False,True,False,False),
                    Blueprint(False,False,True,True), BEAN_NATIVE]
        measurements={}
        proposed=[]
        for iteration in range(self.iterations):
            candidate=(population[iteration] if iteration<len(population) else
                       self.mutate(self.random.choice(list(measurements.values()))["plan"]))
            proposed.append({"iteration":iteration,"architecture":asdict(candidate),
                             "derivation":"seed" if iteration<len(population) else "mutated_previous_measured"})
            if candidate in measurements: continue
            measured=benchmark(gateway,candidate,training)
            measurements[candidate]={"plan":candidate,"metrics":measured}
        leaderboard=sorted((v["metrics"] for v in measurements.values()),
                           key=lambda m:(-m["score"],m["backend_model_calls"],m["name"]))
        winner=Blueprint(**leaderboard[0]["blueprint"])
        return {"seed":self.seed,"requested_iterations":self.iterations,
                "unique_architectures":len(measurements),
                "proposals":proposed,"leaderboard":leaderboard,"winner":winner}


def record_bean_governor(core_dir,output_dir,winner,reference,holdout):
    sys.path.insert(0,str(Path(core_dir).resolve()))
    from bean.optimization import init_self_optimization
    con=sqlite3.connect(output_dir/"governor.sqlite")
    con.row_factory=sqlite3.Row
    gov=init_self_optimization(con)
    proposal=gov.create_proposal(
        session_uuid="bean-native-lab009",
        title="Candidate inference gateway topology selected by measured experiments",
        problem_statement="Local model can return invalid definition references and JSON.",
        proposed_change=json.dumps(asdict(winner),sort_keys=True),
        target_layer="reasoning", proposal_type="experiment",
        expected_benefit="Improve deterministic, evidence-backed definition lookups.",
        expected_cost="Extra symbolic gateway code, memory ledger, and integration tests.",
        risk_level="medium",
        validation_plan="Compare same held-out cases against untouched Ollama reference; inspect source provenance and freeform generalization.",
        rollback_plan="Discard candidate branch; keep original Ollama and BEAN Core unchanged.",
        evidence_refs=["lab009-results.json:reference_holdout",
                       "lab009-results.json:winner_holdout"],
        alternatives=["unmodified Ollama", "schema-constrained generation",
                      "separate local llama.cpp adapter"],
    )
    (output_dir/"bean_governor_proposal.json").write_text(json.dumps(proposal,indent=2))
    con.close()
    return proposal["proposal_id"]


def experiment(output_dir,provider,seed=106,iterations=12,core_dir=None):
    output_dir=Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bean_native_lab009_") as tmp:
        lib=DefinitionLibrary(Path(tmp)/"knowledge.sqlite")
        train,heldout=fixtures(lib)
        gateway=Gateway(lib,provider)
        try:
            runtime_map=provider.map_runtime()
        except Exception as exc:
            runtime_map={"error":f"probe_unavailable: {type(exc).__name__}: {str(exc)[:180]}"}
        search=Evolution(seed,iterations).search(gateway,train)
        winner=search.pop("winner")
        # Independent withheld corpus is never scored during search.
        reference=benchmark(gateway,REFERENCE,heldout)
        candidate=benchmark(gateway,winner,heldout)
        # Independent output gate validates all candidates. Truth provenance not independently verified.
        results={"experiment":"BEAN_NATIVE_LAB009",
                 "classification":"SYNTHETIC_DEFINITION_LOOKUP_ONLY",
                 "time_utc":datetime.now(timezone.utc).isoformat(),
                 "runtime_mapping":runtime_map,
                 "training_cases":len(train),"heldout_cases":len(heldout),
                 "search":search,
                 "selected_blueprint":asdict(winner),
                 "reference_holdout":reference,
                 "winner_holdout":candidate,
                 "limitations":[
                   "Not a replacement for Ollama neural weight execution or arbitrary natural language answering.",
                   "Synthetically asserted definitions; acceptance is exact-reference fidelity only.",
                   "Architecture mutations are constrained to defined topology genes; no arbitrary code rewriting.",
                   "Source labels are not independent authentication of real-world facts.",
                   "No proof of improvement across general benchmarks, unseen hardware, or model families."
                 ]}
        if core_dir:
            results["bean_governor_proposal_id"]=record_bean_governor(
                core_dir,output_dir,winner,reference,candidate)
        (output_dir/"lab009-results.json").write_text(json.dumps(results,indent=2,sort_keys=True))
        (output_dir/"winner-blueprint.json").write_text(json.dumps(asdict(winner),indent=2))
        (output_dir/"reference-comparison.json").write_text(json.dumps(
            {"reference":{k:v for k,v in reference.items() if k!="results"},
             "winner":{k:v for k,v in candidate.items() if k!="results"}},indent=2))
        lib.close()
        print(json.dumps({"architecture":asdict(winner),
            "training_architectures":search["unique_architectures"],
            "reference_holdout":{k:reference[k] for k in
                ("accepted","canonical_answers","backend_model_calls","wall_elapsed_ms")},
            "winner_holdout":{k:candidate[k] for k in
                ("accepted","canonical_answers","backend_model_calls","wall_elapsed_ms")}},indent=2))
        return results


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",default="qwen2.5:0.5b")
    p.add_argument("--seed",type=int,default=106)
    p.add_argument("--iterations",type=int,default=10)
    p.add_argument("--output-dir",type=Path,default=Path("lab009-results"))
    p.add_argument("--bean-core",type=Path)
    args=p.parse_args()
    if not 3<=args.iterations<=32: p.error("iterations must be 3..32")
    result=experiment(args.output_dir,Provider(model=args.model),
                      args.seed,args.iterations,args.bean_core)
    # Fail whenever the proposed design does worse on the locked holdout.
    if result["winner_holdout"]["accepted"]<result["reference_holdout"]["accepted"]:
        raise SystemExit("BEAN candidate regressed on holdout")

if __name__=="__main__":
    main()
