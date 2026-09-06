# Audit Rubric

Score each dimension from 0 to 2, where `0 = healthy`, `1 = review`, and `2 = clear refactor target`.

## Skill dimensions

### 1. Discovery precision
- 0: short, discriminating description with an obvious trigger.
- 1: somewhat broad or keyword-heavy.
- 2: claims a large task class, overlaps several other skills, or has strong “pick me” phrasing.

### 2. Progressive disclosure
- 0: root `SKILL.md` contains only the guidance normally needed after activation.
- 1: some conditional detail is loaded eagerly.
- 2: root contains multiple long workflows, exhaustive references, examples, schemas, or tool catalogs that apply only sometimes.

### 3. Prescription cost
- 0: instructions focus on outcomes, invariants, and genuinely order-sensitive steps.
- 1: some unnecessary sequencing or recipe-like behavior.
- 2: fixed itinerary is imposed across tasks even when competent models could choose an approach safely.

### 4. Boundary quality
- 0: real safety, authority, destructive, or correctness boundaries are clear and proportionate.
- 1: some boundaries are stronger than their consequences justify.
- 2: frequent approval gates or stop rules appear to compensate for historical model behavior rather than current workflow risk.

### 5. Model neutrality
- 0: guidance works across capable agent models.
- 1: wording assumes a narrow model behavior.
- 2: instructions explicitly force scaffolding mainly to compensate for one model generation.

### 6. Duplication and collision
- 0: responsibilities are distinct and not restated elsewhere.
- 1: mild duplication.
- 2: substantial overlap with another skill or with `AGENTS.md`, creating conflicting or duplicated sources of truth.

## AGENTS.md dimensions

### 1. Universal relevance
For every rule ask: would a typo fix, narrow bug fix, and architecture change all need this in context?
- 0: yes, or the rule is a short pointer.
- 1: relevant to many but not most tasks.
- 2: task-specific workflow is universally injected.

### 2. Constitutional value
- 0: architecture authority, security/production boundary, repository invariant, precedence rule, or concise routing pointer.
- 1: useful convention that could plausibly move elsewhere.
- 2: runbook, command catalog, long checklist, or generic methodology.

### 3. Verification proportionality
- 0: verification guidance is scoped by affected surface or concrete risk.
- 1: broadly stated testing expectation.
- 2: mandatory full-suite, repo-wide, browser-wide, or repeated verification regardless of change size.

### 4. Safe autonomy
- 0: safe local work may continue through relevant verification and repair without repeated approval.
- 1: continuation expectations are ambiguous.
- 2: agent is forced to stop at unnecessary intermediate decisions.

### 5. Completion clarity
- 0: completion or stop boundary is clear when persistence matters.
- 1: first-pass completion could be interpreted ambiguously.
- 2: instructions explicitly bias toward premature stopping or indefinite exploration.

## Verdict guidance

- `KEEP`: low cost and clear value; no material change needed.
- `TRIM`: sound responsibility, but description/body contains avoidable eager context.
- `REFACTOR`: capability should remain but activation semantics or progressive disclosure need structural change.
- `MERGE`: major overlap makes separate discovery surfaces harmful.
- `REMOVE`: capability is obsolete, redundant, or better handled by normal model judgment without dedicated instruction.

## Priority heuristic

Prioritize findings in this order:

1. incorrect or dangerous boundaries,
2. broad activation collisions,
3. universally loaded `AGENTS.md` bloat,
4. large roots lacking progressive disclosure,
5. duplicate generic methodology,
6. wording-level concision.
