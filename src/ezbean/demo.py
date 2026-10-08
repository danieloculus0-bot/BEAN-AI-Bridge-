"""Run synthetic ERP events through the bridge. No real EZ Fab data is included."""
import argparse
import json
from pathlib import Path

from .bridge import FixtureAdapter, run_cycle
from .store import Ledger


def main() -> None:
    parser = argparse.ArgumentParser(description='EZ-BEAN generic smoke-test runner')
    parser.add_argument('--fixture', type=Path, default=Path('examples/synthetic_erp.jsonl'))
    parser.add_argument('--as-of', default='2026-10-08T16:00:00+00:00')
    parser.add_argument('--window-start', default='2026-10-01')
    args = parser.parse_args()
    ledger = Ledger()
    report, findings, added = run_cycle(FixtureAdapter(args.fixture), ledger, args.window_start, args.as_of)
    print(json.dumps({'mode': 'SYNTHETIC_TEST', 'events_ingested': added, 'report': report.to_dict(),
                      'findings': [f.to_dict() for f in findings]}, indent=2, sort_keys=True))
    ledger.close()


if __name__ == '__main__':
    main()
