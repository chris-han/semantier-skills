# Source routing and boundaries

Source documentation checked on 2026-10-23. API access, terms and schemas can change; recheck official documentation when a request fails. The bundled helper automates only OSV, GitHub reviewed/malware advisories, NVD, CISA KEV and FIRST EPSS. All other routes below are guided investigations, not implemented connectors.

## Package and CVE sources

| Source | Query and interpretation | Primary documentation |
|---|---|---|
| OSV | POST api.osv.dev/v1/query with ecosystem, registry name and resolved version; follow page_token. Matching may use upstream fuzzy-version semantics. Preserve affected ranges, aliases, withdrawn date and references. | https://google.github.io/osv.dev/post-v1-query/ |
| GitHub advisories | GET api.github.com/advisories with ecosystem, affects=name@version and explicit type=reviewed; separately query type=malware. Capture Link pagination as incomplete if remaining pages are not fetched. | https://docs.github.com/en/rest/security-advisories/global-advisories |
| NVD | GET services.nvd.nist.gov/rest/json/cves/2.0?cveId=...; keep vulnStatus, metrics and nested configurations. NVD enrichment can lag CNA/vendor disclosure. | https://nvd.nist.gov/developers/vulnerabilities |
| CISA KEV | Download the official JSON catalog; match exact CVE. Record catalogVersion/dateReleased and dateAdded. Not listed does not mean not exploited. Federal due dates are not automatically a customer's legal deadline. | https://www.cisa.gov/known-exploited-vulnerabilities-catalog |
| FIRST EPSS | GET api.first.org/data/v1/epss?cve=...; preserve epss, percentile and score date. No record is unknown, not zero. | https://www.first.org/epss/data and https://www.first.org/epss/faq |

For ecosystem names, preserve OSV case (PyPI, npm, Go, Maven, etc.). The helper maps eight common ecosystems to GitHub's different identifiers. Unsupported GitHub ecosystems remain explicitly uncovered even if OSV succeeds.

Use the selected lockfile or SBOM to obtain exact versions. Do not execute package setup/build hooks or install a suspect package to inspect it. Requirements ranges and floating Docker tags are insufficient: obtain the locked/installed version or image digest. A claimed compromised version requires confirmation against a primary incident advisory; do not hard-code the user's examples as facts.

## Emerging threats and vendor/cloud incidents

Use web_search for the named product plus security advisory, incident, CVE or the relevant identifier, constrained to official vendor/security domains where possible. Follow primary references with web_extract. Record publication, modification, incident window and retrieval times separately. News/social reports are leads until corroborated.

For a bounded watch, record since/until in UTC, inventory scope and checked sources. Include newly modified as well as newly published advisories; publication-only discovery misses revised affected ranges. Preserve unresolved prior findings. Without a retained prior run, say this is an initial baseline and avoid claiming a complete delta. Keep a failed run's coverage gap visible rather than advancing its watermark as fully checked.

For platform secret leaks, inspect the vendor's incident scope and whether the selected service, account, feature and time window intersect. CVE/package feeds alone cannot answer this. Recommend scoped credential review/rotation through the owner when supported; never infer that every customer or secret was affected.

## IOC enrichment

Use existing authorized provider tools or securely configured scripts only if the finding contains a relevant public IOC. Check current provider documentation and permitted commercial use before integrating. Do not make access to optional enrichment a prerequisite for core CVE/package assessment.

- ThreatFox: https://threatfox.abuse.ch/api/ — requires Auth-Key; POST https://threatfox-api.abuse.ch/api/v1/ for documented read-only queries. Its public docs distinguish active and expired IOC coverage.
- URLhaus: https://urlhaus.abuse.ch/api/ — requires Auth-Key; export URLs can embed the key. Do not log/cite such URLs or use them in web tools that expose arguments. Prefer an authorized local client with secret redaction; otherwise mark unavailable.
- MalwareBazaar / Feodo Tracker: use current official abuse.ch documentation only when hash/malware/C2 context is needed.
- OTX, AbuseIPDB, GreyNoise: optional existing integrations for public IOC context. Do not transmit internal addresses, customer logs, files or private indicators unless specifically authorized.

Community access does not imply unrestricted commercial use. ThreatFox/URLhaus documentation states commercial needs may require a paid service. No connectors or subscriptions are installed by this skill.

Record IOC type/value, provider, first/last seen, record age, confidence and any expiry. Domain/IP reputation is context; it does not prove exploitation of a CVE or compromise of a local asset. Do not visit malware destinations or download samples.

## Certificate authority and trust issues

Use CA incident reports, https://www.ccadb.org/cas/incident-report and the affected platform's official root-store update/decision. Certificate Transparency, including crt.sh, can help discover issuance but is not evidence of private-key weakness, key theft or universal distrust.

Match the actual certificate fingerprint or issuer/SPKI, chain, issuance time, client trust store/version and distrust effective date. Distinguish misissuance, weak-key evidence, revocation and platform-specific distrust. Do not infer impact from an issuer display name alone or disable TLS verification.

Do not modify trust stores or revoke certificates from this assessment. Recommend renewal/reissuance and a client-specific verification only when the evidence supports it.
