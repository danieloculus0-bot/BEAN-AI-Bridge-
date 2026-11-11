# BEAN Operations — candidate pilot invitation and trial specification

**Technical beta, not a general-production offering.**
This is a reusable description of a potential short operational study. It does
not grant a license, authorize use of anyone's ERP, set pricing, or obligate
BEAN's owner to support a client. Approve those separately before inviting an
outside organization.

## The practical problem

Production managers and quality engineers often compare job schedules,
shipments and RMAs by hand. Missing exports, contradictory shipment dates and
late jobs can consume review time or lead to overconfident conclusions.

## What BEAN Operations does today

On a pilot PC, BEAN ingests **authorized, manually exported** Job Schedule,
Shipment Summary and RMA Tracker files. It produces a private local daily
exception brief with source-based status, a list of issues to investigate,
and a SQLite history for comparison and correction. It uses no hosted AI and
does not modify the ERP. Its shipment-line OTD calculation is **not**
automatically equivalent to a customer's official on-time-delivery policy.

RMA reason codes are optional, not missing-data findings.

## Proposed ten-workday controlled trial

- Site supplies exports by its established authorized method; raw customer,
  job and employee data stays on its private machine.
- Compare the existing manual review with BEAN-assisted review on the same
  snapshots. Record **both** review times, including time spent verifying
  alerts and addressing errors.
- An operator adjudicates confirmed useful findings, false alerts and missed
  issues; BEAN cannot mark its own outputs correct.
- Preserve unfavorable days, investigation history and backup/restore results.
- At the end, the site receives a local HTML/JSON trial report and a clear
  decision: stop, revise, repeat or evaluate a subsequent phase.

## How a prospective pilot could judge value

Primary metric: minutes spent for the same review scope.
Secondary metrics: confirmed useful exceptions, misleading alerts,
missed relevant issues, repeat usage, installation success, backup recovery
and operator confidence in the results.

Do not invent a return on investment or pricing advantage. The existing cloud
ten-day run used **fictional source data and fictional reviewer timings**.
It verifies software behavior, not achieved workplace performance.

## Items BEAN's owner must decide before an external pilot

- Authorized user/license and whether the pilot is free, paid, or trial-only.
- Who supports installation and data mapping; how issues are reported.
- Which on-site person can approve the pilot's KPI definitions and scope.
- Where private exports, logs and backups are stored and who may access them.
- Exit/discontinuation rules, technical support expectations and handling of
  pilot findings. The current repository contains no completed commercial
  agreement or permission grant.

## BEAN as a larger project

BEAN Core remains a **separate experimental cognition platform** with memory,
logic, goals, reasoning and module experimentation. This pilot does not
redefine BEAN as a conventional compliance app, nor does it add Core
behavioral restrictions. BEAN AI Bridge continues to serve as the module
communication layer.
