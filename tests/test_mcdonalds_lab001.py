"""Guardrails for curated-source food-claim experiment."""
from experiments.mcdonalds_lab.run_investigation import load_data, run_investigation

def test_claims_are_all_20_original_topics():
    d = load_data()
    assert [c["id"] for c in d["claims"]] == list(range(1, 21))
    assert len(d["sources"]) >= 20
    for c in d["claims"]:
        assert c["evidence"]
        for e in c["evidence"]:
            assert e["source_id"] in d["sources"]
            assert e["stance"] in (0, 1)
    for src in d["sources"].values():
        assert src["url"].startswith("https://")
        assert 0 <= src["methodology"] <= 1
        assert 0 <= src["freshness"] <= 1

def test_real_bean_agent_ranks_all_claims_without_faked_verification():
    report = run_investigation()
    assert report["claim_count"] == 20
    assert report["unique_source_urls"] >= 20
    assert report["evidence_links"] >= 40
    assert "REAL_CORE_RUN_NOT_LIVE_CRAWL" in report["label"]
    for case in report["claims"]:
        assert len(case["bean_reranking"]) == case["sources_seen"]
        assert 0.0 <= case["source_based_bean_signal_UNCALIBRATED"] <= 1.0
        assert case["confidence_is_verified"] is False
        assert case["next_falsification_step"]

def test_duplicate_sources_not_counted_as_independent_origins():
    report = run_investigation()
    by_id = {r["id"]: r for r in report["claims"]}
    assert by_id[12]["independent_origins"] < by_id[12]["sources_seen"]
    assert by_id[13]["independent_origins"] == 1
    assert by_id[11]["source_based_assessment"] == "disputed_unverified_incident"
