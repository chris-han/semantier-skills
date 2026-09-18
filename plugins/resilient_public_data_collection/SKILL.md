---
name: resilient-public-data-collection
description: >
  Build reproducible public-source data collection pipelines from observable evidence.
  Use this skill when an initial search or download path is blocked, requires authentication,
  hits anti-bot or rate-limit behavior, or yields too little data. It preserves provenance,
  forks discovery into alternate official sources and alternate public surfaces on the same
  source, freezes membership before semantic selection, validates raw bytes, and hands a
  bounded corpus to downstream qualification or evaluation.
version: 0.2.1
author: Semantier
license: MIT
tags:
  - data-collection
  - provenance
  - public-sources
  - reproducibility
  - research
---

# Resilient Public Data Collection

Use this skill to build a research-grade raw corpus from public sources without confusing
one failed access path with an unavailable source.

The core law is:

> Access failure is evidence about a path, not evidence about a source.

A 403, login prompt, missing attachment, failed search endpoint, or anti-bot response
narrows what is known about one route. It does not establish that the source has no public
representation of the target data.

## Registered tools

Use the registered tools directly for the mechanical parts of this workflow:

- `public_source_prepare_runtime` — lazily provision or verify the isolated Crawlee runtime. Core mode pins `crawlee==1.10.1`; browser mode is a separate escalation to `crawlee[playwright]==1.10.1` plus Chromium. `offline=true` is cache-only and `check_only=true` is non-mutating.
- `public_source_route_recovery` — deterministically enforce recovery-before-retry ordering for blocked acquisition. A recovered alternate source or same-site public entry wins before any blocked retry; 401 never auto-escalates; eligible public/session-like 403 and post-backoff 429 may retry once.
- `public_source_probe` — perform one bounded public HTTP(S) request, preserve ordinary
  browser request semantics, and classify the result as public response, access/auth block,
  WAF/anti-bot, rate limit, or other HTTP error.
- `public_source_inspect_page` — fetch one public HTML page and inspect its links, scripts,
  forms, attachment-like anchors, IDs, and known public download derivations. For CCGP,
  `bizDownload` UUID anchors are surfaced as the corresponding public OSS download URL.
- `public_source_freeze_membership` — freeze the bounded source/object membership before
  raw-byte acquisition. Each member binds `source_id + url + referer + source_stratum`.
  Once present, capture is restricted to requests in that frozen membership, and release freeze
  checks that every member produced at least one success or failure receipt.
- `public_source_capture_object` — download one public object into workspace-scoped,
  content-addressed storage, persist an append-oriented receipt, compute SHA-256, recover a
  server filename when present, and classify document bytes by magic/signature rather than
  by HTTP status alone. Use a distinct `attempt` label for later recovery attempts so the
  original failure remains observable.
- `public_source_freeze_collection` — freeze the current set of capture receipts into a
  deterministic manifest and close that collection to further captures.
- `public_source_verify_collection` — replay a frozen collection without network access
  by checking receipt hashes, object hashes, byte lengths, and the freeze identity.

The tools are the executable owner for URL safety, public-network checks, bounded response
sizes, content-addressed persistence, immutable release freeze, and offline hash replay.
Crawlee owns reusable crawler/session/queue/browser mechanics when those capabilities are
actually needed. The skill owns routing and workflow decisions around those tools.

### Runtime dependency contract

Do not install Crawlee when this skill is only being read, reviewed, planned, or used for
existing Semantier deterministic probe/freeze/verify operations.

When reusable crawler mechanics are required, call `public_source_prepare_runtime` with
`mode=core`. The plugin provisions Crawlee `1.10.1` into an isolated Semantier Skills
runtime cache and returns the interpreter path. It does not modify the host Python
environment. Runtime backend selection is automatic: stdlib `venv` is preferred, but
minimal Debian/Ubuntu hosts without `ensurepip/python3-venv` automatically fall back to
a private target-directory runtime installed with host `python -m pip --target` or
`uv pip install --target`. No `sudo apt install python3-venv` prerequisite is required.

Use `offline=true` when network installation is unavailable or prohibited. Offline mode
must reuse an already verified cache and must not create a venv, invoke pip, or download a
browser. Use `check_only=true` for a non-mutating readiness check. Missing or invalid
offline capability is reported explicitly rather than silently repaired.

Browser support is a separate escalation. Only when a public path demonstrably requires
JavaScript/browser behavior should the workflow call `public_source_prepare_runtime` with
`mode=browser`. That is the only path that installs the Playwright extra and Chromium.


When the tool surface is unavailable, report that missing capability rather than replacing
it with an improvised runtime fetcher.

## 1. Outcome contract

The primary output is a raw archive with inspectable provenance, not an evaluation set and
not a semantic conclusion.

A useful handoff contains:

- a frozen source universe or bounded discovery frame;
- source and path provenance for every discovered member;
- raw bytes for successfully acquired objects;
- SHA-256 identities for captured objects;
- explicit failed, missing, gated, partial, and rate-limited acquisition records;
- mechanically derived candidate groups where useful;
- an offline verification path;
- a clear boundary between raw collection and downstream qualification, labeling,
  modeling, or authority activation.

Use a terminal status such as RAW_ARCHIVE_WITH_EXPLICIT_GAPS_NOT_EVALUATION_READY when
raw evidence exists but completeness, independence, labels, or evaluation eligibility have
not yet been adjudicated.

## 2. Define the acquisition object before choosing a site

Write down the object being acquired and the unit of independence before searching.

Examples:

- full procurement or tender document bytes;
- public contract PDF;
- regulatory source text;
- historical notice plus public attachments;
- product specification archive;
- machine-readable public dataset.

Define the minimum evidence needed to count one source member.

For example:

~~~text
source_group
  = one independent procurement project

usable_raw_member
  = public notice provenance
  + at least one byte-valid primary procurement document
  + stable object hash
~~~

This prevents the collection process from drifting toward whatever happens to be easiest
to download.

Also separate three access questions:

1. Can the listing or search metadata be read publicly?
2. Can the target raw bytes be read publicly?
3. Does formal participation, submission, purchase, registration, or transaction require
   authentication?

Question 3 does not answer Question 2.

## 3. First discovery pass

Explore the most obvious authoritative source and record:

- listing or search URL;
- detail URL shape;
- visible metadata;
- attachment labels;
- download-link shape;
- redirects and final host;
- HTTP status and relevant response headers;
- whether JavaScript constructs a public attachment URL;
- whether public pages distinguish view or query files from formally issued transaction
  files.

Classify failure at the narrowest possible level:

- LISTING_PATH_BLOCKED
- DETAIL_PATH_BLOCKED
- ATTACHMENT_METADATA_MISSING
- PUBLIC_OBJECT_PATH_BLOCKED
- TRANSACTION_LOGIN_REQUIRED
- RATE_LIMITED_OR_WAF_BLOCKED

Avoid promoting any one of these into SOURCE_UNAVAILABLE prematurely.

## 4. First blocker: fork into two branches

When the initial route is blocked or insufficient, start both branches. They are
complementary rather than alternatives.

### Branch A — explore other authoritative sources

Search for the same acquisition object on other legitimate public sources.

Prefer:

- other official national portals;
- provincial, state, municipal, or agency portals;
- public-resource or procurement exchanges;
- official archives and mirrors;
- other authoritative publication systems covering the same object class.

Keep every source in its own provenance stratum.

Example:

~~~text
HAIKOU_GGZY
CCGP_PUBLIC_PROCUREMENT
PROVINCE_X_PUBLIC_RESOURCE
AGENCY_Y_ARCHIVE
~~~

A new source broadens the raw universe. It does not silently replace failed members from
the first source.

Use this branch to improve geographic, institutional, document-format, event-type, and
temporal diversity.

### Branch B — explore other public surfaces on the same source

Treat a website as a graph of publication surfaces rather than as one endpoint.

Explore, where publicly linked and legitimate:

~~~text
site
├── category or listing pages
├── search pages
├── detail or notice pages
├── attachment metadata
├── JavaScript-bound attachment identifiers
├── direct public object or download endpoints
├── contract or disclosure subsystem
├── historical or archive pages
└── alternate official publication views
~~~

For each surface, ask whether it exposes the target object without restricted access.

A public detail page may reveal an attachment identifier even when the first search
endpoint fails. A public attachment service may be accessible through ordinary browser
navigation even when a formal participation portal requires login.

Replicate ordinary public navigation semantics when the site expects them, for example by
carrying the publicly linked detail page as the request Referer. Credentials, CAPTCHA
solving, session impersonation, and access-control circumvention are outside this workflow;
classify those paths as gated and continue with legitimate public surfaces.

## 5. Authentication and anti-bot interpretation

Use `public_source_route_recovery` to keep the recovery order mechanical:

~~~text
initial blocked observation
→ alternate authoritative source
→ same-site alternate public entry
→ recovered? use recovered route
→ otherwise eligibility gate
   → 401: stop as AUTH_REQUIRED
   → 403: one blocked retry only if confirmed public + SESSION_OR_BOT_BLOCK
   → 429: wait/backoff first, then at most one blocked retry
→ after one blocked retry: stop rather than loop
~~~

This policy comes from the CCGP collection failure/recovery episode: the initial blocked
path did not establish source absence; alternate official sources and alternate CCGP public
announcement/attachment surfaces produced usable evidence before transport escalation was
justified.


Authentication is a property of a path or operation, not automatically of the underlying
information object.

Distinguish:

~~~text
PUBLIC_READ
PUBLIC_DOWNLOAD
AUTHENTICATED_TRANSACTION
RESTRICTED_ACCESS
~~~

A procurement system can simultaneously expose a public announcement, public query copies
of procurement documents, and an authenticated workflow for formal issuance or bid
submission.

For corpus construction, a public query or download copy may be sufficient when the
research object is the published document rather than proof of formal bidder issuance.

If repeated requests trigger WAF or rate limiting:

- persist the failure receipt;
- stop high-frequency acquisition;
- continue notice or metadata discovery if that surface remains public and stable;
- separate discovery from byte acquisition;
- resume later with a bounded lower-rate acquisition pass;
- prioritize already frozen primary-document candidates;
- keep recovery evidence append-oriented instead of rewriting the first failure.

The goal is reproducibility, not defeating a site's controls.

## 6. Freeze before semantic selection

Collection membership should be determined mechanically before inspecting the semantic
property the experiment intends to test.

Recommended sequence:

~~~text
define source frame
→ discover members
→ freeze member list
→ freeze attachment queue
→ acquire raw bytes
→ validate bytes
→ deduplicate mechanically
→ qualify corpus
→ label or evaluate
~~~

Mechanical discovery criteria may include fixed official categories, fixed date windows,
bounded page ranges, all notices returned by those pages, and all publicly exposed
attachment identifiers.

Avoid selecting members because they look likely to contain the desired positive,
negative, legal, risky, or model-relevant condition.

If an earlier experiment stopped because its old frozen corpus was too small, preserve
that historical stop. Build and freeze a new corpus, then create a new experiment identity
rather than rewriting the old experiment's membership threshold.

## 7. Preserve source and path provenance

For each discovery page, notice, and attachment capture, persist enough evidence to
reconstruct what happened.

Recommended receipt fields:

~~~yaml
requested_url:
final_url:
source_stratum:
listing_or_notice_id:
parent_notice_url:
attachment_id:
visible_filename:
retrieved_at:
http_status:
content_type:
content_disposition:
byte_length:
sha256:
object_path:
request_context:
  referer:
status:
error:
~~~

Treat content hashes as object identity rather than filenames.

Keep discovery evidence and raw bytes separate:

~~~text
metadata/
  source-universe.json
  notices/<id>/notice-response.json
  notices/<id>/attachment-queue.json
  notices/<id>/attachment-000.json

objects/
  <sha256>
~~~

This lets raw objects remain content-addressed while provenance remains queryable.

## 8. Validate bytes, not HTTP success

HTTP 200 is transport evidence, not file-validity evidence.

Validate the object format mechanically. Depending on expected formats:

- PDF: magic bytes and a valid terminal marker;
- ZIP or OOXML: archive structure;
- DOC or OLE: compound-document magic;
- RAR, 7z, or domain-specific containers: format signature;
- HTML, XML, or error pages returned under a document URL should be rejected as documents;
- compare Content-Length when provided;
- retain a failure receipt when validation fails.

Use the validated byte hash as the primary exact-duplicate identity.

## 9. Separate raw archive from qualification

A raw archive answers:

> What public source material did we actually acquire?

Qualification answers different questions:

- Is the document complete enough?
- Is it the intended semantic document type?
- Is the source group independent?
- Was it previously exposed to development or pilot work?
- Does it satisfy the target label or hard-negative family?
- Is authority-source binding sufficient?
- Is it eligible for the planned evaluation?

Keep states explicit:

~~~text
RAW_DISCOVERED
RAW_CAPTURED
RAW_CAPTURE_PARTIAL
RAW_VALIDATED
CANDIDATE_GROUP
QUALIFICATION_PENDING
ELIGIBLE
INELIGIBLE
~~~

A count of raw files is not a count of experimental samples.

## 10. Mechanical deduplication before judgment

Use deterministic signals first:

1. exact attachment SHA-256;
2. stable project or record identifier;
3. normalized re-procurement or reissue title;
4. canonical notice identifier;
5. explicit official supersession or reissue linkage.

Retain underlying records even when mechanically grouped. Grouping changes the candidate
count, not the historical evidence.

Cross-source exact-hash overlap is especially useful for distinguishing source diversity
from duplicated publication.

## 11. Failure evidence is part of the corpus

Persist successful captures, partial captures, missing public attachments, HTTP failures,
unsupported or malformed bytes, rate-limited objects, gated paths, and duplicate objects.

A failed member is evidence about source mechanics. It should not disappear because
another source later succeeds.

Use explicit gap status rather than filling failed slots ad hoc.

## 12. Offline verification

A release or freeze should be replayable without network access.

Offline verification should recompute, where applicable:

- source-universe identity;
- notice and attachment-queue binding;
- object hashes and byte lengths;
- format validation;
- exact-duplicate groups;
- aggregate counts;
- release receipt identity.

Replay should fail if raw bytes were altered, queue members disappeared, source-universe
membership changed, or a receipt no longer binds to the captured object.

## 13. Public-source exhaustion condition

Treat a source's relevant public route as exhausted after a bounded topology review has
covered the public surfaces material to the acquisition object, such as:

- listing or category surface;
- detail or notice surface;
- attachment or reference metadata;
- official direct public object or download route;
- relevant archive or alternate official publication surface;
- distinction between public read or download and authenticated transaction.

If the remaining routes require restricted authentication or access-control
circumvention, classify those routes as gated.

Prefer the narrow statement PUBLIC_PRIMARY_DOCUMENT_PATHS_EXHAUSTED over the broader and
usually unsupported SOURCE_UNAVAILABLE.

## 14. Recommended state machine

~~~text
DEFINE_TARGET
    ↓
DISCOVER_PRIMARY_SOURCE
    ↓
PATH_WORKS ───────────────→ FREEZE_DISCOVERY_FRAME
    │
    └─ PATH_BLOCKED or INSUFFICIENT
          ├─ Branch A: OTHER_AUTHORITATIVE_SOURCES
          └─ Branch B: SAME_SOURCE_PUBLIC_TOPOLOGY
                         ↓
                 PUBLIC_PATH_FOUND
                         ↓
                 FREEZE_DISCOVERY_FRAME
                         ↓
                 RAW_BYTE_ACQUISITION
                         ↓
                 BYTE_VALIDATION
                         ↓
                 MECHANICAL_DEDUP
                         ↓
                 RAW_ARCHIVE_FREEZE
                         ↓
                 OFFLINE_VERIFY
                         ↓
                 QUALIFICATION_HANDOFF
~~~

Branch A and Branch B may both succeed. Preserve both provenance strata.

## 15. Worked example: public procurement corpus

The workflow that motivated this skill followed this pattern.

### Initial failure

An initial China Government Procurement Network request returned a 403 with anti-bot
behavior. The first interpretation was too broad: CCGP is unavailable for raw procurement
documents.

That conclusion was later corrected.

### Branch A: another official source

The collection process explored the Haikou public-resource exchange and found openly linked
procurement and tender attachments. That branch produced a real raw archive with downloaded
bytes, hashes, explicit gaps, and offline verification.

The result became an independent provenance stratum rather than a temporary substitute.

### Branch B: the same source, different public surfaces

The CCGP site was revisited structurally.

Public announcement pages exposed attachment anchors whose bizDownload identifiers mapped
to public download objects. A normal public-browser request following the notice page to
the attachment endpoint could retrieve real PDF bytes even though the original route had
failed.

This established:

~~~text
blocked endpoint
≠ blocked source
≠ unavailable target object
~~~

Later sustained acquisition triggered WAF or rate limiting again. The pipeline therefore
split notice and attachment-queue discovery from raw-byte download: freeze discovery first,
retain failed receipts, then recover bounded primary-document candidates later.

The two branches together produced a stronger corpus than either source alone because they
added both availability resilience and provenance diversity.

## 16. Agent reporting contract

Report progress in evidence states rather than optimistic claims.

A useful status report includes:

- Acquisition target — exact object and unit of independence.
- Frozen discovery frame — source strata, date or page bounds, member count.
- Path findings — which surfaces worked, failed, or were gated.
- Raw acquisition — attempted, succeeded, failed, partial.
- Byte validation — valid objects by format and unique SHA-256 count.
- Candidate groups — mechanical upper bound before semantic qualification.
- Explicit gaps — missing, gated, rate-limited, or invalid records.
- Replay status — whether offline verification reproduces the freeze.
- Qualification boundary — what remains unreviewed.
- Next justified action — expand source universe, recover bytes, or begin qualification.

Keep the distinction between raw material acquired and evaluation-ready corpus explicit.
The downstream experiment begins after its own predeclared membership and qualification
contract is satisfied.
