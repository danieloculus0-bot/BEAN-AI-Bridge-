"""Append-only SQLite evidence ledger with duplicate detection and full replay."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .core import Observation


class Ledger:
    def __init__(self, database: str | Path = ':memory:') -> None:
        self.connection = sqlite3.connect(str(database))
        self.connection.execute('''CREATE TABLE IF NOT EXISTS observations (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            event_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE(source, event_id))''')
        self.connection.commit()

    def ingest(self, observation: Observation) -> bool:
        serialized = json.dumps(observation.payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
        key = (observation.source, observation.event_id)
        old = self.connection.execute('SELECT entity_type, entity_id, observed_at, payload_json FROM observations WHERE source=? AND event_id=?', key).fetchone()
        val = (observation.entity_type, observation.entity_id, observation.observed_at, serialized)
        if old is not None:
            if old != val:
                raise ValueError(f'Conflicting ERP event identity {key}')
            return False
        self.connection.execute('INSERT INTO observations(source,event_id,entity_type,entity_id,observed_at,payload_json) VALUES (?,?,?,?,?,?)', (*key, *val))
        self.connection.commit()
        return True

    def ingest_all(self, observations: Iterable[Observation]) -> int:
        return sum(1 for o in observations if self.ingest(o))

    def replay(self) -> list[Observation]:
        rows = self.connection.execute('SELECT source,event_id,entity_type,entity_id,observed_at,payload_json FROM observations ORDER BY sequence').fetchall()
        return [Observation(source=s, event_id=i, entity_type=t, entity_id=e, observed_at=d, payload=json.loads(p)) for s,i,t,e,d,p in rows]

    def close(self) -> None:
        self.connection.close()
