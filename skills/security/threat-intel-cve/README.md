# Threat Intelligence and CVE Skill

A standalone Hermes skill for **evidence-grounded assessment** of publicly reported software vulnerabilities and supply-chain incidents. It helps evaluate whether an identified package, version, inventory item or deployed asset may be affected; it does **not** claim that an advisory match proves compromise.

**Source name:** `threat-intel-cve`  
**Version:** `0.1.0`  
**Authorship:** Kai Han / Semantier, as declared in [SKILL.md](SKILL.md).

## Use cases

- Examine a CVE or GHSA against a particular software version.
- Compare a user-selected public package inventory or SBOM with advisories.
- Review vendor/cloud/CA incidents, affected configurations and actionable evidence.
- Distinguish severity, exploitation likelihood and actual deployment applicability.

The skill separates **declared**, **locked**, **installed**, **shipped**, and **running** versions. It preserves source timestamps, coverage gaps, withdrawn advisories and uncertainty; no result of an incomplete query is silently interpreted as clean.

## Package contents

- [SKILL.md](SKILL.md) — workflow, source-verification policy, safety boundaries and tool use
- [Assessment guide](references/assessment.md) — applicability, evidence and prioritization
- [Sources guide](references/sources.md) — optional incident-source branches
- [Helper](scripts/threat_intel.py) — Python standard-library CVE/package lookups
- [Offline tests](scripts/test_threat_intel.py) — deterministic checks

## Using the skill

The consuming Hermes agent should load [SKILL.md](SKILL.md) and resolve the installed directory dynamically. It can use the included helper for public package or CVE lookups, subject to source availability and permission to disclose public package coordinates. The skill does not require a new pip dependency.

The agent must not scan unrelated local repositories, share private package names without permission, execute untrusted proof-of-concept payloads, or autonomously patch, revoke, quarantine or install anything.

## Testing

From this skill directory, run:

```sh
python3 scripts/test_threat_intel.py
```

This covers local helper logic. Real public API responses, installed Hermes activation and native Windows acceptance remain separate tests.

## Publishing and license qualification

This directory is GitHub **source**, not an admitted Semantier Official standalone release. The [registry contract](https://github.com/chris-han/semantier-runtime/blob/main/docs/derived/semantier-official-skill-registry-contract-v1.md) records open license qualification and the required release-name transition (`semantier--<slug>`) before official packaging. Do not infer an explicit redistribution license merely from the presence of a public repository.

Official publication also requires reviewed signing authority, immutable verified package bytes and a signed catalog. The proposed URL is `https://assets.semantier.cn/skills/v1/catalog.json`; its availability and this skill's qualification have not been proven by this README.
