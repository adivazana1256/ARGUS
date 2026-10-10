# ARGUS — Engineering Loop

## 1. Purpose

ARGUS is developed using AI-assisted engineering, but AI coding tools are not
treated as autonomous engineering authorities.

The engineering process separates:

- specification
- architecture
- implementation
- testing
- review
- security review
- AI evaluation
- deployment approval

The goal is to maximize development velocity without sacrificing understanding,
security, maintainability or engineering quality.

---

## 2. Core Principle

> AI accelerates engineering. It does not replace engineering judgment.

No coding agent may define requirements, implement a change, approve that same
change and deploy it without independent gates.

---

## 3. Engineering Loop

Every meaningful feature follows:

Requirement
    |
    v
Specification
    |
    v
Architecture / ADR
    |
    v
GitHub Issue
    |
    v
Implementation Plan
    |
    v
Builder
    |
    v
Automated Tests
    |
    v
Independent Review
    |
    v
Security Review
    |
    v
AI Evaluation Gate
    |
    v
Human Review
    |
    v
Pull Request
    |
    v
CI
    |
    v
Staging
    |
    v
E2E / Smoke Tests
    |
    v
Human Approval
    |
    v
Production
    |
    v
Monitoring
    |
    v
Feedback / Next Iteration

Not every small change requires every stage.

Risk determines process depth.

---

## 4. Tool Responsibilities

### ChatGPT — Architecture and Engineering Review

Primary responsibilities:

- requirements refinement
- technology research
- system architecture
- architecture reviews
- ADR design
- threat modeling
- security review
- evaluation strategy
- failure analysis
- code review support
- interview-level explanations

ChatGPT should generally not be used as a blind bulk-code generator for ARGUS.

---

### Cursor — Interactive Development Environment

Primary responsibilities:

- focused implementation
- code navigation
- local edits
- small and medium refactors
- debugging with developer supervision
- test creation
- understanding unfamiliar code
- interactive development

Cursor is preferred when the developer wants tight control over individual changes.

---

### Claude Code — Repository-Level Builder

Primary responsibilities:

- implementation from approved specifications
- repository-wide changes
- larger refactors
- cross-file implementation
- test-suite expansion
- systematic migrations
- repository analysis
- debugging complex multi-file behavior

Claude Code must receive bounded tasks with:

- objective
- relevant architecture
- constraints
- acceptance criteria
- files/components in scope
- testing requirements

Claude Code must not receive vague instructions such as:

"Build ARGUS."

---

### GitHub — Engineering Source of Truth

GitHub will eventually own:

- issues
- branches
- pull requests
- CI
- security scans
- review history
- release history
- version tags

Documentation in the repository defines architectural intent.

---

## 5. Task Lifecycle

A normal implementation task follows:

### Step 1 — Requirement

Define the problem and expected outcome.

### Step 2 — Architecture Check

Determine whether the task:

- fits existing architecture
- requires an ADR
- changes a trust boundary
- changes an API contract
- changes data storage
- changes agent behavior
- affects evaluation

### Step 3 — Issue

Create a bounded issue.

Example:

ARG-042 — Implement IOC normalization

Acceptance criteria:

- detect supported IOC types
- normalize domains
- normalize URLs
- validate IPv4
- validate IPv6
- detect SHA256
- reject malformed values
- unit tests included
- malformed-input tests included
- no network calls
- structured logging where appropriate

### Step 4 — Implementation Plan

Before substantial implementation, the builder produces a concise plan.

The plan should identify:

- files to create/change
- interfaces affected
- tests required
- risks
- assumptions

For large changes, implementation begins only after plan review.

### Step 5 — Build

Cursor or Claude Code implements the approved scope.

### Step 6 — Automated Validation

Run relevant:

- formatting
- linting
- type checks
- unit tests
- integration tests
- security tests
- AI evaluation smoke tests

### Step 7 — Independent Review

Review for:

- correctness
- architecture compliance
- unnecessary complexity
- maintainability
- test quality
- failure handling
- observability

### Step 8 — Security Review

Required when the change affects:

- authentication
- authorization
- external input
- agents
- tools
- MCP
- RAG
- secrets
- external network access
- sensitive data
- deployment

### Step 9 — AI Evaluation

Required when the change can affect:

- retrieval
- prompts
- model selection
- agent behavior
- tool selection
- investigation verdicts
- context construction

### Step 10 — Human Gate

The developer reviews:

- diff
- test results
- security findings
- evaluation results
- unresolved risks

Only then may the change proceed.

---

## 6. Builder / Tester / Reviewer Separation

The engineering loop uses conceptual roles.

### Builder

Implements the requested change.

The Builder does not declare its own implementation approved.

### Tester

Attempts to prove the implementation incorrect.

Focus:

- expected behavior
- edge cases
- malformed inputs
- regression behavior
- failure paths

The Tester should not silently modify production code while testing.

### Reviewer

Evaluates:

- implementation quality
- architecture
- maintainability
- correctness
- unnecessary complexity

### Security Reviewer

Evaluates:

- threat-model impact
- authorization
- trust boundaries
- unsafe input/output handling
- secrets
- agent/tool abuse
- dependency risk

### Eval Reviewer

Evaluates AI-system behavior against defined datasets and metrics.

These roles may be performed by AI tools, automated systems or the developer,
but their responsibilities remain logically separated.

---

## 7. Bounded Repair Loop

When validation fails:

Implementation
    |
    v
Test / Review
    |
    v
Structured Failure Report
    |
    v
Builder Repair
    |
    v
Re-test

Autonomous repair loops must be bounded.

Initial policy:

MAX_AUTONOMOUS_REPAIR_ITERATIONS = 3

After three failed repair cycles:

- stop autonomous modification
- preserve failure evidence
- summarize attempted fixes
- escalate to human analysis

The limit may later be adjusted based on measured results.

---

## 8. Failure Report Format

Feedback to a builder should be structured.

Example:

Failure ID:
TEST-IOC-014

Category:
Input Validation

Expected:
Private IPv4 addresses rejected by external-fetch policy.

Actual:
10.0.0.5 accepted.

Evidence:
tests/security/test_ssrf.py::test_private_ipv4

Severity:
HIGH

Required outcome:
Private, loopback and link-local ranges must be rejected.

Do not prescribe an implementation unless necessary.

This allows the builder to reason about the fix while preserving test independence.

---

## 9. Risk-Based Development

Changes are classified:

### LOW

Examples:

- documentation
- comments
- non-functional UI copy

Process may be lightweight.

### MEDIUM

Examples:

- normal API feature
- database query
- non-security business logic

Requires tests and review.

### HIGH

Examples:

- authentication
- authorization
- agent orchestration
- MCP
- RAG ingestion
- tool execution
- external URL fetching
- secrets
- deployment
- security policy

Requires:

- tests
- independent review
- security review
- relevant evaluation
- explicit human gate

---

## 10. Definition of Done

A normal engineering task is complete only when applicable requirements are met:

- acceptance criteria satisfied
- architecture respected
- code understandable
- tests pass
- failure paths considered
- security controls implemented
- logs/metrics added where justified
- documentation updated
- relevant evals pass
- diff reviewed
- CI passes

"Claude Code finished successfully" is not a Definition of Done.

"Cursor reports no errors" is not a Definition of Done.

---

## 11. Git Workflow

Planned workflow:

main
  |
  +-- feature/arg-xxx-description
  |
  +-- fix/arg-xxx-description
  |
  +-- docs/arg-xxx-description

Rules:

- no feature development directly on main
- one bounded concern per branch where practical
- meaningful commit messages
- pull request before merge
- CI required before merge
- protected main branch once remote repository exists

### 11.1 Release automation conventions

These make the push→PR→green cycle automatable while keeping the merge human-only.
They are the canonical statement of the rules `AGENTS.md` points to.

- **PR base is explicitly `main`.** Never rely on the default base. Create with an
  explicit base (`gh pr create --base main …`).
- **Verify the base after creation.** Confirm the opened PR actually targets `main`
  (`gh pr view --json baseRefName`) before treating it as ready. A wrong base is a
  material blocker — stop and report.
- **Monitor the required checks.** Watch the required CI (`ci.yml`) and security
  (`security.yml`, `codeql.yml`) checks to completion (`gh pr checks --watch`).
- **Repair within the bounded loop.** A failing required check is a structured
  failure (§8) repaired under `MAX_AUTONOMOUS_REPAIR_ITERATIONS = 3` (§7). After the
  bound, stop, preserve evidence, escalate.
- **Stop at a fully green PR.** "Green and merge-ready" is the terminal state for
  autonomous work. Do not proceed past it.
- **Merge is human-only.** No `gh pr merge`, no auto-merge, no base-branch change to
  bypass review. The human performs the merge.

---

## 12. Pull Request Requirements

A meaningful PR should explain:

- What changed?
- Why?
- How was it implemented?
- How was it tested?
- Security impact?
- AI/evaluation impact?
- Architecture impact?
- Known limitations?

Large AI-generated changes must not be merged without diff review.

---

## 13. CI Quality Gates

The CI pipeline will evolve toward:

Pull Request
    |
    v
Formatting
    |
    v
Lint
    |
    v
Type Check
    |
    v
Unit Tests
    |
    v
Integration Tests
    |
    v
Security Tests
    |
    v
Dependency Scan
    |
    v
Secret Scan
    |
    v
AI Eval Smoke Suite
    |
    v
Docker Build
    |
    v
Container Scan

Not all gates need to exist on day one.

They will be introduced as the relevant system capabilities are built.

---

## 14. AI Evaluation Gate

Changes to AI behavior should be compared against a baseline.

Example:

Baseline:
retrieval_recall_at_5 = 0.84
verdict_accuracy = 0.81
unsupported_claim_rate = 0.07
average_cost = $0.12

Candidate:
retrieval_recall_at_5 = 0.89
verdict_accuracy = 0.84
unsupported_claim_rate = 0.04
average_cost = $0.11

A change should not be considered better merely because its output looks better
in one manually selected example.

---

## 15. Prompt Changes Are Code Changes

Prompts will be version controlled.

A meaningful prompt change requires:

- reason for change
- version change
- relevant eval execution
- regression comparison
- review

Prompt behavior must not be modified silently in production.

---

## 16. Architecture Decision Records

Important technical decisions use ADRs.

Examples:

- orchestration framework
- vector storage
- model gateway design
- MCP architecture
- asynchronous job system
- observability platform
- cloud deployment strategy

ADR lifecycle:

PROPOSED
→ ACCEPTED
→ SUPERSEDED

An ADR should document:

- context
- options
- decision
- rationale
- trade-offs
- consequences

---

## 17. AI-Generated Code Policy

AI-generated code is allowed and expected.

However:

- generated code must be understood before merge
- unexplained dependencies should not be accepted
- architecture must not drift because an agent preferred another pattern
- generated tests must themselves be reviewed
- security-sensitive generated code receives extra scrutiny
- unnecessary abstractions should be removed

The developer must be capable of explaining important production code in an interview.

---

## 18. Development Feedback Loop

After deployment:

Observe
    |
    v
Measure
    |
    v
Detect Failure / Opportunity
    |
    v
Create Issue
    |
    v
Implement
    |
    v
Evaluate
    |
    v
Deploy
    |
    +------> Observe

Production behavior eventually becomes an input into engineering decisions.

---

## 19. Engineering Metrics

Potential future metrics:

- CI pass rate
- escaped defect rate
- security findings
- test coverage
- mean repair iterations
- AI-generated change rejection rate
- PR lead time
- rollback frequency
- evaluation regressions
- cost regressions

Metrics are used for improvement, not vanity.

---

## 20. Developer Understanding Gate

Before a major component is considered complete, the developer should be able to explain:

1. What problem does it solve?
2. Why does it exist?
3. Why was this implementation selected?
4. What alternatives were considered?
5. How can it fail?
6. How is it secured?
7. How is it tested?
8. How is it observed?
9. What would need to change at larger scale?

If these cannot be answered, the feature is not considered portfolio-ready.

---

## 21. Engineering Loop Success Criteria

The ARGUS engineering process succeeds when AI tools increase development speed
while the repository remains:

- understandable
- testable
- secure
- reviewable
- measurable
- maintainable
- explainable by the developer

The objective is not maximum AI autonomy.

The objective is maximum engineering leverage with controlled risk.
