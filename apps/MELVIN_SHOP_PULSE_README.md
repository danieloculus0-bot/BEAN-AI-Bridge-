# Melvin Assistant: Shop Pulse v0.2

A single-file, browser-based, offline prototype for shop-floor operational awareness.

## Launch

Open `index.html` in Chrome, Edge, or another modern browser. No installer, Python, server, account, or internet connection is required. The browser reads local user-selected report files into memory. It does not upload, store, or modify ERP information.

## Primary workflow

1. Click **IMPORT REPORT** (large blue button).
2. Choose the meaning of the report: Shipment Summary, Job Schedule, RMA/Customer Return, Production/Scrap, CAR/NCR, or Machine/PM.
3. Select a CSV, TSV, JSON, or XLSX report.
4. Review canonical field names versus source column names. Known aliases are mapped automatically, fuzzy suggestions must be confirmed. Missing fields must be mapped explicitly or the KPI calculation is blocked.
5. Click **Calculate verified KPIs**. Load more report types to build a composite Shop Pulse. Each report type replaces only its own prior import. **Demo** clears all imported data.

### KPI rules

| Type | Calculated KPIs | Important guardrail |
| --- | --- | --- |
| Shipment Summary | Completed lines and OTD % | Shipped date versus mapped promise date; actual official definition must be approved |
| Job Schedule | Confirmed open jobs, past-due | Unknown statuses become N/A, not silently interpreted as open |
| RMA | Distinct RMA IDs, returned quantity, dollar cost | Costs remain N/A if any required cost is missing |
| Production/Scrap | Good units, scrap units, scrap % | Both quantities required; formula scrap / (good + scrap) |
| CAR/NCR | Open actions, overdue actions, closed actions | Status vocabulary must be recognized |
| Machine/PM | PM task count, overdue count | Status vocabulary must be recognized |

Missing reports always show **N/A**. Imported metrics are not combined with the synthetic five-replay demonstration. Rejected rows are excluded and counted. Unsupported or missing denominators are not interpreted as zero.

## Simulated five-replay view

The synthetic 1,618-case experiment contributed five real **synthetic** trial records: 1, 5, 19, 110, and 160. All inject the fictional missing thread-mask failure in part SIM-EZB-1618-A. These deliberately include a baseline customer escape, a prevented fault, an internal catch, and a remaining corrected-route escape.

On the selected five tests, simulated corrected-route internal detection to customer escape is 2:1, exceeding the **experimental** 1.618:1 threshold. Five deliberately selected cases provide no statistical process capability proof.

Commands such as **Investigate defect**, **Hold/contain**, **Draft corrective action**, and **Verify effectiveness** generate **offline, non-authoritative** test outputs for the fictional work order. They do not take actions inside JobBoss², a QMS, or any other ERP.

## 64Δ-style 8x8 board

The 8x8 operational board is only a visual process map inspired by the existing 64Δ prototype. It is **not** a dependency on, or integration with, the 64Δ business logic engine.

## Excel limitation

The included parser reads conventional XLSX first-sheet cells (inline/shared strings and numeric values) using built-in browser ZIP decompression. It does not evaluate formulas or macros or combine multiple sheets. If an unusual XLSX export cannot be read, save it as CSV from the originating application. Dates must be actual ISO, US numeric dates, or Excel serials.

## Deployment boundaries

Public-safe fictional data only. No real EZ Fab customer, personnel, supplier, machine serial, order, account or ERP data is packaged. Before a company rollout, validate actual JobBoss² field semantics and the official OTD/RMA counting definitions, establish authorized read-only access, add identity and authorization controls, and complete source reconciliation.

Source: https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/blob/main/apps/melvin_shop_pulse.html