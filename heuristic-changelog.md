# Heuristic classifier changelog

Each entry records a refresh of
[`heuristic_coefficients.json`](axor_core/policy/heuristic_coefficients.json)
driven by aggregated community telemetry. The file ships with each axor-core
release; the numbers come from the trailing month of anonymized records
collected from opt-in users via `axor-telemetry`.

**What each entry reports**

- Sample size — number of anonymized records that fed the update
- Notable coefficient deltas — which patterns moved, and by how much
- Calibration snapshot — post-update `policy_adjusted` rate per composite cell
- Known blind spots — task shapes the heuristic still misclassifies often,
  and whether a release bumps patterns or leaves them for next round

No individual record text, no file paths, no per-user detail is ever quoted.
All aggregates.

---

## Unreleased (0.3.x → 0.4.0)

_Telemetry pipeline shipped in 0.3.0. First coefficient update will land
once the server has collected ≥1000 opt-in records and calibration is
stable across two consecutive weeks._

**Status:** collecting. See
[telemetry.useaxor.net/stats](https://telemetry.useaxor.net/stats) for live
counts.

---

## 0.3.0 — initial instrumentation (2026-04-23)

No coefficient changes. This release introduced:

- `SignalChosenEvent.scores` — full marginal distribution (not just winner)
- `heuristic_coefficients.json` — regex patterns + weights externalised
- Whitelist-based trace serialization for anonymized records
- `AnonymizedTraceRecord.input_embedding` made Optional to support clients
  without axor-telemetry installed

Heuristic accuracy baseline (from internal benchmark corpus, not telemetry):

| composite cell        | precision | recall |
|-----------------------|-----------|--------|
| focused_generative    | 0.82      | 0.76   |
| focused_readonly      | 0.79      | 0.81   |
| focused_mutative      | 0.74      | 0.70   |
| moderate_generative   | 0.68      | 0.62   |
| moderate_mutative     | 0.71      | 0.68   |
| expansive             | 0.89      | 0.85   |

Moderate-cell weakness is known — these have fewer distinctive keywords.
The first telemetry-driven update will target them.
