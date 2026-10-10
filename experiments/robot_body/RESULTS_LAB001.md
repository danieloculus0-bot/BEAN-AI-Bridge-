# BEAN robotics lab 001/002: verified simulated results

**Experiment date:** 2026-10-10 UTC. **Engine:** MuJoCo run in GitHub Actions Linux. **Status:** measured in simulation only, NOT hardware-validated.

- [First seed-106 physics run](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/38031664680)
- [Re-run with four independent condition checks](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/38031783215)
- [Full raw artifact, including robustness.json](https://github.com/danieloculus0-bot/BEAN-AI-Bridge-/actions/runs/38031783215/artifacts/11662266174)

## Fixed first experiment: baseline plus 24 mutations, 3-second flat-floor tests

| Metric | Starting body | Selected candidate, trial 23 |
| --- | ---: | ---: |
| Forward displacement | 0.0010 m | 0.2018 m |
| Lateral displacement | 0.0322 m | 0.0025 m |
| Fell during run | No | No |
| Upright fraction | 1.000 | 1.000 |
| Highest absolute roll or pitch | 0.1699 rad | 0.0618 rad |
| Simulated joint work | 2.8076 J | 2.6647 J |
| Fraction of near-limit actuator steps | 0.0202 | 0.0756 |
| Composite search score (arbitrary units) | 1.8418 | 4.8909 |

The optimized design traded higher torque-limit occupancy for more travel, tighter heading, and lower tilt. These metrics do not establish peak motor power, thermal safety, or full-world manufacturability.

### Chosen simulated dimensions and gait

| Parameter | First model | Chosen model |
| --- | ---: | ---: |
| Body length | 270 mm | 286.5 mm |
| Body width | 150 mm | 153.33 mm |
| Upper leg | 105 mm | 110.08 mm |
| Lower leg | 117 mm | 119.16 mm |
| Step length (stride) | 45 mm | 58.88 mm |
| Step lift | 28 mm | 12 mm |
| Frequency | 1.000 Hz | 1.451 Hz |
| Stance fraction | 0.620 | 0.520 |

Every candidate used the same eight physically bounded simulated servos. No extra hidden actuators, gravity overrides, or teleports.

## Out-of-sample challenges: not used to select trial 23

| Challenge | Baseline travel | Chosen design travel | Chosen design fell? |
| --- | ---: | ---: | --- |
| 8-second endurance, normal friction | 0.0519 m | 0.5254 m | No |
| 6-second reduced traction | -0.0047 m | 0.3074 m | No |
| 6-second torque limit reduced 30% | 0.0290 m | 0.1358 m | No |
| 6-second reduced traction and torque | 0.0411 m | 0.3374 m | No |

**Challenge result: 4/4 of these scenarios passed the preregistered simple criterion:** candidate outtravels baseline and does not fall. This is not a probabilistic reliability estimate. The challenge perturbations were selected by developers, and the winner remains limited to a two-DOF/leg, level-ground topology.

## BEAN integration and limits

The GitHub Actions job checked out actual `danieloculus0-bot/BEAN` and instantiated `bean.optimization.SelfOptimizationGovernor`, creating a **proposal only**. It exported candidate geometry to BEAN's native BodyRegistry schema, with `servo_channel: null` and `hardware_connected: false` for all eight joints.

**Revision priority:** replace assumed 0.60 N.m actuator torque and speed with bench-observed curves and consider power loss, brownout, joint backlash, 3D-print mechanical stress, and rugged terrain. Run cross-seed cross-terrain validation before suggesting physical hardware fabrication. Future comparison should include wheeled and hexapod alternatives, rather than locking BEAN into a quadruped.
