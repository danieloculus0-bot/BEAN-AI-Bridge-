"""BEAN Investigation 001: curated public evidence for 20 McDonald's food claims.

This is a REAL run of the BEAN Lab 005 agent and BEAN Core AttentionFilter,
using researcher-selected public sources, NOT autonomous live browser fetching,
not a scientific food assay and not a calibrated probability model.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from experiments.search_lab.confidence_search import ConfidenceSearchAgent, Page, SearchPolicy

DATA_PATH = Path(__file__).with_name("claims.json")

def load_data():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))

def run_investigation():
    db = load_data()
    agent = ConfidenceSearchAgent(SearchPolicy(max_fetches=8, max_audits=0))
    records = []
    for claim in db["claims"]:
        agent.reset()
        linked = []
        for ix, entry in enumerate(claim["evidence"], start=1):
            src = db["sources"][entry["source_id"]]
            agent.inspect(Page(
                page_id=f"claim{claim['id']:02d}_source{ix}",
                stream=src["stream"], origin=src["origin"],
                stance=int(entry["stance"]), relevance=0.95,
                methodology=float(src["methodology"]),
                freshness=float(src["freshness"]),
            ))
            linked.append({
                "id": entry["source_id"], "url": src["url"],
                "origin": src["origin"],
                "stance": "supports" if entry["stance"] else "refutes",
                "classification": src["stream"],
            })
        signal = agent.belief()
        origins = {e["origin"] for e in linked}
        manufacturer_only = all(e["origin"] == "mcdonalds.com" for e in linked)
        next_check = ("Obtain independent direct inspection or records" if manufacturer_only
                      else "Find additional independent primary records" if len(origins) < 2
                      else "Check key sources against original records and challenge existing verdict")
        records.append({
            "id": claim["id"], "claim": claim["title"],
            "source_based_assessment": claim["assessment"],
            "reason": claim["explanation"],
            "sources_seen": len(linked),
            "independent_origins": len(origins),
            "source_based_bean_signal_UNCALIBRATED": signal.predicted_probability,
            "confidence_is_verified": signal.verified,
            "bean_attention_window_activated": any(t["challenge_attention"] for t in agent.trace),
            "sources": linked,
            "bean_reranking": agent.rerank(),
            "next_falsification_step": next_check,
        })
    return {
        "label": "BEAN_MCDONALDS_CURATED_EVIDENCE_REAL_CORE_RUN_NOT_LIVE_CRAWL",
        "as_of": db["metadata"]["as_of"],
        "experiment_source": "BEAN Lab 005 + BEAN Core AttentionFilter",
        "claim_count": len(records),
        "unique_source_urls": len({s["url"] for r in records for s in r["sources"]}),
        "evidence_links": sum(r["sources_seen"] for r in records),
        "limitations": [
            db["metadata"]["method"], db["metadata"]["limitation"],
            "BEAN signal is an experimental heuristic, not a measured probability of a conspiracy.",
            "None of the cases were independently lab-verified or evaluated by an autonomous live crawler.",
            "Absence of evidence differs from proof that a historical event never happened.",
            "Source-based classifications were set by human review; BEAN performs provenance-aware reranking.",
        ],
        "claims": records,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("mcdonalds-bean-001.json"))
    args = parser.parse_args()
    result = run_investigation()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "label": result["label"],
        "claim_count": result["claim_count"],
        "unique_source_urls": result["unique_source_urls"],
        "evidence_links": result["evidence_links"],
        "assessments": {x["id"]: x["source_based_assessment"] for x in result["claims"]},
    }, indent=2))

if __name__ == "__main__":
    main()
