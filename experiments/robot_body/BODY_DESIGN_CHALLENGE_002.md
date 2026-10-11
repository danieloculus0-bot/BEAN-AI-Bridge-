# BEAN Body Design Challenge 002: topology-neutral embodiment

## Objective
Let BEAN select its own optimized physical body based on measurable engineering goals, rather than imposing a quadruped, humanoid, or wheeled form. This is an experiment specification, not a completed run.

## Candidate architectures
Evaluate differential wheeled, quadruped, hexapod, and other mechanically plausible topologies. Include a modular printed body option compatible with a Raspberry Pi 4, Nano controllers, and off-the-shelf actuators. The existing 8-servo quadruped from Lab 001 is a baseline, not the required winner.

## Method
1. A conventional CAD/robotics agent creates a baseline parametric model for each eligible topology, with editable source and exportable geometry.
2. Freeze baselines, seeds, evaluation rules, and computational budgets.
3. BEAN proposes alternative morphologies and parametric revisions, records its reasons and uncertainty, and uses the same physics/structural analysis tools to evaluate them.
4. Run multiple seeds and conditions: flat ground, obstacles, low traction, load changes, actuator derating, and tip stability. Record failures.
5. Validate CAD geometry (watertight solids, clearances, printable minimum features, fastener access), estimated print mass, and replaceable modules.
6. Compare candidates using Pareto tradeoffs, not an arbitrary single score. BEAN must state why it prefers its selected body.
7. Preserve baseline, all candidate parameters, simulation configurations, source files, results, and BEAN decision trace.

## Ground rules
- No actual motors or fabrication required.
- Do not call simplified MuJoCo primitives printable CAD or finite-element stress analysis.
- Treat actuator curves, PETG anisotropy, fastener retention, battery capacity, and costs as unverified until measured.
- No claiming BEAN autonomously chose a design until its code actually performs candidate selection and exports traceable results.
- Keep Lab 001 and its reported results unchanged.

## Initial success gate
A reproducible run with at least three distinct topologies, a CAD baseline for each, independent holdout simulations, and a reasoned, auditable BEAN selection that outperforms at least one specialist baseline without hiding tradeoffs.
