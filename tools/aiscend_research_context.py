"""Ingest a local AIscend BEAN_CONTEXT.json packet, without network or trade access."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from ezbean.market_research import MarketResearchLedger,load_context

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--context",type=Path,required=True)
    p.add_argument("--ledger",type=Path,required=True)
    p.add_argument("--as-of",default=None)
    args=p.parse_args(argv)
    asof=args.as_of or datetime.now(timezone.utc).isoformat()
    payload=load_context(args.context,decision_as_of=asof)
    args.ledger.parent.mkdir(parents=True,exist_ok=True)
    with MarketResearchLedger(args.ledger) as ledger:
        receipt=ledger.ingest(payload,observed_at=asof)
        receipt["packets_available"]=len(ledger.recall(as_of=asof))
    print(json.dumps(receipt,indent=2))
    return 0

if __name__=="__main__":raise SystemExit(main())
