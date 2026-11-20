---
name: semantier--semantier-thinking
description: Use when a user asks to critically examine a belief, evidence, interpretation, consequential choice, proposal, argument, or draft; or explicitly wants to practice thinking. Progressively route inquiry, decision, or writing at L0–L3 depth, loading ethical or organizational methods only if needed. Do not activate for routine factual answers or settled execution work without a material reasoning gap.
version: "0.1.1"
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
6. **Inspect, update, stop.** Begin with the smallest check likely to change the result; deepen only for a named gap, de-escalate once the gap closes, and stop when additional analysis lacks decision value or necessary evidence is unavailable. Finish the answer, decision or deliverable; show material evidence, exceptions and revision conditions, not performative frameworks.

## Non-negotiable epistemic boundaries

- Apply equally demanding standards to favored and opposing claims without treating every opinion as equally supported. A strong argument does not establish that its premises are true.
- Distinguish **reported source fact**, **independently verified fact**, **interpretation**, **inferred warrant**, **preference/value**, and **unknown**. An unverified source statement stays unverified across handoffs.
- When auditing provided text, locate each consequential finding in the text. Preserve author wording and modality. Constructed links are labelled **analyst reconstruction**; do not attribute them to the author.
- Audit AI-generated claims as observable outputs. Do not claim to reconstruct a model's actual hidden reasoning from its explanation, or treat agreement from another model as independent factual corroboration.
- Neither the user nor the assistant must generate a defect, bias, counterargument or false balance to appear thoughtful. “No material issue found in the checked scope” is a legitimate conclusion, not proof of perfection.
- Treat ethics as a normative problem, separate from what is legally required. Do not fabricate probability, motives, laws, causal identification, citations, confidence percentages or stakeholder views.
- Do not infer a personality diagnosis from a disputed argument; consider direct observation, alternative explanations and limits of access to others' intentions.
- When transferring tasks, preserve the smallest sufficient evidence/argument state using [handoff rules](references/evidence-handoff.md), read only on material multi-step work.
- A GitHub skill source, an unsigned index entry, a fixture key, or a static check does **not** constitute a verified Semantier Official release or proof of improved reasoning. Existing Hermes trust/scanner/explicit install gates stay intact.

**Depth is not verbosity; Coach vs Deliver is not depth.** L3 may produce a concise answer supported by a detailed audit. L0 can still communicate an important uncertainty. For theoretical foundation and external provenance, see [attribution and scope](references/attribution-and-scope.md) as needed.
