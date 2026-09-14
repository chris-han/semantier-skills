# Track B/C Evaluation Protocol

## Track B — Opportunity Ranking

Track B evaluates whether EOD preserves useful candidates and ranks scarce human attention effectively.

### Public datasets

Initial supported datasets:

- UCI Bank Marketing
- KDD Cup 2009 Orange CRM appetency / up-selling
- UCI Online Shoppers Purchasing Intention

These datasets are not treated as complete opportunity-discovery benchmarks. They only test ranking behavior over already-structured observations.

### Normalization contract

Every prepared dataset must emit a row envelope containing:

```text
row_id
features{}
label
source_dataset
dataset_split
```

Feature preparation must be deterministic and recorded in the benchmark manifest. Leakage-prone post-outcome features must be excluded explicitly.

### Metrics

Primary:

- Precision@K
- Recall@K
- NDCG@K
- PR-AUC / Average Precision when implemented
- calibration error when a probability is emitted

Operational:

- candidates reviewed at fixed useful-opportunity yield
- useful opportunities found at fixed review budget

### Baselines

At minimum:

- B0 random ranking with frozen seed
- B1 simple deterministic heuristic or standard supervised tabular baseline
- B2 same model/context without EOD skill
- B3 same model/context with EOD skill

B2/B3 must follow `b2_b3_protocol.md`.

### Release rule

B3 must be non-inferior to B2 and the simple baseline on Precision@K and NDCG@K while preserving EOD safety/grounding requirements. A small ranking gain does not compensate for evidence fabrication or unsafe action proposals.

## Track C — Incremental Action Value

Track C evaluates whether the system distinguishes high propensity from high incremental treatment value.

### Public dataset

Primary dataset:

- Criteo Uplift Prediction Dataset

The prepared row envelope must include:

```text
row_id
features{}
treatment
outcome
exposure | null
source_dataset
dataset_split
```

### Core question

Track C asks approximately:

```text
P(Y | do(action), X) - P(Y | do(no action), X)
```

rather than only:

```text
P(Y | X)
```

### Metrics

Primary:

- AUUC
- Qini coefficient
- incremental outcomes @ K
- policy value under fixed action budget

Supporting:

- treatment rate in selected segment
- conversion rate by treatment/control in selected segment
- propensity-only policy comparison

### Baselines

- C0 random treatment targeting
- C1 propensity-only targeting
- C2 simple uplift baseline
- C3 EOD action policy

EOD does not receive credit for selecting subjects who would likely convert anyway when treatment creates no measurable increment.

### Action boundary

Track C evaluates policy selection, not execution authority. The benchmark output may recommend treatment/no-treatment, but must not claim that the action is authorized or executed. Consequential authorization remains a Semantier DecisionRecord concern.

## Dataset provenance

Every prepared Track B/C dataset must record:

```text
dataset_name
canonical_source
license_or_terms
retrieved_at
raw_sha256
normalized_sha256
split_policy
feature_exclusions
preparation_version
```

Large public datasets are not committed by default. Small deterministic fixtures may be checked in for tests.

## Reproducibility

A benchmark report is invalid if it omits the exact normalized dataset hash, split policy, model/runtime pins, baseline identifier, and metric implementation version.
