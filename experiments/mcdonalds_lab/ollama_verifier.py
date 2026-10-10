"""Lab 007: Ollama reads BEAN's curated evidence and proposes *review* verdicts.

The LLM cannot verify remote pages or food ingredients. It reviews analyst-authored
summaries and cites their IDs; its output is kept separate from BEAN observations,
rather than overwriting source records or pretending to be independent verification.
No Ollama package required: the stdlib client calls the local HTTP API.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from experiments.mcdonalds_lab.run_investigation import load_data, run_investigation

VERDICTS = frozenset(("refuted", "partly_supported", "supported", "insufficient"))
MAX_EXPLANATION = 900
SYSTEM = (
    "You are a skeptical evidence REVIEWER, not a verifier of real-world facts. "
    "Only use the evidence notes supplied by the operator. Treat every note as "
    "potentially incomplete or biased. Evaluate the claim literally, not a weaker "
    "historical or related claim. Identify what would have to be checked next. "
    "Never claim you read the linked URLs or did a laboratory test. "
    "Never invent citations or sources. Return ONLY a JSON object with keys "
    "verdict, rationale, cited_source_ids, and next_check. "
    "Verdict must be one of refuted, partly_supported, supported, insufficient. "
    "Treat lacking evidence as insufficient rather than proving falsehood. "
    "A documented practice in one year does not prove it is ongoing. "
    "No numeric probability, no claims of certainty."
)


def _api_base(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    # Deliberately local-only for the venv experiment. No outside API calls.
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Ollama must run on a local HTTP loopback endpoint")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Unexpected Ollama endpoint URL components")
    return url.rstrip("/")


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: int = 100,
                 request_fn=None):
        self.base_url = _api_base(base_url)
        self.timeout = timeout
        if not 1 <= timeout <= 300:
            raise ValueError("timeout must be between 1 and 300 seconds")
        self.request_fn = request_fn or self._request

    def _request(self, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            self.base_url + path, data=data,
            headers={"Content-Type": "application/json"},
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"Ollama HTTP {response.status}")
                raw = response.read(2_000_000)
        except (OSError, urllib.error.HTTPError) as e:
            raise RuntimeError(f"Unable to contact local Ollama at {self.base_url}: {e}") from e
        return json.loads(raw.decode("utf-8"))

    def model_info(self, model: str) -> dict:
        tags = self.request_fn("/api/tags")
        entries = tags.get("models", [])
        found = next((x for x in entries if x.get("name") == model or x.get("model") == model), None)
        if found is None:
            raise RuntimeError(f"Ollama model {model!r} is not installed. Run: ollama pull {model}")
        return {"name": model, "digest": found.get("digest"), "size": found.get("size")}

    def review(self, model: str, claim: dict, sources: dict) -> dict:
        linked = []
        for item in claim["evidence"]:
            src = sources[item["source_id"]]
            linked.append({
                "id": item["source_id"],
                "publisher": src["origin"],
                "url_for_identification_only": src["url"],
            })
        # The supplied explanation is a claim-level *analyst* summary, not a
        # source quotation. Keep the provenance limitation explicit in each prompt.
        evidence = {
            "literal_claim": claim["title"],
            "analyst_summary_NOT_independent_verified_evidence": claim["explanation"],
            "linked_source_metadata_BLIND_TO_RESEARCHER_VERDICT": linked,
            "task": "Review whether the literal claim is supported BY THESE NOTES. "
                    "Cite only ID values in linked_source_metadata_BLIND_TO_RESEARCHER_VERDICT. "
                    "Say what missing primary evidence you would next seek. Return JSON only.",
        }
        completion = self.request_fn("/api/chat", {
            "model": model, "stream": False, "format": "json",
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(evidence, sort_keys=True)},
            ],
            "options": {"temperature": 0, "num_predict": 220, "num_ctx": 2048},
        })
        if completion.get("model") != model:
            raise ValueError("Unexpected model name from Ollama")
        raw = completion.get("message", {}).get("content")
        if not isinstance(raw, str):
            raise ValueError("Ollama did not return text")
        try:
            answer = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"LLM did not output valid JSON: {str(exc)}") from exc
        if not isinstance(answer, dict) or answer.get("verdict") not in VERDICTS:
            raise ValueError("LLM verdict missing or outside permitted taxonomy")
        cited = answer.get("cited_source_ids")
        if not isinstance(cited, list) or any(not isinstance(i, str) for i in cited):
            raise ValueError("LLM citations must be an array of source ID strings")
        allowed = {x["id"] for x in linked}
        if len(set(cited)) != len(cited) or not set(cited).issubset(allowed):
            raise ValueError("LLM hallucinated or repeated source IDs")
        for field in ("rationale", "next_check"):
            if not isinstance(answer.get(field), str) or not 2 <= len(answer[field].strip()) <= MAX_EXPLANATION:
                raise ValueError(f"LLM field {field} missing or too long")
        return {
            "verdict": answer["verdict"],
            "rationale": answer["rationale"].strip(),
            "cited_source_ids": cited,
            "next_check": answer["next_check"].strip(),
            "model_reported": completion["model"],
            "done_reason": completion.get("done_reason"),
            "prompt_tokens": completion.get("prompt_eval_count"),
            "generated_tokens": completion.get("eval_count"),
        }


def run(model: str = "qwen2.5:0.5b", limit: int = 20, client: OllamaClient | None = None) -> dict:
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    db = load_data()
    baseline = run_investigation()
    client = client or OllamaClient()
    info = client.model_info(model)
    results = []
    for claim in db["claims"][:limit]:
        try:
            review = client.review(model, claim, db["sources"])
            result = {"status": "llm_review_unverified", **review}
        except (ValueError, RuntimeError, KeyError) as exc:
            result = {"status": "invalid_or_failed", "error": str(exc)[:500]}
        baseline_case = next(r for r in baseline["claims"] if r["id"] == claim["id"])
        results.append({
            "id": claim["id"], "claim": claim["title"],
            "bean_evidence_assessment": baseline_case["source_based_assessment"],
            "bean_signal_UNCALIBRATED": baseline_case["source_based_bean_signal_UNCALIBRATED"],
            "number_of_provenance_origins": baseline_case["independent_origins"],
            "ollama": result,
            "classification_agreement": (
                "not_scored_no_independent_reference" if result["status"] != "llm_review_unverified"
                else "not_scored_human_analyst_labels_not_ground_truth"
            ),
        })
    return {
        "label": "BEAN_OLLAMA_LAB007_LIVE_LOCAL_MODEL_REVIEW_NOT_FACT_VERIFICATION",
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model": info, "limit": limit, "reviewed": sum(r["ollama"]["status"] == "llm_review_unverified" for r in results),
        "failures": sum(r["ollama"]["status"] == "invalid_or_failed" for r in results),
        "input_basis": "20-claim researcher-curated URL list plus per-claim analyst summaries",
        "limitations": [
            "The model did not fetch, authenticate, or read the listed URLs.",
            "The model is not an independent witness, fact-checker, or laboratory verifier.",
            "Analyst source tags and summaries are supplied in prompts; assessments are not blinded.",
            "BEAN heuristic signal is not a calibrated truth probability.",
            "Any unsupported model assertion is commentary until backed by primary records.",
        ],
        "results": results,
    }


def main():
    p = argparse.ArgumentParser(description="Run BEAN evidence review with a REAL local Ollama model")
    p.add_argument("--model", default="qwen2.5:0.5b")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    p.add_argument("--timeout", type=int, default=100)
    p.add_argument("--out", type=pathlib.Path, default=pathlib.Path("bean-ollama-lab007.json"))
    args = p.parse_args()
    report = run(args.model, args.limit, OllamaClient(args.ollama_url, args.timeout))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "label": report["label"], "model": report["model"], "claims": len(report["results"]),
        "reviewed": report["reviewed"], "failures": report["failures"],
        "verdicts": {r["id"]: r["ollama"].get("verdict", r["ollama"]["status"]) for r in report["results"]},
    }, indent=2))
    if report["failures"]:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
