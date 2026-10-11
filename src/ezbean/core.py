"""Deterministic KPI calculations over normalized ERP observations.

No ERP-specific dependencies. No artificial KPI values.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable


def utc_datetime(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f'Timestamp must have an explicit timezone: {value}')
    return result


def iso_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f'{field} must be an ISO YYYY-MM-DD date')
    return date.fromisoformat(value)


def nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f'{field} must be a nonnegative integer')
    return value


def nonnegative_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f'{field} must be a nonnegative decimal')
    try:
        result = Decimal(str(value))
    except Exception as e:
        raise ValueError(f'{field} must be a nonnegative decimal') from e
    if not result.is_finite() or result < 0:
        raise ValueError(f'{field} must be a finite nonnegative decimal')
    return result


@dataclass(frozen=True)
class Observation:
    source: str
    event_id: str
    entity_type: str
    entity_id: str
    observed_at: str
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, obj: dict[str, Any]) -> 'Observation':
        required = ('source', 'event_id', 'entity_type', 'entity_id', 'observed_at', 'payload')
        if any(k not in obj for k in required):
            raise ValueError(f'Observation requires {required}')
        obs = cls(**{k: obj[k] for k in required})
        if any(not isinstance(getattr(obs, k), str) or not getattr(obs, k).strip() for k in required[:-1]):
            raise ValueError('Observation identifiers and timestamp must be nonempty strings')
        utc_datetime(obs.observed_at)
        if not isinstance(obs.payload, dict):
            raise ValueError('Observation payload must be an object')
        return obs


@dataclass(frozen=True)
class KPI:
    name: str
    value: str | None
    unit: str
    evidence_ids: tuple[str, ...]
    note: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {'value': self.value, 'unit': self.unit, 'evidence_ids': list(self.evidence_ids), 'note': self.note}


@dataclass(frozen=True)
class Report:
    window_start: str
    as_of: str
    kpis: dict[str, KPI]
    input_count: int
    coverage: dict[str, dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {'schema_version': '0.2', 'window_start': self.window_start, 'as_of': self.as_of,
                'input_count': self.input_count, 'source_coverage': self.coverage or {},
                'kpis': {k: v.to_dict() for k, v in sorted(self.kpis.items())}}


def latest_entities(observations: Iterable[Observation], as_of: datetime) -> dict[tuple[str, str, str], Observation]:
    # Cache the parsed timestamp with each candidate. Formerly the incumbent
    # timestamp was reparsed whenever another revision arrived for that entity.
    latest: dict[tuple[str, str, str], tuple[datetime, str, Observation]] = {}
    for o in observations:
        timestamp = utc_datetime(o.observed_at)
        if timestamp > as_of:
            continue
        key = (o.source, o.entity_type, o.entity_id)
        old = latest.get(key)
        if old is None or (timestamp, o.event_id) > (old[0], old[1]):
            latest[key] = (timestamp, o.event_id, o)
    return {key: value[2] for key, value in latest.items()}


def calculate(observations: Iterable[Observation], window_start: str, as_of: str) -> Report:
    """Compute a compact first set of KPIs; single final shipment date per job.

    A source ERP with split shipments must normalize delivery-level records before
    using OTD; do not blindly treat first/partial shipments as completion.
    """
    start_date = iso_date(window_start, 'window_start')
    cutoff = utc_datetime(as_of)
    if start_date > cutoff.date():
        raise ValueError('window_start cannot be after as_of')

    obs_list = list(observations)
    entities = latest_entities(obs_list, cutoff)
    completed: list[Observation] = []
    on_time: list[Observation] = []
    past_due: list[Observation] = []
    rmas: list[Observation] = []
    total_rma_qty = 0
    total_rma_cost = Decimal('0')
    production: list[Observation] = []
    good_total = scrap_total = 0

    for (_, kind, _), o in sorted(entities.items()):
        p = o.payload
        if kind == 'job':
            due = iso_date(p.get('due_date'), 'due_date')
            shipped_str = p.get('shipped_date')
            shipped = iso_date(shipped_str, 'shipped_date') if shipped_str is not None else None
            if shipped is not None and shipped <= cutoff.date() and shipped >= start_date:
                completed.append(o)
                if shipped <= due:
                    on_time.append(o)
            if (shipped is None or shipped > cutoff.date()) and due < cutoff.date():
                past_due.append(o)
        elif kind == 'rma':
            opened = iso_date(p.get('opened_date'), 'opened_date')
            if start_date <= opened <= cutoff.date():
                qty = nonnegative_int(p.get('quantity'), 'quantity')
                cost = nonnegative_decimal(p.get('cost'), 'cost')
                rmas.append(o)
                total_rma_qty += qty
                total_rma_cost += cost
        elif kind == 'production':
            day = iso_date(p.get('production_date'), 'production_date')
            if start_date <= day <= cutoff.date():
                good = nonnegative_int(p.get('good_units'), 'good_units')
                scrap = nonnegative_int(p.get('scrap_units'), 'scrap_units')
                production.append(o)
                good_total += good
                scrap_total += scrap

    # Source coverage is *explicitly asserted* by normalized source records. A
    # handful of observations, even if all found entries are complete, cannot
    # establish that the source emitted every job/RMA/production record.
    # The coverage record must match this report's period and as-of instant.
    # Its source has to cover each source providing the corresponding facts.
    domains = ('job', 'rma', 'production')
    contributing_sources = {domain: set() for domain in domains}
    # A later revocation/incomplete snapshot must supersede an earlier valid
    # assertion, even when the producer issues a new entity_id. Do not select
    # by lexicographic entity ID or silently skip negative revisions.
    latest_claim: dict[tuple[str, str], Observation] = {}
    for (_, kind, _), entry in entities.items():
        if kind in contributing_sources:
            contributing_sources[kind].add(entry.source)
        elif kind == 'source_coverage':
            domain = entry.payload.get('domain')
            if domain not in domains:
                raise ValueError('Unknown source coverage domain')
            key = (domain, entry.source)
            previous = latest_claim.get(key)
            if previous is None or (
                utc_datetime(entry.observed_at), entry.event_id
            ) > (utc_datetime(previous.observed_at), previous.event_id):
                latest_claim[key] = entry

    assertions: dict[str, dict[str, str]] = {domain: {} for domain in domains}
    for (domain, source), entry in latest_claim.items():
        payload = entry.payload
        required_scope = 'full_snapshot' if domain == 'job' else 'reporting_window'
        if payload.get('complete') is not True or payload.get('scope') != required_scope:
            continue
        try:
            starts = iso_date(payload.get('window_start'), 'coverage.window_start')
            through = utc_datetime(payload.get('through'))
        except (ValueError, TypeError, AttributeError):
            # A malformed recent claim revokes eligibility for the prior one.
            continue
        if starts <= start_date and through == cutoff:
            assertions[domain][source] = f'{source}:{entry.event_id}'

    coverage = {}
    for domain in domains:
        observed = contributing_sources[domain]
        asserted = assertions[domain]
        complete = bool(asserted) and observed.issubset(asserted)
        coverage[domain] = {
            'state': 'ASSERTED_COMPLETE' if complete else 'UNKNOWN',
            'assertion_evidence_ids': sorted(asserted.values()) if complete else [],
            'observed_sources': len(observed),
            'note': ('Source-asserted completeness only; upstream authority not authenticated'
                     if complete else 'No matching complete snapshot for every observed source'),
        }

    def reported_count(rows: list[Observation], domain: str) -> str | None:
        return str(len(rows)) if rows or coverage[domain]['state'] == 'ASSERTED_COMPLETE' else None

    def reported_total(value: int | Decimal, rows: list[Observation], domain: str) -> str | None:
        return str(value) if rows or coverage[domain]['state'] == 'ASSERTED_COMPLETE' else None

    def evidence(rows: list[Observation], domain: str) -> tuple[str, ...]:
        refs = [f'{r.source}:{r.event_id}' for r in rows]
        if not rows and coverage[domain]['state'] == 'ASSERTED_COMPLETE':
            refs += coverage[domain]['assertion_evidence_ids']
        return tuple(sorted(refs))

    def note(domain: str) -> str:
        return ('Source asserts full coverage; provenance not independently authenticated'
                if coverage[domain]['state'] == 'ASSERTED_COMPLETE'
                else 'Observed evidence only; completeness not established, unobserved zeros are N/A')

    otd = (Decimal(len(on_time)) * 100 / Decimal(len(completed))).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) if completed else None
    scrap = (Decimal(scrap_total) * 100 / Decimal(good_total + scrap_total)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) if good_total + scrap_total else None
    kpis = {
        'otd_percent': KPI('otd_percent', str(otd) if otd is not None else None, '%', evidence(completed, 'job'), 'N/A without a shipment denominator; job-based OTD policy. ' + note('job')),
        'shipments_completed': KPI('shipments_completed', reported_count(completed, 'job'), 'jobs', evidence(completed, 'job'), note('job')),
        'past_due_open_jobs': KPI('past_due_open_jobs', reported_count(past_due, 'job'), 'jobs', evidence(past_due, 'job'), note('job')),
        'rma_count': KPI('rma_count', reported_count(rmas, 'rma'), 'returns', evidence(rmas, 'rma'), note('rma')),
        'rma_quantity': KPI('rma_quantity', reported_total(total_rma_qty, rmas, 'rma'), 'units', evidence(rmas, 'rma'), note('rma')),
        'rma_cost': KPI('rma_cost', reported_total(total_rma_cost.quantize(Decimal('.01')), rmas, 'rma'), 'USD', evidence(rmas, 'rma'), note('rma')),
        'good_units': KPI('good_units', reported_total(good_total, production, 'production'), 'units', evidence(production, 'production'), note('production')),
        'scrap_units': KPI('scrap_units', reported_total(scrap_total, production, 'production'), 'units', evidence(production, 'production'), note('production')),
        'scrap_percent': KPI('scrap_percent', str(scrap) if scrap is not None else None, '%', evidence(production, 'production'), 'N/A without reported production units. ' + note('production')),
    }
    return Report(window_start=window_start, as_of=as_of, kpis=kpis, coverage=coverage,
                  input_count=sum(utc_datetime(o.observed_at) <= cutoff for o in obs_list))
