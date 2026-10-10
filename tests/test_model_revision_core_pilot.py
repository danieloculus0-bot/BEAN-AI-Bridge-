"""Confirm verified source-model revisions reach actual BEAN cognition."""
from experiments.evolution_lab.model_revision_core_pilot import run_pilot


def test_real_core_stores_multiple_verifications_and_model_revision(tmp_path):
    report = run_pilot(str(tmp_path / "lab004-real-core.db"))
    assert report["core"]["verified_events"] == 2
    assert report["core"]["origin_version_in_reasoning"] == report["core"]["expected_origin_version"]
    assert report["revision"]["source"] == "A"
    assert report["revision"]["reason"] == "repeated_out_of_model_verification"
    assert "source_A_changed" in report["agent_hypotheses"]
    assert all(x == "verify" for x in report["inspection_actions"])
    assert all(v == "approved" for v in report["core"]["epistemic_verdicts"])
    assert report["core"]["motion_enabled"] is False


def test_replay_releases_temp_sqlite_file_before_cleanup():
    from pathlib import Path
    from tempfile import TemporaryDirectory

    with TemporaryDirectory(prefix="bean_sqlite_teardown_") as temp:
        result = run_pilot(str(Path(temp) / "temporary.db"))
        assert result["core"]["verified_events"] == 2
    assert not Path(temp).exists()
