# ARGUS Agent Orchestration Architecture Spike

## Objective

Compare LangGraph and OpenAI Agents SDK as the orchestration framework for
ARGUS using equivalent, reproducible investigation workflows.

This spike does not implement production ARGUS.

Its purpose is to produce engineering evidence for ADR-002.

## Core Rule

Both implementations must solve the same problem using the same shared domain
models, mock tools, scenarios and acceptance criteria.

Framework-specific capabilities may be used, but the underlying investigation
semantics must remain equivalent.

## Investigation Scenario

Input:

A suspicious domain IOC.

Example:

suspicious-example.test

The investigation must:

1. create typed investigation state
2. validate the IOC
3. create an investigation plan
4. request threat-intelligence evidence
5. pass the tool request through a deterministic policy layer
6. execute a deterministic mock threat-intelligence tool
7. store normalized evidence
8. evaluate whether evidence is sufficient
9. request additional evidence when required
10. challenge the current hypothesis
11. produce a structured verdict
12. terminate using explicit stopping conditions

## Shared Domain Components

The following must be framework-independent where practical:

- InvestigationState
- Evidence
- ToolRequest
- ToolResult
- InvestigationPlan
- VerificationResult
- Verdict
- ToolPolicy
- mock threat-intelligence tools
- test scenarios

Use typed Python models.

Do not duplicate domain behavior merely to accommodate a framework.

## Required Scenarios

Both implementations must pass equivalent scenarios.

### Scenario 1 — Normal Investigation

Mock evidence is returned successfully.

Expected:

- investigation completes
- evidence is stored
- verification executes
- structured verdict produced

### Scenario 2 — Insufficient Evidence

First tool response is insufficient.

Expected:

- workflow identifies missing evidence
- another investigation step occurs
- investigation remains bounded
- final result records uncertainty

### Scenario 3 — Tool Failure

Mock tool fails on the first attempt.

Expected:

- failure is visible
- bounded retry behavior occurs
- investigation does not crash silently

### Scenario 4 — Maximum Iterations

Evidence never becomes sufficient.

Expected:

- workflow terminates at configured maximum
- no infinite loop
- termination reason recorded

### Scenario 5 — Human Approval

A mock tool is classified as approval-required.

Expected:

- execution pauses before tool execution
- approval request is observable
- workflow can resume after approval
- rejection is handled safely

### Scenario 6 — Unauthorized Tool

Agent requests a tool outside its permissions.

Expected:

- deterministic policy blocks execution
- model cannot override policy
- security event is observable

## Deterministic Security Boundary

The orchestration framework must not own authorization policy.

Required execution flow:

Agent proposes ToolRequest
        |
        v
Schema Validation
        |
        v
ToolPolicy
        |
        +-- DENY --> Record denial
        |
        +-- APPROVAL_REQUIRED --> Pause
        |
        +-- ALLOW --> Execute
                            |
                            v
                     Normalize Evidence

ToolPolicy must be normal application code.

Do not implement authorization through prompt instructions alone.

## Bounded Execution

Configure explicit limits.

Initial spike values:

MAX_INVESTIGATION_ITERATIONS = 3
MAX_TOOL_RETRIES = 2

These values exist for comparison and may change later.

## Model Usage

Keep model dependency minimal.

Prefer deterministic or stubbed behavior where possible so framework behavior
can be tested without confusing orchestration results with model variability.

If a real model is required for a framework capability, isolate that dependency
and document why.

Do not require paid model calls for the core automated test suite.

## MCP

Do not build the production ARGUS MCP server during this spike.

Instead evaluate and document:

- how MCP would integrate
- tool discovery behavior
- tool filtering
- approval capabilities
- security implications
- additional framework coupling

A minimal MCP experiment may be created only if required to validate an
important architectural difference.

## Observability

Each implementation must make it possible to observe:

- investigation ID
- current step/state
- state transitions
- tool requests
- tool results
- retries
- approval interruptions
- policy denials
- final termination reason

Do not log secrets or hidden chain-of-thought.

## Testing Requirements

Use pytest.

Shared tests should be used where possible.

Required coverage includes:

- normal completion
- insufficient evidence
- tool failure
- retry exhaustion
- maximum iterations
- approval pause
- approval resume
- approval rejection
- unauthorized tool denial
- structured output validation

Tests must not depend on external threat-intelligence services.

## Comparison Evidence

For each framework record:

- implementation structure
- framework-specific abstractions
- orchestration LOC
- state-management approach
- HITL implementation
- retry implementation
- testing ergonomics
- traceability
- MCP integration approach
- provider coupling
- debugging experience
- major strengths
- major weaknesses

Do not manipulate implementation style merely to make one framework appear
better.

## Repository Structure

Target:

spikes/orchestration/
├── SPEC.md
├── README.md
├── RESULTS.md
├── shared/
│   ├── models.py
│   ├── tools.py
│   ├── policy.py
│   └── scenarios.py
├── langgraph/
│   └── ...
├── openai_agents/
│   └── ...
└── tests/
    └── ...

The builder may propose small structural changes before implementation if they
improve fairness or testability.

## Builder Workflow

The builder must NOT immediately implement the spike.

First:

1. Read:
   - docs/PRODUCT_SPEC.md
   - docs/ARCHITECTURE.md
   - docs/SECURITY.md
   - docs/ENGINEERING_LOOP.md
   - docs/EVALUATION.md
   - docs/adr/002-agent-orchestration-framework.md
   - this SPEC.md

2. Inspect repository state.

3. Produce an implementation plan.

4. Identify assumptions and architectural risks.

5. Stop and wait for human approval.

Only after approval may implementation begin.

## Definition of Done

The spike is complete only when:

- both frameworks implement equivalent scenarios
- tests pass
- security-policy separation is preserved
- bounded execution is demonstrated
- HITL behavior is demonstrated
- failures are observable
- RESULTS.md contains measured comparison evidence
- ADR-002 can be updated using observed evidence

The builder must not select the winning framework.

The final architecture decision belongs to the ADR review process.
