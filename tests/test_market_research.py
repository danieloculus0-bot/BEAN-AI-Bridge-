import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from ezbean.market_research import MarketResearchLedger,validate_context

def packet():
    p={"schema":"aiscend.bean.research_context.v1","as_of":"2026-10-24T12:00:00Z","scope":"research_evidence_not_trade_authorization","evidence":[{"first_seen_at":"2026-10-24T11:00:00Z","published_at":"2026-10-23T11:00:00Z","available_at":"2026-10-24T11:00:00Z","analysis":{"claims_verified":False}}],"claims":{"trade_authorized":False,"profitability_demonstrated":False}}
    return sign(p)

def sign(p):
    p.pop("content_sha256",None)
    p["content_sha256"]=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    return p

class MarketResearchTests(unittest.TestCase):
    def test_temporal_scope_and_tampering(self):
        p=packet()
        validate_context(p,decision_as_of="2026-10-24T13:00:00Z")
        with self.assertRaises(ValueError):validate_context(p,decision_as_of="2026-10-24T11:00:00Z")
        q=copy.deepcopy(p);q["as_of"]="2026-10-23T12:00:00Z"
        with self.assertRaises(ValueError):validate_context(q,decision_as_of="2026-10-24T13:00:00Z")
        q=copy.deepcopy(p);q["claims"]["trade_authorized"]=True;sign(q)
        with self.assertRaises(ValueError):validate_context(q,decision_as_of="2026-10-24T13:00:00Z")
    def test_evidence_cannot_be_backdated(self):
        q=packet();q["evidence"][0]["available_at"]="2026-10-23T11:00:00Z";sign(q)
        with self.assertRaises(ValueError):validate_context(q,decision_as_of="2026-10-24T13:00:00Z")
    def test_durable_receipt_and_historical_recall(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"ledger.sqlite3";p=packet()
            with MarketResearchLedger(path) as ledger:
                self.assertTrue(ledger.ingest(p,observed_at="2026-10-24T13:00:00Z")["inserted"])
                self.assertFalse(ledger.ingest(p,observed_at="2026-10-24T14:00:00Z")["inserted"])
                self.assertEqual(ledger.recall(as_of="2026-10-24T12:30:00Z"),[])
                with self.assertRaises(sqlite3.IntegrityError):ledger.con.execute("DELETE FROM market_research_packets")
            with MarketResearchLedger(path) as ledger:
                self.assertEqual(ledger.recall(as_of="2026-10-24T13:00:00Z"),[p])

if __name__=="__main__":unittest.main()
