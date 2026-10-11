# BEAN Robotics Lab 001: self-optimized cheap-servo body

A physics-backed experiment **inside BEAN AI Bridge**, with real BEAN Core governor registration. The first form is an 8-servo, 4-legged, 3D-printable robot. **It is not Atlas and is not yet a proven walker.**

## Physical assumptions

- Body baseline: 270 x 150 mm, upper leg 105 mm, lower leg 117 mm.
- Eight metal-gear positional servos, two joints per leg (hip and knee).
- A generic 16-channel PCA9685 and ESP32 could control the eventual prototype.
- Each simulated actuator is capped at **0.60 N.m**; command speed is capped at **3.1 rad/s**. These are *assumptions*, not verified output of any particular Amazon servo.
- Ground contact, gravity, simplified friction, rigid-body masses, inertias, 2-link inverse kinematics, a diagonal gait and limited torque are simulated.
- Motor current, temperature, voltage sag, backlash, gear wear, structural stresses, cable routing, electronics failures and battery life are **not** simulated. Chassis/body dimensions are parametric physics primitives, not printable STL/STEP designs.

## What BEAN does

1. Generates an explicit baseline physical model in MuJoCo MJCF XML.
2. Tries 24 deterministic, seed-controlled variations of body proportions, limb lengths and gait.
3. Records actual simulated forward distance, upright fraction, falls, sideways drift, energy and torque saturation. All trials, not just wins, are saved.
4. Ranks candidates against baseline. The best score **does not** automatically mean that walking succeeded.
5. Exports a candidate in the real BEAN Core BodyRegistry schema, with all servos explicitly disconnected.
6. Calls BEAN Core SelfOptimizationGovernor to register a **proposal only**. No motor controls, self-modification or deployment are authorized.

## Run it

Requires Python 3.11+:

```bash
python -m pip install 'mujoco>=3.2,<4'
python -m unittest discover -s experiments/robot_body -p 'test_*.py' -v
python experiments/robot_body/lab.py --trials 24 --seed 106 --out robot-results
```

The experiment branch's GitHub Actions workflow installs the actual engine, checks out `danieloculus0-bot/BEAN` for governance, runs tests and physics, and publishes **bean-robot-lab001-results** as a workflow artifact.

Output: `results.json`, `ranked.csv`, `baseline.xml`, `winner.xml`, `winner.json`, `body_registry_candidate.json`, and the BEAN Core governor's proposal record in SQLite/JSON.

## Interpretation

This lab optimizes *parameters under a chosen robot topology*; it is not unrestricted invention of new legs or printed parts. Next: measure the real servos, test multiple independent seeds, slopes and disturbances, and let BEAN compare legged, wheeled, and hexapod topologies on cost, mass, energy and terrain capability. No real-world capability should be claimed from a single synthetic environment.
