---
name: cyber-domain-review
description: Review cyber-domain code (IOC detection, normalization, validation, evidence, deterministic risk triage) for semantic correctness, false positives/negatives, normalization invariants, provenance, and determinism. Captures edge cases as regression and eval cases.
---

# Cyber Domain Review

**Trigger:** any change to IOC type detection, normalization, validation, the
evidence model, or deterministic risk triage
([`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) §3, §7).

**Goal:** catch semantic errors a passing happy-path test hides. Correctness
here is about *meaning*, not just "the function returned". No existing doc owns
this — this skill does.

## Inputs

- The diff.
- Acceptance-criteria shape for IOC work: [`docs/ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §3 (ARG-042).
- Domain/provenance model: [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) §3, §7, §11.
- Eval scenario categories + unsupported-claim rules: [`docs/EVALUATION.md`](../../../docs/EVALUATION.md) §3, §4, §9.
- SSRF-adjacent ranges (cross-ref `security-review`): [`docs/SECURITY.md`](../../../docs/SECURITY.md) §8, `T-TOOL-002`.

## Semantic edge cases — enumerate per type touched

**IPv4:** leading-zero / octal / hex / decimal forms; `0.0.0.0`, broadcast;
private, loopback, link-local, CGNAT (`100.64/10`); cloud-metadata
`169.254.169.254` (SSRF — flag to `security-review`).

**IPv6:** `::` zero-compression; zone id (`%eth0`); IPv4-mapped (`::ffff:1.2.3.4`);
bracketed URL host form; upper/lower canonicalization.

**Domains:** IDN / punycode + homoglyphs; trailing-dot FQDN; case-fold;
mixed-script; overlong labels / >253 total; `localhost`; registrable domain
(PSL) vs subdomain.

**URLs:** scheme allow-listing; userinfo `@` host confusion; percent-encoding;
host/path ambiguity; defanged input (`hxxp://`, `[.]`, `(dot)`) normalization;
embedded-IP host.

**SHA-256:** exactly 64 hex; case-insensitive; reject MD5 (32) / SHA-1 (40) and
near-misses (63/65 chars, non-hex).

## Normalization invariants

- **Deterministic:** same input → identical output on every run; no locale,
  wall-clock, randomness, or dict-ordering dependence.
- **Idempotent:** `normalize(normalize(x)) == normalize(x)`.
- **Canonical form documented:** one defined output shape per type.
- **Total + explicit:** malformed input is rejected explicitly, never silently
  coerced or passed through.

## False positives / negatives

For each IOC type the change touches, confirm tests cover **both**:
- a **false positive** candidate — looks valid, must be rejected;
- a **false negative** candidate — valid but unusual, must be accepted.
Feed these into the eval dataset ([`EVALUATION.md`](../../../docs/EVALUATION.md) §3).

## Provenance

- Raw external value and normalized value stay distinct
  ([`ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) §7).
- No AI-asserted value silently becomes evidence (`T-AI-004`,
  [`SECURITY.md`](../../../docs/SECURITY.md) §6).
- Evidence carries source / trust / reference fields where the model defines them.

## Stopping conditions

- Every IOC type touched has FP + FN coverage **and** determinism/idempotency
  assertions → done.
- Unresolved semantic ambiguity (e.g. "is this edge case valid?") → stop and
  escalate the specific case to the human; do not guess a rule.

## Must not

- Invent threat-intel, enrichment, or reputation behavior (out of M1 scope).
- Introduce any network lookup or external call.
- Accept a happy-path pass as sufficient.
- Let an LLM judgment stand in for a deterministic rule.
