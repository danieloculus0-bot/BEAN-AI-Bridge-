"""Real Core -> Bridge -> Core closed-loop communication experiments."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ezbean.cognitive_dispatch import CognitiveDispatcher
from ezbean.modules import BlockRuntime
from ezbean.modules.catalog import register_core


@pytest.fixture
def connected(tmp_path):
    if not os.environ.get("BEAN_CORE_PATH"):
        pytest.skip("Set BEAN_CORE_PATH to the matching experimental Core checkout")
    from bean.memory.store import init_store, get_store
    from bean.memory.identity import bootstrap_identity
    from bean.memory.session import begin_session
    init_store(str(tmp_path / "core.sqlite"))
    bootstrap_identity()
    session = begin_session()

    def new_runner():
        runner = BlockRuntime(db_path=tmp_path / "bridge.sqlite",
                              cache_dir=tmp_path / "bridge_cache")
        register_core(runner, local_root=os.environ["BEAN_CORE_PATH"])
        return runner
    runner = new_runner()
    try:
        yield session, runner, new_runner, tmp_path
    finally:
        runner.conn.close()
        get_store().close()


def observe(runner, session, history, label):
    trial = runner.run(
        "observe_experiment",
        {"capability": "binary_forecast",
         "inputs": {"history": history},
         "expected_output": {"prediction": label},
         "question": "Which method best predicts this observed sign?"},
        context={"session_uuid": session},
    )
    return trial["output"]["question_id"]


def test_curiosity_forms_executable_goals_and_feeds_outcomes_back_to_memory(connected):
    session, runner, new_runner, tmp_path = connected
    from bean.memory.store import get_store
    from bean.cognition.goal_state import GoalStateEngine, ActionType
    from bean.runtime.tick_handlers import build_default_handlers
    from bean.reasoning.context_builder import build_reasoning_context
    from bean.cognition.consolidation import ConsolidationEngine

    question_id = observe(runner, session, [5, 4, -2], 1)
    open_question = dict(get_store().fetchone(
        "SELECT id, question, context FROM curiosity WHERE id=?", (question_id,)
    ))
    goals = GoalStateEngine()
    assert len(goals.propose(session, [], [open_question])) == 1
    assert goals.propose(session, [], [open_question]) == []
    assert goals.get_pending(session)[0].action_type == ActionType.RUN_EXPERIMENT

    dispatcher = CognitiveDispatcher(runner)
    handlers = build_default_handlers(cognitive_dispatcher=dispatcher,
                                      cognition_interval=1,
                                      reflection_interval=500)
    handlers.run_due(1, session, {"session_uuid": session})
    assert next(h for h in handlers.summary() if h["name"] == "cognitive_experiments")["run_count"] == 1
    assert get_store().fetchone("SELECT status FROM curiosity WHERE id=?",
                                (question_id,))["status"] == "answered"
    assert get_store().fetchone(
        "SELECT COUNT(*) FROM cognition_goal_proposals WHERE action_type='run_experiment' AND status='completed'"
    )[0] == 1

    # Once an observation has been processed, the same question is not retried.
    assert dispatcher.poll(session) == []
    first = get_store().fetchone(
        "SELECT id, data FROM events WHERE subtype='cognitive_module_experiment' ORDER BY id DESC LIMIT 1"
    )
    first_payload = json.loads(first["data"])
    assert first_payload["question_id"] == question_id
    assert first_payload["capability"] == "binary_forecast"
    assert first_payload["reward"] in (-1.0, 1.0)
    assert first_payload["run_id"].startswith("block_")
    assert first_payload["observed"] == {"prediction": 1}
    packet = build_reasoning_context(session, source_event_id=first["id"])
    assert any(e.get("data", {}).get("run_id") == first_payload["run_id"]
               for e in packet["context"]["recent_events"])
    assert ConsolidationEngine()._close_resolved_questions(session) == 0

    # A different observed trial triggers a different, previously untried tool.
    q2 = observe(runner, session, [-5, -4, 2], 0)
    second = dispatcher.poll(session)
    assert len(second) == 1
    assert second[0]["question_id"] == q2
    assert second[0]["block"] != first_payload["block"]

    # Bridge retains its method preferences after SQLite restart.
    old_preference = runner.preference("binary_forecast", second[0]["block"])
    runner.conn.close()
    resumed = new_runner()
    assert resumed.preference("binary_forecast", second[0]["block"]) == old_preference
    assert resumed.choose("binary_forecast").name in ("bean.mean_sign", "bean.last_sign")

    # Core's reasoning and drive systems are now loadable through the SAME bus.
    reasoning = resumed.run("reasoning", {
        "adapter_name": "mock", "session_uuid": session,
        "source_event_id": first["id"],
    })
    assert reasoning["output"]["success"] is True
    drives = resumed.run("drive_evaluation", {"session_uuid": session})
    assert len(drives["output"]["states"]) > 0
    resumed.conn.close()


def test_experiment_failure_changes_method_and_keeps_question_open(connected):
    session, runner, new_runner, tmp_path = connected
    from bean.memory.store import get_store
    a, b = tmp_path / "faulty", tmp_path / "working"
    a.mkdir()
    b.mkdir()
    (a / "logic.py").write_text(
        'def run(data, context):\n    raise RuntimeError("failed hypothesis")\n',
        encoding="utf-8",
    )
    (b / "logic.py").write_text(
        'def run(data, context):\n    return {"value": 42}\n',
        encoding="utf-8",
    )
    for name, source in (("faulty", a), ("working", b)):
        runner.register({
            "name": name,
            "entrypoint": "logic:run",
            "capabilities": ["test_hypothesis"],
            "source": {"local_root": str(source), "module_file": "logic.py"},
        })
    report = runner.run("observe_experiment", {
        "session_uuid": session,
        "capability": "test_hypothesis", "inputs": {"x": 4},
        "expected_output": {"value": 42},
    })
    question_id = report["output"]["question_id"]
    dispatcher = CognitiveDispatcher(runner)
    first = dispatcher.poll(session)
    assert len(first) == 1
    assert first[0]["status"] == "experiment_error"
    assert get_store().fetchone(
        "SELECT status FROM curiosity WHERE id=?", (question_id,)
    )["status"] == "open"
    assert runner.preference("test_hypothesis", "faulty") == (1, -1.0)

    runner.conn.close()
    resumed = new_runner()
    for name, source in (("faulty", a), ("working", b)):
        resumed.register({
            "name": name, "entrypoint": "logic:run",
            "capabilities": ["test_hypothesis"],
            "source": {"local_root": str(source), "module_file": "logic.py"},
        })
    # Restarted Bridge sees the failed attempt; Core retains the open question.
    result = CognitiveDispatcher(resumed).poll(session)
    assert len(result) == 1
    assert result[0]["block"] == "working"
    assert result[0]["matched"] is True
    assert get_store().fetchone(
        "SELECT status FROM curiosity WHERE id=?", (question_id,)
    )["status"] == "answered"
    assert resumed.preference("test_hypothesis", "working") == (1, 1.0)
    errors = get_store().fetchone(
        "SELECT COUNT(*) FROM events WHERE subtype='cognitive_module_failure'"
    )[0]
    assert errors == 1
    resumed.conn.close()


@pytest.mark.skipif(not os.environ.get("BEAN_CORE_PATH"),
                    reason="Real Core branch required")
def test_runnable_end_to_end_demo_reports_actual_method_experience(tmp_path):
    from examples.connected_cognition import run
    results = run(core_root=os.environ["BEAN_CORE_PATH"],
                  data_dir=tmp_path / "demo")
    assert len(results["trials"]) == 4
    assert sum(results["bridge_visits"].values()) == 4
    assert results["core_answered"] == 4
    assert results["learned_preference"] in ("bean.mean_sign", "bean.last_sign")
    assert (tmp_path / "demo" / "core.sqlite").exists()
    assert (tmp_path / "demo" / "bridge.sqlite").exists()
