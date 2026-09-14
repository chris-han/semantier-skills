# First Controlled B2/B3 Run Matrix

## Scope

Run Track A first. Do not mix Track B/C public datasets into the first live model experiment.

## Model/runtime

Use one exact Hermes model/provider configuration for all runs. Freeze:

```text
model_id
provider_id
model_config_hash
reasoning_config
max_tokens
max_iterations / tool-call budget
enabled_toolsets
disabled_toolsets
Semantier ContextGraph + Evidence + Ontology pins
```

## Matrix

For each held-out Track A case:

```text
Repeat 0: B2 then B3 with seed 0, if provider supports seed
Repeat 1: B2 then B3 with seed 1
Repeat 2: B2 then B3 with seed 2
```

If the provider does not expose deterministic seeds, still run three paired repeats and record seed as `null`; pair by repeat index and execute B2/B3 adjacent in time to reduce provider/runtime drift.

Total initial calls:

```text
8 current held-out cases × 2 arms × 3 repeats = 48 case runs
```

As the held-out set grows, retain the same pairing discipline.

## Arm configuration

B2:

- EOD skill disabled;
- base evaluation instructions only;
- same EOD toolset availability as B3 only if the tools themselves are under test; otherwise disable EOD tools for both arms and measure procedural skill effect first.

B3:

- exact same runtime configuration;
- EOD `SKILL.md` appended as the only procedural treatment.

For the first experiment, recommended configuration is **no EOD tool invocation in either arm**. Both arms read the same Semantier Decision Context projection and return the prediction schema. This isolates skill-instruction value before testing skill + registered tool effects.

A second experiment may enable EOD tools equally for both arms, while B2 still lacks EOD instructions. That measures whether the skill improves tool selection/use rather than merely tool availability.

## Ordering

Alternate arm order by case/repeat to reduce systematic temporal bias:

```text
case 1 repeat 0: B2 -> B3
case 2 repeat 0: B3 -> B2
case 3 repeat 0: B2 -> B3
...
```

Do not allow one arm to run entirely before the other.

## Required outputs

Persist for each run:

- run manifest;
- raw final response;
- parsed prediction;
- token accounting;
- reasoning-token accounting when available;
- tool call count and names when enabled;
- wall-clock latency;
- retry/failure status;
- exact ContextGraph/Evidence/Ontology pins.

## Abort conditions

Abort/fail the controlled run if:

- model/provider config drifts between paired arms;
- context/evidence/ontology hashes differ;
- token or tool-call budget differs;
- one arm silently receives additional source data;
- output cannot be parsed after the same bounded retry policy;
- runtime falls back to a different model/provider for one arm only.

Fallback behavior must be either disabled or identically pinned for both arms.

## First analysis

Report:

1. aggregate B2/B3 metrics;
2. three-repeat mean/stddev;
3. paired B3-B2 differences;
4. per-case disagreements;
5. token/tool/latency costs;
6. release-gate result;
7. qualitative review of cases where B3 improved grounding but changed the opportunity classification.
