"""BEAN Bridge's actual module communication and feedback-learning tests."""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezbean.modules import BlockRuntime
from ezbean.modules.catalog import register_bridge, register_core


def _bridge(tmp_path):
    runtime = BlockRuntime(db_path=tmp_path / "bridge.sqlite",
                           cache_dir=tmp_path / "module_cache")
    register_bridge(runtime)
    return runtime


def test_bridge_block_is_lazy_then_learns_and_survives_restart(tmp_path):
    # Uses the real, existing Bridge Lab010 OnlinePolicy: no mocked learner.
    runner = _bridge(tmp_path)
    assert runner.available("strategy_selection")[0]["loaded"] is False
    history = [0.01] * 14
    context = {"data_dir": str(tmp_path)}
    before = runner.run("strategy_selection", {"history": history},
                        context=context)
    assert before["block"] == "bridge.strategy_policy"
    assert before["output"]["strategy"] == "momentum"
    assert runner.available("strategy_selection")[0]["loaded"] is True

    state = before["output"]["state"]
    loser = runner.run("policy_feedback", {
        "mode": "feedback", "state": state,
        "strategy": "momentum", "reward_bps": -100,
    }, context=context)
    winner = runner.run("policy_feedback", {
        "mode": "feedback", "state": state,
        "strategy": "reversion", "reward_bps": 100,
    }, context=context)
    assert loser["output"]["updated_value"] < 0
    assert winner["output"]["updated_value"] > 0

    # Reopen a new Bridge database connection and the separately saved policy.
    runner.conn.close()
    resumed = _bridge(tmp_path)
    after = resumed.run("strategy_selection", {"history": history},
                        context=context)
    assert after["output"]["strategy"] == "reversion"
    assert (tmp_path / "bridge-online-policy.json").exists()


def test_scratch_style_graph_ports_connect_bridge_functions(tmp_path):
    runner = _bridge(tmp_path)
    plan = [
        {"id": "choice", "capability": "strategy_selection",
         "payload": {"history": {"$from": "input.history"}}},
        {"id": "observe", "capability": "policy_feedback",
         "payload": {
             "mode": "feedback",
             "state": {"$from": "choice.state"},
             "strategy": {"$from": "choice.strategy"},
             "reward_bps": {"$from": "input.reward_bps"},
         }},
    ]
    trace = runner.chain(plan, inputs={
        "history": [0.02] * 14, "reward_bps": 31.0,
    }, context={"data_dir": str(tmp_path)})
    assert trace["outputs"]["observe"]["visits"] == 1
    assert trace["outputs"]["observe"]["strategy"] == trace["outputs"]["choice"]["strategy"]
    assert len(trace["runs"]) == 2
    assert all(receipt["run_id"].startswith("block_") for receipt in trace["runs"])


@pytest.mark.skipif(not os.environ.get("BEAN_CORE_PATH"),
                    reason="Provide BEAN_CORE_PATH to exercise the real Core branch")
def test_core_and_bridge_modules_connect_and_learn_from_outcomes(tmp_path):
    core = os.environ["BEAN_CORE_PATH"]
    runner = _bridge(tmp_path)
    register_core(runner, local_root=core)
    assert all(not item["loaded"] for item in runner.available("binary_forecast"))
    assert runner.choose("binary_forecast").name == "bean.last_sign"

    inputs = [4, 5, -2]
    trace = runner.chain([
        {"id": "analysis", "capability": "numeric_context",
         "payload": {"history": {"$from": "input.history"}}},
        {"id": "predict", "capability": "binary_forecast",
         "payload": {"history": {"$from": "analysis.history"}}},
    ], inputs={"history": inputs})
    assert trace["outputs"]["analysis"]["mean"] > 0
    assert trace["outputs"]["predict"]["prediction"] == 0
    assert trace["runs"][1]["block"] == "bean.last_sign"

    # Correct method for independent training inputs is the rolling mean.
    for series, target in [
        ([5, 4, -2], 1), ([-5, -4, 2], 0),
        ([3, 6, -1], 1), ([-3, -6, 1], 0),
    ]:
        for method in ("bean.last_sign", "bean.mean_sign"):
            result = runner.run("binary_forecast", {"history": series},
                                block_name=method)
            runner.feedback(result["run_id"],
                            1.0 if result["output"]["prediction"] == target else 0.0)

    assert runner.choose("binary_forecast").name == "bean.mean_sign"
    runner.conn.close()

    # Restart retains actual Bridge selection state, then evaluate unseen series.
    restarted = _bridge(tmp_path)
    register_core(restarted, local_root=core)
    holdouts = [([10, 8, -2], 1), ([-10, -8, 2], 0),
                ([6, 3, -1], 1), ([-6, -3, 1], 0)]
    after_score = sum(
        restarted.run("binary_forecast", {"history": xs})["output"]["prediction"] == y
        for xs, y in holdouts
    )
    baseline = _bridge(tmp_path / "fresh")
    register_core(baseline, local_root=core)
    before_score = sum(
        baseline.run("binary_forecast", {"history": xs})["output"]["prediction"] == y
        for xs, y in holdouts
    )
    assert before_score == 0
    assert after_score == 4
    assert restarted.choose("binary_forecast").name == "bean.mean_sign"

    # Core owns its memory; Bridge can access it as a selected logic module.
    from bean.memory.store import init_store
    from bean.memory.session import begin_session
    from bean.memory.event_logger import log_event, EventType, Source
    init_store(str(tmp_path / "core.sqlite"))
    session = begin_session()
    log_event(session, EventType.HUMAN_INPUT, "A synthetic experiment happened.", Source.HUMAN)
    recalled = restarted.run("memory_recall", {"session_uuid": session})
    assert recalled["output"]["count"] >= 1
    assert any("synthetic experiment" in x["summary"]
               for x in recalled["output"]["events"])


@pytest.mark.skipif(not os.environ.get("BEAN_CORE_PATH"),
                    reason="A checked-out Core branch is required")
def test_registered_git_branch_is_pulled_compiled_and_run_only_when_selected(tmp_path):
    """Git module checkout is lazy and has a revision receipt."""
    from pathlib import Path
    import subprocess
    runner = _bridge(tmp_path)
    runner.register({
        "name": "test.git.core.mean_sign",
        "entrypoint": "bean.modules.builtin:predict_mean_sign",
        "capabilities": ["remote_binary_forecast"],
        "source": {
            "git_url": os.environ["BEAN_CORE_PATH"],
            "ref": "fix/audit-learning-reliability-20261019",
            "python_root": ".",
            "module_file": "bean/modules/builtin.py",
        },
    })
    cache = tmp_path / "module_cache"
    assert runner.available("remote_binary_forecast")[0]["loaded"] is False
    assert list(cache.glob("*/.git")) == []
    result = runner.run("remote_binary_forecast", {"history": [4, 3, -2]})
    assert result["output"]["prediction"] == 1
    expected_revision = subprocess.check_output(
        ["git", "-C", os.environ["BEAN_CORE_PATH"], "rev-parse", "HEAD"],
        text=True,
    ).strip()
    assert result["revision"] == expected_revision
    assert list(cache.glob("*/.git"))
    assert list(cache.glob("*/bean/modules/__pycache__/builtin.*.pyc"))
