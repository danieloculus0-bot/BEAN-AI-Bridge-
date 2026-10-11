"""Lab 002: out-of-sample robustness checks after Lab 001 picks the winner."""
import argparse, json
from pathlib import Path
from unittest.mock import patch
import lab

SCENARIOS={
    "eight_second_endurance": dict(duration=8.0,friction=1.3,torque=.60),
    "slick_floor": dict(duration=6.0,friction=.65,torque=.60),
    "weakened_motor_torque": dict(duration=6.0,friction=1.3,torque=.42),
    "slick_floor_weak_motors": dict(duration=6.0,friction=.65,torque=.42),
}

def challenge(design,spec):
    orig=lab.model_xml
    def altered(d):
        xml=orig(d)
        xml=xml.replace('friction="1.3 .01 .0001"',
                        f'friction="{spec["friction"]:.3f} .01 .0001"')
        xml=xml.replace('forcerange="-.60 .60"',
                        f'forcerange="-{spec["torque"]:.2f} {spec["torque"]:.2f}"')
        return xml
    with patch.object(lab,"model_xml",altered):
        return lab.run_physics(design,duration=spec["duration"])

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=Path("robot-results"))
    a=parser.parse_args()
    report=json.loads((a.out/"results.json").read_text())
    base=lab.Design(**report["baseline"]["design"])
    win=lab.Design(**report["winner"]["design"])
    checks=[]
    for name,spec in SCENARIOS.items():
        b=challenge(base,spec); w=challenge(win,spec)
        checks.append(dict(scenario=name,conditions=spec,baseline=b,winner=w,
                           winner_survived=not w["fell"],
                           winner_outtraveled_baseline=w["forward_m"]>b["forward_m"]))
    passed=sum(c["winner_survived"] and c["winner_outtraveled_baseline"] for c in checks)
    evidence=dict(lab="BEAN body validation 002",classification="MEASURED_SIMULATION",
                  no_reoptimization=True,independent_scenarios=len(checks),
                  scenarios_passed=passed,robust_in_all=passed==len(checks),
                  caveat="Not proof of real-world performance",scenarios=checks)
    (a.out/"robustness.json").write_text(json.dumps(evidence,indent=2))
    print(json.dumps(evidence,indent=2))

if __name__=="__main__":main()
