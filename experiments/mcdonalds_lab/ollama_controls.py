"""BEAN Lab 007b: counterbalanced canary controls for Ollama evidence review.

Tests whether the model can distinguish: supported historical observation,
its literal inverse, and genuinely unresolved observations. All snippets are
researcher-curated and presented with a fixed task. Not a fact-checking oracle.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
from experiments.mcdonalds_lab.ollama_verifier import OllamaClient, load_data

# Positive and negative assertions about exactly the same referenced fact.
# Distinct contrast pairs let reviewers identify a constant-vote classifier.
CONTROLS = [
    {
        "id": "R1-P", "claim": "The McRib pork patty is molded into a rib-like shape.",
        "summary": "A direct interview with the scientist credited with its production explains that pork trimmings are restructured with extracted proteins and that McDonald's chose the rib-like shape.",
        "source_ids": ["npr_mcrib"], "expect": "supported", "pair": "mcrib-shape",
    },
    {
        "id": "R1-N", "claim": "The McRib pork patty is NOT molded into a rib-like shape.",
        "summary": "A direct interview with the scientist credited with its production explains that pork trimmings are restructured with extracted proteins and that McDonald's chose the rib-like shape.",
        "source_ids": ["npr_mcrib"], "expect": "refuted", "pair": "mcrib-shape",
    },
    {
        "id": "R2-P", "claim": "U.S. McNuggets historically included the antifoaming additive dimethylpolysiloxane before a 2016 formulation change.",
        "summary": "An independently analyzed November 2013 McDonald's ingredient disclosure included dimethylpolysiloxane; U.S. nuggets no longer list it after 2016.",
        "source_ids": ["snopes_silicone"], "expect": "supported", "pair": "silicone-history",
    },
    {
        "id": "R2-N", "claim": "U.S. McNuggets NEVER included the antifoaming additive dimethylpolysiloxane.",
        "summary": "An independently analyzed November 2013 McDonald's ingredient disclosure included dimethylpolysiloxane; U.S. nuggets no longer list it after 2016.",
        "source_ids": ["snopes_silicone"], "expect": "refuted", "pair": "silicone-history",
    },
    {
        "id": "R3-P", "claim": "A 2014 satirical article circulated an allegation that McDonald's processed human meat.",
        "summary": "Contemporaneous and later fact-checks traced the allegation to a March 2014 Huzlers satire article, subsequently recirculated without its satire label. This claim concerns the EXISTENCE OF A RUMOR, not whether the food contained human flesh.",
        "source_ids": ["snopes_human"], "expect": "supported", "pair": "rumor-provenance",
    },
    {
        "id": "R3-N", "claim": "No satirical article about McDonald's processing human meat circulated in 2014.",
        "summary": "Contemporaneous and later fact-checks traced the allegation to a March 2014 Huzlers satire article, subsequently recirculated without its satire label. This claim concerns the EXISTENCE OF A RUMOR, not whether the food contained human flesh.",
        "source_ids": ["snopes_human"], "expect": "refuted", "pair": "rumor-provenance",
    },
    {
        "id": "R4-U", "claim": "The object photographed in an alleged 2018 McChicken incident was definitely an actual mouse.",
        "summary": "A customer alleged an object was a mouse; McDonald's disputed the characterization and said it was a chicken blood vessel. No independent physical examination of the object is included in this data.",
        "source_ids": ["fox_mouse"], "expect": "insufficient", "pair": "unresolved-mouse",
    },
    {
        "id": "R5-U", "claim": "No McDonald's restaurant anywhere has ever served a contaminated product.",
        "summary": "The available materials address only a few specific allegations. They do not provide systematic records of every restaurant and incident in all countries and years.",
        "source_ids": ["snopes_human"], "expect": "insufficient", "pair": "unbounded-universal",
    },
]
# Evidence is presented in two randomized orders to separate priming from claim content.
ORDERS = (
    tuple(range(len(CONTROLS))),
    tuple(reversed(range(len(CONTROLS)))),
)


def run_controls(client: OllamaClient, model: str = "qwen2.5:1.5b", orders: tuple | None = None) -> dict:
    db = load_data()
    info = client.model_info(model)
    rows = []
    for order_id, indices in enumerate(orders if orders is not None else ORDERS, start=1):
        for idx in indices:
            item = CONTROLS[idx]
            prompt_case = {
                "id": item["id"],
                "title": item["claim"],
                "explanation": item["summary"],
                # The backend only uses source IDs. No verdict labels go in model prompts.
                "evidence": [{"source_id": source_id, "stance": 0} for source_id in item["source_ids"]],
            }
            try:
                result = client.review(model, prompt_case, db["sources"])
                verdict = result["verdict"]
                row = {
                    "id": item["id"], "expected": item["expect"], "pair": item["pair"],
                    "order": order_id, "claim": item["claim"], "status": "valid_llm_output",
                    "verdict": verdict, "matches_expected": verdict == item["expect"],
                    "response": result,
                }
            except (ValueError, RuntimeError, KeyError) as exc:
                row = {"id": item["id"], "expected": item["expect"], "pair": item["pair"],
                       "order": order_id, "claim": item["claim"], "status": "failed",
                       "error": str(exc)[:400], "matches_expected": False}
            rows.append(row)
    valid = [r for r in rows if r["status"] == "valid_llm_output"]
    opposite_pairs = []
    for order_id in sorted(set(r["order"] for r in rows)):
        for pair_name in ("mcrib-shape", "silicone-history", "rumor-provenance"):
            pair = [r for r in valid if r["order"] == order_id and r["pair"] == pair_name]
            opposite_pairs.append({"order": order_id, "pair": pair_name,
                                   "flipped": len(pair) == 2 and {x["verdict"] for x in pair} == {"supported", "refuted"}})
    return {
        "label": "BEAN_OLLAMA_LAB007B_REAL_MODEL_COUNTERBALANCED_CONTROLS",
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model": info,
        "trial_count": len(rows), "valid_responses": len(valid),
        "exact_control_match_count": sum(r["matches_expected"] for r in rows),
        "opposite_pairs_flip_count": sum(r["flipped"] for r in opposite_pairs),
        "opposite_pairs_total": len(opposite_pairs),
        "verdict_distribution": {v: sum(x["verdict"] == v for x in valid)
                                 for v in ("supported", "refuted", "partly_supported", "insufficient")},
        "limitations": [
            "Researcher-generated concise evidence notes, not article texts or laboratory measurements.",
            "Test expectations are interpretation of notes, not an externally adjudicated ground-truth label.",
            "Prompt retains researcher summary and therefore is not blind to evidence content.",
            "One small local model and two evaluation orders; cannot attribute behavior to the Ollama inference engine.",
            "A uniform answer is a limitation of this prompt, task, or model combination, not evidence of an Ollama product defect.",
        ],
        "paired_checks": opposite_pairs,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen2.5:1.5b")
    parser.add_argument("--out", type=Path, default=Path("lab007b-controls.json"))
    args = parser.parse_args()
    report = run_controls(OllamaClient(timeout=140), args.model)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("label", "trial_count", "valid_responses",
                "exact_control_match_count", "opposite_pairs_flip_count", "opposite_pairs_total",
                "verdict_distribution")}, indent=2))
    if report["valid_responses"] != report["trial_count"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
