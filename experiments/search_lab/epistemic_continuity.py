"""BEAN Lab006: perpetual, defeasible learning with linked abstraction layers.

Every observation is retained. Empirical confidence has a nonzero uncertainty
floor. Only independently verified provenance contributes to claim calibration.
Tiny physical deviations are preserved, but influence decisions only when an
explicit evidence-supported connection can be traced across abstractions.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field

LAYERS = ("physical", "measurement", "claim", "decision")
FLOOR = 0.000001


def empirical(p: float) -> float:
    if isinstance(p, bool) or not isinstance(p, (float, int)) or not math.isfinite(p):
        raise ValueError("nonfinite empirical confidence")
    return max(FLOOR, min(1.0-FLOOR, float(p)))


@dataclass(frozen=True)
class Observation:
    id: str
    layer: str
    origin: str
    value: float
    uncertainty: float
    note: str = ""


@dataclass(frozen=True)
class AbstractionLink:
    child: str
    parent: str
    relevance: float
    rationale: str


@dataclass
class Belief:
    positive: float = 1.0
    negative: float = 1.0
    settled_for_now: int | None = None
    reopen_count: int = 0
    observed_count: int = 0
    verified_count: int = 0
    verified_origins: set[str] = field(default_factory=set)

    @property
    def confidence(self) -> float:
        return empirical(self.positive/(self.positive + self.negative))

    def settle(self) -> int:
        self.settled_for_now = int(self.confidence >= 0.5)
        return self.settled_for_now


class EpistemicContinuity:
    """A transparent research graph. Priorities are heuristics, not truth."""

    def __init__(self):
        self.nodes: dict[str, Observation] = {}
        self.edges: list[AbstractionLink] = []
        self.beliefs: dict[str, Belief] = {}
        self.log: list[dict] = []

    def belief(self, claim: str) -> Belief:
        if not claim:
            raise ValueError("claim required")
        return self.beliefs.setdefault(claim, Belief())

    def observe(self, *, id: str, layer: str, origin: str,
                value: float, uncertainty: float, note: str = "") -> Observation:
        if not id or not origin or id in self.nodes:
            raise ValueError("evidence identifier missing or repeated")
        if layer not in LAYERS:
            raise ValueError("invalid abstraction layer")
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError("invalid measured value")
        if isinstance(uncertainty, bool) or not isinstance(uncertainty, (float, int)) or not math.isfinite(uncertainty) or not 0 <= uncertainty <= 1:
            raise ValueError("invalid observation uncertainty")
        item = Observation(id, layer, origin, float(value), max(FLOOR, float(uncertainty)), note)
        self.nodes[id] = item
        self.log.append({"event": "observed", "id": id, "layer": layer, "origin": origin})
        return item

    def connect(self, child: str, parent: str, relevance: float, rationale: str) -> AbstractionLink:
        if child not in self.nodes or parent not in self.nodes:
            raise ValueError("missing linked evidence")
        if LAYERS.index(self.nodes[child].layer) >= LAYERS.index(self.nodes[parent].layer):
            raise ValueError("must link toward higher abstraction")
        if isinstance(relevance, bool) or not isinstance(relevance, (float, int)) or not math.isfinite(relevance) or not 0 <= relevance <= 1:
            raise ValueError("invalid causal relevance")
        if not rationale.strip():
            raise ValueError("reason required for cross-layer link")
        edge = AbstractionLink(child, parent, float(relevance), rationale)
        self.edges.append(edge)
        self.log.append({"event": "linked", "child": child, "parent": parent, "relevance": relevance})
        return edge

    def relevance_to(self, child: str, target: str) -> float:
        if child not in self.nodes or target not in self.nodes:
            raise ValueError("missing node")
        if child == target:
            return 1.0
        best = 0.0
        # Each edge goes upward in the fixed DAG layer order.
        frontier = [(child, 1.0)]
        while frontier:
            node, weight = frontier.pop()
            for edge in self.edges:
                if edge.child != node:
                    continue
                w = weight * edge.relevance
                if edge.parent == target:
                    best = max(best, w)
                else:
                    frontier.append((edge.parent, w))
        return round(best, 8)

    def priority(self, node_id: str, target: str, claim: str) -> float:
        relevance = self.relevance_to(node_id, target)
        if relevance == 0:
            return 0.0  # Still retained, no automatic importance inflation.
        confidence = self.belief(claim).confidence
        uncertainty = max(FLOOR, 2 * min(confidence, 1 - confidence))
        variation = self.nodes[node_id].uncertainty
        return round(relevance * (0.05 + 0.95 * uncertainty) * (0.6 + 0.4 * variation), 9)

    def add_claim_evidence(self, claim: str, evidence_id: str, *, supports: bool,
                           independently_verified: bool, weight: float = 1.0,
                           independent_sample_id: str | None = None) -> float:
        if evidence_id not in self.nodes:
            raise ValueError("cannot claim unseen evidence")
        if isinstance(weight, bool) or not isinstance(weight, (float, int)) or not math.isfinite(weight) or not 0 <= weight <= 1:
            raise ValueError("invalid evidence weight")
        model = self.belief(claim)
        model.observed_count += 1
        origin = self.nodes[evidence_id].origin
        # Copies share an origin and count once. A genuinely new verified
        # measurement can be identified by its explicit sampling ID.
        if independent_sample_id is not None and not independent_sample_id.strip():
            raise ValueError("empty independent sample")
        sample_key = origin if independent_sample_id is None else f"{origin}:sample:{independent_sample_id}"
        if independently_verified and sample_key not in model.verified_origins:
            model.verified_origins.add(sample_key)
            model.verified_count += 1
            if supports:
                model.positive += weight
            else:
                model.negative += weight
            if model.settled_for_now is not None and int(supports) != model.settled_for_now:
                model.reopen_count += 1
                model.settled_for_now = None
                self.log.append({"event": "reopened", "claim": claim, "evidence": evidence_id})
        self.log.append({"event": "claim_update", "claim": claim, "evidence": evidence_id,
                         "independently_verified": independently_verified, "confidence": model.confidence})
        return model.confidence

    def describe(self, claim: str, decision: str) -> dict:
        model = self.belief(claim)
        if decision not in self.nodes:
            raise ValueError("unknown decision")
        # A single backwards pass through the four-layer acyclic graph keeps
        # repeated search episodes cheap even when the complete evidence
        # ledger grows. Irrelevant nodes remain recorded, not discarded.
        relevance = {decision: 1.0}
        for layer in reversed(LAYERS):
            for edge in self.edges:
                if self.nodes[edge.parent].layer != layer:
                    continue
                if edge.parent in relevance:
                    relevance[edge.child] = max(
                        relevance.get(edge.child, 0.0),
                        relevance[edge.parent] * edge.relevance,
                    )
        uncertainty = max(FLOOR, 2 * min(model.confidence, 1 - model.confidence))
        visible = [
            {"id": node.id, "layer": node.layer,
             "priority": round(relevance[node.id] * (0.05 + 0.95 * uncertainty) *
                               (0.6 + 0.4 * node.uncertainty), 9)}
            for node in self.nodes.values() if relevance.get(node.id, 0.0) > 0
        ]
        return {
            "claim": claim, "confidence_positive": model.confidence,
            "temporarily_settled": model.settled_for_now is not None,
            "reopen_count": model.reopen_count, "observations_stored": len(self.nodes),
            "independent_verifications": model.verified_count,
            "learning_status": "always_open",
            "unlinked_or_other_context_observations": len(self.nodes) - len(visible),
            "abstractions": visible,
        }
