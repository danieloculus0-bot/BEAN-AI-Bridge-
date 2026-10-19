"""BEAN logic blocks communicate via Bridge, not Core.

From Bridge checkout (Python 3.10+), Core will be pulled on first use:
    PYTHONPATH=src python -m examples.cognitive_blocks

For offline operation with existing Core checkout:
    PYTHONPATH=src python -m examples.cognitive_blocks --core ../BEAN
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from ezbean.modules import BlockRuntime
from ezbean.modules.catalog import register_bridge, register_core


def demonstrate(core_root: str | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="bean-blocks-") as tmp:
        directory = Path(tmp)
        bridge = BlockRuntime(db_path=directory / "bridge.sqlite",
                              cache_dir=directory / "cache")
        register_core(bridge, local_root=core_root)
        register_bridge(bridge)
        history = [.01, .02, -.01, .03] * 4
        plan = [
            {"id": "analysis", "capability": "numeric_context",
             "payload": {"history": {"$from": "input.history"}}},
            {"id": "strategy", "capability": "strategy_selection",
             "payload": {"history": {"$from": "analysis.history"}, "seed": 7}},
        ]
        return bridge.chain(plan, inputs={"history": history},
                            context={"data_dir": str(directory)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--core", help="Existing local Core checkout for offline use")
    print(json.dumps(demonstrate(parser.parse_args().core), indent=2))
