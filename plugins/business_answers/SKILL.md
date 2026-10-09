---
name: business_answers
description: Build and read source-bounded receivables answers from an authorized CSV/XLSX company import.
---

Use `business_answers_receivables_run` with an existing import reference. The native core returns progress, clarification, checks and an immutable answer reference. If clarification is required, ask for the ambiguous field or snapshot date and submit the explicit mapping/confirmation.

Use `business_answers_receivables_status` to resume a run and `business_answers_receivables_read_answer` to reopen its answer and invoice contributions. Reuse the saved answer reference for unchanged inputs; changed inputs create a new run. Explain per-currency totals, unavailable overdue results, source scope and candidate status.

<!-- runtime-owner: TOOL invariant-class: EXPLAINED_AND_ENFORCED enforced-by: src/agents/business_answers.py::native_service -->
Identity and authority must come from the authenticated native core, never model-supplied organization or actor fields.

<!-- runtime-owner: WORKFLOW invariant-class: WORKFLOW_HEURISTIC -->
Do not substitute ad hoc shell, Python or HTTP calculations for these registered tools. Report a missing tool surface clearly.

Recipe asset: `receivables.recipe.json`. Core owns recipe execution, exact source pins, Decimal calculations, checks and retention. Installing this package does not admit or activate an ontology.
