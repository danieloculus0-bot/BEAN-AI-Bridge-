"""BEAN Lab 008: versioned definitions and evidence-gated model outputs.

The library, not the model, owns canonical values. Every output must match the
current eligible record and cite its exact immutable revision. Output rendering
is deterministic. This does not independently authenticate upstream evidence.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


def utc_stamp(value: str) -> str:
    """Normalize UTC-only ISO timestamps to a fixed lexical SQL time format."""
    if not isinstance(value, str):
        raise ValueError("UTC timestamp must be a string")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid timestamp") from exc
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError("Only explicitly UTC timestamps are supported")
    return stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class Definition:
    definition_id: str
    concept: str
    revision: int
    value: str
    status: str
    evidence_refs: tuple[str, ...]
    valid_from: str
    expires_at: str | None


class DefinitionLibrary:
    """Append-only SQLite ledger of declarative definitions, with as-of lookup."""
    def __init__(self, path: str | Path = ":memory:"):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS definitions (
            definition_id TEXT PRIMARY KEY,
            concept TEXT NOT NULL,
            revision INTEGER NOT NULL,
            value TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('verified','provisional','retracted')),
            evidence_refs_json TEXT NOT NULL,
            valid_from TEXT NOT NULL,
            expires_at TEXT,
            UNIQUE(concept, revision)
        );
        CREATE INDEX IF NOT EXISTS definitions_lookup
          ON definitions(concept, valid_from, revision);
        """)
        self.db.commit()

    def define(self, concept: str, value: str, *, status: str, evidence_refs: list[str],
               valid_from: str, expires_at: str | None = None) -> Definition:
        """Append a revision. Verification status is asserted by an upstream reviewer."""
        if not isinstance(concept, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{1,79}", concept):
            raise ValueError("Invalid concept key")
        if status not in {"verified", "provisional", "retracted"}:
            raise ValueError("Invalid evidence status")
        if not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError("Definition value must be nonempty and <=2000 characters")
        if (not isinstance(evidence_refs, list) or
                any(not isinstance(ref, str) or not ref.strip() or len(ref) > 200
                    for ref in evidence_refs) or len(set(evidence_refs)) != len(evidence_refs)):
            raise ValueError("Invalid evidence references")
        if status == "verified" and not evidence_refs:
            raise ValueError("Verified claims require explicit evidence references")
        start = utc_stamp(valid_from)
        expiration = utc_stamp(expires_at) if expires_at else None
        if expiration and expiration <= start:
            raise ValueError("Expiry must be after effective time")
        # Strictly monotonic effective revisions. Historical updates are corrections,
        # not silent alterations to the record or rewrites of past as-of answers.
        row = self.db.execute(
            "SELECT revision,valid_from FROM definitions WHERE concept=? ORDER BY revision DESC LIMIT 1",
            (concept,),
        ).fetchone()
        if row and start <= row["valid_from"]:
            raise ValueError("New revision must have a later effective timestamp")
        revision = (int(row["revision"]) if row else 0) + 1
        definition_id = f"{concept}@{revision}"
        refs = tuple(evidence_refs)
        self.db.execute("""
            INSERT INTO definitions(definition_id,concept,revision,value,status,evidence_refs_json,valid_from,expires_at)
            VALUES(?,?,?,?,?,?,?,?)
        """, (definition_id, concept, revision, value, status,
              json.dumps(refs, separators=(",", ":")), start, expiration))
        self.db.commit()
        return Definition(definition_id, concept, revision, value, status, refs, start, expiration)

    def lookup(self, concept: str, at: str) -> tuple[Definition | None, str]:
        stamp = utc_stamp(at)
        row = self.db.execute("""
            SELECT * FROM definitions WHERE concept=? AND valid_from<=?
            ORDER BY revision DESC LIMIT 1
        """, (concept, stamp)).fetchone()
        if row is None:
            return None, "missing"
        if row["expires_at"] is not None and stamp >= row["expires_at"]:
            return None, "expired"
        if row["status"] != "verified":
            return None, row["status"]
        return Definition(row["definition_id"], row["concept"], row["revision"],
                          row["value"], row["status"],
                          tuple(json.loads(row["evidence_refs_json"])),
                          row["valid_from"], row["expires_at"]), "current_verified"

    def history(self, concept: str) -> list[Definition]:
        rows = self.db.execute("SELECT * FROM definitions WHERE concept=? ORDER BY revision", (concept,)).fetchall()
        return [Definition(r["definition_id"], r["concept"], r["revision"], r["value"],
                           r["status"], tuple(json.loads(r["evidence_refs_json"])),
                           r["valid_from"], r["expires_at"]) for r in rows]

    def close(self):
        self.db.close()


class ModelProvider(Protocol):
    def complete(self, payload: dict) -> dict: ...


class OllamaProvider:
    """Small local-only Ollama chat adapter using stdlib, no cloud fallback."""
    def __init__(self, endpoint: str = "http://127.0.0.1:11434", model: str = "qwen2.5:0.5b",
                 timeout: int = 90, request_fn=None):
        from urllib.parse import urlparse
        parsed = urlparse(endpoint)
        if (parsed.scheme != "http" or parsed.hostname not in
                {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or
                parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
            raise ValueError("Ollama endpoint must be local HTTP loopback only")
        if not 1 <= timeout <= 300:
            raise ValueError("Timeout outside supported range")
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.request_fn = request_fn or self._request

    def _request(self, path, payload):
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        req = Request(self.endpoint + path, json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"Ollama returned HTTP {response.status}")
                return json.loads(response.read(1_000_000).decode())
        except HTTPError as exc:
            diagnostic=exc.read(2048).decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP {exc.code}: {diagnostic[:1200]}") from exc

    def complete(self, payload: dict) -> dict:
        return self.request_fn("/api/chat", {
            "model": self.model, "stream": False, "format": "json",
            "messages": [
                {"role": "system", "content": (
                    "You are BEAN's definition lookup candidate generator. "
                    "Output EXACTLY a JSON object with four keys: concept, decision, value, definition_ids. "
                    "For a verified_definition object, copy concept, value, definition_id EXACTLY with "
                    'decision="answer" and definition_ids=[definition_id]. '
                    "If no verified definition exists, output decision=\"abstain\", value=null, "
                    "definition_ids=[]. No invented definitions, citations, synonyms or explanations. "
                    "Never use older definitions than the provided as-of snapshot."
                )},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
            ],
            "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 300},
        })


class OutputGate:
    """Hard acceptance check between model generation and user-visible output."""
    def __init__(self, library: DefinitionLibrary):
        self.library = library

    def context(self, concept: str, at: str) -> dict:
        definition, reason = self.library.lookup(concept, at)
        return {
            "requested_concept": concept,
            "as_of_utc": utc_stamp(at),
            "verified_definition": asdict(definition) if definition is not None else None,
            "availability_reason": reason,
            "source_caveat": "Upstream reviewers, not this engine or LLM, assert evidence quality.",
        }

    def verify(self, concept: str, at: str, candidate: Any) -> dict:
        """Never render candidate prose directly; build output from library only."""
        snap = self.context(concept, at)
        definition = snap["verified_definition"]
        reason = "accepted"
        valid = False
        if not isinstance(candidate, dict) or set(candidate) != {"concept", "decision", "value", "definition_ids"}:
            reason = "invalid_shape"
        elif candidate["concept"] != concept:
            reason = "concept_mismatch"
        elif not isinstance(candidate["definition_ids"], list):
            reason = "invalid_references"
        elif definition is None:
            if candidate["decision"] == "abstain" and candidate["value"] is None and candidate["definition_ids"] == []:
                valid = True
                reason = "accepted_abstention"
            else:
                reason = "unverified_or_missing_definition"
        elif candidate["decision"] != "answer":
            reason = "unexpected_abstention_or_decision"
        elif candidate["definition_ids"] != [definition["definition_id"]]:
            reason = "stale_or_hallucinated_reference"
        elif candidate["value"] != definition["value"]:
            reason = "value_mismatch"
        else:
            valid = True
        if valid and definition is not None:
            user_text = definition["value"]
            classification = "library_verified_status_NOT_independent_fact_verification"
        else:
            user_text = f"No verified current definition available for {concept}." if valid else None
            classification = "abstention" if valid else "rejected"
        return {"accepted": valid, "reason": reason, "output": user_text,
                "classification": classification,
                "concept": concept,
                "definition_id": definition["definition_id"] if valid and definition else None,
                "library_reason": snap["availability_reason"]}

    def query(self, provider: ModelProvider, concept: str, at: str) -> dict:
        snap = self.context(concept, at)
        response = provider.complete(snap)
        raw = response.get("message", {}).get("content") if isinstance(response, dict) else None
        try:
            candidate = json.loads(raw) if isinstance(raw, str) else None
        except json.JSONDecodeError:
            candidate = None
        result = self.verify(concept, at, candidate)
        result["model_response_valid_json"] = candidate is not None
        # Evidence lab only: untrusted candidate retained for examination, never displayed
        # as a verified answer. Production integrations must apply retention limits.
        result["audit_candidate_untrusted"] = candidate
        result["audit_raw_model_content"] = raw[:3000] if isinstance(raw, str) else None
        return result
