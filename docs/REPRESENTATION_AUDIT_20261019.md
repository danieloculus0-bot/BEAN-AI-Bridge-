# BEAN representation audit — October 19, 2026

**Status: measured prototype, no default migration.** The objective was to
evaluate information fidelity and movement inside the existing Core/Bridge
architecture, not create a new cognitive layer.

## Current representation map (source inspected)

| Boundary | Today | Observed concern | Verdict |
| --- | --- | --- | --- |
| Python cognition -> Bridge callable | Native `dict` arguments and results | Bridge serializes result to check JSON compatibility, even though modules share a Python process | Keep Python structures in-process; no mandatory encoding when not crossing a process boundary |
| Core event -> SQLite `events.data` | JSON in TEXT column | Previous `json.dumps` could record non-standard `NaN`/`Infinity`; Bridge enforces strict JSON | Repair encoding, preserve original semantic status |
| SQLite -> Core memory recall -> Bridge output port | SQLite text decoded into Python values | Legacy non-finite values could leak into strict Bridge output and be confused with failed cognitive method | Decode with explicitly tagged non-finite semantics |
| Core reasoning context | Python dict serialized to JSON text for explainable packet | Same historical non-finite ambiguity in observed events | Carry strict, tagged observations into context |
| Bridge block runner output | Validated with `json.dumps(..., allow_nan=False)` | A *transport* failure was counted as a **negative learned outcome** for that method | Split transport error from actual execution result; only the latter affects preference |
| Bridge learning receipts | SQLite structured columns; JSON in experiment record fields | A general-purpose text format is understandable but not necessarily optimal for numerical volume | Keep readable ledgers; tune only after measuring |
| Numeric and sensory streams | Python numerical lists through JSON-compatible ports | Expensive serialization and larger representations for thousands of homogeneous readings | Binary/MessagePack deserve later specialized evaluation, not a global switch |

## Important repairs already made

1. Core event logging now encodes `NaN`, `+Infinity`, and `-Infinity`
   as explicit tagged JSON objects: `{"$bean_nonfinite_float":"nan"}`,
   `{"$bean_nonfinite_float":"+inf"}`, and
   `{"$bean_nonfinite_float":"-inf"}`.
   This is **not** null substitution or invented measurements.
2. Core memory recall and reasoning context can interpret historical
   non-standard Python JSON tokens into those same explicit tags, without
   changing the SQLite record or the existing byte-checked audit mirror.
3. Bridge distinguishes `transport_error` receipts from actual
   `error` execution receipts. A non-JSON-compatible output remains an
   explicit error, but it no longer gives the cognitive strategy an
   unwarranted negative reward.
4. The format experiment compares strict compact and canonical UTF-8 JSON,
   optional MessagePack, and little-endian float64 arrays for homogeneous
   numerical readings. It records data size and median encode/decode
   microseconds plus strict round-trip results.

## Benchmark methodology and limitations

Run:

```bash
python -m pip install msgpack
python -m experiments.representation_sweep.benchmark --out format-evidence.json --loops 150
```

Tests and experiments also execute on GitHub Actions (Windows and Linux,
Python 3.10 and 3.12). MessagePack is an **experiment-only** dependency and
is not added to BEAN's install requirements. The script still runs without
it, marking the unavailable candidate by absence of rows.

Compact JSON is tested in original field order; canonical JSON additionally
sorts object keys for repeatable evidence hashing. Keeping them separate avoids
misattributing canonicalization overhead to JSON itself.\n\nDatasets are synthetic but shaped like actual observed events, reasoning
packets, Bridge feedback receipts, and 4096-item numerical arrays. Each
result must round-trip without changes. The format benchmark does **not**
measure actual production workloads, cross-process RPC latency, large
database query plans, schema-version evolution, GPU tensor transport,
multi-machine throughput or real customer data. Results fluctuate by CPU,
Python version and operating system; compare both size and decode speed,
not just best encode timing.

Typed binary stores values efficiently but carries **no provenance, units,
timestamps, feature names, missing-value semantics or trust metadata**
unless those are separately defined. MessagePack is smaller on common
fixtures and encodes binary, but is less inspectable without tooling.
Strict JSON is portable and readable but does not define `NaN`, non-finite
infinity, Python Decimal, arbitrary Python objects, or lossless JavaScript
handling of 64-bit integers beyond 2^53. These are **representation and
consumer-contract questions**, not permission rules for experiments.

## Format decision: keep the current architecture; develop a native contract

- **Memory of events and learned outcomes**: SQLite with explicit typed
  columns for identity, source, time and relational references; JSON TEXT
  for variable, readable observation metadata where it fits.
- **Same-process cognition**: native Python types; avoid unnecessary
  stringify/parse cycles between blocks.
- **Bridge interoperability**: stable versioned input/output semantics
  (event references, value provenance, units, optional/missing/unknown,
  timestamps, strategy and measured reward). Use JSON externally for
  inspection and simple exchange. Do not silently change active APIs.
- **Dense numerical observations**: future opt-in binary or MessagePack
  transport *only if* representative profiling shows it is worth it.
  Preserve metadata outside the raw numeric buffer and preserve a way
  back to the original observational context.
- **Audit and debugging**: maintain canonical readable JSONL mirror as
  well as the authoritative SQLite ledger. Do not rewrite historical
  mirror entries just to cosmetically normalize old data.
- **Do not adopt a graph database, event broker or protobuf schema merely
  because they sound brainlike.** The cognitive experiment needs the
  correct information relationships, not more moving parts.

## Next checks before any real format change

1. Compare small/large *measured* task trajectories on realistic BEAN
   workloads and log their actual data sizes/frequencies.
2. Verify that both old and new module versions agree on how to interpret
   `$bean_nonfinite_float` and on reserved marker key collision policy;
   no consumer should mistake a tagged unknown for a confirmed number.
3. Test timestamp timezones, larger-than-JavaScript-safe integers,
   Decimal precision, schema evolution, unknown fields, and process
   restarts before introducing additional data types.
4. Add an explicit portable event/feedback contract when the ordinary
   Core-to-Bridge autonomous experiment dispatch is being wired.
5. Separate **learned performance of an algorithm** from **failure of a
   transport or storage representation** in every real feedback path.

All patches live in two new experimental branches:
`experiment/representation-fidelity-20261019` in BEAN and
BEAN-AI-Bridge-. No merge, public site work, new cognitive modules,
commercial pitch, or new executable behavioral restrictions.
