"""BEAN Lab006: no empirical certainty lockout; contextual micro-variation."""
import pytest

from experiments.search_lab.epistemic_continuity import (
    EpistemicContinuity, empirical, FLOOR,
)
from experiments.search_lab.confidence_search import (
    ConfidenceSearchAgent, Page, SearchPolicy, search_episode, make_world,
)


def connected_graph():
    graph = EpistemicContinuity()
    graph.observe(id="electrical-fluctuation", layer="physical", origin="sensor-board",
                  value=0.00000000001, uncertainty=0.000001,
                  note="Realistic synthetic micro-scale voltage deviation")
    graph.observe(id="voltage-reading", layer="measurement", origin="meter",
                  value=3.30000000001, uncertainty=0.02)
    graph.observe(id="spec-evaluation", layer="claim", origin="quality-engineer",
                  value=1.0, uncertainty=0.02)
    graph.observe(id="ship-or-hold", layer="decision", origin="control-logic",
                  value=1.0, uncertainty=0.1)
    graph.connect("electrical-fluctuation", "voltage-reading", 1.0,
                  "voltage reading directly records the observed deviation")
    graph.connect("spec-evaluation", "ship-or-hold", 0.9,
                  "measurement specification affects shipment decision")
    return graph


def test_confidence_never_reaches_one_or_zero_despite_extreme_learning():
    g = connected_graph()
    claim = g.belief("voltage-in-spec")
    claim.positive = 1000000000.0
    claim.negative = 1.0
    claim.settle()
    assert claim.confidence == 1 - FLOOR
    assert 0 < g.priority("spec-evaluation", "ship-or-hold", "voltage-in-spec") < 1
    claim.positive, claim.negative = 1, 1000000000
    assert claim.confidence == FLOOR
    assert g.describe("voltage-in-spec", "ship-or-hold")["learning_status"] == "always_open"


def test_nearly_invisible_variation_is_preserved_but_not_automatically_material():
    g = connected_graph()
    assert g.relevance_to("electrical-fluctuation", "ship-or-hold") == 0.0
    assert g.priority("electrical-fluctuation", "ship-or-hold", "voltage-in-spec") == 0
    assert "electrical-fluctuation" in g.nodes
    # This link must be supported by an explicit physical-to-concept relation.
    g.connect("voltage-reading", "spec-evaluation", 0.8,
              "verified tolerance rule connects magnitude to specification")
    assert g.relevance_to("electrical-fluctuation", "ship-or-hold") == 0.72
    assert g.priority("electrical-fluctuation", "ship-or-hold", "voltage-in-spec") > 0
    assert {item["layer"] for item in g.describe("voltage-in-spec", "ship-or-hold")["abstractions"]} == {
        "physical", "measurement", "claim", "decision"
    }


def test_apparent_certainty_does_not_block_independent_contradiction():
    g = connected_graph()
    b = g.belief("voltage-in-spec")
    b.positive = 1000000000.0
    assert b.settle() == 1
    g.observe(id="second-inspection", layer="claim", origin="independent-lab",
              value=0, uncertainty=0.05)
    new = g.add_claim_evidence(
        "voltage-in-spec", "second-inspection", supports=False,
        independently_verified=True)
    assert 0 < new < 1
    assert b.reopen_count == 1
    assert b.settled_for_now is None
    assert b.observed_count == b.verified_count == 1
    assert any(x["event"] == "reopened" for x in g.log)


def test_syndicated_evidence_is_stored_but_not_counted_multiple_times():
    g = connected_graph()
    for i in range(5):
        k = f"syndicated-{i}"
        g.observe(id=k, layer="claim", origin="same-upstream-publisher",
                  value=1, uncertainty=0.3)
        g.add_claim_evidence("claim", k, supports=True, independently_verified=True)
    b = g.belief("claim")
    assert b.verified_count == 1
    assert b.observed_count == 5
    assert len(g.nodes) == 9
    assert b.confidence == pytest.approx(2 / 3)


def test_no_unverified_page_promoted_to_certain_claim():
    agent = ConfidenceSearchAgent()
    page = Page("page-1", "independent", "publisher-1", 1, .95, .9, .8)
    agent.inspect(page)
    state = agent.continuity.describe(agent.claim_id, agent.decision_id)
    assert state["observations_stored"] == 2
    assert state["independent_verifications"] == 0
    assert state["learning_status"] == "always_open"
    assert state["abstractions"][1]["priority"] > 0


def test_decision_stops_at_budget_but_learning_continues_into_next_topic():
    agent = ConfidenceSearchAgent(SearchPolicy(max_fetches=6))
    first = search_episode(agent, make_world(81000, "ordinary"), "confidence")
    first_topic = agent.claim_id
    agent.learn_from_outcome(first["truth"], first["before_audit_probability"])
    first_count = len(agent.continuity.nodes)
    second = search_episode(agent, make_world(81001, "viral_misinformation"), "confidence")
    agent.learn_from_outcome(second["truth"], second["before_audit_probability"])
    assert first_topic != agent.claim_id
    assert len(agent.continuity.nodes) > first_count
    assert agent.continuity.belief(first_topic).verified_count == 1
    assert agent.continuity.belief(agent.claim_id).verified_count == 1
    assert agent.continuity.describe(agent.claim_id, agent.decision_id)["learning_status"] == "always_open"


@pytest.mark.parametrize("x", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_confidence_rejected(x):
    with pytest.raises(ValueError):
        empirical(x)


def test_unjustified_or_backward_cross_abstraction_links_rejected():
    g = connected_graph()
    with pytest.raises(ValueError):
        g.connect("voltage-reading", "spec-evaluation", .8, "")
    with pytest.raises(ValueError):
        g.connect("spec-evaluation", "voltage-reading", .8, "backwards")
    with pytest.raises(ValueError):
        g.connect("voltage-reading", "spec-evaluation", 1.5, "overweighted")


def test_repeated_measurements_same_device_can_reopen_belief_without_echo_votes():
    g = connected_graph()
    b = g.belief("motor-in-spec")
    b.positive = 1000000
    b.settle()
    for i in range(2):
        n = f"calibration-shift-{i}"
        g.observe(id=n, layer="measurement", origin="same-meter",
                  value=-0.002, uncertainty=0.01)
        g.add_claim_evidence("motor-in-spec", n, supports=False,
                             independently_verified=True,
                             independent_sample_id=f"independent-check-{i}")
    assert b.reopen_count == 1
    assert b.verified_count == 2
    assert b.observed_count == 2
    # A syndicated copy of the first measured sample is still only a copy.
    g.observe(id="copy", layer="measurement", origin="same-meter",
              value=-0.002, uncertainty=0.01)
    g.add_claim_evidence("motor-in-spec", "copy", supports=False,
                         independently_verified=True,
                         independent_sample_id="independent-check-0")
    assert b.verified_count == 2
    assert b.observed_count == 3


def test_search_preserves_microphysics_but_requires_specific_relevance_link():
    agent = ConfidenceSearchAgent()
    unrelated = Page("noise", "independent", "vendor", 1, .7, .7, .7,
                     physical_deviation=0.0000001, physical_uncertainty=.02)
    agent.inspect(unrelated)
    initial = agent.rerank()[0]
    assert initial["physical_relevance"] == 0
    node = f"{agent.claim_id}:page:noise:physical"
    assert node in agent.continuity.nodes
    relevant = Page("tolerance", "primary", "calibrated-lab", 1, .75, .94, .92,
                    physical_deviation=0.0000001, physical_uncertainty=.02,
                    physical_link_strength=.6,
                    physical_link_basis="independently established measurement-to-spec linkage")
    agent.inspect(relevant)
    ranking = {x["page_id"]: x for x in agent.rerank()}
    assert ranking["tolerance"]["physical_relevance"] == pytest.approx(.6 * .75)
    assert ranking["noise"]["physical_relevance"] == 0
    assert agent.continuity.nodes[f"{agent.claim_id}:page:tolerance:measurement"].layer == "measurement"


def test_ungrounded_physical_link_is_rejected_before_ranking():
    agent = ConfidenceSearchAgent()
    with pytest.raises(ValueError, match="grounded rationale"):
        agent.inspect(Page("groundless", "primary", "test", 1, .8, .8, .8,
                           physical_deviation=.00001,
                           physical_link_strength=.9))
