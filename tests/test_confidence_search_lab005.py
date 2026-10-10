"""BEAN Lab005: ranking and multi-stream confidence test harness."""
import json

import pytest

from experiments.search_lab.confidence_search import (
    ConfidenceSearchAgent, Page, SearchPolicy, STREAMS, evaluate,
    make_world, run_study, search_episode,
)


def page(page_id, origin, stance=1, stream="viral", relevance=0.9,
         methodology=0.4, freshness=0.9):
    return Page(page_id, stream, origin, stance, relevance, methodology, freshness)


def test_duplicates_from_one_publisher_cannot_masquerade_as_independent_sources():
    single = ConfidenceSearchAgent()
    many = ConfidenceSearchAgent()
    single.inspect(page("original", "same-wire"))
    for i in range(6):
        many.inspect(page(f"mirror-{i}", "same-wire"))
    assert single.belief().unique_origins == many.belief().unique_origins == 1
    assert single.belief().predicted_probability == many.belief().predicted_probability
    assert many.rerank()[0]["provenance_discount"] < single.rerank()[0]["provenance_discount"]


def test_relevance_and_claim_confidence_are_distinct():
    agent = ConfidenceSearchAgent()
    agent.inspect(page("hot", "wire", stance=1, relevance=1.0, methodology=0.1))
    agent.inspect(page("method", "primary", stance=0, stream="primary",
                       relevance=0.75, methodology=1.0, freshness=1.0))
    rows = agent.rerank()
    assert rows[0]["page_id"] == "method"
    assert rows[0]["relevance"] < 1.0
    assert rows[0]["ranking_score"] > rows[1]["ranking_score"]
    assert rows[0]["verification_status"] == "unverified"


def test_self_confidence_updates_only_after_external_outcome():
    agent = ConfidenceSearchAgent()
    agent.inspect(page("obs", "origin", stance=1))
    before = agent.own_confidence()
    agent.learn_from_outcome(1, prior_probability=0.9)
    assert agent.own_confidence() > before
    agent.learn_from_outcome(0, prior_probability=0.9)
    assert agent.own_confidence() < (3 / 5)
    assert agent.stream_confidence("viral") == pytest.approx(0.5)


def test_oracle_confirmation_not_mistaken_for_self_accuracy():
    agent = ConfidenceSearchAgent(SearchPolicy(max_audits=1))
    agent.inspect(page("false", "wire", stance=1))
    own_pre = agent.own_confidence()
    agent.independent_audit(lambda: 0)
    assert agent.belief().verified
    assert agent.belief().predicted_probability == 0.01
    agent.learn_from_outcome(0, prior_probability=0.9)
    assert agent.own_confidence() < own_pre


def test_audit_callback_not_invoked_when_not_authorized():
    agent = ConfidenceSearchAgent(SearchPolicy(max_audits=0))
    def forbidden():
        raise AssertionError("verifier should not run")
    with pytest.raises(ValueError, match="budget"):
        agent.independent_audit(forbidden)
    assert agent.audit_count == 0


def test_audit_rejects_corrupted_truth_without_accepting_it():
    agent = ConfidenceSearchAgent(SearchPolicy(max_audits=1))
    with pytest.raises(ValueError, match="invalid"):
        agent.independent_audit(lambda: 5)
    assert agent.audit_count == 0 and agent.verified_truth is None


def test_page_invalid_confidence_is_fail_closed():
    agent = ConfidenceSearchAgent()
    with pytest.raises(ValueError):
        agent.inspect(page("bad", "wire", relevance=float("nan")))
    with pytest.raises(ValueError):
        agent.inspect(page("bad", "wire", stance=3))
    assert agent.pages == []


def test_duplicate_page_id_is_rejected():
    agent = ConfidenceSearchAgent()
    agent.inspect(page("reused", "first"))
    with pytest.raises(ValueError, match="duplicate"):
        agent.inspect(page("reused", "second"))


def test_confidence_streams_seek_distinct_sources():
    agent = ConfidenceSearchAgent()
    world = make_world(81001, "viral_misinformation")
    result = search_episode(agent, world, "confidence")
    assert result["pages_seen"] <= 6
    assert result["origins_seen"] >= 3
    assert "primary" in result["search_streams"]
    assert "challenger" in result["search_streams"]
    assert result["audits"] == 0
    assert agent.own_confidence() == 0.5


def test_popularity_only_can_repeat_one_syndicated_source():
    agent = ConfidenceSearchAgent()
    world = make_world(81001, "viral_misinformation")
    result = search_episode(agent, world, "popularity")
    assert result["origins_seen"] == 1
    assert result["pages_seen"] == 6
    assert all(s == "viral" for s in result["search_streams"])


def test_search_event_and_conflict_evidence_are_audited():
    agent = ConfidenceSearchAgent()
    agent.inspect(page("for", "origin-A", stance=1))
    agent.inspect(page("against", "origin-B", stance=0, stream="challenger"))
    assert agent.belief().supports == 1 and agent.belief().refutes == 1
    assert len(agent.trace) == 2
    assert agent.trace[-1]["challenge_attention"] is True


@pytest.mark.parametrize("profile", ["ordinary", "viral_misinformation", "stale_archive"])
def test_confidence_search_audit_and_provenance(profile):
    world = make_world(81002, profile)
    agent = ConfidenceSearchAgent(SearchPolicy(max_audits=1))
    result = search_episode(agent, world, "confidence_audit")
    assert result["pages_seen"] <= 6
    assert result["audits"] <= 1
    assert all(0 <= row["claim_confidence"] <= 1 for row in result["ranked_pages"])
    assert all(0 <= row["ranking_score"] <= 1 for row in result["ranked_pages"])


def test_completed_episode_feedback_is_reproducible():
    seeds = list(range(81000, 81016))
    profiles = ["viral_misinformation"] * len(seeds)
    a = evaluate("confidence", seeds, profiles)
    assert a == evaluate("confidence", seeds, profiles)
    assert 0 <= a["claim_accuracy"] <= 1
    assert 0 <= a["top_page_accuracy"] <= 1
    assert a["mean_fetches"] <= 6


def test_invalid_profile_and_vectors():
    with pytest.raises(ValueError):
        make_world(1, "unsupported")
    with pytest.raises(ValueError):
        evaluate("confidence", [], [])
    with pytest.raises(ValueError):
        evaluate("confidence", [1], ["ordinary", "stale_archive"])
    with pytest.raises(ValueError):
        search_episode(ConfidenceSearchAgent(), make_world(1, "ordinary"), "invalid")


def test_full_study_includes_separate_scenarios_and_strategy_controls():
    report = run_study()
    assert report["seed_window"] == [81000, 81079]
    assert set(report["evaluations"]) == {
        "ordinary", "viral_misinformation", "stale_archive",
        "misinformation_to_normal",
    }
    for scenarios in report["evaluations"].values():
        assert set(scenarios) == {
            "popularity", "round_robin", "confidence", "confidence_audit",
        }
        assert all(s["episodes"] == 80 for s in scenarios.values())
    assert all(s["total_audits"] == 0
               for scenario in report["evaluations"].values()
               for method, s in scenario.items() if method != "confidence_audit")
