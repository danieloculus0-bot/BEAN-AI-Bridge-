"""Regression checks for independent audit-frequency selection."""
import pytest

from experiments.evolution_lab.model_revision_lab004 import RevisionRules, evaluate_history
from experiments.evolution_lab.sparse_calibration_lab004b import (
    AUDIT_RATES, run_study, select_frequency, worlds_for,
)


def test_sparse_audit_boundaries():
    with pytest.raises(ValueError):
        RevisionRules(independent_audits=True, audit_probability=-0.1)
    with pytest.raises(ValueError):
        RevisionRules(independent_audits=True, audit_probability=1.1)


def test_zero_probability_never_invokes_independent_audits():
    seeds = list(range(51000, 51008))
    base = evaluate_history(["standard"] * len(seeds), seeds,
                            RevisionRules(independent_audits=False))
    zero = evaluate_history(["standard"] * len(seeds), seeds,
                            RevisionRules(independent_audits=True, audit_probability=0.0))
    assert base == zero


def test_sparse_calibration_has_fewer_blind_checks_than_continuous():
    seeds = list(range(51000, 51024))
    p = ["standard"] * len(seeds)
    sparse = evaluate_history(p, seeds, RevisionRules(independent_audits=True, audit_probability=0.25))
    every = evaluate_history(p, seeds, RevisionRules(independent_audits=True, audit_probability=1.0))
    assert sparse["overall"]["independent_audits"] < every["overall"]["independent_audits"]


def test_training_selection_does_not_consume_holdouts():
    best, leaderboard = select_frequency()
    assert len(leaderboard) == len(AUDIT_RATES)
    assert best.audit_probability in AUDIT_RATES
    assert leaderboard == sorted(leaderboard, key=lambda x: (-x["mean_training_score"], x["audit_probability"]))
    assert set(worlds_for(40)) == set(worlds_for(120))


def test_study_reports_all_modes_and_generalization():
    result = run_study()
    assert result["train_seed_window"][1] < result["holdout_seed_window"][0]
    assert result["selected_rules"]["audit_probability"] in AUDIT_RATES
    assert set(result["aggregates"]) == {
        "trained_frequency", "no_independent_audits", "every_episode_audit",
        "no_revisions", "fresh_each_time",
    }
    assert all(x["overall"]["episodes"] == 120
               for world in result["by_world"].values() for x in world.values())
