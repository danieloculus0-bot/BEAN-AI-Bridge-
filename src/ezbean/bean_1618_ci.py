"""Independent headless CI replay: actual BEAN memory + EZ-BEAN KPI core.

1,618 seeded paired synthetic work orders, one fictional part. No production ERP.
"""
from __future__ import annotations
import argparse
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
import random
import sys

from .core import Observation, calculate
from .store import Ledger

N = 1618
SEED = 20261008
HAZARDS = ['mask_missing', 'tap_offset', 'weld_distortion', 'wrong_revision', 'unauthorized_signoff', 'none']
PREVENTION = {'mask_missing': .84, 'tap_offset': .80, 'weld_distortion': .62, 'wrong_revision': .95, 'unauthorized_signoff': .99, 'none': 1.}
DETECT = {'mask_missing': .18, 'tap_offset': .22, 'weld_distortion': .26, 'wrong_revision': .22, 'unauthorized_signoff': .15}
ROUTE = ['contract/revision review', 'route release', '10 Receive material', '20 Laser', '30 Brake', '40 Weld', '50 Tap', '60 Precoat', '70 Powder', '80 Final Inspect', '90 Pack/ship', 'customer response', 'containment/CAR', 'effectiveness/closure']


def run(out_dir: Path, use_bean: bool = False) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    if use_bean:
        sys.path.insert(0, str((Path.cwd() / 'bean_core').resolve()))
        from bean.memory.store import init_store
        from bean.memory.identity import bootstrap_identity
        from bean.memory.session import begin_session, end_session
        from bean.memory.event_logger import log_event, EventType, Source, Severity
        from bean.reflection.reflect import run_reflection
        init_store(str(out_dir / 'native_bean_memory.sqlite'))
        bootstrap_identity()
        sid = begin_session()
    rnd = random.Random(SEED)
    counter = {'baseline': Counter(), 'corrected': Counter()}
    evidence = {'baseline': Ledger(), 'corrected': Ledger()}
    case_one = []
    bean_sample_ids = []
    trial_journal = out_dir / 'trial_journal.jsonl'
    with trial_journal.open('w', encoding='utf-8') as sink:
        for i in range(1, N + 1):
            if i == 1:
                hazard, rolls = 'mask_missing', (.92, .89, .24, .30)
            else:
                hazard = rnd.choices(HAZARDS, weights=[20, 15, 10, 8, 7, 40])[0]
                rolls = (rnd.random(), rnd.random(), rnd.random(), rnd.random())
            for policy in ('baseline', 'corrected'):
                corrected = policy == 'corrected'
                prevention = corrected and hazard != 'none' and rolls[0] < PREVENTION[hazard]
                defect = hazard in HAZARDS[:4] and not prevention
                inprocess = corrected and defect and rolls[2] < .60
                final = defect and not inprocess and (rolls[3] < .86 if corrected else rolls[1] < DETECT[hazard])
                detected = bool(inprocess or final)
                escape = bool(defect and not detected)
                unauthorized = bool(hazard == 'unauthorized_signoff' and not prevention and not corrected and rolls[1] >= DETECT[hazard])
                reworked = detected
                trace = [{'operation': op, 'status': ('hold_then_rework' if op == '80 Final Inspect' and reworked else 'completed'),
                          'evidence': f'SYN-WO-{i:04d}:{policy}:{j}', 'synthetic': True} for j, op in enumerate(ROUTE)]
                trace[0]['status'] = 'revision_checked'
                trace[-3]['status'] = 'RMA_confirmed' if escape else 'no_RMA'
                trace[-2]['status'] = 'containment_and_CAR' if escape else 'no_external_failure'
                trace[-1]['status'] = 'effectiveness_recorded'
                record = {'trial': i, 'part': 'SIM-EZB-1618', 'policy': policy, 'hazard': hazard,
                          'prevented': bool(prevention), 'defect_created': bool(defect), 'internal_detection': detected,
                          'customer_escape': escape, 'RMA_issued': escape, 'CAR_created': escape,
                          'unauthorized_release': unauthorized, 'steps_completed': len(trace)}
                sink.write(json.dumps(record, sort_keys=True) + '\n')
                c = counter[policy]
                for k in ('prevented', 'defect_created', 'internal_detection', 'customer_escape', 'RMA_issued', 'CAR_created', 'unauthorized_release'):
                    c[k] += int(record[k])
                c['jobs'] += 1
                ship_date = '2026-10-14' if reworked else '2026-10-12'
                event_time = '2026-10-15T00:00:00+00:00'
                key = f'{policy}-{i:04d}'
                evidence[policy].ingest(Observation('SYNTHETIC_REPLAY', key + ':job', 'job', key, event_time,
                                                    {'due_date': '2026-10-13', 'shipped_date': ship_date}))
                evidence[policy].ingest(Observation('SYNTHETIC_REPLAY', key + ':production', 'production', key, event_time,
                                                    {'production_date': '2026-10-12', 'good_units': 40, 'scrap_units': 0}))
                if escape:
                    evidence[policy].ingest(Observation('SYNTHETIC_REPLAY', key + ':rma', 'rma', key, event_time,
                                                        {'opened_date': '2026-10-15', 'quantity': 1, 'cost': '75.00'}))
                if i == 1:
                    case_one.append({'record': record, 'trace': trace})
                if use_bean:
                    eid = log_event(sid, EventType.OBSERVATION, f'Synthetic trial {i} {policy}: {hazard}, escape={escape}',
                                    Source.SYSTEM, subtype='ezbean_erp_rma_cycle', data=record)
                    if i == 1:
                        bean_sample_ids.append(eid)
                        for event in trace:
                            bean_sample_ids.append(log_event(sid, EventType.OBSERVATION,
                                f'Synthetic case 1 {policy}: {event["operation"]}', Source.SYSTEM,
                                subtype='ezbean_traveler_step', data=event))
    def result(policy):
        c = counter[policy]
        detected, escaped = c['internal_detection'], c['customer_escape']
        ratio = str((Decimal(detected) / Decimal(escaped)).quantize(Decimal('.001'))) if escaped else 'infinite_no_escapes'
        kpi = calculate(evidence[policy].replay(), '2026-10-08', '2026-10-16T00:00:00+00:00')
        assert int(kpi.kpis['rma_count'].value) == escaped
        assert int(kpi.kpis['shipments_completed'].value) == N
        assert detected + escaped == c['defect_created']
        evidence[policy].close()
        return dict(c) | {'internal_per_external_ratio': ratio,
                          'kpis': {k: v.value for k, v in kpi.kpis.items()}}
    before, after = result('baseline'), result('corrected')
    assert before['jobs'] == after['jobs'] == N
    assert before['customer_escape'] > after['customer_escape']
    assert after['unauthorized_release'] == 0
    assert after['customer_escape'] == after['RMA_issued'] == after['CAR_created']
    assert Decimal(after['internal_per_external_ratio']) >= Decimal('1.618') if after['customer_escape'] else True
    assert case_one[0]['record']['customer_escape'] and not case_one[1]['record']['customer_escape']
    reflection = None
    if use_bean:
        x = run_reflection(sid, trigger_type='manual', event_ids=bean_sample_ids)
        reflection = {'status': x['status'], 'event_count': x['event_count'],
                      'summary': x['summary'], 'grounded_event_ids': bean_sample_ids,
                      'anomalies': x['anomalies']}
        end_session(sid, 'clean', f'1618 synthetic paired replays, native BEAN logged and reflected')
    summary = {'mode': 'SYNTHETIC_TEST', 'runs': N, 'paired_execution_count': N*2,
               'seed': SEED, 'part': 'SIM-EZB-1618', 'target_ratio': '1.618:1 minimum internal detected to external escape',
               'baseline': before, 'corrected': after,
               'escape_reduction_percent': str((Decimal(before['customer_escape'] - after['customer_escape']) * 100 / Decimal(before['customer_escape'])).quantize(Decimal('.01'))),
               'native_bean_reflection': reflection,
               'assumptions': 'All incidence, detection and prevention rates are synthetic hypotheses, not EZ Fab historical rates.'}
    (out_dir / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    (out_dir / 'sample_case.json').write_text(json.dumps(case_one, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('artifacts/bean_1618'))
    parser.add_argument('--use-bean', action='store_true')
    opts = parser.parse_args()
    result = run(opts.out, opts.use_bean)
    print(json.dumps({'runs': result['runs'], 'baseline_RMAs': result['baseline']['customer_escape'],
                      'corrected_RMAs': result['corrected']['customer_escape'],
                      'ratio': result['corrected']['internal_per_external_ratio'],
                      'native_bean_reflection': bool(result['native_bean_reflection'])}, indent=2))
