# Semantier Thinking

[简体中文说明 / Chinese README](README.zh-CN.md)

English, Simplified Chinese, and mixed-language questions are supported by the **same** reasoning workflows. The user’s requested response language takes priority; otherwise answer in the language of their request, not in the language of an attached quotation. Original source quotations and locators remain verbatim. This is a source-level behavior contract, not yet proof of model-language parity.

A progressive critical-thinking skill for Semantier and compatible Hermes skill loaders. It helps users examine claims and evidence, make defensible decisions, improve arguments and writing, or practice independent reasoning without forcing a full audit on every question.

**Skill ID (source):** `semantier/semantier/semantier-thinking`  
**Installed name:** `semantier--semantier-thinking`  
**Source version:** `0.1.2`  
**Author / copyright:** Semantier Technology; see [LICENSE](LICENSE).

## How it works

Start with the user's actual outcome, then choose **one lead task** and adjust depth only for a decision-changing reason:

| Lead task | Use when |
| --- | --- |
| Inquiry and verification | Understand a claim, check evidence, distinguish fact from inference |
| Decision reasoning | Compare feasible actions, constraints, risks and trade-offs |
| Argument and writing | Analyze or revise an argument and deliver a usable draft |

Add **ethical reasoning** for material rights, duties or value conflicts and **organizational reasoning** for group incentives, power structures or feedback effects. Neither specialty is mandatory.

| Depth | Intended behavior |
| --- | --- |
| L0 · Direct | Complete a clear, bounded task; no ceremonial audit |
| L1 · Lightweight | Check the most consequential premise or inference |
| L2 · Structured | Inspect evidence, assumptions, relevant alternatives and uncertainty |
| L3 · Deep audit | Source-grounded, adversarial review of load-bearing claims and consequences |

**Deliver** mode produces the requested answer or artifact. **Coach** mode guides the user's own thinking, normally one decision-relevant question at a time. Mode and depth are independent; a deep audit need not be a long interview.

Depth can increase **or decrease** as evidence changes. Stop when the result is defensible within its declared scope or when further work cannot resolve a material uncertainty. Do not invent confidence scores, citations, causal certainty or ethical consensus.

When a new observation challenges an earlier inference *mid-task*, the skill may conditionally re-enter inquiry. The [attribution and revision reference](references/diagnostic-revision.md) distinguishes observation from explanation, selects one discriminating check, hands mechanical changes to the existing specialist, and revises the conclusion using the returned evidence. It does not turn ordinary debugging into a second agent workflow, rewrite sealed results, or self-promote a learned method.

## Package contents

- [SKILL.md](SKILL.md) — compact Agent entry and critical epistemic boundaries
- [Chinese and bilingual usage](references/language-and-terminology.md) — response-language choice, terminology, quotation fidelity and cross-language scope
- [Depth routing](references/depth-routing.md) — escalation, de-escalation and stopping rules
- [Inquiry](references/critical-inquiry.md), [decision](references/decision-reasoning.md) and [writing](references/argument-writing.md) — lead task workflows
- [Ethical](references/ethical-reasoning.md) and [organizational](references/organizational-reasoning.md) — optional specialist workflows
- [Evidence handoff](references/evidence-handoff.md) — preserves what is verified, inferred, assumed or unknown across modules
- [Attribution and scope](references/attribution-and-scope.md) — research origins, adaptations and reuse boundaries
- [Evaluation guide](evals/README.md) — tests, dataset handling, and claims the tests do **not** support

Reference files load progressively; do not pre-load the entire package for simple queries.

## Example requests

- “Is this productivity claim supported by the data? Check the strongest alternative explanation.”
- “We must choose one vendor within a hard budget cap. Compare the feasible options.”
- “Audit this board memo's argument and rewrite only the unsupported claims.”
- “Help me practice the reasoning myself; ask one important question at a time.”
- “Analyze whether this management policy is fair, and which organizational incentives could defeat it.”

## Chinese examples

- “这个实验只是前后对比，能证明 AI 导致效率提升吗？请指出最关键的证据缺口。”
- “在总预算不能超出的约束下比较两个方案，给出可修正的建议。”
- “请审查这份英文 memo 的逻辑，但用中文解释，并保留英文原文引号和数字。”
- “请一轮只问我一个问题，帮助我自己检验判断。”

## Testing

From the repository root:

```sh
python3 -m unittest discover -s skills/semantier-thinking/evals -p 'test_*.py' -v
```

The offline tests validate package contracts, the English and bilingual scenario-oracle coverage, and both the bilingual and FOLIO benchmark adapters. The synthetic scenario routes are **expected labels**, not observed model successes. The [FOLIO evaluator](evals/README.md) requires an independently supplied dataset and an authorized model driver to produce baseline-vs-skill accuracy. No deterministic check establishes real reasoning improvement.

## Source vs official distribution

This GitHub directory is **source**, not a signed Semantier Official Marketplace release. The intended official catalog is `https://assets.semantier.cn/skills/v1/catalog.json`; production publisher-key admission, immutable OSS package release, signature verification and live HTTPS/native Windows acceptance are separate gates. A repository link, test pass or unsigned index cannot satisfy those gates.

The legacy [plugin catalog](../../marketplace/index.json) is not the official standalone-skill registry. Skill installation must retain user approval and existing Hermes scan/trust boundaries.
