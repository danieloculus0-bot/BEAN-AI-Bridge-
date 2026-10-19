"""Module revisions are distinct executable code, not Python import-cache aliases."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ezbean.modules import BlockRuntime


def test_two_modules_with_same_python_name_do_not_exchange_code(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "logic.py").write_text(
        'def run(data, context):\n    return {"source": "first", "value": data["x"] + 1}\n',
        encoding="utf-8",
    )
    (second / "logic.py").write_text(
        'def run(data, context):\n    return {"source": "second", "value": data["x"] * 2}\n',
        encoding="utf-8",
    )
    runner = BlockRuntime(db_path=tmp_path / "bridge.sqlite",
                          cache_dir=tmp_path / "cache")
    for label, root in (("first", first), ("second", second)):
        runner.register({
            "name": label,
            "entrypoint": "logic:run",
            "capabilities": ["arithmetic"],
            "source": {"local_root": str(root), "module_file": "logic.py"},
        })
    assert runner.run("arithmetic", {"x": 4}, block_name="first")["output"] == {
        "source": "first", "value": 5,
    }
    assert runner.run("arithmetic", {"x": 4}, block_name="second")["output"] == {
        "source": "second", "value": 8,
    }
    assert runner.run("arithmetic", {"x": 9}, block_name="first")["output"] == {
        "source": "first", "value": 10,
    }


def test_explicit_refresh_reloads_changed_source(tmp_path):
    root = tmp_path / "code"
    root.mkdir()
    source = root / "logic.py"
    source.write_text('def run(data, context):\n    return {"value": 1}\n',
                      encoding="utf-8")
    runner = BlockRuntime(db_path=tmp_path / "bridge.sqlite",
                          cache_dir=tmp_path / "cache")
    runner.register({
        "name": "learnable_logic", "entrypoint": "logic:run",
        "capabilities": ["logic"],
        "source": {"local_root": str(root), "module_file": "logic.py"},
    })
    assert runner.run("logic", {})["output"]["value"] == 1
    source.write_text('def run(data, context):\n    return {"value": 2}\n',
                      encoding="utf-8")
    # Existing callable stays loaded until BEAN requests an update.
    assert runner.run("logic", {})["output"]["value"] == 1
    assert runner.run("logic", {}, refresh=True)["output"]["value"] == 2


def test_failed_module_updates_future_choice_and_survives_restart(tmp_path):
    broken, capable = tmp_path / "broken", tmp_path / "capable"
    broken.mkdir()
    capable.mkdir()
    (broken / "logic.py").write_text(
        'def run(data, context):\n    raise RuntimeError("experiment failed")\n',
        encoding="utf-8",
    )
    (capable / "logic.py").write_text(
        'def run(data, context):\n    return {"answer": 21}\n',
        encoding="utf-8",
    )

    def register(runner):
        for name, root in (("broken", broken), ("capable", capable)):
            runner.register({
                "name": name,
                "entrypoint": "logic:run",
                "capabilities": ["discover"],
                "source": {"local_root": str(root), "module_file": "logic.py"},
            })

    from pytest import raises
    path = tmp_path / "experiment.sqlite"
    runner = BlockRuntime(db_path=path, cache_dir=tmp_path / "cache")
    register(runner)
    assert runner.choose("discover").name == "broken"
    with raises(RuntimeError, match="experiment failed"):
        runner.run("discover", {})
    assert runner.preference("discover", "broken") == (1, -1.0)
    receipt = runner.conn.execute(
        "SELECT execution_status, error_summary, feedback "
        "FROM cognitive_block_runs").fetchone()
    assert receipt[0] == "error"
    assert "experiment failed" in receipt[1]
    assert receipt[2] == -1.0
    runner.conn.close()

    restarted = BlockRuntime(db_path=path, cache_dir=tmp_path / "cache")
    register(restarted)
    assert restarted.choose("discover").name == "capable"
    assert restarted.run("discover", {})["output"]["answer"] == 21
