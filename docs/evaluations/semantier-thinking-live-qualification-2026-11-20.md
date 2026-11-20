# Semantier Thinking — live qualification, 2026-11-20

## Scope and source pin

- Canonical source: `chris-han/semantier-skills`, commit `4ff1a270026ae76329db6af3cb6250b8f0ea8d11` (skill v0.1.1).
- Bilingual scenario oracle: 24 author-designed cases, each in English, Simplified Chinese and mixed-language form; 72 prompts per arm.
- Model used in real calls: `deepseek-v4.1-flash-1017` via the pre-existing Alibaba Cloud MaaS DEVELOPMENT research credential. 144 attempted calls, no retries.
- Conditions: baseline without Skill instructions; candidate with `SKILL.md` and multilingual reference pre-injected. Both had the same instrumented JSON response contract. `temperature=0`, `max_tokens=512`, `enable_thinking=false`.
- Evaluated at prompt level; this **did not run native Hermes skill discovery or progressive reference loading**. Route metadata was self-reported by the model, not independently observed. No independently evaluated answer correctness or fluency claim.

## Full matched case metrics

| Metric (total-denominator) | Baseline (72) | Skill (72) |
| --- | ---: | ---: |
| Structurally valid results | 56/72 | 53/72 |
| Route-label match to author-designed oracle | 22/72 (30.56%) | 32/72 (44.44%) |
| Output script matches requested language (weak heuristic) | 54/72 (75.00%) | 43/72 (59.72%) |
| Route agreement over all 3 language variants | 7/24 (29.17%) | 8/24 (33.33%) |
| Original English quotation preserved | 3/3 | 3/3 |
| Invalid driver/model outputs | 16 | 19 |

By language, route-label matches: English 6/24 → 10/24; Chinese 5/24 → 12/24; mixed-language 11/24 → 10/24.

By language, weak output-script checks: English 17/24 → 8/24; Chinese 17/24 → 19/24; mixed-language 20/24 → 16/24.

By task family, route-label matches: L0 direct 3/6 → 5/6; inquiry 11/21 → 14/21; decision 3/18 → 8/18; writing 5/15 → 5/15; ethics/organization group 0/12 → 0/12 (the Skill arm's 12/12 in this last group were invalid under the strict JSON schema; do not interpret this as a subject-matter accuracy score).

Known validity limitations: this is one model, one run, author-designed oracle labels and no blinded independent adjudicator. Invalid results remain in the 72-case denominator for each arm. The script-based language check does not establish Chinese fluency or semantic fidelity. The candidate condition preloaded the Chinese terminology reference even for English prompts, violating intended conditional disclosure; prompt overhead and the language result cannot be attributed solely to the language rules.

Valid-response token lower bounds reported by provider: baseline 8,972 prompt + 10,548 completion = 19,520; candidate 124,512 prompt + 9,753 completion = 134,265. Failures can accrue more tokens and charges not captured in these lower bounds. Exact upstream monetary spend was not independently settled; no production/customer billing claim is made.

A diagnostic rerun of the previously invalid B21 English Skill sample showed an `INVALID_PROVIDER_JSON` failure with 512 tokens; raising the **separate diagnostic** output limit to 1024 produced parseable JSON after 577 completion tokens, but a malformed specialist label (`organizations` instead of `organizational`). Neither diagnostic rerun is mixed into the frozen 144-call metrics. This points to distinct length/driver-schema problems; it does not prove all other invalid outputs have the same cause.

**Disposition:** `REAL_MODEL_PROMPT_ABLATION_OBSERVED_WITH_NEGATIVE_SIGNALS`; *not* evidence of general critical-thinking improvement, language parity, native skill behavior, or official release readiness.

## Semantier Official OSS publication preflight

- Registry target: `https://assets.semantier.cn/skills/v1/catalog.json`.
- Public HTTPS HEAD actually returned `403 Forbidden` from `AliyunOSS` on 2026-11-20; response indicated AccessDenied due to bucket ACL. No public catalog was verified.
- Current Hermes trust file `hermes-agent/tools/semantier_skill_trust.json` had `keys={}` and explicitly stated no production publisher key is admitted. Test signer keys cannot count as official identity.
- Existing `semantier-skills/scripts/publish_official_skills.py` is a **read-only** inventory/signing-serialization helper, with no key provisioning, OSS upload or atomic catalog replacement implementation. Its offline tests passed 2/2 on this run.
- Exact source-pinned release candidate reconstructed: 20 files, 107,393 bytes, MIT licensed skill source, runtime name `semantier--semantier-thinking`.
- Dry-run canonical manifest SHA-256: `6dc76fc513400768aac6fd1a186d584f68d7a318ae06dc8ae45b1a836657ac03`.
- Derived immutable prefix: `skills/v1/packages/semantier/semantier-thinking/0.1.1/6dc76fc513400768aac6fd1a186d584f68d7a318ae06dc8ae45b1a836657ac03/`.
- RAM service user `semantier-msix-staging-publisher` was observed, but the existing staging profile could not read the bucket policy (`AccessDenied`). No separate scoped skills publisher role, public prefix read policy, or safe production signer was verified.
- **No OSS writes, ACL/policy changes, catalog replacement, publisher key creation, signing admission, native Windows skill install or live public package readback were performed.**

**Disposition:** `OSS_RELEASE_CANDIDATE_DRY_RUN_PASS__PRODUCTION_PUBLICATION_BLOCKED`.

To qualify Gate 2: admit a real publisher signing key and fingerprint under an existing secure operator owner; verify independent `skills/v1/` Put/Get and public-read policy without broadening Windows release permissions; implement serialized immutable object upload/full GET readback and catalog publication; verify signed catalog and package hashes with the production client trust asset; then perform a real native Windows install/update from distinct immutable A/B releases. None of these outcomes is inherited from a fixture or the dry run.