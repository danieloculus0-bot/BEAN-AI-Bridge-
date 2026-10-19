"""BEAN AI Bridge: local-first, on-demand communication for logic blocks.

A block is a Python callable accepting (input_data, context) and returning a
dictionary. A catalog describes capabilities without eagerly loading code.
Blocks can come from the current checkout or a registered Git repository/branch.
Python compiles the selected module when it is first loaded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import py_compile
import random
import sqlite3
import subprocess
import sys
from typing import Any
import uuid


@dataclass(frozen=True)
class Block:
    name: str
    entrypoint: str
    capabilities: tuple[str, ...]
    description: str = ""
    source: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict) -> "Block":
        return cls(
            name=value["name"], entrypoint=value["entrypoint"],
            capabilities=tuple(value["capabilities"]),
            description=value.get("description", ""),
            source=dict(value.get("source") or {}),
        )


def _schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cognitive_block_preferences (
            capability TEXT NOT NULL,
            block_name TEXT NOT NULL,
            visits INTEGER NOT NULL,
            reward_mean REAL NOT NULL,
            PRIMARY KEY (capability, block_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cognitive_block_runs (
            run_id TEXT PRIMARY KEY,
            capability TEXT NOT NULL,
            block_name TEXT NOT NULL,
            code_revision TEXT,
            feedback REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # Existing Bridge SQLite histories remain readable on upgrade.
    columns = {row[1] for row in conn.execute(
        "PRAGMA table_info(cognitive_block_runs)").fetchall()}
    if "execution_status" not in columns:
        conn.execute(
            "ALTER TABLE cognitive_block_runs ADD COLUMN "
            "execution_status TEXT NOT NULL DEFAULT 'completed'")
    if "error_summary" not in columns:
        conn.execute(
            "ALTER TABLE cognitive_block_runs ADD COLUMN error_summary TEXT")
    conn.commit()


class BlockRuntime:
    """Bridge composes logic blocks and retains outcome-based module choices."""

    def __init__(self, *, conn=None, db_path: str | Path | None = None,
                 cache_dir: str | Path | None = None):
        # Bridge owns the communication and selection ledger, not Core.
        # When not supplied, this persists on the user's local machine.
        directory = Path(cache_dir or (Path.home() / ".bean_bridge" / "modules"))
        directory.mkdir(parents=True, exist_ok=True)
        self.conn = conn or sqlite3.connect(str(db_path or directory / "bridge_modules.sqlite"))
        self.cache_dir = directory
        self.blocks: dict[str, Block] = {}
        self._functions: dict[str, Any] = {}
        self._revisions: dict[str, str] = {}
        _schema(self.conn)

    def register(self, block: Block | dict) -> None:
        if isinstance(block, dict):
            block = Block.from_dict(block)
        if block.name in self.blocks:
            raise ValueError("block already registered: " + block.name)
        self.blocks[block.name] = block

    def register_manifest(self, path: str | Path) -> None:
        for row in json.loads(Path(path).read_text(encoding="utf-8"))["blocks"]:
            self.register(row)

    def available(self, capability: str | None = None) -> list[dict]:
        """List metadata without importing, compiling or downloading blocks."""
        return [
            {"name": b.name, "description": b.description,
             "capabilities": list(b.capabilities),
             "loaded": b.name in self._functions}
            for b in self.blocks.values()
            if capability is None or capability in b.capabilities
        ]

    def _checkout(self, block: Block, *, refresh: bool = False) -> Path:
        source = block.source
        if "local_root" in source:
            return Path(source["local_root"]).resolve()
        if "git_url" not in source:
            return Path(__file__).resolve().parents[3]
        url, ref = source["git_url"], source.get("ref", "main")
        key = hashlib.sha256((url + "\n" + ref).encode()).hexdigest()[:20]
        directory = self.cache_dir / key
        if not (directory / ".git").exists():
            directory.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", ref, url, str(directory)],
                check=True, capture_output=True, text=True,
            )
        elif refresh:
            subprocess.run(
                ["git", "-C", str(directory), "fetch", "--depth", "1", "origin", ref],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                ["git", "-C", str(directory), "checkout", "--detach", "FETCH_HEAD"],
                check=True, capture_output=True, text=True,
            )
            self._functions.pop(block.name, None)
        return directory

    def _load(self, block: Block, *, refresh: bool = False):
        if block.name in self._functions and not refresh:
            return self._functions[block.name]
        checkout = self._checkout(block, refresh=refresh)
        source = block.source
        root = checkout / source.get("python_root", ".")
        file_name = source.get("module_file")
        if file_name:
            py_compile.compile(str(checkout / file_name), doraise=True)
        # TODO: review optional plugin provenance/runtime constraints after
        # learning experiments; this development runtime does not add gates.
        root_path = str(root.resolve())
        if root_path not in sys.path:
            sys.path.insert(0, root_path)
        mod_name, separator, attr = block.entrypoint.partition(":")
        if not separator or not attr:
            raise ValueError("entrypoint must look like package.module:callable")
        importlib.invalidate_caches()
        if file_name:
            # Each checked-out version gets its own module identity. The
            # normal import cache must not substitute stale code from another
            # Git branch or from a previous refresh of the same checkout.
            source_file = (checkout / file_name).resolve()
            parent = mod_name.rpartition(".")[0]
            if parent:
                importlib.import_module(parent)
            signature = hashlib.sha256(
                (str(source_file) + ":" +
                 hashlib.sha256(source_file.read_bytes()).hexdigest()).encode()
            ).hexdigest()[:20]
            alias = (parent + "." if parent else "") + "_bean_block_" + signature
            if alias not in sys.modules:
                spec = importlib.util.spec_from_file_location(alias, source_file)
                if spec is None or spec.loader is None:
                    raise ImportError("could not load selected block module: " + str(source_file))
                module = importlib.util.module_from_spec(spec)
                sys.modules[alias] = module
                try:
                    spec.loader.exec_module(module)
                except Exception:
                    del sys.modules[alias]
                    raise
            function = getattr(sys.modules[alias], attr)
        else:
            module = importlib.import_module(mod_name)
            function = getattr(importlib.reload(module) if refresh else module, attr)
        if not callable(function):
            raise TypeError("block entrypoint must be callable")
        self._functions[block.name] = function
        revision = "local"
        if (checkout / ".git").exists():
            result = subprocess.run(
                ["git", "-C", str(checkout), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True,
            )
            revision = result.stdout.strip()
        self._revisions[block.name] = revision
        return function

    def preference(self, capability: str, block_name: str) -> tuple[int, float]:
        row = self.conn.execute(
            "SELECT visits, reward_mean FROM cognitive_block_preferences "
            "WHERE capability=? AND block_name=?", (capability, block_name)
        ).fetchone()
        return (int(row[0]), float(row[1])) if row else (0, 0.0)

    def choose(self, capability: str, *, explore: bool = False,
               rng: random.Random | None = None) -> Block:
        candidates = [b for b in self.blocks.values()
                      if capability in b.capabilities]
        if not candidates:
            raise LookupError("no installed catalog block for " + capability)
        if explore and (rng or random).random() < 0.15:
            return (rng or random).choice(candidates)
        # Successful results change *which* method BEAN selects next.
        # Untried blocks retain a neutral score; caller controls exploration.
        return max(candidates, key=lambda b: self.preference(capability, b.name)[1])

    def run(self, capability: str, payload: dict, *,
            block_name: str | None = None, context: dict | None = None,
            explore: bool = False, rng: random.Random | None = None,
            refresh: bool = False) -> dict:
        block = self.blocks[block_name] if block_name else self.choose(
            capability, explore=explore, rng=rng)
        if capability not in block.capabilities:
            raise ValueError("block does not implement " + capability)
        run_id = "block_" + uuid.uuid4().hex
        try:
            fn = self._load(block, refresh=refresh)
            output = fn(dict(payload), dict(context or {}))
            if not isinstance(output, dict):
                raise TypeError("block must return a dictionary")
            # Keep graph ports serializable across independent programs.
            json.dumps(output, allow_nan=False)
        except Exception as exc:
            # An unusable module is an observed negative outcome. Record it
            # and adapt selection before propagating the error to the caller.
            self.conn.execute(
                "INSERT INTO cognitive_block_runs "
                "(run_id, capability, block_name, code_revision, "
                "execution_status, error_summary) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, capability, block.name, self._revisions.get(block.name),
                 "error", f"{type(exc).__name__}: {exc}"[:500]),
            )
            self.conn.commit()
            self.feedback(run_id, -1.0)
            raise
        self.conn.execute(
            "INSERT INTO cognitive_block_runs "
            "(run_id, capability, block_name, code_revision) VALUES (?, ?, ?, ?)",
            (run_id, capability, block.name, self._revisions.get(block.name)),
        )
        self.conn.commit()
        return {"run_id": run_id, "block": block.name, "output": output,
                "revision": self._revisions.get(block.name)}

    def feedback(self, run_id: str, reward: float) -> dict:
        """Observed reward updates future selection, never just a report."""
        import math
        if not isinstance(reward, (float, int)) or not math.isfinite(reward):
            raise ValueError("reward must be finite")
        record = self.conn.execute(
            "SELECT capability, block_name, feedback "
            "FROM cognitive_block_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if record is None:
            raise KeyError(run_id)
        if record[2] is not None:
            raise ValueError("feedback already recorded for " + run_id)
        capability, block_name = record[0], record[1]
        count, average = self.preference(capability, block_name)
        updated = (average * count + float(reward)) / (count + 1)
        self.conn.execute(
            "UPDATE cognitive_block_runs SET feedback=? WHERE run_id=?",
            (float(reward), run_id),
        )
        self.conn.execute(
            "INSERT INTO cognitive_block_preferences "
            "(capability, block_name, visits, reward_mean) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(capability, block_name) DO UPDATE SET "
            "visits=excluded.visits, reward_mean=excluded.reward_mean",
            (capability, block_name, count + 1, updated),
        )
        self.conn.commit()
        return {"capability": capability, "block": block_name,
                "visits": count + 1, "mean_reward": updated}

    def chain(self, steps: list[dict], *, inputs: dict | None = None,
              context: dict | None = None) -> dict:
        """Run Scratch-style JSON nodes, referencing earlier output ports.

        Each step has id, capability, optional block, and payload. A value of
        {"$from": "node.key"} wires a previous node's output to an input port.
        """
        values = {"input": dict(inputs or {})}
        receipts = []
        for step in steps:
            node = step["id"]
            if node in values:
                raise ValueError("duplicate block node: " + node)
            payload = self._wire(step.get("payload", {}), values)
            receipt = self.run(
                step["capability"], payload, block_name=step.get("block"),
                context=context,
            )
            values[node] = receipt["output"]
            receipts.append({"node": node, **receipt})
        return {"outputs": values, "runs": receipts}

    @staticmethod
    def _wire(value, values):
        if isinstance(value, dict) and set(value) == {"$from"}:
            reference = value["$from"].split(".")
            current = values[reference[0]]
            for key in reference[1:]:
                current = current[key]
            return current
        if isinstance(value, dict):
            return {k: BlockRuntime._wire(v, values)
                    for k, v in value.items()}
        if isinstance(value, list):
            return [BlockRuntime._wire(v, values) for v in value]
        return value
