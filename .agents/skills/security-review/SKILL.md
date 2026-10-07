---
name: security-review
description: Threat-model-aware review of changes touching security surfaces — external input, trust boundaries, secrets, SSRF/network, auth, tool/agent surfaces, deployment, error/log output. Findings are investigated, never suppressed.
---

# Security Review

**Trigger:** the change affects external input, a trust boundary, secrets,
SSRF/network, auth(z), tool/agent surfaces, deployment, or error/log output
([`docs/ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §8 list).

Distinct from `cyber-domain-review`: that skill owns IOC *semantic* correctness;
this skill owns *threat exposure*. Where they meet (SSRF via IP/URL), domain
review flags the range, security review owns the control.

## Inputs

- The diff.
- Threat model + threat IDs (T-AI-*, T-TOOL-*, T-NET-*): [`docs/SECURITY.md`](../../../docs/SECURITY.md) §6–§8.
- Security Definition of Done: [`docs/SECURITY.md`](../../../docs/SECURITY.md) §22.
- Existing posture to preserve: secure-failure error envelope, `SecretStr`,
  correlation-ID log-injection defense ([`M0`](../../../docs/milestones/M0_PRODUCTION_FOUNDATION.md) §4.4, §5; [`README.md`](../../../README.md) Security posture).

## Checklist

1. Map the change to the relevant threat IDs in [`SECURITY.md`](../../../docs/SECURITY.md).
2. External input validated at the boundary (typed, length-limited, allow-listed
   where appropriate — `T-TOOL-002`).
3. Errors fail safe: generic envelope, correlation id, no stack trace or internals
   leaked ([`M0`](../../../docs/milestones/M0_PRODUCTION_FOUNDATION.md) §4.4; [`SECURITY.md`](../../../docs/SECURITY.md) §11).
4. Secrets: none in code, logs, or committed `.env`; secret fields use `SecretStr`
   ([`SECURITY.md`](../../../docs/SECURITY.md) §10).
5. SSRF / network: private, loopback, link-local, and cloud-metadata ranges
   blocked where URLs/IPs flow outward; no unrestricted fetch (`T-NET-001`).
6. Each successful abuse case becomes a regression test
   ([`SECURITY.md`](../../../docs/SECURITY.md) §18).
7. If the change alters a trust boundary, update the relevant threat-model entry
   ([`SECURITY.md`](../../../docs/SECURITY.md) §20, §22).

## Investigate, do not suppress

- A Gitleaks / pip-audit / Trivy / CodeQL / Ruff-`S` finding is investigated and
  fixed at root cause.
- No blanket `# noqa: S*`, no scanner ignore/allowlist, no `ignore-unfixed`
  without a recorded, human-reviewed justification.
- A finding is treated as real until evidence proves it a false positive.

## Stopping conditions

- Security DoD §22 items satisfied → done.
- A HIGH-risk item ([`ENGINEERING_LOOP.md`](../../../docs/ENGINEERING_LOOP.md) §9)
  is flagged for the human gate; it is never self-approved.

## Must not

- Weaken or suppress a scanner or gate to pass.
- Approve its own change, or merge a HIGH-risk change.
- Add auth/crypto/identity beyond current scope.
- Assume a finding is a false positive without evidence.
