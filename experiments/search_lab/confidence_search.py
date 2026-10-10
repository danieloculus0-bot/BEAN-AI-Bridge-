"""BEAN Lab 005: confidence-directed evidence search and page reranking.

Offline synthetic search results. The *real* BEAN AttentionFilter makes
uncertainty/conflict eligible for investigation. BEAN's own reliability estimate
influences which search stream receives the next query. Scores distinguish:
topical relevance, supported claim confidence, source independence, and
independent verification. Duplicate/syndicated pages count as one origin.

The evaluator knows ground truth; the search agent DOES NOT, except through
an explicitly metered simulated verification callback.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from bean.cognition.attention import AttentionFilter

STREAMS = ("viral", "primary", "independent", "challenger", "archive")
PROFILES = ("ordinary", "viral_misinformation", "stale_archive")


@dataclass(frozen=True)
class Page:
    page_id: str
    stream: str
    origin: str
    stance: int  # 0 or 1, claim made by page; not ground truth
    relevance: float
    methodology: float
    freshness: float


@dataclass(frozen=True)
class SearchPolicy:
    max_fetches: int = 6
    max_audits: int = 0
    confidence_for_stop: float = 0.79
    stream_exploration: float = 0.20


@dataclass
class SearchBelief:
    predicted_probability: float
    supports: int
    refutes: int
    unique_origins: int
    verified: bool = False


class ConfidenceSearchAgent:
    """Agent can inspect pages, not the evaluator's hidden truth."""

    def __init__(self, policy: SearchPolicy = SearchPolicy()):
        if policy.max_fetches < 1 or policy.max_audits < 0:
            raise ValueError("invalid search budgets")
        self.policy = policy
        self.stream_correct = {s: [2.0, 2.0] for s in STREAMS}
        self.self_correct = [2.0, 2.0]
        self.reset()

    def reset(self):
        self.pages: list[Page] = []
        self.seen_ids: set[str] = set()
        self.verified_truth: int | None = None
        self.audit_count = 0
        self.selected_streams: list[str] = []
        self.trace: list[dict] = []

    def own_confidence(self) -> float:
        good, wrong = self.self_correct
        return round(good / (good + wrong), 6)

    def stream_confidence(self, stream: str) -> float:
        good, wrong = self.stream_correct[stream]
        return good / (good + wrong)

    @staticmethod
    def _page_strength(page: Page) -> float:
        return max(0.05, min(0.90,
            0.20 + 0.44 * page.methodology + 0.20 * page.freshness + 0.16 * page.relevance))

    def belief(self) -> SearchBelief:
        if self.verified_truth is not None:
            return SearchBelief(0.99 if self.verified_truth else 0.01,
                                0, 0, len({p.origin for p in self.pages}), True)
        # Most favorable single piece of evidence per provenance origin. Six
        # syndicated copies can never masquerade as six independent sources.
        by_origin: dict[str, Page] = {}
        for page in self.pages:
            incumbent = by_origin.get(page.origin)
            if incumbent is None or self._page_strength(page) > self._page_strength(incumbent):
                by_origin[page.origin] = page
        log_odds = 0.0
        for page in by_origin.values():
            # Weight high-methodology, fresh evidence more than mere popularity.
            strength = self._page_strength(page)
            stream_quality = self.stream_confidence(page.stream)
            weight = strength * (0.55 + stream_quality) * 2.4
            log_odds += weight if page.stance else -weight
        uncalibrated = 1.0 / (1.0 + math.exp(-max(-12.0, min(12.0, log_odds))))
        # Agent confidence is earned on *previously* independently checked
        # episodes. Uncertain calibration shrinks extreme evidence estimates.
        trust = max(0.30, self.own_confidence())
        probability = 0.5 + (uncalibrated - 0.5) * trust
        return SearchBelief(
            predicted_probability=round(probability, 6),
            supports=sum(p.stance == 1 for p in by_origin.values()),
            refutes=sum(p.stance == 0 for p in by_origin.values()),
            unique_origins=len(by_origin),
        )

    def select_stream(self, remaining: dict[str, int]) -> str | None:
        candidates = [s for s in STREAMS if remaining.get(s, 0) > 0]
        if not candidates:
            return None
        if not self.pages and "viral" in candidates:
            return "viral"
        view = self.belief()
        p = view.predicted_probability
        uncertainty = 1 - 2 * abs(p - 0.5)
        origins = {page.origin for page in self.pages}
        used = set(self.selected_streams)
        # Source diversity, independent corroboration and active challenge
        # are valued separately from estimated source reliability.
        scores = {}
        for stream in candidates:
            base = {
                "viral": 0.12, "primary": 1.20, "independent": 0.82,
                "challenger": 0.65, "archive": 0.10,
            }[stream]
            quality = self.stream_confidence(stream)
            exploration = self.policy.stream_exploration / (1 + self.selected_streams.count(stream))
            focus = uncertainty * ({
                "viral": 0.04, "primary": 0.22, "independent": 0.32,
                "challenger": 0.48, "archive": 0.09,
            }[stream])
            if stream == "primary" and stream not in used:
                base += 0.55
            if stream == "challenger" and stream not in used and view.unique_origins >= 2:
                base += 0.45
            if stream == "independent" and len(origins) < 3:
                base += 0.30
            duplicate_penalty = 0.85 * self.selected_streams.count(stream)
            scores[stream] = base + quality * 0.50 + exploration + focus - duplicate_penalty
        return max(candidates, key=lambda name: (scores[name], -STREAMS.index(name)))

    def inspect(self, page: Page):
        if page.page_id in self.seen_ids:
            raise ValueError("duplicate search result")
        if page.stance not in (0, 1):
            raise ValueError("invalid page claim")
        if not all(math.isfinite(x) and 0 <= x <= 1 for x in
                   (page.relevance, page.methodology, page.freshness)):
            raise ValueError("invalid page features")
        self.seen_ids.add(page.page_id)
        self.pages.append(page)
        self.selected_streams.append(page.stream)
        view = self.belief()
        event = {
            "id": len(self.pages), "event_type": "observation",
            "severity": "warn" if view.supports and view.refutes else "info",
            "summary": "Search evidence conflict" if view.supports and view.refutes else "Search evidence observation",
            "subtype": "search_claim",
        }
        relevant = AttentionFilter(threshold=0.45).build_window(
            [event],
            open_questions=[{"question": "Which evidence would falsify the prevailing claim?"}]
            if view.supports and view.refutes else [],
        )
        self.trace.append({
            "action": "inspect", "stream": page.stream, "page_id": page.page_id,
            "origin": page.origin, "estimated_p": view.predicted_probability,
            "own_calibration": self.own_confidence(), "challenge_attention": bool(relevant.event_ids()),
        })

    def independent_audit(self, verifier):
        if self.audit_count >= self.policy.max_audits:
            raise ValueError("audit budget exhausted")
        answer = int(verifier())
        if answer not in (0, 1):
            raise ValueError("invalid independent verification")
        self.audit_count += 1
        self.verified_truth = answer
        self.trace.append({"action": "independent_audit", "confirmed": True})

    def maybe_stop(self) -> bool:
        p = self.belief().predicted_probability
        return (
            self.belief().unique_origins >= 3 and
            "primary" in self.selected_streams and
            "challenger" in self.selected_streams and
            max(p, 1 - p) >= self.policy.confidence_for_stop and
            self.own_confidence() >= 0.72
        )

    def rerank(self) -> list[dict]:
        """Separate relevance from confidence that a page's claim is correct."""
        p = self.belief().predicted_probability
        lineage_sizes = {}
        for page in self.pages:
            lineage_sizes[page.origin] = lineage_sizes.get(page.origin, 0) + 1
        rows = []
        for page in self.pages:
            support = p if page.stance else 1 - p
            novelty = 1 / math.sqrt(lineage_sizes[page.origin])
            score = (
                0.33 * page.relevance + 0.32 * page.methodology +
                0.13 * page.freshness + 0.12 * novelty + 0.10 * support
            )
            rows.append({
                "page_id": page.page_id,
                "stream": page.stream,
                "origin": page.origin,
                "relevance": page.relevance,
                "claim_confidence": round(support, 4),
                "ranking_score": round(score, 6),
                "provenance_discount": round(novelty, 4),
                "verification_status": "verified_against_independent_audit"
                if self.verified_truth is not None else "unverified",
                "stance": page.stance,
            })
        return sorted(rows, key=lambda row: (-row["ranking_score"], row["page_id"]))

    def learn_from_outcome(self, verified_outcome: int):
        """Only prior completed episodes inform future self calibration."""
        if verified_outcome not in (0, 1):
            raise ValueError("outcome must be independently verified")
        predicted = int(self.belief().predicted_probability >= 0.5)
        self.self_correct[int(predicted != verified_outcome)] += 0  # explicit no-op; indexes below
        if predicted == verified_outcome:
            self.self_correct[0] += 1
        else:
            self.self_correct[1] += 1
        # Every family gets at most one score per episode, even if it produced
        # dozens of near-identical copies of the same misinformation.
        seen_streams = {}
        for page in self.pages:
            seen_streams.setdefault(page.stream, {})
            if page.origin not in seen_streams[page.stream]:
                seen_streams[page.stream][page.origin] = page
        for stream, origins in seen_streams.items():
            correctness = sum(int(page.stance == verified_outcome) for page in origins.values())
            failures = len(origins) - correctness
            self.stream_correct[stream][0] += correctness
            self.stream_correct[stream][1] += failures


def make_world(seed: int, profile: str) -> dict:
    if profile not in PROFILES:
        raise ValueError("unknown evidence world")
    rng = random.Random(seed)
    truth = int(rng.random() < 0.5)
    trending_correct = rng.random() < (0.82 if profile == "ordinary" else 0.18 if profile == "viral_misinformation" else 0.68)
    syndicated_stance = truth if trending_correct else 1 - truth

    def page(stream, origin, stance, index, relevance, method, freshness):
        return Page(f"{seed}-{stream}-{index}", stream, origin, stance,
                    relevance, method, freshness)

    pages = {
        "viral": [page("viral", "shared-syndication", syndicated_stance, i, 0.96 - i * 0.01, 0.25, 0.94)
                  for i in range(8)],
        "primary": [page("primary", f"primary-{i}", truth if rng.random() < 0.94 else 1 - truth,
                         i, 0.78, 0.96, 0.92) for i in range(2)],
        "independent": [page("independent", f"independent-{i}", truth if rng.random() < 0.80 else 1 - truth,
                             i, 0.84, 0.82, 0.80) for i in range(4)],
        "challenger": [page("challenger", f"challenge-{i}", truth if rng.random() < 0.73 else 1 - truth,
                            i, 0.79, 0.86, 0.86) for i in range(3)],
        "archive": [page("archive", "archived-source", truth if rng.random() < (
            0.27 if profile == "stale_archive" else 0.72) else 1 - truth,
            i, 0.90, 0.72, 0.12) for i in range(3)],
    }
    return {"truth": truth, "pages": pages, "profile": profile}


def search_episode(agent: ConfidenceSearchAgent, world: dict, strategy: str) -> dict:
    if strategy not in ("popularity", "round_robin", "confidence", "confidence_audit"):
        raise ValueError("unknown routing strategy")
    agent.reset()
    cursor = {stream: 0 for stream in STREAMS}
    for step in range(agent.policy.max_fetches):
        remaining = {name: len(pages) - cursor[name] for name, pages in world["pages"].items()}
        if strategy == "popularity":
            stream = next((s for s in ("viral", "archive", "primary", "independent", "challenger")
                           if remaining[s] > 0), None)
        elif strategy == "round_robin":
            stream = next((s for s in list(STREAMS)[step % len(STREAMS):] +
                           list(STREAMS)[:step % len(STREAMS)] if remaining[s] > 0), None)
        else:
            stream = agent.select_stream(remaining)
        if stream is None:
            break
        hit = world["pages"][stream][cursor[stream]]
        cursor[stream] += 1
        agent.inspect(hit)
        if strategy.startswith("confidence") and agent.maybe_stop():
            break
    pre_verification = agent.belief().predicted_probability
    if strategy == "confidence_audit" and agent.policy.max_audits:
        view = agent.belief()
        has_conflict = view.supports > 0 and view.refutes > 0
        if has_conflict or max(pre_verification, 1 - pre_verification) < 0.68:
            agent.independent_audit(lambda: world["truth"])
    ranked = agent.rerank()
    winner = ranked[0] if ranked else None
    return {
        "prediction": agent.belief().predicted_probability,
        "before_audit_probability": pre_verification,
        "truth": world["truth"],  # evaluator output ONLY
        "top_page_id": winner["page_id"] if winner else None,
        "top_page_correct": int(winner["stance"] == world["truth"]) if winner else 0,
        "top_page_verified": bool(winner and agent.verified_truth is not None),
        "pages_seen": len(agent.pages),
        "origins_seen": len({page.origin for page in agent.pages}),
        "audits": agent.audit_count,
        "search_streams": list(agent.selected_streams),
        "ranked_pages": ranked,
        "decision_trace": agent.trace,
    }


def evaluate(strategy: str, seeds: list[int], profiles: list[str]) -> dict:
    if not seeds or len(seeds) != len(profiles):
        raise ValueError("nonempty and equally long case vectors required")
    # The same budget is assigned; only the audited mode may spend verification.
    policy = SearchPolicy(max_fetches=6, max_audits=int(strategy == "confidence_audit"))
    agent = ConfidenceSearchAgent(policy)
    records = []
    for seed, profile in zip(seeds, profiles):
        result = search_episode(agent, make_world(seed, profile), strategy)
        truth = result["truth"]
        confidence = result["prediction"]
        records.append({
            "correct": int((confidence >= 0.5) == bool(truth)),
            "top_correct": result["top_page_correct"],
            "brier": (confidence - truth) ** 2,
            "fetches": result["pages_seen"],
            "audits": result["audits"],
            "diversity": result["origins_seen"],
        })
        # Ground truth feedback is revealed ONLY after ranking is complete.
        # This is an evaluator-supplied training signal for the *next* query.
        agent.learn_from_outcome(truth)
    n = len(records)
    return {
        "episodes": n,
        "claim_accuracy": round(sum(x["correct"] for x in records) / n, 4),
        "top_page_accuracy": round(sum(x["top_correct"] for x in records) / n, 4),
        "brier": round(sum(x["brier"] for x in records) / n, 4),
        "mean_fetches": round(sum(x["fetches"] for x in records) / n, 4),
        "mean_independent_origins": round(sum(x["diversity"] for x in records) / n, 4),
        "total_audits": sum(x["audits"] for x in records),
        "calibrated_agent_confidence": agent.own_confidence(),
        "final_stream_confidence": {name: round(agent.stream_confidence(name), 4) for name in STREAMS},
    }


def run_study():
    seeds = list(range(81000, 81080))
    sequences = {
        "ordinary": ["ordinary"] * len(seeds),
        "viral_misinformation": ["viral_misinformation"] * len(seeds),
        "stale_archive": ["stale_archive"] * len(seeds),
        "misinformation_to_normal": ["viral_misinformation"] * 40 + ["ordinary"] * 40,
    }
    return {
        "label": "BEAN_CONFIDENCE_ROUTED_SYNTHETIC_SEARCH_NOT_LIVE_BROWSER",
        "evaluations": {
            scenario: {
                mode: evaluate(mode, seeds, profiles)
                for mode in ("popularity", "round_robin", "confidence", "confidence_audit")
            }
            for scenario, profiles in sequences.items()
        },
        "seed_window": [min(seeds), max(seeds)],
        "criteria": ["claim_accuracy", "top_page_accuracy", "brier", "fetches", "source_diversity", "verification_cost"],
        "limitations": [
            "Synthetic, simplified two-sided claims; no real web scraping, index or live search.",
            "Verification and episode-end feedback are evaluator-controlled ground truth.",
            "Stream confidence reflects outcomes only for previously fetched pages, so selection bias persists.",
            "Citations and provenance are simulated labels, not authentication of actual domains.",
            "Confidence scores must be measured for calibration; self-asserted certainty is not proof.",
            "No changes to BEAN/Bridge main or AIscend.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("bean-search-lab005.json"))
    args = parser.parse_args()
    result = json.dumps(run_study(), indent=2, sort_keys=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(result + "\n", encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
