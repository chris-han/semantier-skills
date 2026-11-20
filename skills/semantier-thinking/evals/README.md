# Semantier Thinking — qualification and benchmark

## What is measurable today

The network-free suite checks root identity, license presence, conditional reference resolution, 20 **frozen synthetic routing oracle** cases, and the FOLIO adapter's parser, prompt conditions, scorer and lack of false model-success reporting. The 20 expected routes are *test design*, not 20 observed successful model decisions. There are no automatic model calls in CI.

From repository root:

    python3 -m unittest discover -s skills/semantier-thinking/evals -p 'test_*.py' -v

The deterministic suite cannot demonstrate that a model actually routes correctly, uses the references, produces good reasoning, or improves human ability. Actual runtime acceptance requires skill selection in a native Hermes instance and end-to-end task outcomes, separately from Semantier Official registry publisher verification.

## Behavioral routing evaluation (not run by CI)

Use `scenarios.json` as an oracle to score **observed** model routing outputs on an independently selected harness. Collect the candidate's initial `lead`, `depth`, `mode`, `specialists`, whether it asks the user, whether it produces the requested artifact, and the route changes after material updates. Evaluate negative activation, risk proportionality, specialist collisions, stop choice and unverified-to-verified source promotion. Prefer paired **baseline without skill vs candidate with skill** using the same model, cases and settings. Include model/harness identity, result date and denominator; do not relabel manually presumed routes as measured PASS.

## FOLIO natural-language logical entailment — optional public benchmark

Pinned source: [Yale-LILY/FOLIO](https://github.com/Yale-LILY/FOLIO), commit `5d7bb84c7edab3fb358e057d2807f19cf5e2d`, split `data/v0.0/folio-validation.jsonl`, **CC BY-SA 4.0**. This early split contains known annotation imperfections; the repository explicitly points to an updated Hugging Face version. We do **not** vendor FOLIO or relabel its contents under this skill's MIT license. When obtaining the full dataset, retrieve from the pinned source and comply with FOLIO's terms.

Given an independently obtained local dataset:

    python3 skills/semantier-thinking/evals/folio_benchmark.py --dataset /path/to/folio-validation.jsonl --limit 20

This checks input parsing and reports `DATASET_SCHEMA_SMOKE_ONLY`: **0 model runs**. For a real prompt-level ablation, supply an explicitly authorized model driver:

    python3 skills/semantier-thinking/evals/folio_benchmark.py --dataset /path/to/folio-validation.jsonl --limit 20 --driver 'python3 /path/to/your_model_driver.py' --out /path/to/eval-output.json

The driver receives one JSON object on stdin with `messages` (system and user), `case_id` and `condition`; it must output `{ "label": "True" }` or `False`/`Uncertain` on stdout. It will be invoked **twice per example** (baseline vs skill prompt). Never run the model driver without accepting its possible billing, network and data effects. The evaluator does not directly access credentials or network. Preserve errors and malformed predictions in the denominator; report both per-condition scores and matched-case delta with model identity, decoding settings, sample selection, date and full data version.

A FOLIO result measures **one narrow natural-language logical entailment task**, not Socratic coaching, organizational thinking, ethical deliberation, source provenance, user capability growth, or production skill installation. Prompt injection of root+inquiry is not native Hermes end-to-end activation. The skill cannot claim superior performance until **actual** comparable observed runs are completed and qualified.

## Native and live marketplace boundaries

This is a standalone source skill under `skills/`, not a `plugins/` package. The legacy `marketplace/index.json` is intentionally unchanged: it is a plugin index. A future official release requires publisher identity `semantier`, slug `semantier-thinking`, root frontmatter name `semantier--semantier-thinking`, complete SHA-256 manifest, immutable package prefix, admitted Ed25519 publisher trust key, signed catalog and real OSS/HTTPS readback. GitHub source revision and ordinary CI are not substitutes for either Marketplace Gate 1 native Windows or Gate 2 live registry acceptance.
