# Cross-platform cross-repository wiring evidence

This is an integration test against three real repository source trees checked
out in GitHub Actions, not copied sample implementations.

1. BEAN AI Bridge -> BEAN Core: Bridge reads synthetic ERP events into its
   actual append-only SQLite ledger and computes KPI values with evidence IDs.
   One KPI is passed to the actual Core EvidenceBridge as a single unverified
   claim. Core persists the observation across a restart, but must not certify
   it, manufacture independent corroboration, or authorize action. Bridge
   replay remains idempotent after restart.
2. EZ-FEA -> BEAN Core: Actual EZ-FEA file transport writes a report note to
   the actual Core CommandInbox; the registered Core log_note handler processes
   it, persists the factual source SHA and unvalidated status in SQLite, and
   does not reprocess the note after restart. This is transport validation,
   not numerical verification of the 3D CalculiX solver.

The workflow (../.github/workflows/real-suite-wiring.yml) runs on both
Windows and Ubuntu using Python 3.11 and Python 3.12, with explicit Git SHA
pins for Core and EZ-FEA. Temporary test data only; no live ERP, customer
drawings, real FEA claims, proprietary records, credentials or paid AI model.

Not yet connected: live Axiom <-> ForgeVault, ForgeVault <-> EZ-FAIR or
authoritative manufacturing data exchange. We do not claim these tests
validate integrations that have not been implemented. Whenever Core/FEA API
contracts change, update pinned SHAs and rerun the full four-job matrix.
