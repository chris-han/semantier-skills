# Article Principles

Source: Eric Provencher, “Rethinking skills and prompts for GPT-6 Astra”.

This reference captures the article's review lens. It is intentionally concise and should not replace the original article.

## Skills

- Skill names and descriptions consume discovery context before a skill is opened.
- Descriptions should be as short as possible while still making activation conditions clear.
- Too many skills, long descriptions, overlapping descriptions, contradictions, and excessive “pick me” phrasing reduce selection quality.
- Progressive disclosure is a key marker of a useful skill. For multiple workflows, keep the root document as a minimal router and move conditional detail to supporting docs or scripts.
- Elaborate itineraries and recipes can hinder stronger models. Prefer guidance that states outcomes, constraints, and the few steps whose order genuinely matters.
- Repository skills may be consumed by different models, so avoid instructions that compensate for one model at the expense of others.

## AGENTS.md

- `AGENTS.md` is always-loaded repository context, so each instruction should justify its universal cost.
- Requiring broad repo maps or large doc stacks before every edit is excessive; contextual pointers are preferable.
- Blanket reminders to test and re-check may cause unnecessary verification if the model already performs those behaviors. Testing guidance should reflect real risk and scope.
- `AGENTS.md` can usefully grant safe autonomy for known-safe workflows, such as running disposable local tests and fixing failures caused by the requested change without repeatedly asking for approval.

## Decision boundaries

- Revisit strong ask-first rules added to compensate for older model behavior.
- Preserve boundaries with real safety, authority, production, or destructive-operation consequences.
- Avoid causing unnecessary early stops by expressing boundaries more strongly than the workflow requires.

## Persistence and completion

- Define completion when the workflow should continue beyond a first implementation.
- If the task includes implementation, running it, inspecting the result, and fixing failures, say so explicitly.
- State where exploration should stop when deeper iteration is desired.

## Review interpretation

The article does not argue for minimal text at any cost. It argues for minimizing always-loaded and prematurely loaded instruction while preserving concrete constraints, useful routing, and explicit completion boundaries.
