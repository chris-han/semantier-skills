# Semantier Thinking — qualification and benchmark

## What is measurable today

The network-free suite checks root identity, license presence, conditional reference resolution, 20 **frozen English synthetic routing oracle** cases plus bilingual paraphrase triples, and the FOLIO adapter's parser, prompt conditions, scorer and lack of false model-success reporting. The 20 expected routes are *test design*, not 20 observed successful model decisions. There are no automatic model calls in CI.

From repository root:

    python3 -m unittest discover -s skills/semantier-thinking/evals -p 'test_*.py' -v

The deterministic suite cannot demonstrate that a model actually routes correctly, uses the references, produces good reasoning, or improves human ability. Actual runtime acceptance requires skill selection in a native Hermes instance and end-to-end task outcomes, separately from Semantier Official registry publisher verification.

## Chinese / English / mixed-language qualification (v0.1.2)

- Source contract and independent [Chinese README](../README.zh-CN.md) explain the default reply-language policy, explicit override and quotation fidelity. [Language reference](../references/language-and-terminology.md) is conditional, not a mandatory extra skill.
- `bilingual_pairs.json` freezes independently authored **English / Chinese / mixed-language paraphrase triples**, with one expected lead task, depth, mode and specialist route per triple. The three requests are intended to be semantically equivalent, not independently labelled ground truth. Explicit output-language overrides are separate from reasoning depth.
- `test_bilingual.py` checks coverage of L0–L3, all three main tasks, Coach/Deliver across L1–L3, ethical and organizational specialists, locale-specific target language, and the offline evaluation adapter. **These are contract tests, not observed model answers**.
- `bilingual_eval.py` can run a bounded *prompt-level* comparison if the operator supplies a model driver. It records reported route fields, answer text, a low-confidence Chinese-script heuristic, and matched-locale consistency. It does not perform native Hermes progressive file loading or independently judge argument correctness. Script classification is not proof of fluent, correct Chinese.

From the repo root, for a no-model data smoke:

    python3 skills/semantier-thinking/evals/bilingual_eval.py --limit 6

For a separately authorized model driver (may incur network/model cost):

    python3 skills/semantier-thinking/evals/bilingual_eval.py --limit 6 --driver 'python3 /path/to/your_route_driver.py' --out /path/to/bilingual-results.json

The driver reads one UTF-8 JSON object on stdin with `messages`, `case_id`, `locale`, `condition` and returns JSON containing `lead`, `depth`, `mode`, `specialists`, `ask_user` and `answer`. All errors count toward the full denominator. Keep driver model/harness/version, prompts, decoding settings, timestamps and output intact for evaluation; do not substitute an oracle stub and call it model performance. This benchmark is a controlled prompt-level probe only, **not** a production skill-activation or human-learning result.

## Behavioral routing evaluation (not run by CI)

Use `scenarios.json` as an oracle to score **observed** model routing outputs on an independently selected harness. Collect the candidate's initial `lead`, `depth`, `mode`, `specialists`, whether it asks the user, whether it produces the requested artifact, and the route changes after material updates. Evaluate negative activation, risk proportionality, specialist collisions, stop choice and unverified-to-verified source promotion. Prefer paired **baseline without skill vs candidate with skill** using the same model, cases and settings. Include model/harness identity, result date and denominator; do not relabel manually presumed routes as measured PASS.

The eight `recovery_scenarios.json` cases are **new author-designed, exposed routing/transition oracles** for disputed conclusions, candidate-vs-method scope, missing binding, residual branching, wrong-reason UNKNOWN, legitimate uncertainty, ordinary debugging and STOP. `test_recovery_contract.py` checks source contract and fixture coverage; it cannot establish native Hermes activation or real multi-step behavior. Before an efficacy claim, compare v0.1.1 vs v0.1.2 on the same model/harness/budget and new source-independent multistep tasks, capture actual trigger and reference loads (not self-reported labels), and measure whether the specialist return updates the conclusion. The exposed E3-R1 teaching case is regression material only.

**2026-11-21 bounded native diagnostic (NOT QUALIFIED):** `native_reentry_probe.py` was run through actual Hermes `AIAgent` with the configured `qwen3.5-plus` DEVELOPMENT model, isolated temporary skill homes, one v0.1.1 source-pinned baseline and one local v0.1.2 candidate, and **only** the `skills` toolset. `skill_view` was observed in both arms and `references/diagnostic-revision.md` was loaded in one candidate run. Both versions distinguished candidate failure from method falsification, but neither reliably handled the second turn using the supplied predicate facts alone: requests for additional source/file access persisted. A candidate-only control run for a settled typo did **not** load skill content, although it attempted `skills_list`. This limited, already-exposed same-conversation probe is a **negative/inconclusive signal for complete behavioral improvement**; no independent efficacy, generalization or production claim follows. The model serving revision, exact charge and full provider cost are UNKNOWN. The skill-only tool set was intentionally unable to read arbitrary source files, so the failure is not evidence that a full-tool Hermes deployment has identical behavior.

To rerun a **bounded, development-only** native probe (not CI or release qualification), from `semantier-skills` with the sibling Semantier runtime and its already-configured DEVELOPMENT route:

```sh
../.venv/bin/python skills/semantier-thinking/evals/native_reentry_probe.py --arm both --scenario recovery --turns 2
../.venv/bin/python skills/semantier-thinking/evals/native_reentry_probe.py --arm after --scenario control --turns 1
```

These commands make real model calls and may incur charges. They print only bounded tool-event metadata and answer excerpts; they do not establish native Windows install, real-editor return flow or official registry publication. The script is a local research diagnostic, not a release prerequisite.

## FOLIO natural-language logical entailment — optional public benchmark

Pinned source: [Yale-LILY/FOLIO](https://github.com/Yale-LILY/FOLIO), commit `5d7bb84c7edab3fb358e057d2807f19cf5cf5e2d`, split `data/v0.0/folio-validation.jsonl`, **CC BY-SA 4.0**. This early split contains known annotation imperfections; the repository explicitly points to an updated Hugging Face version. We do **not** vendor FOLIO or relabel its contents under this skill's MIT license. When obtaining the full dataset, retrieve from the pinned source and comply with FOLIO's terms.

Given an independently obtained local dataset:

    python3 skills/semantier-thinking/evals/folio_benchmark.py --dataset /path/to/folio-validation.jsonl --limit 20

This checks input parsing and reports `DATASET_SCHEMA_SMOKE_ONLY`: **0 model runs**. For a real prompt-level ablation, supply an explicitly authorized model driver:

    python3 skills/semantier-thinking/evals/folio_benchmark.py --dataset /path/to/folio-validation.jsonl --limit 20 --driver 'python3 /path/to/your_model_driver.py' --out /path/to/eval-output.json

The driver receives one JSON object on stdin with `messages` (system and user), `case_id` and `condition`; it must output `{ "label": "True" }` or `False`/`Uncertain` on stdout. It will be invoked **twice per example** (baseline vs skill prompt). Never run the model driver without accepting its possible billing, network and data effects. The evaluator does not directly access credentials or network. Preserve errors and malformed predictions in the denominator; report both per-condition scores and matched-case delta with model identity, decoding settings, sample selection, date and full data version.

A FOLIO result measures **one narrow natural-language logical entailment task**, not Socratic coaching, organizational thinking, ethical deliberation, source provenance, user capability growth, or production skill installation. Prompt injection of root+inquiry is not native Hermes end-to-end activation. The skill cannot claim superior performance until **actual** comparable observed runs are completed and qualified.

## Native and live marketplace boundaries

This is a standalone source skill under `skills/`, not a `plugins/` package. The legacy `marketplace/index.json` is intentionally unchanged: it is a plugin index. A future official release requires publisher identity `semantier`, slug `semantier-thinking`, root frontmatter name `semantier--semantier-thinking`, complete SHA-256 manifest, immutable package prefix, admitted Ed25519 publisher trust key, signed catalog and real OSS/HTTPS readback. GitHub source revision and ordinary CI are not substitutes for either Marketplace Gate 1 native Windows or Gate 2 live registry acceptance.

### Native multi-turn v0.1.1 / v0.1.2 comparison

The Runtime qualification plan owns the disposition, per-case adjudication and exact execution provenance. This directory supplies the frozen [cases and rubric](native_multiturn_cases.json) and [native runner](native_multiturn_qualification.py).

Reproduce the apparatus with Linux Git, clean Hermes source from commit `691da21aa3f3842192b13e8ee73d9a9ec9ad9602`, that source's Python dependencies, and both historical Skill commits available in this Git checkout. The runner archives complete Skill packages from their immutable revisions. It starts an isolated Hermes home per process and records native tool starts, completions, denied requests, full turn history and HTTP attempts.

```bash
env -i PATH=/usr/bin:/bin "$HERMES_PYTHON" native_multiturn_qualification.py \
  --hermes "$PINNED_HERMES_SOURCE" --route "$DEV_ROUTE_ENV_FILE" \
  --arm B0 --preflight --output "$OUTPUT_DIR/preflight-B0.json"
```

Repeat offline preflight for B1. The input env file identifies the existing Beijing DashScope DEVELOPMENT route. Preflight uses an offline placeholder and blocks network requests. The live comparison used the same runner with `--preflight` omitted, one fresh process per `--case` and arm, and new output filenames. First run the separate `pilot` fixture in both arms, then use this historical order to reproduce the protocol: denominator B0/B1, binding B1/B0, layers B0/B1, ranking B1/B0, settled B0/B1, unknown B1/B0. The sealed case bundle is now exposed. A later replay measures repeatability of the protocol and does not produce fresh holdout evidence.

**Disposition — THINKING_WEAK_SIGNAL_NOT_QUALIFIED.** On the four fresh positive cases, v0.1.1 passed 1/4 and v0.1.2 passed 2/4. Both passed the two boundary controls. Both received the native freight fixture response. v0.1.2 identified the field binding rather than inferring unsupported unit handling. Neither arm loaded the Thinking Skill for that case, and neither arm loaded `diagnostic-revision.md` anywhere in the sealed cohort. This is one case-level difference with no demonstrated mechanism attribution or qualification. See the archived Runtime plan at <https://github.com/chris-han/semantier-runtime/blob/main/docs/plans/archive/2026-11-21-semantier-thinking-v012-native-multiturn-attribution-eval-mvl-v1.md>.
