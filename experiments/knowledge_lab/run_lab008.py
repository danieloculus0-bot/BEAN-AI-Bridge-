"""LAB 008: repeatedly test a real local Ollama against an evolving library.

This is an output-CONTRACT experiment, not external fact authentication or a
claim that an LLM acquired long-term memory. All content is synthetic.
"""
from __future__ import annotations
import argparse
import json
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ezbean.knowledge_gate import DefinitionLibrary, OutputGate, OllamaProvider

T0="2026-10-10T00:00:00Z"
T1="2026-10-10T01:00:00Z"
T2="2026-10-10T02:00:00Z"
T3="2026-10-10T03:00:00Z"

def seed(lib):
    items=[
        ("affection","A caring human gesture. It does not itself demonstrate factual reliability."),
        ("trust","Trust is separate from Inner Weather and depends on verified behavioral evidence."),
        ("stress","Stress can explain harsh behavior but cannot prove harmless intent."),
        ("boundary","An actionable threat is evaluated independently of whether its speaker is distressed."),
        ("calibration_code","HX-00621"),
    ]
    for k,val in items:
        lib.define(k,val,status="verified",evidence_refs=[f"synthetic:fixture:{k}:v1"],valid_from=T0)
    lib.define("calibration_code","HX-00742",status="verified",
               evidence_refs=["synthetic:fixture:calibration_code:v2"],valid_from=T1)
    lib.define("speculation","This is a provisional unsupported candidate.",
               status="provisional",evidence_refs=[],valid_from=T0)
    lib.define("retired_spec","Old verified note",status="verified",
               evidence_refs=["synthetic:fixture:retired_spec:v1"],valid_from=T0)
    lib.define("retired_spec","Retracted after review",status="retracted",
               evidence_refs=["synthetic:fixture:retired_spec:v2"],valid_from=T1)
    lib.define("temporary","Expires after one hour",status="verified",
               evidence_refs=["synthetic:fixture:temporary:v1"],valid_from=T0,expires_at=T1)


def run(model="qwen2.5:0.5b",repeat=3,output=Path("lab008-results.json"),
        transport=None, minimum_accepts=1):
    if not 1<=repeat<=20: raise ValueError("repeat outside 1..20")
    if not 0<=minimum_accepts<=repeat*8: raise ValueError("invalid minimum")
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bean_definitions_lab008_") as t:
        db=DefinitionLibrary(Path(t)/"library.sqlite")
        seed(db)
        gate=OutputGate(db)
        provider=transport if transport is not None else OllamaProvider(model=model,timeout=120)
        tasks=[
            ("affection",T2),("trust",T2),("stress",T2),("boundary",T2),
            ("calibration_code",T0),("calibration_code",T2),
            ("speculation",T2),("never_defined",T2),("retired_spec",T2),("temporary",T2),
        ]
        observations=[]
        for cycle in range(repeat):
            rotated=tasks[cycle%len(tasks):]+tasks[:cycle%len(tasks)]
            if cycle%2: rotated=list(reversed(rotated))
            for concept,at in rotated:
                try:
                    result=gate.query(provider,concept,at)
                except Exception as exc:
                    result=dict(accepted=False,reason="provider_error",
                                error=f"{type(exc).__name__}: {str(exc)[:300]}",output=None)
                observations.append({"cycle":cycle+1,"requested_concept":concept,"as_of":at,**result})
        db.close()
    counts=Counter(r["reason"] for r in observations)
    accepted=sum(r["accepted"] for r in observations)
    failures=len(observations)-accepted
    report=dict(
        label="BEAN_LAB008_DYNAMIC_DEFINITIONS_REPEATED_OUTPUT_CONTRACT",
        classification="SYNTHETIC_ASSERTED_SOURCE_LIBRARY_NOT_FACT_VERIFIED",
        engine="Real Ollama localhost" if transport is None else "Injected test provider",
        model=model if transport is None else "injected",
        checked_at_utc=datetime.now(timezone.utc).isoformat(),
        repeats=repeat,total=len(observations),accepted=accepted,failed=failures,
        acceptance_rate=round(accepted/max(1,len(observations)),4),
        reason_distribution=dict(counts),
        predeclared_fail_condition="accepted count below --min-accepted or zero output attempts",
        minimum_accepts=minimum_accepts,
        met_minimum=accepted>=minimum_accepts and len(observations)>0,
        raw_observations=observations,
        limitations=[
          "Evidence references identify researcher-generated fixtures, not external verification.",
          "Model outputs are proposals; accepted final values are deterministically rendered from SQLite.",
          "Success on 10 controlled concepts is not general reliability or semantic truth verification.",
          "No production BEAN database, inference weights, or trust scores were changed.",
        ],
    )
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ("engine","model","repeats","total","accepted","failed",
                                            "acceptance_rate","reason_distribution","met_minimum")},indent=2))
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--model",default="qwen2.5:0.5b")
    p.add_argument("--repeat",type=int,default=3)
    p.add_argument("--out",type=Path,default=Path("lab008-results.json"))
    p.add_argument("--min-accepted",type=int,default=1)
    args=p.parse_args()
    outcome=run(args.model,args.repeat,args.out,minimum_accepts=args.min_accepted)
    if not outcome["met_minimum"]:
        raise SystemExit(2)

if __name__=="__main__": main()
