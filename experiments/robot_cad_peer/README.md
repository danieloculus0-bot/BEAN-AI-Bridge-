# BEAN / Shelbot CAD: independent mechanical QA peer

This is an **independent engineering verification lane** for the ongoing robotics/body design experiment in [Bridge PR #1](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/pull/1). It leaves the experiment's simulation source, MuJoCo results and BEAN choice of topology untouched.

## What the verifier actually checks

The independent gate accepts `part.step`, `part.stl`, and `interface.json` from any CAD author who explicitly adopts the **experimental axle-block** interface. It does not assume the CAD author's declared dimensions are true; it imports the real STEP solid with CadQuery/OpenCASCADE and the actual STL triangle mesh with Trimesh.

It requires one valid STEP solid, a manifold/oriented positive-volume STL, close STEP/STL volume and **absolute bounding-box** agreement, a 6.35 mm nominal through-axle interface with an allowed 6.50–7.10 mm bore, two declared M4-class mounting passages with 4.15–4.80 mm allowed bores, local solid-web evidence, and an explicit maximum size envelope. Axle and bolt passages are checked through the **actual solid**, not a JSON flag.

The supplied **neutral reference fixture** is a real parametric 38 × 30 × 24 mm block with an experimentally assumed 6.65 mm axle bore and two 4.30 mm vertical mount holes. It is deliberately not BEAN's autonomous design nor a specialist optimal baseline; it exists so the independent verifier can be tested against both good and deliberately defective CAD.

## Eleven adversarial tests

A valid real CAD export must pass. The checker must reject blind/blocked axle passage, axle bore undersize, axle bore oversize, omitted mounting holes, bolt undersize, oversize envelope, unrelated STL shape, non-manifold STL, false unit metadata, and an STL **translated 5 mm without corresponding STEP movement**.

The translated-mesh adversarial test caught and drove a real verifier correction: checking only mesh extents is insufficient because an entire part could be misregistered even when its dimensions are identical.

## Run and inspect evidence

Python 3.11+; CadQuery 2.8.0, Trimesh 4.11.1:

```bash
python -m unittest discover -s experiments/robot_cad_peer -p test_cad.py -v
python experiments/robot_cad_peer/axle_fixture.py --out robot-cad-peer-results
python experiments/robot_cad_peer/verify.py --folder robot-cad-peer-results
```

The isolated [Shelbot CAD peer workflow](../../.github/workflows/bean-shelbot-cad-peer.yml) runs exactly those commands and preserves actual STEP/STL output, input interface, SHA256 hashes and the machine-readable QA receipt. All source changes are confined to this peer lane. The parent BEAN robotics branch and its original Lab 001 results stay independent.

**Limits:** Passing here is *not* finite-element analysis, measured load strength, printer fit, motor/gearbox compatibility, thermal durability, bearing retention, full tolerance stack-up, slicer validation, or physical hardware proof. The declared interfaces are assumptions pending the designer's requirements, and cannot be silently treated as production specifications.

## How BEAN can use this

Have BEAN design an alternate axle mount or another conforming component in CAD, emit actual STEP + STL, and run the **unmodified independent verifier**. Record failed geometry and its reasons; use the feedback to improve the *CAD source*. Do not edit the checker or substitute a reference fixture as BEAN's answer. The separate topology-neutral robot-design challenge remains open.
