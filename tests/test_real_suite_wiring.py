"""Cross-repository wiring checks against real, pinned BEAN and EZ-FEA sources.

Run in GitHub Actions on Windows and Linux. No model service, ERP access or
native solver is emulated or claimed: these are adapter/transport tests.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for folder in ("src", "bean-core", "fea-core"):
    location = ROOT / folder
    if not location.is_dir():
        raise RuntimeError(f"Required live source checkout missing: {location}")
    sys.path.insert(0, str(location))

from ezbean import FixtureAdapter, Ledger, run_cycle
from bean.integration import BeanReasoningLayer, EvidenceBridge, SourceClaim
from bean.runtime.inbox import CommandInbox
from bean.runtime.inbox_handlers import register_all
from bean.memory.store import get_store
from ezfea.bean import send_to_bean_inbox

AS_OF = "2026-10-08T16:00:00+00:00"
START = "2026-10-01"
FIXTURE = ROOT / "examples" / "synthetic_erp.jsonl"


class CrossRepositoryWiringTests(unittest.TestCase):
    def test_bridge_report_reaches_core_evidence_and_survives_restart(self):
        """Bridge ledger feeds Core as ONE unverified source, not knowledge."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ledger_path = root / "erp-evidence.sqlite"
            core_path = root / "bean-core.sqlite"
            ledger = Ledger(ledger_path)
            report, findings, added = run_cycle(
                FixtureAdapter(FIXTURE), ledger, START, AS_OF
            )
            self.assertEqual(added, 7)
            self.assertEqual(report.kpis["rma_count"].value, "2")
            self.assertIn("synthetic_erp:rma-001-v1",
                          report.kpis["rma_count"].evidence_ids)
            self.assertTrue(findings)
            ledger.close()

            digest = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
            claim = SourceClaim(
                record_id="bridge_rma_receipt",
                round_id="bridge_cycle_one",
                origin="bridge_ledger",
                source_ref=f"bridge-ledger:sha256:{digest}",
                value=report.kpis["rma_count"].value,
                verified=False, verification_ref=None,
                observed_at=AS_OF,
            )
            with BeanReasoningLayer(str(core_path)) as core:
                bridge = EvidenceBridge(core)
                opened = bridge.start(
                    "bridge_cycle_one", "manufacturing_rma_count",
                    "What is the recorded RMA count for this synthetic period?"
                )
                self.assertTrue(opened["new"])
                self.assertTrue(bridge.observe(claim))
                self.assertFalse(bridge.observe(claim))
                result = bridge.finalize("bridge_cycle_one")
                self.assertEqual(result["status"], "insufficient")
                self.assertIsNone(result["value"])
                self.assertEqual(result["execution_permission"], "none")
                self.assertIsNone(bridge.current("manufacturing_rma_count"))

            restored = Ledger(ledger_path)
            replay, _, repeat_added = run_cycle(
                FixtureAdapter(FIXTURE), restored, START, AS_OF
            )
            self.assertEqual(repeat_added, 0)
            self.assertEqual(replay.to_dict(), report.to_dict())
            restored.close()
            with BeanReasoningLayer(str(core_path)) as core:
                bridge = EvidenceBridge(core)
                history = bridge.history("manufacturing_rma_count")
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0]["status"], "insufficient")
                self.assertIsNone(bridge.current("manufacturing_rma_count"))
                self.assertEqual(bridge.pending(), [])

    def test_fea_handoff_is_consumed_by_real_core_inbox_and_logged(self):
        """EZ-FEA handoff is a factual BEAN note, never a solver verdict."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            inbox_dir = root / "inbox"
            inbox_dir.mkdir()
            digest = hashlib.sha256(b"synthetic CAD bytes").hexdigest()
            handoff = root / "bean_handoff.json"
            handoff.write_text(json.dumps({
                "schema": "ezfea.bean_handoff.v1",
                "analysis": {
                    "status": "completed", "input_sha256": digest,
                    "disclaimer": "EXPERIMENTAL - NOT VALIDATED FOR ENGINEERING SIGN-OFF",
                },
                "bean_review_status": "not_requested",
            }), encoding="utf-8")
            with patch.dict(os.environ, {"EZFEA_BEAN_INBOX": str(inbox_dir)}):
                receipt = send_to_bean_inbox(handoff)
            self.assertTrue(receipt.is_file())
            transmitted = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(transmitted["command"], "log_note")
            self.assertEqual(transmitted["from"], "ezfea")
            self.assertIn(digest, transmitted["args"]["text"])
            self.assertIn("experimental_not_validated", transmitted["args"]["text"])

            core_db = root / "core.sqlite"
            with BeanReasoningLayer(str(core_db)) as core:
                inbox = CommandInbox(inbox_dir)
                register_all(inbox)
                results = inbox.poll(core.session_uuid)
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["status"], "ok")
                self.assertEqual(results[0]["command"], "log_note")
                self.assertEqual(results[0]["result"], {"logged": True})
                self.assertEqual(inbox.poll(core.session_uuid), [])
                self.assertEqual(len(list((inbox_dir / "processed").glob("*.json"))), 1)
                notes = get_store().fetchall(
                    "SELECT data FROM events WHERE subtype='runtime_note'"
                )
                self.assertEqual(len(notes), 1)
                logged = json.loads(notes[0]["data"])
                self.assertEqual(logged["from"], "ezfea")
                self.assertIn(digest, logged["text"])
                self.assertIn("experimental_not_validated", logged["text"])
            with BeanReasoningLayer(str(core_db)) as core:
                notes = get_store().fetchall(
                    "SELECT data FROM events WHERE subtype='runtime_note'"
                )
                self.assertEqual(len(notes), 1)
                self.assertEqual(json.loads(notes[0]["data"])["from"], "ezfea")
                self.assertEqual(CommandInbox(inbox_dir).poll(core.session_uuid), [])


if __name__ == "__main__":
    unittest.main()
