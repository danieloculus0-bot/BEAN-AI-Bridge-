"""Generic ERP adapter contract and a deterministic rules-only thinking stub."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Iterable

from .core import Observation, Report, calculate
from .store import Ledger


class ERPAdapter(Protocol):
    """ERP connectors must normalize read-only records to observations."""
    def read_observations(self) -> Iterable[Observation]: ...


class FixtureAdapter:
    """JSONL fixture connector for offline smoke tests, never live ERP access."""
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read_observations(self) -> Iterable[Observation]:
        with self.path.open(encoding='utf-8') as stream:
            for line_num, line in enumerate(stream, start=1):
                if line.strip():
                    try:
                        yield Observation.from_dict(json.loads(line))
                    except (ValueError, TypeError) as exc:
                        raise ValueError(f'Invalid event at {self.path}:{line_num}: {exc}') from exc


@dataclass(frozen=True)
class Finding:
    severity: str
    statement: str
    evidence_ids: tuple[str, ...]
    classification: str = 'rule_observation'

    def to_dict(self) -> dict:
        return {'severity': self.severity, 'statement': self.statement,
                'classification': self.classification, 'evidence_ids': list(self.evidence_ids)}


class ThinkingModule(Protocol):
    """Replace with governed BEAN reasoning without allowing model-generated KPI math."""
    def analyze(self, report: Report) -> list[Finding]: ...


class RuleThinkingModule:
    """Explain a signal without pretending to know its root cause."""
    def analyze(self, report: Report) -> list[Finding]:
        k = report.kpis
        findings: list[Finding] = []
        if k['otd_percent'].value is None:
            findings.append(Finding('information', 'No completed shipments in the reporting period; OTD is unavailable.', ()))
        if int(k['past_due_open_jobs'].value or '0') > 0:
            findings.append(Finding('attention', 'Open jobs are past due; review the attached job evidence.', k['past_due_open_jobs'].evidence_ids))
        if int(k['rma_count'].value or '0') > 0:
            findings.append(Finding('review', 'RMA records exist in this period; identify issue themes before assigning a cause.', k['rma_count'].evidence_ids))
        return findings


def run_cycle(adapter: ERPAdapter, ledger: Ledger, window_start: str, as_of: str, thinking: ThinkingModule | None = None) -> tuple[Report, list[Finding], int]:
    added = ledger.ingest_all(adapter.read_observations())
    report = calculate(ledger.replay(), window_start, as_of)
    return report, (thinking or RuleThinkingModule()).analyze(report), added
