# BEAN Weather Intelligence: Chatfield Minnesota

Research-grade historical forecast study. Experimental branch only.

Location is Chatfield, MN (43.8455, -92.1891), America/Chicago.

## Sources and periods

- Reference: ERA5 gridded reanalysis, 2025-10-11 to 2026-10-05. This is a model-assisted estimate, not an instrument reading at Chatfield.
- Climate input: ERA5 data exclusively from 2015-01-01 through 2024-12-31.
- Seven-day model: dated individual ECMWF IFS HRES forecast runs.
- Fourteen-day model: dated GFS forecast runs where archived, starting April 2026.
- Thirty-day baseline: prior-decade climatology; 30-day as-issued model run is not yet available and must be N/A.
- Initial retrospectively sampled forecast issue dates are spaced every 28 days, not every seven days.

## No-lookahead protocol

The as-of forecasting job never fetches the later period's ERA5 reference. The reference collector and forecast collector have separate GitHub jobs and artifacts. The chronological judge alone receives both, rejects invalid issuance timestamps, and updates trust using only older episodes whose final valid date is six or more days before the new issuance. Scores of the current case cannot choose the source that is judged for that same case.

A model with missing archived results is not considered defeated. Source receipts include URL and SHA256; raw source details are downloaded again from the recorded URL for reproduction. Open-Meteo brokerage is not an independent weather observation.

CI reports temperature high/low MAE in degrees C and aggregate precipitation error in mm, with trust selection from mature historical cases and an explicit cold-start state. Initial three- and four-week evidence is a descriptive backtest, not verified forecast intelligence or physical station truth.

## Run

Use Python 3.11+ from repository root:

    python -m unittest discover -s experiments/weather_chatfield_lab -p 'test_*.py' -v
    python -m experiments.weather_chatfield_lab.weather_lab forecast --out evidence/forecaster/predictions.json
    python -m experiments.weather_chatfield_lab.weather_lab truth --out evidence/verifier/reference.json
    python -m experiments.weather_chatfield_lab.weather_lab grade --out evidence/judge/verdict.json

Actions workflow: `.github/workflows/bean-weather-chatfield-backtest.yml`. Artifacts expire after 90 days. The future weekly standing capture will be a separate audited workflow after historical testing.

Reference documentation: https://open-meteo.com/en/docs/single-runs-api and https://open-meteo.com/en/docs/historical-weather-api .
