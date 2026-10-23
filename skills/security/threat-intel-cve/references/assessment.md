# Evidence and assessment

## Independent fields

Keep each dimension separate; do not combine CVSS, KEV and EPSS into a fabricated risk probability.

| Dimension | Values / evidence |
|---|---|
| Finding kind | vulnerability, malicious_package, vendor_incident, certificate_issue, ioc_context |
| Applicability | confirmed_affected, potentially_affected, not_affected, unknown |
| Exploitation | KEV listed, vendor-confirmed observed exploitation, PoC only, not established, unknown |
| Compromise | confirmed by incident evidence, suspected, not established |
| Source coverage | checked with date, failed, unsupported, incomplete pagination, not checked |
| Recommendation | action, rationale, owner, next verification; distinct from source facts |

A provider version match establishes a candidate or potentially affected item. Confirmed affected requires trustworthy inventory identity, applicable range/build/platform and known necessary preconditions. Unknown deployment configuration remains an explicit uncertainty. Not affected requires positive exclusion evidence, not a feed miss, a low score or absence of telemetry.

If an advisory is rejected or withdrawn, preserve it for traceability but do not count it as an active finding. Conflicting current sources require reconciliation or an unresolved status. Retain exact aliases without counting one issue multiple times.

## Suggested triage policy

These are local review recommendations, not CISA SSVC or an empirically calibrated model. Use the organization's existing policy if provided.

- Urgent: confirmed compromise or credible malicious artifact execution; or confirmed affected, reachable asset with observed exploitation and relevant preconditions. Recommend incident-response review and scoped containment/remediation.
- High: credible malicious distribution matching a selected artifact/version without execution confirmation; or affected asset with material impact and plausible exposure. Known exploitation or a high EPSS forecast can strengthen the rationale without proving local exposure.
- Review now: potentially affected or missing inventory/configuration for a severe/current threat. Treat evidence collection as the next action; do not downgrade uncertainty to low risk.
- Routine: positively scoped, lower-impact affected item with no urgent signals under the organization's policy.
- Informational: incident intelligence with no established asset match, or a withdrawn/rejected advisory. Explain what was checked.

Do not let a low EPSS forecast cancel observed exploitation or confirmed malicious execution. Record numeric CVSS with score version, vector, source and date; record EPSS probability, percentile and score date without presenting either as asset-level compromise probability.

## Output

Start with whether any selected asset is affected or unresolved, then provide the next action. Use a compact table:

| Item/version | Finding and kind | Applicability and evidence | Exploitation/context | Priority and reason | Action / verification |
|---|---|---|---|---|---|

For material findings include stable source URLs, provider record identifiers, publication/modified and retrieval times, current fixed-version evidence, affected-range proof and unresolved questions. Use a source's opaque incident ID when no CVE exists; do not invent one.

Close with coverage: selected/checked/excluded/failed/remaining package counts, inventory origin and timestamp, checked sources and incomplete pagination. State that no match in the checked feeds does not establish safety. Call a source unavailable when authentication, network, schema or throttling prevents checking it.

Preserve returned provider records and receipt metadata for review. A response SHA-256 identifies the fetched bytes, but the helper stores parsed JSON rather than a byte-for-byte archive; do not claim byte-exact replay. If an audit needs original bytes, use the existing governed collection path, not reconstructed JSON. Any later live refresh creates new evidence and a new assessment rather than rewriting the old basis.

## Proportionate responses

For a verified malicious package: establish affected artifact hashes/versions, provenance, whether installed/executed, exposed permissions and the incident window; propose a clean rebuild and appropriately scoped credential review. A simple upgrade is not sufficient evidence that an already compromised environment is clean.

For an ordinary CVE: verify vendor-fixed build and prerequisites, propose update/mitigation, then verify deployed versions and relevant exposure. Do not promise that upgrading the dependency alone resolves every transitive copy or running workload.

For a cloud or CA incident: map the precise vendor scope or certificate chain and client versions first. Preserve applicability uncertainty until evidence closes it.
