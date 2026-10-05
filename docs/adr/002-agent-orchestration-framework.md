# ADR-002 — Agent Orchestration Framework

- Status: Proposed
- Date: 2026-10-05

## Context

ARGUS requires an orchestration layer for bounded, evidence-driven cyber
investigations.

The orchestration layer must support:

- explicit investigation state
- multi-step workflows
- specialized agents
- tool calling
- branching
- bounded loops
- retries and failure handling
- human-in-the-loop interruption
- pause and resume
- structured outputs
- MCP integration
- observability
- testing
- evaluation
- security controls

Because orchestration is a core architectural dependency, ARGUS will not select
a framework based only on popularity or developer familiarity.

## Candidates

The initial architecture spike compares:

1. LangGraph
2. OpenAI Agents SDK

## Spike Principle

Both candidates must implement the same conceptual investigation workflow.

Input
  |
  v
Create Investigation State
  |
  v
Plan
  |
  v
Select Tool
  |
  v
Policy Check
  |
  v
Execute Mock Threat-Intel Tool
  |
  v
Store Evidence
  |
  v
Verify Evidence
  |
  v
Enough Evidence?
  |           |
  NO          YES
  |           |
  +--> Loop   +--> Verdict

The spike must also exercise:

- tool failure
- retry
- maximum-iteration termination
- structured state
- human approval interruption
- resume after approval
- traceability

Real threat-intelligence APIs are not required for this spike.

Mock deterministic tools should be used so framework behavior can be compared
without model or external-service noise.

## Evaluation Criteria

Each candidate will be evaluated using the same criteria.

### 1. Workflow Explicitness

Can an engineer understand the investigation flow from the code?

Questions:

- Are transitions visible?
- Are loops explicit?
- Are stopping conditions obvious?
- Can invalid transitions be prevented?

### 2. State Management

Evaluate:

- typed state
- state persistence
- pause/resume
- investigation recovery
- state inspection
- reproducibility

### 3. Human-in-the-Loop

Evaluate:

- interruption model
- approval requests
- persistence while paused
- resume behavior
- developer complexity

### 4. Tool Control

Evaluate:

- typed tool arguments
- tool validation
- authorization hooks
- tool filtering
- approval before execution
- failure handling

### 5. Failure Handling

Evaluate:

- retries
- timeouts
- malformed model output
- tool failure
- maximum iterations
- recovery behavior

### 6. MCP

Evaluate:

- MCP client integration
- tool discovery
- tool filtering
- approval controls
- security boundaries
- implementation complexity

### 7. Observability

Evaluate:

- traces
- agent visibility
- tool-call visibility
- state-transition visibility
- custom telemetry integration
- OpenTelemetry compatibility

### 8. Testing

Evaluate:

- unit-test ergonomics
- deterministic workflow testing
- mockability
- state-transition testing
- tool testing
- regression testing

### 9. Evaluation Integration

Evaluate how easily ARGUS can record:

- model version
- prompt version
- workflow version
- tool calls
- investigation steps
- tokens
- latency
- cost
- final verdict

### 10. Provider Portability

Evaluate:

- dependency on one model provider
- custom model support
- ability to route models
- impact on ARGUS Model Gateway

### 11. Framework Complexity

Evaluate:

- amount of framework-specific code
- hidden behavior
- learning curve
- debugging complexity
- architectural lock-in

### 12. Security Fit

Evaluate whether deterministic ARGUS security controls can remain outside model
authority.

The framework must not force authorization decisions into prompts.

## Scoring

Each category will receive a score from 1 to 5.

1 = poor fit
2 = significant limitations
3 = acceptable
4 = strong
5 = excellent

Scores alone do not determine the winner.

Security, workflow control and maintainability may outweigh total score.

## Required Evidence

The final ADR decision must reference observed behavior from both prototypes.

Examples:

- implementation complexity
- lines of orchestration code
- number of framework-specific abstractions
- test complexity
- pause/resume behavior
- retry behavior
- trace quality
- MCP integration experience

## Decision

Not yet decided.

The ADR remains PROPOSED until both architecture-spike implementations have
been evaluated.

## Expected Outcome

ARGUS will select the framework that provides the best balance of:

- explicit control
- security
- testability
- observability
- maintainability
- agent capability

The objective is not to select the framework with the most features.

The objective is to select the framework that best supports controlled,
evidence-driven cyber investigations.
