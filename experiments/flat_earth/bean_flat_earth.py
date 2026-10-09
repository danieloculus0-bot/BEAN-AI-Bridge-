"""Native BEAN falsification experiment, reproducible across GitHub Windows/Linux.

Scope: a precisely defined north-pole-centered Euclidean disk with:
  - radial distance proportional to geographic co-latitude;
  - finite-height Sun over equator and finite-height Polaris over north pole;
  - ordinary straight-line light rays, no unmeasured spotlight/refraction law.
Competing model: spherical approximation of Earth.
Not a test of every imaginable flat-Earth hypothesis.

Reference observations:
- Antarctic field observations of 24-hour summer sunlight & polar winter:
  https://www.antarctica.gov.au/about-antarctica/weather-and-climate/weather/sunlight-hours/
  https://www.antarctica.gov.au/news/2018/marking-the-midnight-sun-in-antarctica/
- North Star altitude tracks north latitude (navigational observations):
  https://www.nps.gov/interp/JR_Final_2013.pdf
- North/South longitude spacing converges toward poles:
  https://oceanservice.noaa.gov/education/tutorial_nautical_charts/nautical_charts02_information_2b.html
- Solar altitude calculation reference (model-based, not independent measurement):
  https://aa.usno.navy.mil/faq/alt_az
  https://gml.noaa.gov/grad/solcalc/
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any

SOURCES = {
    "antarctic_observations": "https://www.antarctica.gov.au/about-antarctica/weather-and-climate/weather/sunlight-hours/",
    "antarctic_field_report": "https://www.antarctica.gov.au/news/2018/marking-the-midnight-sun-in-antarctica/",
    "polaris_navigation": "https://www.nps.gov/interp/JR_Final_2013.pdf",
    "longitude_geometry": "https://oceanservice.noaa.gov/education/tutorial_nautical_charts/nautical_charts02_information_2b.html",
    "usno_solar_geometry": "https://aa.usno.navy.mil/faq/alt_az",
    "noaa_solar_calculator": "https://gml.noaa.gov/grad/solcalc/",
}
MODELS = ("sphere", "north_centered_flat_disk")


def degree_sun_alt(latitude: float, declination: float, hour_angle: float) -> float:
    """USNO horizon-coordinate relation under a spherical Earth approximation."""
    p, d, h = (math.radians(v) for v in (latitude, declination, hour_angle))
    sin_alt = math.sin(p)*math.sin(d) + math.cos(p)*math.cos(d)*math.cos(h)
    return math.degrees(math.asin(max(-1., min(1., sin_alt))))


def finite_height_angle(height: float, radius: float) -> float:
    return math.degrees(math.atan2(height, radius))


def best_finite_height(distances: list[float], observed: list[float]) -> tuple[float, list[float], float]:
    """Grant the disk model its most favorable one-parameter least-squares fit."""
    best_h, best_predictions, best_mse = 0., [], float("inf")
    for i in range(1, 4001):
        h = i / 20.0
        predictions = [finite_height_angle(h, d) for d in distances]
        mse = sum((p-o)**2 for p,o in zip(predictions, observed)) / len(observed)
        if mse < best_mse:
            best_h, best_predictions, best_mse = h, predictions, mse
    return best_h, [round(x,3) for x in best_predictions], round(math.sqrt(best_mse),3)


def run_observation_checks() -> list[dict[str,Any]]:
    """Predefined, testable predictions. Model assumptions stated in each record."""
    checks: list[dict[str,Any]] = []
    # Observed Polaris navigational rule from NPS; compare a finite north-pole star.
    lat = [20.,40.,60.]
    observed_polaris = lat[:]
    polaris_h, polaris_disk, polaris_error = best_finite_height([90.-x for x in lat], observed_polaris)
    checks.append({
        "id":"polaris_altitude", "reference_type":"published_navigational_observation",
        "source":SOURCES["polaris_navigation"],
        "observed_degrees":observed_polaris, "latitudes_north":lat,
        "sphere_prediction_degrees":lat,
        "disk_prediction_degrees":polaris_disk, "disk_best_fit_height_units":polaris_h,
        "sphere_rmse_degrees":0., "disk_rmse_degrees":polaris_error,
        "sphere_pass":True, "north_centered_flat_disk_pass":polaris_error <= 2.,
        "tolerance":"2-degree angular RMSE; approximate Polaris alignment",
    })
    # Reference angles are USNO spherical solar coordinate values, not independent sensor data.
    # This test checks consistency with operational astronomy, not independent confirmation.
    equinox_lat = [20.,40.,60.]
    solar_reference = [90.-v for v in equinox_lat]
    solar_h, solar_disk, solar_error = best_finite_height(equinox_lat, solar_reference)
    checks.append({
        "id":"equinox_solar_noon", "reference_type":"published_astronomical_prediction_not_independent_measurement",
        "source":SOURCES["usno_solar_geometry"],
        "observed_degrees":None, "reference_degrees":solar_reference,
        "latitudes_north":equinox_lat,
        "sphere_prediction_degrees":solar_reference, "disk_prediction_degrees":solar_disk,
        "disk_best_fit_height_units":solar_h, "sphere_rmse_degrees":0.,
        "disk_rmse_degrees":solar_error,
        "sphere_pass":True, "north_centered_flat_disk_pass":solar_error <= 2.,
        "tolerance":"2-degree model-to-reference angular RMSE",
    })
    # December: station Davis ~68.58S sun stays above horizon and at equator night occurs.
    # June: South Pole in polar darkness. Source AAD documents these directly.
    winter_south = degree_sun_alt(-90., +23.44, 0.)
    summer_davis_midnight = degree_sun_alt(-68.58, -23.44, 180.)
    equator_midnight_dec = degree_sun_alt(0., -23.44, 180.)
    case_records = [
        {"place":"Davis, Antarctica","season":"December summer", "expected_daylight":True,
         "sphere_altitude_degrees":round(summer_davis_midnight,3)},
        {"place":"Equator","season":"December midnight", "expected_daylight":False,
         "sphere_altitude_degrees":round(equator_midnight_dec,3)},
        {"place":"South Pole","season":"June winter","expected_daylight":False,
         "sphere_altitude_degrees":round(winter_south,3)},
    ]
    globe_matches = all((x["sphere_altitude_degrees"]>0)==x["expected_daylight"] for x in case_records)
    # An always-above-plane point light with straight unobstructed rays never goes below the local horizontal.
    disk_matches = all(x["expected_daylight"] for x in case_records)
    checks.append({
        "id":"polar_day_night", "reference_type":"field_observation_and_seasonal_night",
        "source":SOURCES["antarctic_observations"],
        "additional_source":SOURCES["antarctic_field_report"],
        "cases":case_records, "sphere_pass":globe_matches,
        "north_centered_flat_disk_pass":disk_matches,
        "disk_prediction":"always above horizon without an added directional illumination law",
        "qualification":"A spotlight/occlusion law is outside this specified disk model.",
    })
    # NOAA parallels converge to both poles. Reference: 60N and 60S same longitude degree width.
    # In the north-pole-centered azimuthal equidistant disk, r_N=30, r_S=150 -> ratio=5.
    sphere_ratio = math.cos(math.radians(-60))/math.cos(math.radians(60))
    disk_ratio = (90.+60.)/(90.-60.)
    checks.append({
        "id":"sixty_degree_parallel_spacing", "reference_type":"geodetic_geometric_observation",
        "source":SOURCES["longitude_geometry"],
        "north_latitude_degrees":60, "south_latitude_degrees":-60,
        "expected_south_to_north_ratio":1.0,
        "sphere_south_to_north_ratio":round(sphere_ratio,6),
        "disk_south_to_north_ratio":disk_ratio,
        "sphere_pass":abs(sphere_ratio-1.0)<0.05,
        "north_centered_flat_disk_pass":abs(disk_ratio-1.0)<0.05,
        "tolerance":"5% ratio error",
    })
    return checks


def run(output_dir: Path) -> dict[str,Any]:
    output_dir.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str((Path.cwd()/"bean_core").resolve()))
    from bean.memory.store import init_store, get_store
    from bean.memory.session import begin_session, end_session
    from bean.memory.identity import bootstrap_identity
    from bean.memory.event_logger import log_event, EventType, Source
    from bean.reflection.reflect import run_reflection
    from bean.cognition.epistemic_guard import EpistemicGuard, CandidateClaim
    from bean.cognition.falsification import FalsificationEngine, FalsificationRule, FalsificationType
    from bean.cognition.uncertainty_garden import UncertaintyGarden, UncertaintyRecord

    dbfile=output_dir/"bean_flat_earth_evidence.sqlite"
    init_store(str(dbfile))
    bootstrap_identity()
    session=begin_session()
    store=get_store()
    store.execute("""CREATE TABLE IF NOT EXISTS model_checks(
        id TEXT NOT NULL, model TEXT NOT NULL, passed INTEGER NOT NULL,
        evidence TEXT NOT NULL, PRIMARY KEY(id,model)
    )""")
    store.commit()

    checks=run_observation_checks()
    evidence_event_ids=[]
    for entry in checks:
        for model in MODELS:
            passed=bool(entry[f"{model}_pass"])
            store.execute("INSERT INTO model_checks (id,model,passed,evidence) VALUES (?,?,?,?)",
                          (entry["id"],model,int(passed),json.dumps(entry,sort_keys=True)))
            event_id=log_event(session,EventType.OBSERVATION,
                f"Model {model} / {entry['id']}: {'PASS' if passed else 'FAIL'}",
                Source.SYSTEM,subtype="flat_earth_model_replay",
                data={"model":model,"passed":passed,"check_id":entry["id"],
                      "source":entry["source"],"reference_type":entry["reference_type"]})
            evidence_event_ids.append(event_id)
    store.commit()

    guard=EpistemicGuard()
    audits=[]
    for model in MODELS:
        audit=guard.audit(CandidateClaim(
            key=f"earth_geometry.{model}",
            content=("A spherical Earth approximates the documented geographic and astronomical observations."
                     if model=="sphere" else
                     "A north-centered disk with finite-height Sun and Polaris and straight unobstructed rays explains these observations."),
            source_type="published_observation_and_explicit_test_assumptions",
            source_ref=SOURCES["antarctic_observations"],confidence=.5,
            evidence=list(SOURCES.values()),
            falsification_path="Independent observation tests in experiments/flat_earth/bean_flat_earth.py"))
        audits.append({"model":model,"verdict":audit.verdict.value,"reasons":audit.reasons,
                       "note":"EpistemicGuard validates sourcing and falsifiability; APPROVED does not mean physically true."})

    garden=UncertaintyGarden()
    uncertain=garden.plant(UncertaintyRecord(
        question="Which specified geometry reproduces the published observational constraints?",
        what_would_resolve_it="Independent tests and validated predictions across sites.",
        significance=.8),
        [("spherical_approximation",.5),("north_centered_finite_height_disk",.5)])
    # Deliberately avoid assigning quantitative Bayesian likelihoods without justified error models.
    review=garden.review(uncertain.uncertainty_id)

    engine=FalsificationEngine()
    for model in MODELS:
        engine.add_rule(FalsificationRule(
            claim_key=f"earth_geometry.{model}",
            falsification_type=FalsificationType.SQL_ASSERTION_FALSE,
            condition={"note":"Fails if any of four registered observation constraints fails"},
            check_query=f"SELECT CASE WHEN SUM(CASE WHEN passed=0 THEN 1 ELSE 0 END)=0 THEN 1 ELSE 0 END FROM model_checks WHERE model='{model}'",
            failure_action="downgrade_claim_and_record_contradiction"))
    falsification=engine.check_all(session_uuid=session)
    reflection=run_reflection(session,trigger_type="manual",event_ids=evidence_event_ids)
    bymodel={model:{"passed":sum(x[f"{model}_pass"] for x in checks),
                    "failed":sum(not x[f"{model}_pass"] for x in checks)} for model in MODELS}
    # Invariant: the default disk fails cross-latitude and daylight constraints.
    assert bymodel["sphere"]["passed"]==4 and bymodel["sphere"]["failed"]==0
    assert bymodel["north_centered_flat_disk"]["failed"]>=2
    assert sum(int(r.falsified) for r in falsification)==1
    summary={
        "mode":"REAL_GITHUB_BEAN_WORKFLOW_WITH_PUBLISHED_OBSERVATIONAL_REFERENCES",
        "models_tested":list(MODELS),"model_definitions":{
          "sphere":"Spherical approx; USNO solar-altitude model, symmetric latitude-parallel geometry.",
          "north_centered_flat_disk":"North-centered azimuthal equidistant disk; fixed height Sun at equatorial ring, Polaris at pole; straight rays, unobstructed, one fixed height per source."},
        "model_check_counts":bymodel,
        "registered_tests":checks,
        "BEAN_epistemic_audits":audits,
        "BEAN_falsification_results":[{
            "claim_key":r.claim_key,"falsified":r.falsified,"evidence":r.evidence,
            "action_taken":r.action_taken} for r in falsification],
        "BEAN_uncertainty_review":{"summary":review["summary"],"note":"Option weights are arbitrary starting weights; not scientific posterior probabilities."},
        "BEAN_reflection":{"status":reflection["status"],
          "event_count":reflection["event_count"],
          "summary":reflection["summary"],
          "uncertainties":reflection["uncertainties"]},
        "probability":"NOT_CALCULATED: no justified priors and measurement-error likelihood functions. Passing fraction is NOT probability.",
        "limitations":["Not a test of every possible flat-Earth theory.",
                       "NOAA/USNO solar-angle reference is itself model-derived and not independent sensor evidence.",
                       "Reference claims are published observations, not newly acquired measurements.",
                       "EpistemicGuard checks claim provenance, not physical truth.",
                       "Fixed thresholds and model definitions are preregistered in source."],
        "reference_urls":SOURCES,
    }
    (output_dir/"results.json").write_text(json.dumps(summary,indent=2,sort_keys=True),encoding="utf-8")
    end_session(session,"clean","Flat-Earth model contrast with BEAN falsification and published observation references")
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,default=Path("artifacts/flat_earth"))
    a=parser.parse_args()
    result=run(a.out)
    print(json.dumps({"scores":result["model_check_counts"],
          "falsifications":result["BEAN_falsification_results"],
          "reflection_events":result["BEAN_reflection"]["event_count"]},indent=2))
