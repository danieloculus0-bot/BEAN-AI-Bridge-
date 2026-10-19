"""Serialization is transport, not BEAN's reward signal.

Tests are attached to the existing module runtime, not a new cognition layer.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ezbean.modules import BlockRuntime
from ezbean.modules.catalog import register_core
from experiments.representation_sweep.benchmark import run as benchmark


def test_format_benchmark_roundtrips_and_does_not_select_a_winner():
    result = benchmark(loops=3)
    assert result["changes_runtime_format"] is False
    assert result["synthetic"] is True
    assert all(row["roundtrip_ok"] for row in result["results"])
    assert {x["dataset"] for x in result["results"]} == {
        "observation", "reasoning_context", "feedback_receipt",
        "numeric_series_4096",
    }
    assert any(row["format"] == "json_compact" for row in result["results"])
    assert any(row["format"] == "binary_float64_little_endian"
               for row in result["results"])


def test_unrepresentable_module_output_is_not_a_failed_cognitive_strategy(tmp_path):
    root = tmp_path / "modules"
    root.mkdir()
    (root / "sensor.py").write_text(
        'def run(data, context):\n'
        '    return {"value": float("nan"), "context": "unobserved"}\n',
        encoding="utf-8",
    )
    bridge = BlockRuntime(db_path=tmp_path / "bridge.sqlite",
                          cache_dir=tmp_path / "cache")
    bridge.register({
        "name": "synthetic-nan", "entrypoint": "sensor:run",
        "capabilities": ["measure"],
        "source": {"local_root": str(root), "module_file": "sensor.py"},
    })
    with pytest.raises(ValueError, match="Out of range float values"):
        bridge.run("measure", {"sensor": "fictional"}, block_name="synthetic-nan")
    row = bridge.conn.execute(
        "SELECT execution_status, feedback, error_summary "
        "FROM cognitive_block_runs WHERE block_name='synthetic-nan'"
    ).fetchone()
    assert row[0] == "transport_error", row
    assert row[1] is None
    assert "ValueError" in row[2]
    assert bridge.preference("measure", "synthetic-nan") == (0, 0.0)
    bridge.conn.close()
    reopened = BlockRuntime(db_path=tmp_path / "bridge.sqlite",
                            cache_dir=tmp_path / "cache")
    row_again = reopened.conn.execute(
        "SELECT execution_status, feedback FROM cognitive_block_runs"
    ).fetchone()
    assert row_again[0] == "transport_error"
    assert row_again[1] is None
    assert reopened.preference("measure", "synthetic-nan") == (0, 0.0)


@pytest.mark.skipif(not os.environ.get("BEAN_CORE_PATH"),
                    reason="Set BEAN_CORE_PATH for actual Core -> Bridge cross-repo test")
def test_core_nonfinite_observation_crosses_bridge_as_tagged_evidence(tmp_path):
    core_root = os.environ["BEAN_CORE_PATH"]
    if core_root not in sys.path:
        sys.path.insert(0, core_root)
    from bean.memory.store import init_store, get_store
    from bean.memory.identity import bootstrap_identity
    from bean.memory.session import begin_session
    from bean.memory.event_logger import log_event, EventType, Source

    init_store(str(tmp_path / "core.sqlite"))
    bootstrap_identity()
    session = begin_session()
    event_id = log_event(
        session, EventType.OBSERVATION, "Synthetic uncertain instrument.",
        Source.SENSOR, data={
            "samples": [12.5, float("nan"), float("inf"), None],
            "origin": "fixture",
        },
    )
    bridge = BlockRuntime(db_path=tmp_path / "bridge.sqlite",
                          cache_dir=tmp_path / "cache")
    register_core(bridge, local_root=core_root)
    receipt = bridge.run(
        "memory_recall", {"session_uuid": session, "limit": 10}
    )
    event = next(
        row for row in receipt["output"]["events"] if row["id"] == event_id
    )
    assert event["data"]["samples"] == [
        12.5,
        {"$bean_nonfinite_float": "nan"},
        {"$bean_nonfinite_float": "+inf"},
        None,
    ]
    assert bridge.preference("memory_recall", "bean.memory_recall") == (0, 0.0)
    json.dumps(receipt["output"], allow_nan=False)
    assert bridge.conn.execute(
        "SELECT execution_status FROM cognitive_block_runs WHERE run_id=?",
        (receipt["run_id"],),
    ).fetchone()[0] == "completed"
    bridge.conn.close()
    get_store().close()
