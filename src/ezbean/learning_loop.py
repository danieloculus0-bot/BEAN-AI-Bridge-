"""BEAN learning loop: output failure -> uncertainty -> evidence -> revision -> replay.

High-level coordinator for BEAN AI Bridge, built on the existing versioned
DefinitionLibrary and OutputGate (LAB008). A distinct investigator supplies
source claims and a *separate* verifier checks each one. The model output is
NEVER evidence. At least two verified, distinct provenance origins must agree
to create a new library revision. Contradictions or insufficient evidence
remain open, with a durable audit trail. The host controls verifier trust.

This records bounded learning episodes, not self-training model weights or
a continuously executing daemon. BEAN Core's real SQLite cognition can be
enabled through CoreEvidenceJournal, without granting external actions.
"""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from typing import Protocol, Sequence

from .knowledge_gate import DefinitionLibrary, OutputGate, utc_stamp


@dataclass(frozen=True)
class SourceObservation:
    """Raw claim from a source; not independently verified merely by presence."""
    ref: str
    origin: str
    value: str

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip() for v in (self.ref, self.origin, self.value)):
            raise ValueError("source needs reference, origin and value")
        if len(self.ref) > 200 or len(self.origin) > 150 or len(self.value) > 2000:
            raise ValueError("source metadata exceeds limits")


class Investigator(Protocol):
    def investigate(self, concept: str, question: str) -> Sequence[SourceObservation]: ...


class EvidenceVerifier(Protocol):
    def check(self, concept: str, observation: SourceObservation) -> bool: ...


class ResearchJournal(Protocol):
    def record(self, kind: str, concept: str, details: dict) -> None: ...


@dataclass(frozen=True)
class LearningOutcome:
    cycle_id: str
    concept: str
    initial_status: str
    investigation_status: str
    confirmed_sources: int
    distinct_origins: int
    definition_id: str | None
    system_answer: str | None
    model_accepted: bool
    result_status: str
    evidence_refs: tuple[str, ...]


class EvidenceLearningLoop:
    """Bounded, provider-agnostic orchestration with a durable SQLite audit."""

    def __init__(
        self, library: DefinitionLibrary, *,
        investigator: Investigator,
        verifier: EvidenceVerifier,
        journal: ResearchJournal | None = None,
        min_origins: int = 2, max_sources: int = 8,
    ):
        if min_origins < 2 or max_sources < min_origins or max_sources > 32:
            raise ValueError("invalid investigation limits")
        self.library = library
        self.gate = OutputGate(library)
        self.investigator = investigator
        self.verifier = verifier
        self.journal = journal
        self.min_origins = min_origins
        self.max_sources = max_sources
        library.db.execute("""
            CREATE TABLE IF NOT EXISTS learning_cycles (
                id TEXT PRIMARY KEY, concept TEXT NOT NULL,
                as_of_utc TEXT NOT NULL, initial_json TEXT NOT NULL,
                observations_json TEXT NOT NULL,
                outcome_json TEXT NOT NULL
            )
        """)
        library.db.commit()

    def _record(self, kind: str, concept: str, details: dict):
        if self.journal:
            self.journal.record(kind, concept, details)

    def _initial(self, provider, concept: str, at: str) -> dict:
        try:
            return self.gate.query(provider, concept, at)
        except (ValueError, RuntimeError, OSError, TypeError, KeyError) as exc:
            return {"accepted": False, "reason": "provider_error",
                    "error": f"{type(exc).__name__}: {str(exc)[:250]}", "output": None}

    def process(self, provider, concept: str, as_of: str, *, refresh: bool = False) -> LearningOutcome:
        """One bounded attempt; subsequent calls can revise anything learned.

        Always create a durable cycle. Refresh explicitly re-investigates even
        successful output, so high confidence never disables future checks.
        Neither an LLM's answer nor popularity can self-authorize a revision.
        """
        timestamp = utc_stamp(as_of)
        cycle_id = str(uuid.uuid4())
        initial = self._initial(provider, concept, timestamp)
        status = "already_accepted" if initial.get("accepted") else "unverified_model_output"
        if initial.get("accepted") and initial.get("classification") == "abstention":
            status = "no_current_verified_definition"
        observations: list[dict] = []
        refs: list[str] = []
        committed_id = None
        verified_by_origin: dict[str, SourceObservation] = {}
        investigated = bool(refresh or not initial.get("accepted") or initial.get("classification") == "abstention")
        investigation_status = "not_requested"
        if investigated:
            question = ("What evidence would establish or overturn the current "
                        f"definition of {concept}, independently of the model output?")
            self._record("uncertainty", concept, {
                "cycle_id": cycle_id, "reason": status, "question": question,
                "model_result": initial.get("reason"),
            })
            investigation_status = "insufficient_verified_evidence"
            # Source retrieval is host-provided and independently metered.
            candidates = list(self.investigator.investigate(concept, question))[:self.max_sources]
            seen_refs: set[str] = set()
            for candidate in candidates:
                if not isinstance(candidate, SourceObservation):
                    raise TypeError("investigator returned an untyped source")
                if candidate.ref in seen_refs:
                    observations.append({"ref": candidate.ref, "origin": candidate.origin,
                                         "status": "duplicate_reference"})
                    continue
                seen_refs.add(candidate.ref)
                verified = self.verifier.check(concept, candidate)
                if not isinstance(verified, bool):
                    raise TypeError("evidence verifier must return bool")
                result = {"ref": candidate.ref, "origin": candidate.origin,
                          "value": candidate.value, "verified": verified}
                observations.append(result)
                if verified:
                    old = verified_by_origin.get(candidate.origin)
                    if old is not None and old.value != candidate.value:
                        investigation_status = "conflicting_same_origin"
                    else:
                        verified_by_origin.setdefault(candidate.origin, candidate)

            values = {source.value for source in verified_by_origin.values()}
            if investigation_status == "conflicting_same_origin" or len(values) > 1:
                investigation_status = "conflicting_verified_evidence"
            elif len(verified_by_origin) < self.min_origins:
                investigation_status = "insufficient_verified_evidence"
            else:
                candidate_value = next(iter(values))
                current, lookup_reason = self.library.lookup(concept, timestamp)
                if current and current.value == candidate_value:
                    investigation_status = "corroborated_no_revision"
                    committed_id = current.definition_id
                else:
                    refs = [source.ref for source in verified_by_origin.values()]
                    newest = self.library.history(concept)
                    if newest and utc_stamp(newest[-1].valid_from) >= timestamp:
                        investigation_status = "requires_later_effective_time"
                        refs = []
                    else:
                        # Existing OutputGate alone can't change definitions;
                        # this explicit two-origin trusted-verifier policy can.
                        definition = self.library.define(
                            concept, candidate_value, status="verified",
                            evidence_refs=refs, valid_from=timestamp,
                        )
                        committed_id = definition.definition_id
                        investigation_status = "committed_verified_revision"
                        self._record("evidence_revision", concept, {
                            "cycle_id": cycle_id, "definition_id": committed_id,
                            "sources": [asdict(x) for x in verified_by_origin.values()],
                            "classification": "host_verifier_attested_NOT_independent_fact_authentication",
                            "confidence": min(0.99, len(verified_by_origin) /
                                              (len(verified_by_origin) + 1)),
                            "falsification": "Re-check with new independent samples and contrary origins",
                        })
            self._record("investigation", concept, {
                "cycle_id": cycle_id, "result": investigation_status,
                "observations": observations, "unique_verified_origins": len(verified_by_origin),
            })

        # The deterministic library output is the system's protected answer.
        # It is NOT relabeled as an LLM success; the model's original gate
        # acceptance remains a separate metric.
        current, _ = self.library.lookup(concept, timestamp)
        answer = current.value if current is not None and investigation_status != "conflicting_verified_evidence" else None
        outcome = LearningOutcome(
            cycle_id=cycle_id, concept=concept, initial_status=status,
            investigation_status=investigation_status,
            confirmed_sources=sum(bool(x.get("verified")) for x in observations),
            distinct_origins=len(verified_by_origin),
            definition_id=current.definition_id if current else None,
            system_answer=answer,
            model_accepted=bool(initial.get("accepted") and
                                initial.get("classification") != "abstention"),
            result_status="answerable" if answer is not None else "unresolved",
            evidence_refs=tuple(refs or (list(current.evidence_refs) if current else [])),
        )
        self.library.db.execute(
            "INSERT INTO learning_cycles(id, concept, as_of_utc, initial_json, observations_json, outcome_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (cycle_id, concept, timestamp, json.dumps(initial, default=str),
             json.dumps(observations), json.dumps(asdict(outcome))),
        )
        self.library.db.commit()
        self._record("cycle_closed", concept, {"cycle_id": cycle_id, "status": outcome.result_status,
                                                "investigation": investigation_status})
        return outcome

    def history(self) -> list[dict]:
        return [{**json.loads(row["outcome_json"]), "observations": json.loads(row["observations_json"])}
                for row in self.library.db.execute(
                    "SELECT outcome_json, observations_json FROM learning_cycles ORDER BY rowid"
                ).fetchall()]


class CoreEvidenceJournal:
    """Write learning trace into actual BEAN Core memory, not a mocked store.

    Instantiate only in isolated BEAN worker processes (core uses a global
    singleton). Caller owns lifecycle. No physical or financial actions.
    """
    def __init__(self, db_path: str):
        from bean.memory.store import init_store
        from bean.memory.identity import bootstrap_identity
        from bean.memory.session import begin_session
        from bean.memory.origin import ensure_origin_records
        from bean.cognition.uncertainty_garden import UncertaintyGarden
        from bean.cognition.epistemic_guard import EpistemicGuard
        self.store = init_store(db_path)
        bootstrap_identity()
        self.session_uuid = begin_session()
        ensure_origin_records(self.session_uuid)
        self.garden = UncertaintyGarden()
        self.guard = EpistemicGuard()
        self.recorded: list[dict] = []
        self.open_questions: dict[str, str] = {}

    def record(self, kind: str, concept: str, details: dict) -> None:
        from bean.memory.event_logger import EventType, Source, log_event
        from bean.cognition.uncertainty_garden import UncertaintyRecord
        from bean.cognition.epistemic_guard import CandidateClaim

        event_types = {
            "uncertainty": EventType.CURIOSITY,
            "investigation": EventType.OBSERVATION,
            "evidence_revision": EventType.FACT_LEARNED,
            "cycle_closed": EventType.REFLECTION,
        }
        if kind not in event_types:
            raise ValueError("unsupported BEAN research event")
        eid = log_event(
            self.session_uuid, event_types[kind],
            f"BEAN evidence loop {kind} for {concept}",
            source=Source.SYSTEM, subtype="research_learning_loop",
            data={"synthetic_or_host_attested": True, **details},
        )
        self.recorded.append({"id": eid, "kind": kind, "concept": concept})
        if kind == "uncertainty":
            record = UncertaintyRecord(
                question=str(details["question"]),
                what_would_resolve_it="Two distinct independently checked sources agree, with no verified contradiction",
                significance=0.65,
            )
            self.garden.plant(record, [
                ("The current knowledge is correct", 0.33),
                ("The recorded knowledge is stale", 0.34),
                ("Source information is insufficient", 0.33),
            ])
            self.open_questions[concept] = record.uncertainty_id
        elif kind == "evidence_revision":
            self.guard.audit(CandidateClaim(
                key=f"research.loop.{concept}",
                content=f"Two or more checked source records support revised {concept} definition",
                source_type="verified_by_host_adapter",
                source_ref=f"learning_cycle:{details['cycle_id']}",
                evidence=[x["ref"] for x in details["sources"]],
                confidence=details["confidence"],
                falsification_path=details["falsification"],
            ))
        elif kind == "investigation" and details["result"] in {
            "committed_verified_revision", "corroborated_no_revision"
        }:
            # A resolved specific question doesn't forbid opening it again
            # when later evidence contradicts it.
            key = self.open_questions.pop(concept, None)
            if key:
                options = self.garden.options(key)
                if options:
                    expected = ("stale" if details["result"] == "committed_verified_revision" else "correct")
                    selected = next((o for o in options if expected in o["interpretation"].lower()), options[0])
                    self.garden.resolve(key, selected["option_id"],
                                        "The host verifier supplied corroborating independent records")

    def context(self) -> dict:
        from bean.reasoning.context_builder import build_reasoning_context
        packet = build_reasoning_context(self.session_uuid, packet_type="bridge_learning_loop")
        return {"packet_id": packet["packet_id"],
                "origin": packet["context"]["origin_covenant"]["history"],
                "recent_events": packet["context"]["recent_events"],
                "body_output_status": packet["context"]["body_output_status"]}

    def close(self):
        from bean.memory.session import end_session
        try:
            end_session(self.session_uuid, reason="clean", notes="Offline evidence learning experiment")
        finally:
            self.store.close()
