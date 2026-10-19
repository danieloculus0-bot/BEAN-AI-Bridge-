"""Read-only synthetic representation benchmark for BEAN Core/Bridge.

Compare payloads that BEAN actually passes: observations, cognitive context,
method-feedback records and numeric histories. This changes no production
serializer and records evidence, not a preconceived format winner.

Run: python -m experiments.representation_sweep.benchmark --out results.json
Optional: pip install msgpack  (experiment ONLY, not Bridge dependency).
"""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
import statistics
import struct
import sys
import time

try:
    import msgpack
except ImportError:
    msgpack = None


def _encode_json(value, *, canonical: bool):
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False,
        sort_keys=canonical, separators=(",", ":")
    ).encode("utf-8")


def _canonical(value):
    return _encode_json(value, canonical=True)


def _compact(value):
    return _encode_json(value, canonical=False)


def fixtures() -> dict:
    observation = {
        "event_uuid": "synthetic-e-0001",
        "type": "sensor_reading",
        "observed_at": "2026-10-19T09:00:00-05:00",
        "data": {"temperature_c": 87.125,
                 "quality": {"$bean_nonfinite_float": "nan"},
                 "source": "mock_thermocouple", "confidence": 0.41},
        "causality": {"parent_ids": ["synthetic-e-0000"]},
    }
    reasoning = {
        "session": {"id": "synthetic-session", "stage": "experimental"},
        "recent_events": [
            {"id": i, "summary": "simulated signal " + str(i),
             "data": {"reading": round(i * 0.03125, 6),
                      "hypothesis": "fixture-" + str(i % 3)}}
            for i in range(20)
        ],
        "open_goals": [
            {"id": f"g{i}", "question": f"Why was error {i} observed?",
             "priority": i % 5, "state": "open"}
            for i in range(12)
        ],
        "uncertainty": {"unknown": True, "trust": 0.13, "provisional": True},
    }
    feedback = {
        "run_id": "block_synthetic123", "strategy": "bean.mean_sign",
        "reward": 0.75, "observed": True, "parent_event_ids": [1, 3, 8],
        "method_revision": "synthetic-git-revision", "failure": None,
    }
    numbers = [round((i % 47 - 23) * 0.013671875, 8) for i in range(4096)]
    return {
        "observation": observation,
        "reasoning_context": reasoning,
        "feedback_receipt": feedback,
        "numeric_series_4096": {"samples": numbers},
    }


def _median_us(operation, loops: int) -> float:
    # Measurements are descriptive, not assertions or performance SLAs.
    timings = []
    for _ in range(5):
        start = time.perf_counter_ns()
        for _ in range(loops):
            operation()
        timings.append((time.perf_counter_ns() - start) / loops / 1000)
    return round(statistics.median(timings), 3)


def _trial(name: str, value, fmt: str, encode, decode, loops: int):
    raw = encode(value)
    returned = decode(raw)
    if returned != value:
        raise AssertionError(f"{name}/{fmt} lost or changed information")
    return {
        "dataset": name, "format": fmt, "encoded_bytes": len(raw),
        "encode_us_median": _median_us(lambda: encode(value), loops),
        "decode_us_median": _median_us(lambda: decode(raw), loops),
        "roundtrip_ok": True,
    }


def run(*, loops: int = 100) -> dict:
    if loops < 1 or loops > 5000:
        raise ValueError("loops outside experiment range")
    rows = []
    for name, value in fixtures().items():
        strict_decode = lambda raw: json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda x: (_ for _ in ()).throw(
                ValueError("non-standard JSON constant " + x)),
        )
        rows.append(_trial(
            name, value, "json_compact", _compact, strict_decode, loops,
        ))
        rows.append(_trial(
            name, value, "json_canonical", _canonical, strict_decode, loops,
        ))
        if msgpack:
            rows.append(_trial(
                name, value, "msgpack",
                lambda x: msgpack.packb(x, use_bin_type=True, strict_types=True),
                lambda raw: msgpack.unpackb(raw, raw=False), loops,
            ))
        if name == "numeric_series_4096":
            # Typed binary arrays are only meaningful for homogeneous signals:
            # they cannot directly carry goals, tags, provenance or records.
            values = value["samples"]
            def pack(x):
                return struct.pack("<" + str(len(x["samples"])) + "d",
                                   *x["samples"])
            def unpack(raw):
                n = len(raw) // 8
                return {"samples": list(struct.unpack("<" + str(n) + "d", raw))}
            rows.append(_trial(name, value, "binary_float64_little_endian",
                               pack, unpack, loops))
    return {
        "schema": "BEAN_REPRESENTATION_SWEEP_V1",
        "synthetic": True,
        "changes_runtime_format": False,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "iterations_per_sample": loops,
        "comparison_notes": [
            "Small synthetic microbenchmarks are environment dependent.",
            "Do not rank candidates solely by encoded bytes or microseconds.",
            "Python in-process dict communication need not serialize at all.",
            "Binary float64 requires external metadata: units, timestamps and provenance.",
            "JSON/MessagePack here preserve tagged non-finite observations without interpretation.",
            "No schema migration or default module protocol change was executed.",
        ],
        "results": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--loops", type=int, default=100)
    args = parser.parse_args()
    outcome = run(loops=args.loops)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps({"recorded": len(outcome["results"]),
                      "formats": sorted({r["format"] for r in outcome["results"]}),
                      "output": str(args.out)}))


if __name__ == "__main__":
    main()
