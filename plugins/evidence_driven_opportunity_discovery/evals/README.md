# EOD-Bench v1

EOD-Bench evaluates four tracks: Evidence -> Hypothesis, Opportunity Ranking, Action Incremental Value, and Outcome -> Assessment -> Learning replay.

Primary controlled skill evaluation is B2 versus B3: the same foundation model, Semantier Decision Context, tool surface, token/tool budget, task prompt, and output schema are held constant; only the EOD skill condition differs. See `b2_b3_protocol.md`.

Controlled execution assets:

- `case.schema.json` — frozen Semantier Decision Context case envelope;
- `prediction.schema.json` — machine-readable model output and usage accounting;
- `run_manifest.schema.json` — one B2/B3 repeat's exact runtime/model/budget pins;
- `pairing.py` — rejects confounded B2/B3 pairs and records per-case disagreements;
- `repeats.py` — repeat-level mean/variance, paired differences, and usage aggregation;
- `release_report.py` — quality/safety release gate.

The initial release protocol uses at least three paired stochastic repeats when the model/provider is stochastic. Repeats must preserve every controlled pin except a deliberately varied seed when the provider supports one; corresponding B2/B3 runs use the same seed/repeat index.

Track B/C public-dataset use is scoped to ranking and incremental action value, not full opportunity discovery. See `track_b_c_protocol.md`.

Public datasets are referenced by manifest and reproducible preparation scripts; large raw datasets are not committed into the plugin package. UCI Bank Marketing and Online Shoppers are CC BY 4.0. The Criteo Uplift dataset is CC BY-NC-SA 4.0 and is evaluation/research-only for this benchmark unless separate rights permit commercial use; do not bundle it into a commercial product artifact.

`run_public_baselines.py` reproduces the checked-in `public_baseline_results.json` from externally downloaded raw files. `live_b2_b3_status.json` records the current live-model validation state without fabricating scores when Hermes provider credentials are unavailable.

For live B2/B3 validation, prefer Hermes `openai-codex` OAuth when available. Run `uv run --extra dev python hermes-agent/hermes auth add openai-codex` from the repository root and complete the device-code login. Hermes-managed OAuth is separate from the standalone Codex CLI session; when using the Codex app-server runtime, also ensure `codex login` is valid. Then run `uv run --extra dev python -m evidence_driven_opportunity_discovery.evals.resume_live_validation --provider openai-codex --execute` from `semantier-skills/plugins`. The wrapper fails closed until `live_preflight.py` reports `READY`.
