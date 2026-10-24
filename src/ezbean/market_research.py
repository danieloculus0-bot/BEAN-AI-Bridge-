"""Read AIscend research context into a separate, timestamped BEAN evidence ledger.

Financial research is deliberately kept out of ERP KPI observations. No trade
executor or strategy-code writer is exposed by this adapter.
"""
from __future__ import annotations
import hashlib
import json
import math
import sqlite3
from datetime import datetime,timezone
from pathlib import Path

SCHEMA="aiscend.bean.research_context.v1"

def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)

def _time(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        if not math.isfinite(value):raise ValueError("Nonfinite timestamp")
        return float(value)
    parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if parsed.tzinfo is None:raise ValueError("Explicit timezone required")
    return parsed.timestamp()

def validate_context(payload,*,decision_as_of):
    if not isinstance(payload,dict) or payload.get("schema")!=SCHEMA:raise ValueError("Unsupported market-research schema")
    copied=dict(payload);receipt=copied.pop("content_sha256",None)
    if receipt!=hashlib.sha256(_canonical(copied).encode()).hexdigest():raise ValueError("Research packet checksum mismatch")
    if _time(payload["as_of"])>_time(decision_as_of):raise ValueError("Research packet from future")
    if payload.get("scope")!="research_evidence_not_trade_authorization":raise ValueError("Research scope required")
    claims=payload.get("claims",{})
    if claims.get("trade_authorized") is not False or claims.get("profitability_demonstrated") is not False:raise ValueError("Packet cannot grant trading authority or assert validated profitability")
    for row in payload.get("evidence",[]):
        available=_time(row["available_at"])
        seen=_time(row["first_seen_at"])
        published=_time(row["published_at"]) if row.get("published_at") else -math.inf
        if available<max(seen,published) or available>_time(payload["as_of"]):raise ValueError("Evidence availability leakage")
        if not isinstance(row.get("analysis"),dict) or row["analysis"].get("claims_verified") is not False:raise ValueError("Unverified headline claims must remain labeled")
    return payload

class MarketResearchLedger:
    def __init__(self,path):
        self.con=sqlite3.connect(path)
        self.con.execute("CREATE TABLE IF NOT EXISTS market_research_packets(id TEXT PRIMARY KEY,context_as_of REAL NOT NULL,ingested_at REAL NOT NULL,payload_json TEXT NOT NULL)")
        self.con.execute("CREATE TRIGGER IF NOT EXISTS market_research_no_update BEFORE UPDATE ON market_research_packets BEGIN SELECT RAISE(ABORT,'immutable research packet'); END")
        self.con.execute("CREATE TRIGGER IF NOT EXISTS market_research_no_delete BEFORE DELETE ON market_research_packets BEGIN SELECT RAISE(ABORT,'immutable research packet'); END")
        self.con.commit()
    def close(self):self.con.close()
    def __enter__(self):return self
    def __exit__(self,*a):self.close()
    def ingest(self,payload,*,observed_at):
        validate_context(payload,decision_as_of=observed_at)
        with self.con:
            result=self.con.execute("INSERT OR IGNORE INTO market_research_packets VALUES (?,?,?,?)",(payload["content_sha256"],_time(payload["as_of"]),_time(observed_at),_canonical(payload)))
        return {"packet_id":payload["content_sha256"],"inserted":result.rowcount==1,"mode":"research_only","trade_authorized":False}
    def recall(self,*,as_of):
        timestamp=_time(as_of)
        rows=self.con.execute("SELECT payload_json FROM market_research_packets WHERE context_as_of<=? AND ingested_at<=? ORDER BY context_as_of,id",(timestamp,timestamp))
        return [validate_context(json.loads(row[0]),decision_as_of=as_of) for row in rows]

def load_context(path,*,decision_as_of):
    return validate_context(json.loads(Path(path).read_text(encoding="utf-8")),decision_as_of=decision_as_of)
