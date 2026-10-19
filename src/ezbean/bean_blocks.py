"""Drop-in Bridge learning block for BEAN Core's cognitive module runner.

This wraps the existing Lab010 OnlinePolicy; it is not another fake policy
or a model-weight trainer. Choose and feedback are separate calls so the
caller can observe a result before teaching the policy.
"""
from __future__ import annotations

import random
from pathlib import Path
from . import growth_sim


def run(data: dict, context: dict) -> dict:
    directory = Path(context.get("data_dir") or ".bean_runtime")
    policy_path = directory / "bridge-online-policy.json"
    policy = (growth_sim.OnlinePolicy.load(policy_path)
              if policy_path.exists() else growth_sim.OnlinePolicy())
    mode = data.get("mode", "choose")
    if mode == "choose":
        history = [float(v) for v in data.get("history", [])]
        state = growth_sim.context(history)
        action = policy.choose(
            state, random.Random(data.get("seed", 0)),
            explore=bool(data.get("explore", False)),
        )
        return {"state": state, "strategy": action,
                "exposure": growth_sim.exposure(action, history),
                "visits": policy.visits.get(state, {}).get(action, 0)}
    if mode == "feedback":
        state, action = data["state"], data["strategy"]
        reward = float(data["reward_bps"])
        policy.learn(state, action, reward)
        digest = policy.save(policy_path)
        return {"state": state, "strategy": action, "reward_bps": reward,
                "visits": policy.visits[state][action],
                "updated_value": policy.q[state][action],
                "checkpoint_sha256": digest}
    raise ValueError("unsupported Bridge block mode: " + str(mode))


def manifest() -> dict:
    return {
        "name": "bridge.strategy_policy",
        "entrypoint": "ezbean.bean_blocks:run",
        "capabilities": ["strategy_selection", "policy_feedback"],
        "description": "Persisted contextual strategy selection using real Bridge Lab010 learner",
        "source": {
            "module_file": "src/ezbean/bean_blocks.py",
            "python_root": "src",
            "git_url": "https://github.com/danieloculus0-bot/BEAN-AI-Bridge-.git",
            "ref": "feature/cognitive-blocks-20261019",
        },
    }
