---
name: skill-review
description: Review SKILL.md and AGENTS.md instructions for activation noise, unnecessary always-on context, weak progressive disclosure, obsolete model scaffolding, and unclear decision or completion boundaries.
---

# Skill Review

Use this skill to audit agent instruction surfaces such as `SKILL.md`, `AGENTS.md`, repository agent guidance, or an installed skill set.

The goal is not brevity for its own sake. Minimize always-loaded instruction cost while preserving constraints whose violation has a concrete consequence.

## Review method

1. Inventory the instruction surfaces in scope.
2. Review skill descriptions before bodies. Flag descriptions that are broad, overlapping, contradictory, or have excessive “pick me” energy.
3. For each skill, separate routing information, selected-workflow guidance, conditional detail that should move behind progressive disclosure, and genuine invariants or safety boundaries.
4. Review `AGENTS.md` as universally loaded repository context. Ask whether each instruction is needed for nearly every task or should instead be a contextual pointer.
5. Flag obsolete model-compensation rules, especially blanket requirements to map the repository, read large doc stacks, ask for approval at every step, run broad tests, brainstorm, plan, or follow a fixed itinerary regardless of task shape.
6. Check decision and completion boundaries. Preserve real authority and safety limits; remove unnecessary stop gates. Where useful, state safe autonomy and a concrete definition of done.
7. Produce a prioritized audit with concrete rewrite recommendations. Prefer deleting or relocating whole classes of unnecessary instruction over merely shortening sentences.

## Principles

- Keep skill descriptions as short as possible while still discriminating when the skill should be used.
- Avoid overlapping activation surfaces unless the distinction is obvious from the descriptions.
- Prefer progressive disclosure. Multi-workflow skills should use the root `SKILL.md` as a minimal router into references, scripts, or workflow-specific files.
- Avoid elaborate itineraries when capable models can infer reasonable steps. Prescribe sequences only where order matters or deviation creates concrete risk.
- Treat `AGENTS.md` as a repository constitution, not a universal runbook.
- Preserve hard invariants: security, authority, destructive-operation limits, deterministic correctness requirements, architecture laws, and other boundaries with real consequences.
- Verification should be proportionate to the affected surface unless the repository has a concrete reason for stronger coverage.
- Do not require approval at every intermediate step for safe local work. Make stop conditions explicit where they matter.
- Define completion for workflows that should continue through implementation, inspection, and repair.
- Prefer outcome- and invariant-oriented guidance over model-specific handholding; repository instructions may be consumed by different models.

## Output

For substantial audits, return:

- instruction inventory and effective scope,
- highest-risk issues first,
- per-skill verdict: `KEEP`, `TRIM`, `REFACTOR`, `MERGE`, or `REMOVE`,
- `AGENTS.md` findings split into `KEEP ALWAYS LOADED`, `ROUTE`, and `RELOCATE/REMOVE`,
- activation-collision findings,
- progressive-disclosure opportunities,
- obsolete scaffolding findings,
- decision-boundary and persistence findings,
- a concrete target structure or patch plan.

Use `references/audit-rubric.md` for systematic scoring. Read `references/article-principles.md` when the review should be explicitly grounded in Eric Provencher's “Rethinking skills and prompts for GPT-6 Astra”.
