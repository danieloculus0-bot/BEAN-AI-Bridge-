"""BEAN Chatfield weather laboratory: archive replay, no future-weather input.

Only stdlib. Forecast issuance inputs and later observations are fetched in
different CI jobs. All decisions use pre-issued model runs or pre-2025-10
climatology; withheld truth is consumed by a separate scoring command.
"""
from __future__ import annotations

import argparse
import collections
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

LAT = 43.8455
LON = -92.1891
TZ = "America/Chicago"
START = date(2025, 10, 11)
OBS_END = date(2026, 10, 5)  # ERA5 needs a publication lag
BEFORE_PROJECT = date(2025, 10, 11)
METRICS = ("temperature_2m_max", "temperature_2m_min", "precipitation_sum")
SINGLE = "https://single-runs-api.open-meteo.com/v1/forecast"
REANALYSIS = "https://archive-api.open-meteo.com/v1/archive"
DAYS = (7, 14, 30)
MIN_HISTORY = 3


def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fetch(url, params):
    query = urllib.parse.urlencode(params, safe=",/:")
    request_url = url + "?" + query
    if urllib.parse.urlsplit(request_url).hostname not in {
        "archive-api.open-meteo.com", "single-runs-api.open-meteo.com"
    }:
        raise ValueError("Unapproved forecast/archive host")
    last = None
    for n in range(3):
        try:
            req = urllib.request.Request(request_url, headers={"User-Agent": "BEAN-Chatfield-Weather-Research/0.1"})
            with urllib.request.urlopen(req, timeout=75) as rsp:
                payload = json.loads(rsp.read(8_000_000))
            if "error" in payload:
                raise RuntimeError(str(payload.get("reason", "source response error")))
            return {"url": request_url, "sha256": sha(payload), "payload": payload}
        except urllib.error.HTTPError as exc:
            # Preserve the API's actual explanation: opaque HTTP 400s hid every
            # failed as-issued weather run in the first real backtest.
            detail = exc.read(1200).decode("utf-8", errors="replace")
            last = "HTTP " + str(exc.code) + ": " + detail[:700]
            if exc.code in (400, 404):
                break  # Permanent invalid/missing archive; no point retrying
            if n < 2:
                time.sleep(2 * (n + 1))
        except (OSError, ValueError, RuntimeError) as exc:
            last = str(exc)
            if n < 2:
                time.sleep(2 * (n + 1))
    raise RuntimeError("Source request failed: " + str(last))


def daily_rows(payload):
    data = payload.get("daily") or {}
    times = data.get("time") or []
    if not times or any(len(data.get(k, [])) != len(times) for k in METRICS):
        raise ValueError("Malformed or incomplete daily source response")
    rows = {}
    for n, day in enumerate(times):
        rows[day] = {
            metric: (None if data[metric][n] is None else float(data[metric][n]))
            for metric in METRICS
        }
    return rows


def require_numeric(row):
    return all(isinstance(row.get(k), (int, float)) and math.isfinite(row[k]) for k in METRICS)


def issuance_days():
    current = START + timedelta(days=1)
    while current + timedelta(days=30) <= OBS_END:
        yield current
        current += timedelta(days=28)


def archive_params(start, end):
    return {
        "latitude": LAT, "longitude": LON,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": ",".join(METRICS), "timezone": TZ,
        "models": "era5",
        "temperature_unit": "celsius", "precipitation_unit": "mm",
    }


def history_baseline(history, target):
    """2015-2024 only. Symmetric +/-7-day climatology around date in old years.

    This is a climate baseline, NOT a model-issued 30-day prediction.
    """
    vals = collections.defaultdict(list)
    for year in range(2015, 2025):
        for delta in range(-7, 8):
            try:
                candidate = target.replace(year=year) + timedelta(days=delta)
            except ValueError:
                continue
            sample = history.get(candidate.isoformat())
            if sample and require_numeric(sample):
                for k in METRICS:
                    vals[k].append(sample[k])
    if any(len(vals[k]) < 25 for k in METRICS):
        raise ValueError("Insufficient pre-issuance climatology")
    return {k: round(sum(vals[k]) / len(vals[k]), 4) for k in METRICS}


def add_predictions(rows, issue, horizon, source, forecast_rows, provenance, receipts):
    valid_from = issue + timedelta(days=1)
    valid_thru = issue + timedelta(days=horizon)
    for offset in range(1, horizon + 1):
        day = (issue + timedelta(days=offset)).isoformat()
        row = forecast_rows.get(day)
        if not row or not require_numeric(row):
            return False
    for offset in range(1, horizon + 1):
        day = (issue + timedelta(days=offset)).isoformat()
        rows.append({
            "issue": issue.isoformat(), "valid_date": day,
            "horizon": horizon, "source": source,
            "provider_family": provenance, "values": forecast_rows[day],
            "source_sha256": receipts,
            "data_available_as_of": issue.isoformat() + "T06:00:00Z",
            "training_cutoff_exclusive": BEFORE_PROJECT.isoformat(),
        })
    return True


def run_forecast(output):
    """NO 2025-26 outcomes are read, requested, received or available here."""
    history_data = fetch(REANALYSIS, archive_params(date(2015, 1, 1), date(2024, 12, 31)))
    history = daily_rows(history_data["payload"])
    predictions = []
    unavailable = []
    receipts = [{"purpose": "climatology", "source": "ERA5", "url": history_data["url"],
                 "raw_sha256": history_data["sha256"], "scope_end": "2024-12-31"}]
    issued = list(issuance_days())
    for issue in issued:
        # This archive model was actually initialised on its stated 00Z date.
        # Available by the 06Z cutoff, before the forecast target days.
        candidates = [("ecmwf_ifs", "ECMWF_IFS_HRES", 7)]
        if issue >= date(2026, 4, 3):
            candidates.append(("gfs_global", "NOAA_GFS", 14))
        for model_id, provider, horizon in candidates:
            try:
                source = fetch(SINGLE, {
                    "latitude": LAT, "longitude": LON, "run": issue.isoformat() + "T00:00",
                    "models": model_id, "daily": ",".join(METRICS),
                    "timezone": TZ, "temperature_unit": "celsius",
                    "precipitation_unit": "mm",
                    # ECMWF IFS HRES is a 10-day model, not a 16-day model.
                    # Request enough to score the seven complete future days.
                    "forecast_days": 9 if horizon == 7 else 16,
                })
                forecast = daily_rows(source["payload"])
                if not add_predictions(predictions, issue, horizon, provider, forecast,
                                       provider, source["sha256"]):
                    unavailable.append({"issue": issue.isoformat(), "horizon": horizon,
                                        "source": provider, "reason": "missing or incomplete issued forecast days"})
                else:
                    receipts.append({"purpose": "issued_forecast", "issue": issue.isoformat(),
                                     "horizon": horizon, "source": provider,
                                     "url": source["url"], "raw_sha256": source["sha256"]})
            except Exception as exc:
                unavailable.append({"issue": issue.isoformat(), "horizon": horizon,
                                    "source": provider, "reason": str(exc)[:260]})

        for horizon in DAYS:
            baseline = {}
            for offset in range(1, horizon + 1):
                day = issue + timedelta(days=offset)
                baseline[day.isoformat()] = history_baseline(history, day)
            add_predictions(predictions, issue, horizon, "CLIMATOLOGY_2015_2024",
                            baseline, "ERA5_CLIMATOLOGY_BASELINE", history_data["sha256"])

        # Not a hypothetical EC46 archived forecast. We need an archived run ID.
        unavailable.append({"issue": issue.isoformat(), "horizon": 30,
                            "source": "ARCHIVED_30D_MODEL", "reason": "N/A: as-issued 30d archived run not verified"})

    packet = {
        "schema": "bean_weather_1", "location": "Chatfield MN", "latitude": LAT,
        "longitude": LON, "period": [START.isoformat(), OBS_END.isoformat()],
        "observations_embedded": False, "forecast_decisions": predictions,
        "raw_source_receipts": receipts, "unavailable": unavailable,
        "issue_dates": [d.isoformat() for d in issued],
        "climatology_ends": "2024-12-31",
        "note": "No 2025-26 truth downloaded in forecast job; model archive may be incomplete.",
    }
    write_json(output, packet)
    print(json.dumps({"forecast_rows": len(predictions),
                      "archived_issues": len([r for r in receipts if r["purpose"] == "issued_forecast"]),
                      "unavailable": len(unavailable), "output": output}))
    if len(predictions) < 200:
        raise RuntimeError("Forecast samples insufficient: don't treat this as verified backtest")


def run_truth(output):
    ref = fetch(REANALYSIS, archive_params(START, OBS_END))
    rows = daily_rows(ref["payload"])
    if len(rows) < 350 or sum(require_numeric(row) for row in rows.values()) < 345:
        raise RuntimeError("Insufficient historical reference coverage")
    packet = {
        "schema": "bean_weather_truth_1",
        "reference_type": "ERA5_GRIDDED_REANALYSIS_NOT_STATION_OBSERVATION",
        "source_url": ref["url"], "source_sha256": ref["sha256"],
        "start": START.isoformat(), "end": OBS_END.isoformat(),
        "observations": rows,
    }
    write_json(output, packet)
    print(json.dumps({"reference_days": len(rows), "reference_type": packet["reference_type"]}))


def eligible(prior, issue):
    """Mature evidence cutoff, including 5-day ERA5 publication latency."""
    return [x for x in prior if date.fromisoformat(x["last_valid"]) + timedelta(days=6) <= issue]


def metric_error(pred, actual, horizon, metric):
    diffs = [abs(pred[k][metric] - actual[k][metric]) for k in pred]
    if metric == "precipitation_sum":
        return abs(sum(pred[k][metric] for k in pred) - sum(actual[k][metric] for k in actual))
    return sum(diffs) / horizon


def run_grade(pred_path, truth_path, output):
    forecast = json.loads(Path(pred_path).read_text(encoding="utf-8"))
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    if forecast.get("observations_embedded") is not False or forecast.get("schema") != "bean_weather_1":
        raise ValueError("Forecast isolation receipt missing")
    if truth.get("reference_type") != "ERA5_GRIDDED_REANALYSIS_NOT_STATION_OBSERVATION":
        raise ValueError("Reference is not the declared observed proxy")
    reference = truth["observations"]
    combos = collections.defaultdict(dict)
    for row in forecast["forecast_decisions"]:
        issue = date.fromisoformat(row["issue"])
        valid = date.fromisoformat(row["valid_date"])
        horizon = int(row["horizon"])
        if horizon not in DAYS or not issue < valid <= issue + timedelta(days=horizon):
            raise ValueError("Invalid forecast issuance or horizon")
        if row["training_cutoff_exclusive"] != BEFORE_PROJECT.isoformat():
            raise ValueError("Unapproved forecast training boundary")
        if row["source"] == "CLIMATOLOGY_2015_2024":
            if row["provider_family"] != "ERA5_CLIMATOLOGY_BASELINE":
                raise ValueError("Baseline falsely claims an issuing model")
        else:
            if row["source"] not in ("ECMWF_IFS_HRES", "NOAA_GFS"):
                raise ValueError("Untrusted as-issued model")
            if not row["source_sha256"]:
                raise ValueError("Archived source receipt absent")
        if not require_numeric(row["values"]):
            raise ValueError("Malformed predicted metric")
        key = (row["issue"], horizon, row["source"])
        if row["valid_date"] in combos[key]:
            raise ValueError("Duplicate forecast date")
        combos[key][row["valid_date"]] = row["values"]

    scored = []
    prior_outcomes = []
    skipped = []
    for issue in sorted(forecast["issue_dates"]):
        for horizon in DAYS:
            names = sorted({k[2] for k in combos if k[0] == issue and k[1] == horizon})
            source_errors = {}
            for name in names:
                pred = combos[(issue, horizon, name)]
                dates = [(date.fromisoformat(issue) + timedelta(days=i)).isoformat()
                         for i in range(1, horizon + 1)]
                if len(pred) != horizon or any(d not in pred or d not in reference or not require_numeric(reference[d]) for d in dates):
                    skipped.append({"issue": issue, "horizon": horizon, "source": name, "reason": "missing actual or prediction"})
                    continue
                act = {d: reference[d] for d in dates}
                err = {m: round(metric_error(pred, act, horizon, m), 3) for m in METRICS}
                source_errors[name] = err
                scored.append({"issue": issue, "horizon": horizon, "source": name,
                               "errors": err, "last_valid": dates[-1]})

            # BEAN-style independent trust: source choice is made from matured past
            # cases ONLY, not this episode's score. Each metric gets its own trust.
            history = eligible(prior_outcomes, date.fromisoformat(issue))
            if "CLIMATOLOGY_2015_2024" in source_errors:
                for metric in METRICS:
                    candidates = {}
                    for name in source_errors:
                        seen = [q["errors"][metric] for q in history
                                if q["source"] == name and q["horizon"] == horizon]
                        if len(seen) >= MIN_HISTORY:
                            candidates[name] = sum(seen) / len(seen)
                    # Only call source choice "learned" when two distinct
                    # scored contenders BOTH have sufficiently mature history.
                    # Repeatedly choosing the ONLY available climate baseline
                    # is not weather-model learning, no matter how many cases.
                    if len(candidates) >= 2:
                        selected = min(candidates, key=candidates.get)
                        decision_status = "learned"
                    elif candidates:
                        selected = "CLIMATOLOGY_2015_2024"
                        decision_status = "single_source_no_comparison"
                    else:
                        selected = "CLIMATOLOGY_2015_2024"
                        decision_status = "cold_start_baseline"
                    selected_error = source_errors[selected][metric]
                    scored.append({"issue": issue, "horizon": horizon, "source": "BEAN_TRUST_SELECTION",
                                   "metric": metric, "selected": selected, "error": selected_error,
                                   "history_count": len([q for q in history if q["source"] == selected and q["horizon"] == horizon]),
                                   "last_valid": (date.fromisoformat(issue) + timedelta(days=horizon)).isoformat(),
                                   "status": decision_status})
            for name, err in source_errors.items():
                prior_outcomes.append({"source": name, "horizon": horizon, "errors": err,
                                       "last_valid": (date.fromisoformat(issue) + timedelta(days=horizon)).isoformat()})

    summary = {}
    for horizon in DAYS:
        horizon_records = [x for x in scored if x["horizon"] == horizon]
        summary[str(horizon)] = {}
        for source in sorted({x["source"] for x in horizon_records}):
            matches = [x for x in horizon_records if x["source"] == source]
            if source == "BEAN_TRUST_SELECTION":
                summary[str(horizon)][source] = {"n_metrics": len(matches),
                    "learned_choices": sum(x["status"] == "learned" for x in matches),
                    "single_source_no_comparison": sum(x["status"] == "single_source_no_comparison" for x in matches),
                    "cold_start_choices": sum(x["status"] == "cold_start_baseline" for x in matches)}
            else:
                summary[str(horizon)][source] = {
                    "n_issued_predictions": len(matches),
                    "high_mae_c": round(sum(x["errors"]["temperature_2m_max"] for x in matches) / len(matches), 3),
                    "low_mae_c": round(sum(x["errors"]["temperature_2m_min"] for x in matches) / len(matches), 3),
                    "precip_total_abs_error_mm": round(sum(x["errors"]["precipitation_sum"] for x in matches) / len(matches), 3),
                }
    report = {"schema": "bean_weather_verdict_1", "location": "Chatfield MN",
              "reference": "ERA5 gridded reanalysis proxy, not actual Chatfield gauge",
              "forecast_packet_sha256": sha(forecast), "reference_packet_sha256": sha(truth),
              "summary": summary, "scored": scored, "skipped": skipped,
              "unavailable_forecasts": forecast["unavailable"],
              "causality_rule": "Only prior forecast episodes ending at least 6 days before issue inform trust",
              "archive_gap": "30-day archival models unverified; historical 30-day lane uses dated climatology baseline only"}
    write_json(output, report)
    print(json.dumps({"summary": summary, "scored_rows": len(scored),
                      "missing_archive_cases": len(forecast["unavailable"])}))
    if not scored:
        raise RuntimeError("No independently scored historical records")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["forecast", "truth", "grade"])
    p.add_argument("--out", required=True)
    p.add_argument("--predictions", default="evidence/forecaster/predictions.json")
    p.add_argument("--reference", default="evidence/verifier/reference.json")
    args = p.parse_args()
    if args.mode == "forecast":
        run_forecast(args.out)
    elif args.mode == "truth":
        run_truth(args.out)
    else:
        run_grade(args.predictions, args.reference, args.out)


if __name__ == "__main__":
    main()
