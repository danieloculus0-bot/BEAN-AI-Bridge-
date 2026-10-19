"""Default Bridge block catalog.

Descriptions are not imports: BEAN chooses a capability before its code is
loaded. Supply local_root to use a local checkout or use the branch reference
for on-demand Git retrieval.
"""
from __future__ import annotations

CORE_URL = "https://github.com/danieloculus0-bot/BEAN.git"


def register_core(runtime, *, local_root: str | None = None,
                  ref: str = "feature/cognitive-blocks-20261019"):
    """Make native BEAN cognition available without making Core depend on Bridge."""
    blocks = [
        ("bean.numeric_context", "numeric_context", ("data_analysis", "numeric_context"),
         "Analyze an observed numeric series"),
        ("bean.last_sign", "predict_last_sign", ("binary_forecast",),
         "Predict next sign from most recent observation"),
        ("bean.mean_sign", "predict_mean_sign", ("binary_forecast",),
         "Predict next sign using mean observation"),
        ("bean.memory_recall", "memory_recall", ("memory_recall",),
         "Recall local BEAN Core events"),
    ]
    source = {"python_root": ".", "module_file": "bean/modules/builtin.py"}
    if local_root is not None:
        source["local_root"] = local_root
    else:
        source.update({"git_url": CORE_URL, "ref": ref})
    for name, function, capabilities, description in blocks:
        runtime.register({
            "name": name, "entrypoint": "bean.modules.builtin:" + function,
            "capabilities": list(capabilities), "description": description,
            "source": dict(source),
        })


def register_bridge(runtime):
    """Expose the real Lab010 learner under the same interface as Core logic."""
    runtime.register({
        "name": "bridge.strategy_policy",
        "entrypoint": "ezbean.bean_blocks:run",
        "capabilities": ["strategy_selection", "policy_feedback"],
        "description": "Persisted contextual bandit from Bridge Lab010",
        "source": {"module_file": "src/ezbean/bean_blocks.py", "python_root": "src"},
    })
