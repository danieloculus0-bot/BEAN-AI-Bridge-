"""LAB012: bounded cross-domain adaptation, with train-only selection and independent holdouts.

This is an isolated, synthetic test of a parameter optimizer plus actual BEAN Core
attention/governance integration. No deployed BEAN policies or source code are changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DOMAINS = ('sensor', 'erp', 'provenance', 'release')
FEATURES = ('surprise', 'contradiction', 'coverage_gap', 'echo_risk')
BASELINE = (4, 2, 1, 1)


@dataclass(frozen=True)
class Policy:
    weights: tuple[int, int, int, int]

    def score(self, item: dict) -> float:
        return sum(w * item[f] for w, f in zip(self.weights, FEATURES)) / max(sum(self.weights), 1)


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def scenario(domain: str, seed: int, *, shifted: bool = False) -> list[dict]:
    """Truth is evaluator-only. Inputs presented to policy contain features only."""
    assert domain in DOMAINS
    rng = random.Random(f'lab012:{domain}:{seed}:{shifted}')
    gains = {
        'sensor': (0.55, 0.38, 0.05, 0.12),
        'erp': (0.06, 0.10, 0.66, 0.18),
        'provenance': (0.06, 0.16, 0.08, 0.65),
        'release': (0.40, 0.48, 0.38, 0.06),
    }[domain]
    output = []
    for i in range(12):
        truth = rng.random() < 0.32
        values = [rng.uniform(0.04, 0.52) for _ in FEATURES]
        for j, gain in enumerate(gains):
            values[j] += gain if truth else 0.0
            if rng.random() < 0.07:
                values[j] += rng.uniform(0.22, 0.50)
        if shifted:
            # The world changes: one historically predictive feature becomes unreliable.
            corrupted = {'sensor': 0, 'erp': 2, 'provenance': 3, 'release': 1}[domain]
            values[corrupted] = _clip(rng.uniform(0.12, 0.88) + (0.15 if not truth else -0.10))
        output.append({'id': f'{domain}:{seed}:{i}', 'features': dict(zip(FEATURES, map(_clip, values))), 'truth': truth})
    return output


def evaluate(policy: Policy, domain: str, seeds: range, *, shifted: bool = False) -> dict:
    tp = fp = fn = tn = 0
    total = 0
    for seed in seeds:
        items = scenario(domain, seed, shifted=shifted)
        ranked = sorted(items, key=lambda item: (-policy.score(item['features']), item['id']))
        inspected = {item['id'] for item in ranked[:3]}
        for item in items:
            predicted = item['id'] in inspected
            tp += bool(predicted and item['truth'])
            fp += bool(predicted and not item['truth'])
            fn += bool(not predicted and item['truth'])
            tn += bool(not predicted and not item['truth'])
            total += 1
    reward = 3 * tp - 2 * fp - 3 * fn
    return {'reward_per_world': round(reward / len(seeds), 4),
            'precision': round(tp / (tp + fp), 4) if (tp + fp) else None,
            'recall': round(tp / (tp + fn), 4) if (tp + fn) else None,
            'true_positive': tp, 'false_positive': fp, 'false_negative': fn,
            'true_negative': tn, 'records': total, 'worlds': len(seeds)}


def average_reward(policy: Policy, domains: tuple[str, ...], seeds: range) -> float:
    return sum(evaluate(policy, d, seeds)['reward_per_world'] for d in domains) / len(domains)


def train(domains: tuple[str, ...], seed: int = 923) -> tuple[Policy, list[dict]]:
    """Deterministic bounded neighborhood search; no access to heldout evaluation seeds."""
    rng = random.Random(seed)
    training = range(1000, 1040)
    champion = Policy(BASELINE)
    history = [{'generation': 0, 'policy': champion.weights,
                'train_macro_reward': round(average_reward(champion, domains, training), 4)}]
    for generation in range(1, 7):
        candidates = [champion]
        for _ in range(45):
            weights = list(champion.weights)
            for index in rng.sample(range(4), rng.choice((1, 2, 3))):
                weights[index] = min(8, max(0, weights[index] + rng.choice((-3, -2, -1, 1, 2, 3))))
            if not any(weights):
                weights[0] = 1
            candidates.append(Policy(tuple(weights)))
        champion = max(candidates, key=lambda p: (average_reward(p, domains, training),
                                                 -sum(abs(a-b) for a,b in zip(p.weights, BASELINE)),
                                                 tuple(-w for w in p.weights)))
        history.append({'generation': generation, 'policy': champion.weights,
                        'train_macro_reward': round(average_reward(champion, domains, training), 4)})
    return champion, history


def score_table(policy: Policy, seeds: range, shifted: bool = False) -> dict:
    return {d: evaluate(policy, d, seeds, shifted=shifted) for d in DOMAINS}


def delta_by_domain(candidate: dict, baseline: dict) -> dict:
    return {d: round(candidate[d]['reward_per_world'] - baseline[d]['reward_per_world'], 4) for d in DOMAINS}


def core_receipt(report: dict) -> dict:
    """Exercise real BEAN attention and supervised governor; never execute a proposal."""
    from bean.cognition.attention import AttentionFilter
    from bean.optimization import init_self_optimization

    sample = scenario('sensor', 91919)
    events = [{'id': i, 'event_type': 'sensor_reading',
               'severity': 'warn' if item['features']['surprise'] > 0.65 else 'info',
               'summary': 'Synthetic signal, no verified classification', 'subtype': 'synthetic_input'}
              for i, item in enumerate(sample)]
    window = AttentionFilter(threshold=0.0).build_window(events)
    assert len(window.entries) == len(events)
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    try:
        governor = init_self_optimization(conn)
        evidence_id = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
        proposal = governor.create_proposal(
            session_uuid='lab012-isolated',
            title='Evaluate bounded cross-domain attention weights',
            problem_statement='A training-only adaptation may not transfer to unrelated tasks.',
            proposed_change='Consider trained parameters only after independent validation.',
            target_layer='reasoning', proposal_type='experiment',
            expected_benefit='Potentially better verified alert selection across domains.',
            expected_cost='Additional verification and false alarms in some environments.',
            risk_level='medium',
            validation_plan='Use unseen seeds, reversed signals, leave-one-domain-out transfer and failure receipts.',
            rollback_plan='Discard candidate weights; preserve frozen baseline and evidence.',
            evidence_refs=[f'lab012:sha256:{evidence_id}'],
            alternatives=['retain frozen policy', 'train independently per domain'],
        )
        assert proposal['status'] == 'proposed' and proposal['auto_executed'] is False
        return {'attention_entries': len(window.entries), 'governor_status': proposal['status'],
                'execution_permission': proposal['execution_permission'],
                'auto_executed': proposal['auto_executed'], 'evidence_sha256': evidence_id}
    finally:
        conn.close()


def run(*, integrate_core: bool = False) -> dict:
    selected, history = train(DOMAINS)
    baseline = Policy(BASELINE)
    holdout = range(21000, 21080)
    shifted = range(30000, 30080)
    ordinary_base, ordinary_new = score_table(baseline, holdout), score_table(selected, holdout)
    shifted_base, shifted_new = score_table(baseline, shifted, True), score_table(selected, shifted, True)
    holdout_delta = delta_by_domain(ordinary_new, ordinary_base)
    shifted_delta = delta_by_domain(shifted_new, shifted_base)
    transfer = {}
    for index, domain in enumerate(DOMAINS):
        other_domains = tuple(d for d in DOMAINS if d != domain)
        foreign_policy, _ = train(other_domains, 923 + index)
        transfer[domain] = {'foreign_trained_policy': foreign_policy.weights,
                            'baseline': evaluate(baseline, domain, holdout),
                            'candidate': evaluate(foreign_policy, domain, holdout)}
        transfer[domain]['reward_delta'] = round(transfer[domain]['candidate']['reward_per_world'] -
                                                  transfer[domain]['baseline']['reward_per_world'], 4)
    transfer_deltas = [v['reward_delta'] for v in transfer.values()]
    verdict = ('BROAD_IMPROVEMENT_DEMONSTRATED_IN_SYNTHETIC_LAB'
               if sum(holdout_delta.values()) > 0 and min(holdout_delta.values()) >= -0.25
               and sum(shifted_delta.values()) >= 0 and min(shifted_delta.values()) >= -0.75
               and sum(d >= 0 for d in transfer_deltas) >= 3 and sum(transfer_deltas) > 0
               else 'BROAD_IMPROVEMENT_NOT_DEMONSTRATED')
    output = {'schema': 'bean.broad-improvement.lab012.v1', 'synthetic_only': True,
              'core_main_unchanged': True, 'training_seeds': [1000, 1039],
              'holdout_seeds': [21000, 21079], 'shifted_seeds': [30000, 30079],
              'baseline_policy': BASELINE, 'selected_policy': selected.weights,
              'training_history': history,
              'ordinary_holdout': {'baseline': ordinary_base, 'candidate': ordinary_new, 'reward_delta': holdout_delta},
              'shifted_holdout': {'baseline': shifted_base, 'candidate': shifted_new, 'reward_delta': shifted_delta},
              'leave_one_domain_out': transfer,
              'verdict': verdict,
              'limitations': ['Synthetic binary investigation rewards, not open-ended intelligence.',
                              'Optimizer changes four bounded attention weights, not arbitrary program code.',
                              'Holdout seeds are disjoint but not hidden from someone able to edit benchmark code.',
                              'No evidence of real-world generalization or continuously autonomous learning.']}
    if integrate_core:
        output['core_receipt'] = core_receipt(output)
    return output


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, default=Path('lab012-report.json'))
    ap.add_argument('--core', action='store_true')
    args = ap.parse_args()
    report = run(integrate_core=args.core)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf8')
    print(json.dumps({'verdict': report['verdict'], 'selected_policy': report['selected_policy'],
                      'ordinary_delta': report['ordinary_holdout']['reward_delta'],
                      'shifted_delta': report['shifted_holdout']['reward_delta'],
                      'transfer': {d: v['reward_delta'] for d, v in report['leave_one_domain_out'].items()},
                      'core_receipt': report.get('core_receipt')}, indent=2))


if __name__ == '__main__':
    main()
