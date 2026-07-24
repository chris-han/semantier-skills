---
name: regulatory-source-monitor
description: >
  Initiate governed legal regulatory source monitor runs, inspect due sources,
  summarize persisted scan status, request deterministic source status, and
  acknowledge regulatory alerts through Semantier-owned legal-corpus contracts.
version: 1.0.0
author: Semantier
license: MIT
tags:
  - legal-corpus
  - regulatory-monitor
  - governance
---

# Regulatory Source Monitor

Use this Skill only through the registered `regulatory_source_monitor_*` tools.

Allowed operations:

- list governed due legal sources for an organization;
- start or resume one bounded regulatory monitor run;
- inspect source, knowledge, and runtime status projections;
- acknowledge an existing legal regulatory alert;
- summarize persisted run results and resolution errors.

Do not register arbitrary URLs, fetch outside the resolved monitor-policy allowlist, mutate SQLite tables or files directly, certify legal source versions, activate authority bundles, choose runtime posture freely, create Git commits, use GitHub as regulatory source authority, or treat acknowledgement as approval.

If a tool returns a policy resolution error, source unavailable result, missing acquisition URI, authorization failure, or stale object state, report that state directly and do not invent a workaround.

Deterministic posture names are produced by Semantier runtime. Explain them as persisted status only:

- `CONTINUE_PINNED`
- `REVIEW_NEW_EXECUTIONS`
- `BLOCK_NEW_EXECUTIONS`

The finite cron entrypoint is `python -m eos.legal_regulatory_monitor_cron`. It is intended for no-agent cron jobs with explicit governed environment variables:

- `SEMANTIER_LEGAL_MONITOR_ORGANIZATION_ID`
- optional `SEMANTIER_LEGAL_MONITOR_WORKSPACE_ID`
- optional `SEMANTIER_LEGAL_MONITOR_SCHEDULED_AT`
