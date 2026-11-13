# BEAN AI Bridge (EZ-BEAN)

Synthetic-data evidence, KPI and replay layer for manufacturing/ERP analysis. It is an experimental adapter and reasoning bridge—not a deployed live ERP connector or enterprise dashboard.

## Current build state

**Reviewed:** 2026-10-20 · **Main:** `6a8782dcaa22` · **Stage:** experimental/beta.

- [EZ-BEAN cross-platform smoke and replay](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/39498949989) — **Passed** at inspected `main`.
- [BEAN deterministic knowledge gate regression](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/39498949965) — **Passed** at inspected `main`.
- [BEAN JobBOSS export sponge smoke](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/39498950143) — **Passed** at inspected `main`.
- [Real cross-repository wiring (Windows and Linux)](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/39498949970) — **Passed** at inspected `main`.

Consult [live Actions](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions) before treating any build as release-ready.

## Working implementation

- Generic offline ERP fixture ingestion, persistent ledger/replay, evidence-linked metrics and exception reports.
- Real checked-out **BEAN Bridge → BEAN Core** and **EZ-FEA → BEAN Core** JSON/file handoff tests on Windows and Ubuntu with Python 3.11/3.12.
- Independent experimental learning, review and repair test labs; supported positive receipts are separate from failed exploratory runs.

## Install and verification

Follow the [full earlier README](docs/archive/README_2026-10-20_before_refresh.md) for synthetic fixture commands; run the Bridge test suite and its [real cross-repository wiring workflow](.github/workflows/real-suite-wiring.yml).

## Known limitations

- No authenticated live connection to an employer or any particular ERP system is established by synthetic fixtures.
- Passing event transport does not show generalized AI autonomy or deployable automatic code repairs.
- A single unverified observation must not be misrepresented as independently corroborated evidence.

## Next priorities

Version and validate real read-only, authorized ERP export adapters; prove replay and source identity across independently managed systems.

## Documentation

- [Wiring evidence documentation](docs/REAL_SUITE_WIRING.md)
- [BEAN Core](https://github.com/danieloculus0-bot/BEAN)
- [**Original complete README: earlier designs, experiments, full setup and history**](docs/archive/README_2026-10-20_before_refresh.md)

Older milestones have been archived rather than presented as current build capabilities.
