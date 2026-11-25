---
name: tutor
description: Learn from selected project material, practice an objective, submit an answer, or resume a learning plan.
version: 0.1.1
author: Semantier
---

# Tutor

## Routing

Use tutor_progress when resuming an existing plan. Use tutor_plan for a new goal or an edit requested by the learner.

## Workflow

For English teaching turns, follow [the teaching instructions](prompts/teaching.en.md). 中文辅导使用[中文教学说明](prompts/teaching.zh.md)。

Let the learner select the material and adjust or defer objectives. Use tutor_teach for an explanation or hint, then tutor_practice to present a frozen exercise. Wait for an answer. Use tutor_submit for the learner's actual submission. Include learner_assistance only when the learner states whether they used help. A recorded hint or previously displayed grading feedback counts as assistance for the same exercise. When a learner asks about the evidence, open the cited entry under their current access.

## Tool use

Carry forward the project, plan, objective, exercise and revision references returned by the tools. Preserve the original request identity on retries. Report an unavailable operation or ungraded response as returned.
