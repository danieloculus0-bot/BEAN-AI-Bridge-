"""Engine sweep across existing BEAN cognition, memory and Bridge module bus.

Every stage uses the real existing API. The synthetic test *explicitly wires*
the layers together; passing is not evidence of a default autonomous driver.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ezbean.modules import BlockRuntime
from ezbean.modules.catalog import register_bridge, register_core


@pytest.mark.skipif(not os.environ.get("BEAN_CORE_PATH"),
                    reason="Provide a checkout of the actual Core engine-sweep branch")
def test_engine_firing_end_to_end_across_two_repos_and_reboot(tmp_path):
    core_path = os.environ["BEAN_CORE_PATH"]
    # The actual host has Core installed/available; the Bridge CI checkout
    # is a sibling repository, so make that package root importable here.
    if core_path not in sys.path:
        sys.path.insert(0, core_path)
    from bean.memory.store import init_store, get_store
    from bean.memory.identity import bootstrap_identity
    from bean.memory.session import begin_session, get_continuity_context
    from bean.memory.event_logger import EventType, Severity, Source, log_event
    from bean.reflection.reflect import run_reflection
    from bean.cognition.goal_state import GoalStateEngine
    from bean.reasoning.reasoning_engine import ReasoningEngine
    from bean.cognition.preference import PreferenceEngine, PreferenceStore

    core_db = tmp_path / "core.sqlite"
    bridge_db = tmp_path / "bridge.sqlite"
    init_store(str(core_db))
    bootstrap_identity()
    first_session = begin_session()
    error_id = log_event(
        first_session, EventType.ERROR, "Fictional sensor disagreement.",
        Source.SYSTEM, severity=Severity.ERROR,
        data={"fixture": "motor-A", "error_code": "SIM_EVIDENCE_DISAGREEMENT"},
    )
    reflection = run_reflection(
        first_session, trigger_type="engine_sweep", event_ids=[error_id],
    )
    assert reflection["questions"]
    questions = [
        dict(x) for x in get_store().fetchall(
            "SELECT * FROM curiosity WHERE status='open' ORDER BY id"
        )
    ]
    goals = GoalStateEngine()
    assert len(goals.propose(first_session, [], questions)) == len(questions)
    assert goals.propose(first_session, [], questions) == []

    reason = ReasoningEngine().run(
        first_session, source_event_id=error_id, adapter_name="mock",
    )
    assert reason["success"]
    assert reason["proposal_id"]

    # Store an actual observation in Core and pass its *nested JSON data*
    # to the next Bridge graph node as a Scratch-style array output port.
    observation = log_event(
        first_session, EventType.OBSERVATION, "Fictional numeric samples.",
        Source.SYSTEM, data={"samples": [4, 5, -2], "unit": "fixture_only"},
    )
    bridge = BlockRuntime(db_path=bridge_db,
                          cache_dir=tmp_path / "module_cache")
    register_core(bridge, local_root=core_path)
    register_bridge(bridge)
    pipeline = [
        {"id": "recall", "capability": "memory_recall",
         "payload": {"session_uuid": {"$from": "input.session"}, "limit": 8}},
        {"id": "analysis", "capability": "numeric_context",
         "payload": {"history": {"$from": "recall.events.0.data.samples"}}},
        {"id": "strategy", "capability": "binary_forecast",
         "payload": {"history": {"$from": "analysis.history"}}},
    ]
    wire = bridge.chain(pipeline, inputs={"session": first_session})
    assert wire["outputs"]["recall"]["events"][0]["id"] == observation
    assert wire["outputs"]["recall"]["events"][0]["data"]["samples"] == [4, 5, -2]
    assert wire["outputs"]["analysis"]["mean"] > 0
    assert wire["outputs"]["strategy"]["prediction"] == 0
    assert len(wire["runs"]) == 3
    assert all(receipt["run_id"].startswith("block_") for receipt in wire["runs"])

    # Feed *observed test results* back into the existing Bridge chooser.
    # Also preserve exact Bridge run references in Core's existing preference
    # evidence; neither side should have to guess what the other executed.
    training = [
        ([5, 4, -2], 1), ([-5, -4, 2], 0),
        ([3, 6, -1], 1), ([-3, -6, 1], 0),
    ]
    pref_engine = PreferenceEngine()
    for series, expected in training:
        for name in ("bean.last_sign", "bean.mean_sign"):
            result = bridge.run(
                "binary_forecast", {"history": series},
                block_name=name,
            )
            correct = result["output"]["prediction"] == expected
            reward = 1.0 if correct else 0.0
            updated = bridge.feedback(result["run_id"], reward)
            assert updated["block"] == name
            log_event(
                first_session, EventType.PREFERENCE_UPDATE,
                "Bridge strategy result observed.", Source.SYSTEM,
                data={"bridge_run_id": result["run_id"],
                      "block_name": name, "correct": correct,
                      "reward": reward, "provisional": True},
            )
            pref_engine.record_outcome(
                f"bridge.method.{name}", correct, result["run_id"],
                "Synthetic method selection benchmark",
                session_uuid=first_session,
            )

    assert bridge.choose("binary_forecast").name == "bean.mean_sign"
    stored = get_store().fetchall(
        "SELECT data FROM events WHERE event_type='preference_update'"
    )
    tracked_runs = [
        json.loads(row["data"]).get("bridge_run_id") for row in stored
        if row["data"]
    ]
    tracked_runs = [rid for rid in tracked_runs if rid]
    assert len(tracked_runs) == 8
    for rid in tracked_runs:
        assert bridge.conn.execute(
            "SELECT COUNT(*) FROM cognitive_block_runs "
            "WHERE run_id=? AND feedback IS NOT NULL", (rid,),
        ).fetchone()[0] == 1

    bridge.conn.close()
    get_store().close()
    init_store(str(core_db))
    bootstrap_identity()
    second_session = begin_session()
    assert second_session != first_session
    assert get_continuity_context()["total_boots"] == 2

    reloaded = BlockRuntime(db_path=bridge_db, cache_dir=tmp_path / "module_cache")
    register_core(reloaded, local_root=core_path)
    register_bridge(reloaded)
    assert reloaded.choose("binary_forecast").name == "bean.mean_sign"
    assert len(GoalStateEngine().get_pending(first_session)) == len(questions)
    assert PreferenceStore().get_latest("bridge.method.bean.mean_sign") is not None

    holdout = [
        ([10, 8, -2], 1), ([-10, -8, 2], 0),
        ([6, 3, -1], 1), ([-6, -3, 1], 0),
    ]
    assert all(
        reloaded.run("binary_forecast", {"history": series})["output"]["prediction"]
        == expected for series, expected in holdout
    )
    old = reloaded.run(
        "memory_recall", {"session_uuid": first_session, "limit": 100}
    )
    assert any(
        item["data"] and isinstance(item["data"], dict)
        and item["data"].get("bridge_run_id") in tracked_runs
        for item in old["output"]["events"]
    )


def test_generic_scratch_ports_can_address_nested_arrays_without_core(tmp_path):
    runner = BlockRuntime(db_path=tmp_path / "bridge.sqlite",
                          cache_dir=tmp_path / "cache")
    values = {
        "events": [
            {"data": {"matrix": [[3, 4], [5, 6]]}},
        ]
    }
    assert runner._wire(
        {"values": {"$from": "events.0.data.matrix.1"}}, values
    ) == {"values": [5, 6]}
