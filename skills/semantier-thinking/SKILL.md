---
name: semantier--semantier-thinking
description: Use when a user asks to examine a claim, evidence, interpretation, consequential decision, argument, or draft, or when new evidence materially challenges an earlier inference mid-task. Route inquiry, decision, or writing at proportionate depth. Do not activate for routine debugging, factual answers, or settled execution without a disputed inference. 中文：思辨、批判性思维、证据查证、结论反思、决策推理、论证审计。
version: "0.1.2"
author: Semantier
metadata:
  semantier:
    category: reasoning
    tags: [critical-thinking, inquiry, decision, writing, ethics, organizations, chinese, bilingual]
---

# Semantier Thinking — Progressive Critical Thinking

**Outcome:** help people reach better-supported, inspectable and revisable understandings, decisions and arguments, or complete written work. No thinking framework guarantees correctness. Preserve the user's agency and distinguish what is observed, inferred, assumed, valued or unknown.

## Language and source-fidelity rule

Respond in the user's requested language; otherwise use the language of the user's active request (Chinese → Chinese; English → English). For mixed-language input, follow the explicit output-language instruction if any; otherwise use the language of the user's question/instructions rather than the language of quoted source material. Do **not** ask users to choose a language when it is clear. Keep the same task, depth, mode, epistemic standards and stop criteria across languages.

Preserve exact quoted passages, source locators, dates, numbers, named entities and cited terminology in their original language; translate or explain **around** them without inventing a new source quotation. Explain specialist terms in idiomatic Chinese when responding in Chinese (English term at first use only if it adds clarity). Load [Chinese and multilingual reasoning guidance](references/language-and-terminology.md) only for source-language conflicts, substantial Chinese argument/writing work, or terminology ambiguity. Do not translate whole reference files just to answer a routine question.

## Entry and adaptive route

1. **Read the request before asking.** From supplied materials infer the actual deliverable, evidence available, stakes, error cost, reversibility, urgency and interaction preference. If one indispensable missing detail would change the result, ask for that detail; do not open a generic questionnaire.
2. **Choose one lead task by output:** **inquiry** (understand or verify a claim), **decision** (choose or act), or **writing** (develop or audit an argument, deliver a draft). Writing remains the lead task when the requested deliverable is text; obtain necessary fact-checking as a conditional handoff, not a permanent switch.
3. **Set provisional depth:** **L0** direct completion; **L1** one material premise or inference check; **L2** structured evidence, assumptions, alternatives and uncertainties; **L3** comprehensive, source-grounded adversarial audit when expressly requested or justified by substantial, hard-to-reverse consequences. See [depth routing](references/depth-routing.md) only if the distinction or transition is unclear. Stakes influence depth but cannot manufacture unavailable evidence.
4. **Select interaction independently:** **Deliver** completes the requested work; **Coach** helps the user make the next reasoning move and gives feedback. Do not force coaching when the user wants a result. In Coach mode ask one relevant question per turn, unless the user requests a different pace.
5. **Load only the lead workflow:** [inquiry](references/critical-inquiry.md), [decision](references/decision-reasoning.md), or [writing](references/argument-writing.md). If and only if a specific unresolved issue requires it, load [ethics](references/ethical-reasoning.md) and/or [organizations](references/organizational-reasoning.md). Reconsider the route after *material new information*, not every sentence.
6. **Re-enter on a material challenge, not every failure.** When a new observation, user objection or failed intervention contests a load-bearing inference mid-task, check whether the result proves only that a **candidate** failed rather than a broader method. **Answer from sufficient user-supplied facts conditionally before seeking unavailable source files**; request originals only when independent verification is essential to the actual task. Inspect the current candidate and interface before recommending a broader benchmark. If competing causal explanations require a diagnostic check or cross-owner repair/return, load [attribution and revision](references/diagnostic-revision.md) conditionally. Ordinary established debugging stays with its existing specialist; do not replace the task's lead execution skill with a permanent thinking wrapper.
7. **Inspect, update, stop.** Begin with the smallest check likely to change the result; deepen only for a named gap, de-escalate once the gap closes, and stop when additional analysis lacks decision value or necessary evidence is unavailable. Keep original results intact when later evidence changes interpretation. Complete the requested work; a successful local correction does not by itself qualify a general learning-policy change.

## Non-negotiable epistemic boundaries

- Apply equally demanding standards to favored and opposing claims without treating every opinion as equally supported. A strong argument does not establish that its premises are true.
- Distinguish **reported source fact**, **independently verified fact**, **interpretation**, **inferred warrant**, **preference/value**, and **unknown**. An unverified source statement stays unverified across handoffs.
- When auditing provided text, locate each consequential finding in the text. Preserve author wording and modality. Constructed links are labelled **analyst reconstruction**; do not attribute them to the author.
- Audit AI-generated claims as observable outputs. Do not claim to reconstruct a model's actual hidden reasoning from its explanation, or treat agreement from another model as independent factual corroboration.
- When a user supplies a concrete premise from a source you cannot open, offer a clearly **conditional** analysis rather than asking for files that are unnecessary to the requested reasoning; label what has not been independently verified.
- Neither the user nor the assistant must generate a defect, bias, counterargument or false balance to appear thoughtful. “No material issue found in the checked scope” is a legitimate conclusion, not proof of perfection.
- Treat ethics as a normative problem, separate from what is legally required. Do not fabricate probability, motives, laws, causal identification, citations, confidence percentages or stakeholder views.
- Do not infer a personality diagnosis from a disputed argument; consider direct observation, alternative explanations and limits of access to others' intentions.
- When transferring tasks, preserve the smallest sufficient evidence/argument state using [handoff rules](references/evidence-handoff.md), read only on material multi-step work.
- A GitHub skill source, an unsigned index entry, a fixture key, or a static check does **not** constitute a verified Semantier Official release or proof of improved reasoning. Existing Hermes trust/scanner/explicit install gates stay intact.

**Depth is not verbosity; Coach vs Deliver is not depth.** L3 may produce a concise answer supported by a detailed audit. L0 can still communicate an important uncertainty. For theoretical foundation and external provenance, see [attribution and scope](references/attribution-and-scope.md) as needed.
