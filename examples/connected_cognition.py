"""Live, local-first Core <-> Bridge cognitive loop demonstration.

From Bridge:
  python -m examples.connected_cognition --core D:\\BEAN\\core
Both checkouts must contain the feature/connected-cognition-20261019 changes.
The demo uses separate temporary databases unless --data-dir is supplied.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from ezbean.cognitive_dispatch import CognitiveDispatcher
from ezbean.modules import BlockRuntime
from ezbean.modules.catalog import register_core


def run(*, core_root: str | None = None, data_dir: Path) -> dict:
    data_dir.mkdir(parents=True, exist_ok=True)
    runtime = BlockRuntime(db_path=data_dir / "bridge.sqlite",
                           cache_dir=data_dir / "module_cache")
    register_core(runtime, local_root=core_root)

    # Force the FIRST actual import of Core before accessing its real SQLite.
    from importlib import import_module
    runtime._load(runtime.blocks["bean.observe_experiment"])
    from bean.memory.store import init_store, get_store
    from bean.memory.identity import bootstrap_identity
    from bean.memory.session import begin_session

    init_store(str(data_dir / "core.sqlite"))
    bootstrap_identity()
    session = begin_session()
    dispatcher = CognitiveDispatcher(runtime)
    trials = [
        ([5, 4, -2], 1), ([-5, -4, 2], 0),
        ([9, 4, -1], 1), ([-8, -4, 2], 0),
    ]
    trajectory = []
    for history, observed in trials:
        note = runtime.run(
            "observe_experiment",
            {"capability": "binary_forecast",
             "inputs": {"history": history},
             "expected_output": {"prediction": observed},
             "question": "Which local predictor is useful for this observed sequence?"},
            context={"session_uuid": session},
        )
        outcome = dispatcher.poll(session)[0]
        trajectory.append({
            "question_id": note["output"]["question_id"],
            "method": outcome["block"],
            "prediction": outcome["output"]["prediction"],
            "observed": observed,
            "reward": outcome["reward"],
        })
    # Evaluation uses fresh sequences that were not part of adaptation.
    # The "cold" arm is the initial, untrained first-block selection;
    # the other arm uses the retained preference actually learned above.
    heldout = [
        ([10, 8, -2], 1), ([-10, -8, 2], 0),
        ([6, 3, -1], 1), ([-6, -3, 1], 0),
    ]
    cold_correct, learned_correct = 0, 0
    for history, observed in heldout:
        cold = runtime.run("binary_forecast", {"history": history},
                           block_name="bean.last_sign")["output"]
        chosen = runtime.run("binary_forecast", {"history": history})["output"]
        cold_correct += int(cold["prediction"] == observed)
        learned_correct += int(chosen["prediction"] == observed)

    result = {
        "session": session, "trials": trajectory,
        "holdout": {"cases": len(heldout), "cold_correct": cold_correct,
                    "learned_correct": learned_correct},
        "learned_preference": runtime.choose("binary_forecast").name,
        "core_answered": get_store().fetchone(
            "SELECT COUNT(*) FROM curiosity WHERE status='answered'")[0],
        "bridge_visits": {
            name: runtime.preference("binary_forecast", name)[0]
            for name in ("bean.last_sign", "bean.mean_sign")
        },
        "core_database": str(data_dir / "core.sqlite"),
        "bridge_database": str(data_dir / "bridge.sqlite"),
    }
    runtime.conn.close()
    get_store().close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", help="existing local Core experiment checkout")
    parser.add_argument("--data-dir", type=Path,
                        help="retain demo core/bridge databases in this folder")
    args = parser.parse_args()
    if args.data_dir is None:
        with tempfile.TemporaryDirectory(prefix="bean-connected-cognition-") as folder:
            print(json.dumps(run(core_root=args.core,
                                 data_dir=Path(folder)), indent=2))
    else:
        print(json.dumps(run(core_root=args.core, data_dir=args.data_dir), indent=2))
