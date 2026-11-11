# Private legacy BIFF shipment adapter

This optional offline adapter converts legacy OLE/BIFF .xls shipment reports into
the existing BEAN Bridge shipment CSV schema, then reuses the existing snapshot
ledger. It never contacts ERP or the network, and has no access to mapped drives.

Install xlrd==2.0.2 locally, and keep the actual report and private mapping
JSON outside the public repository. The mapping requires start_row,
record_indicator_column, and columns keyed by canonical shipment field names.
All column and row indices are zero-based. Optional inherit fields support
continuation rows, and an optional trailing-field regex can recover a PO
from a subsequent non-record row. Record detection uses the numeric marker,
not presence of a job number. See source and synthetic fixture tests for the
configuration contract.

Use independent breakdown totals to verify the conversion, without
double-counting a breakdown's summary row. The adapter refuses to produce
a CSV until both expected line and late counts reconcile.

Example with fictional input filenames and fictional counts:

    python -m ezbean.jobboss_xls_adapter --source PRIVATE.xls --layout private-layout.json --expected-lines 3 --expected-late 1 --output PRIVATE.csv
    python -m ezbean.jobboss_exports --database PRIVATE.sqlite import PRIVATE.csv --captured-at 2026-01-01T12:00:00Z

The CSV output is create-only, never an overwrite. Keep source, mapping,
output and SQLite ledger on authorized private storage. Never publish real
report structure, employee records, job/customer data, or worksite details.

Evidence: synthetic CI builds real BIFF workbooks and checks repeated page
headers, continuation rows, blank job numbers, reconciliation failures,
source-file rejection, and importer handoff on Windows and Linux.

Limit: this does not prove compatibility with any specific private report.
The adapter retains blank-job shipment records in the existing ledger.
Bridge reporting counts these records separately under
unverifiable_due_date_shipment_lines (latest snapshot only), excludes them
from job-traceable OTD, and emits an aggregate management data-quality gap.
The reconciled CSV row count includes these exceptions, but the OTD
denominator excludes them. Unverifiable promise dates require a separate
authorized source, not an assumed on-time classification.
