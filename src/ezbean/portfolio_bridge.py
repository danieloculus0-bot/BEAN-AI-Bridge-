"""Optional real Bridge to experimental BEAN portfolio Q/state ledger.

Run BEAN Core's CLI in a separate checked-out interpreter process. Existing
Bridge cycle data stays in Bridge, never copied wholesale to public ledgers.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$")


def code(value):
    """Small, stable context reference. Names with spaces become coded IDs."""
    import hashlib
    if not isinstance(value, str) or not value:
        raise ValueError("missing context")
    normal = re.sub(r"[^a-z0-9_-]", "_", value.lower())[:55]
    return normal + "." + hashlib.sha256(value.encode()).hexdigest()[:12]


class BridgePortfolioLedger:
    def __init__(self, core_dir, database):
        self.root = Path(core_dir).resolve()
        self.database = Path(database).resolve()
        if not (self.root / "bean/optimization/portfolio_cli.py").is_file():
            raise ValueError("BEAN portfolio CLI is not available in selected checkout")

    def _invoke(self, command, args=(), event=None):
        env = {"PATH":os.environ.get("PATH",""),
               "PYTHONPATH":str(self.root),"PYTHONDONTWRITEBYTECODE":"1",
               "PYTHONIOENCODING":"utf-8"}
        if os.name == "nt":
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT","")
            env["TEMP"] = os.environ.get("TEMP","")
        result = subprocess.run(
            [sys.executable,"-m","bean.optimization.portfolio_cli",command,
             "--db",str(self.database),*args],
            cwd=self.root,env=env,
            input=json.dumps(event) if event is not None else None,
            text=True,capture_output=True,timeout=20,check=True)
        return json.loads(result.stdout)

    def remember_cycle(self, outcome, *, revision="bridge-research"):
        """Preserve a research cycle ID, NOT falsely reward a resolved claim."""
        cycle_id = str(outcome.cycle_id)
        if not ID.fullmatch(cycle_id):
            raise ValueError("invalid bridge cycle id")
        state = code(str(outcome.concept)) + "/" + code(str(outcome.result_status))
        return self._invoke("record",event={
            "app":"BEAN-AI-Bridge-",
            "event_id":cycle_id,"state":state,
            "action":None,"reward":None,"next_state":None,
            "done":False,"evidence_ref":"bridge://"+cycle_id,
            "kind":"unverified","revision":revision})

    def learn_from_evaluation(self, *, evaluation_id, concept, action,
                              reward, next_concept, evidence_ref, kind="synthetic",
                              revision="bridge-research"):
        """Only an externally evaluated, named outcome carries Q reward."""
        for value in (evaluation_id,action,evidence_ref):
            if not ID.fullmatch(str(value)):
                raise ValueError("invalid evaluation identity or evidence ref")
        if kind not in ("synthetic","measured"):
            raise ValueError("cannot reward unverified evidence")
        return self._invoke("record",event={
            "app":"BEAN-AI-Bridge-","event_id":evaluation_id,
            "state":code(concept),"action":action,"reward":reward,
            "next_state":code(next_concept),"done":False,
            "evidence_ref":evidence_ref,"kind":kind,"revision":revision})

    def context(self, query="", max_bytes=2048):
        return self._invoke("context",args=(
            "--app","BEAN-AI-Bridge-","--query",query,
            "--max-bytes",str(max_bytes)))

    def verify(self):
        return self._invoke("verify")
