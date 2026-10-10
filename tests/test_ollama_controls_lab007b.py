"""Lab 007b control-design tests; no actual LLM is involved in these unit tests."""
import json
from experiments.mcdonalds_lab.ollama_controls import CONTROLS, run_controls
from experiments.mcdonalds_lab.ollama_verifier import OllamaClient

def mock_transport(path, payload=None):
    if path == "/api/tags":
        return {"models": [{"name": "qwen2.5:1.5b", "digest": "mock-not-real"}]}
    item = json.loads(payload["messages"][1]["content"])
    assert "analyst_tag" not in str(item)
    claim = item["literal_claim"]
    if "definitely an actual mouse" in claim or "anywhere has ever" in claim:
        verdict = "insufficient"
    elif "NOT molded" in claim or "NEVER included" in claim or "No satirical article" in claim:
        verdict = "refuted"
    else:
        verdict = "supported"
    ids = [x["id"] for x in item["linked_source_metadata_BLIND_TO_RESEARCHER_VERDICT"]]
    return {"model": "qwen2.5:1.5b", "message": {"content": json.dumps({
        "verdict": verdict, "rationale": "The data supplied constrains the literal claim.",
        "cited_source_ids": ids, "next_check": "Review the cited primary record."
    })}}

def test_controls_cover_positive_negative_unresolved_and_pair_inversions():
    assert len(CONTROLS) == 8
    assert [c["expect"] for c in CONTROLS].count("supported") == 3
    assert [c["expect"] for c in CONTROLS].count("refuted") == 3
    assert [c["expect"] for c in CONTROLS].count("insufficient") == 2
    for pair in ("mcrib-shape", "silicone-history", "rumor-provenance"):
        group = [x for x in CONTROLS if x["pair"] == pair]
        assert len(group) == 2
        assert {x["expect"] for x in group} == {"supported", "refuted"}
        assert group[0]["summary"] == group[1]["summary"]

def test_controls_mock_demonstrates_flip_detection():
    report = run_controls(OllamaClient(request_fn=mock_transport))
    assert report["trial_count"] == 16
    assert report["valid_responses"] == 16
    assert report["exact_control_match_count"] == 16
    assert report["opposite_pairs_flip_count"] == 6
