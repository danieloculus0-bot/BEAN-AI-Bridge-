"""Unit tests use faked HTTP responses ONLY; live GitHub Actions separately uses Ollama."""
import json

import pytest
from experiments.mcdonalds_lab.ollama_verifier import OllamaClient, _api_base, load_data, run


def transport(path, payload=None):
    if path == "/api/tags":
        return {"models": [{"name": "qwen2.5:0.5b", "digest": "test-fixture", "size": 123}]}
    assert path == "/api/chat"
    assert payload["model"] == "qwen2.5:0.5b"
    assert payload["stream"] is False
    assert payload["format"] == "json"
    supplied = json.loads(payload["messages"][1]["content"])
    ids = [item["id"] for item in supplied["linked_source_metadata_and_researcher_tags"]]
    return {"model": "qwen2.5:0.5b", "message": {"content": json.dumps({
        "verdict": "insufficient", "rationale": "These notes do not directly authenticate the claim.",
        "cited_source_ids": ids[:1], "next_check": "Inspect the original primary records."
    })}, "eval_count": 42}


def test_loopback_only_and_rejects_credentialized_url():
    for url in ("https://localhost:11434", "http://example.com:11434",
                "http://user:pass@localhost:11434", "http://localhost:11434/api/chat"):
        with pytest.raises(ValueError):
            _api_base(url)
    assert _api_base("http://127.0.0.1:11434") == "http://127.0.0.1:11434"


def test_real_http_contract_with_mocked_server_response():
    client = OllamaClient(request_fn=transport)
    db = load_data()
    assert client.model_info("qwen2.5:0.5b")["digest"] == "test-fixture"
    row = client.review("qwen2.5:0.5b", db["claims"][0], db["sources"])
    assert row["verdict"] == "insufficient"
    assert row["cited_source_ids"][0] in db["sources"]


def test_invented_citations_rejected():
    def invent(path, payload=None):
        if path == "/api/tags":
            return transport(path, payload)
        return {"model": "qwen2.5:0.5b", "message": {"content": json.dumps({
            "verdict": "supported", "rationale": "Allegedly true.",
            "cited_source_ids": ["totally_invented_reference"], "next_check": "More data."
        })}}
    db = load_data()
    with pytest.raises(ValueError, match="hallucinated"):
        OllamaClient(request_fn=invent).review("qwen2.5:0.5b", db["claims"][0], db["sources"])


def test_bad_json_and_out_of_taxonomy_rejected():
    def bad(path, payload=None):
        return {"model": "qwen2.5:0.5b", "message": {"content": "I refuse JSON"}}
    db = load_data()
    with pytest.raises(ValueError, match="JSON"):
        OllamaClient(request_fn=bad).review("qwen2.5:0.5b", db["claims"][0], db["sources"])


def test_full_dataset_not_marked_verified():
    rows = run(model="qwen2.5:0.5b", limit=20, client=OllamaClient(request_fn=transport))
    assert rows["reviewed"] == 20
    assert rows["failures"] == 0
    assert all(r["ollama"]["status"] == "llm_review_unverified" for r in rows["results"])
    assert "did not fetch" in rows["limitations"][0]
    assert all(r["classification_agreement"].startswith("not_scored") for r in rows["results"])


def test_real_model_required_no_silent_mock_fallback():
    def empty_model_tags(path, payload=None):
        return {"models": []}
    with pytest.raises(RuntimeError, match="not installed"):
        run(limit=1, client=OllamaClient(request_fn=empty_model_tags))
