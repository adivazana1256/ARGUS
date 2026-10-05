# ARGUS — AI Evaluation Strategy

## 1. Purpose

ARGUS must not evaluate AI behavior using subjective impressions alone.

The evaluation system exists to measure whether changes to retrieval, agents,
prompts, models, tools and workflows actually improve investigation quality.

Core principle:

> AI changes are engineering changes and must be measurable.

---

## 2. Evaluation Layers

ARGUS evaluates the system at multiple independent layers:

1. Deterministic behavior
2. Retrieval quality
3. Tool-use quality
4. Agent workflow quality
5. Investigation quality
6. Security behavior
7. Production performance

This separation helps identify where a failure originates.

---

## 3. Evaluation Dataset

ARGUS will maintain versioned evaluation datasets.

Initial scenario categories:

- benign domain
- malicious domain
- suspicious domain
- benign IP
- malicious IP
- ambiguous IP
- benign URL
- phishing URL
- suspicious URL
- known malicious SHA256
- unknown SHA256
- incomplete alert
- conflicting evidence
- insufficient evidence
- false-positive scenario
- prompt-injection attempt
- malicious retrieved content
- tool failure
- external-service timeout

Each evaluation case may contain:

- case_id
- input
- input_type
- expected evidence
- expected relevant sources
- expected tool behavior
- expected verdict
- acceptable verdicts
- expected ATT&CK mappings
- prohibited claims
- security expectations
- notes

Datasets must have explicit versions.

---

## 4. Deterministic Evaluation

Traditional tests cover deterministic behavior.

Examples:

- IOC detection
- IOC normalization
- schema validation
- state transitions
- authorization
- rate limits
- retry limits
- SSRF protection
- evidence storage
- tool policy enforcement

These tests should be deterministic and repeatable.

---

## 5. Retrieval Evaluation

RAG quality is evaluated independently from final LLM output.

Primary metrics:

### Recall@K

Measures whether relevant knowledge appears in the top K retrieved chunks.

### Precision@K

Measures how much retrieved context is actually relevant.

### MRR

Measures how highly the first relevant result is ranked.

Additional measurements:

- retrieval latency
- duplicate retrieval rate
- source diversity
- metadata-filter correctness
- citation availability

Example targets will be established only after a baseline is measured.

---

## 6. Tool-Use Evaluation

Agent tool behavior should be measurable.

Metrics:

- correct tool selection rate
- tool-call success rate
- invalid argument rate
- unnecessary tool-call rate
- duplicate tool-call rate
- tool timeout rate
- unauthorized tool-request rate
- average tool calls per investigation

The objective is not maximum tool usage.

The objective is sufficient evidence with efficient tool usage.

---

## 7. Agent Workflow Evaluation

Agentic behavior is evaluated for:

- investigation completion
- correct next-action selection
- missing-evidence identification
- retry behavior
- stopping behavior
- human-escalation correctness
- loop efficiency
- failure recovery

Potential metrics:

- workflow completion rate
- average investigation steps
- unnecessary-step rate
- successful recovery rate
- correct escalation rate
- max-iteration termination rate

---

## 8. Investigation Quality

Final investigations are evaluated for:

### Verdict Quality

Does the final classification match the expected outcome?

### Groundedness

Are material claims supported by collected evidence?

### Citation Correctness

Do cited evidence objects actually support the associated claims?

### Completeness

Were important facts required for the investigation included?

### Contradictory Evidence Handling

Did the system identify and represent meaningful evidence against its conclusion?

### Uncertainty Calibration

Does confidence appropriately reflect evidence quality and ambiguity?

---

## 9. Unsupported Claim Evaluation

ARGUS explicitly measures unsupported claims.

A material claim is unsupported when:

- no evidence ID supports it
- the cited evidence does not support it
- the claim exceeds what the evidence establishes

Target direction:

unsupported_claim_rate → lower

A fluent answer with unsupported claims is considered a failure.

---

## 10. Security Evaluation

AI security evaluation includes adversarial scenarios.

Categories:

- direct prompt injection
- indirect prompt injection
- RAG poisoning
- malicious retrieved documents
- unauthorized tool requests
- malformed tool arguments
- tool-output injection
- goal manipulation
- excessive agency
- cost amplification

Potential metrics:

- attack success rate
- unauthorized action prevention rate
- policy violation rate
- malicious instruction compliance rate
- guardrail activation rate

Successful attacks should become regression cases.

---

## 11. Failure Injection

ARGUS should intentionally test infrastructure and dependency failures.

Examples:

- threat-intelligence API timeout
- model timeout
- model malformed output
- MCP server unavailable
- database unavailable
- retrieval returns no results
- retrieval returns conflicting results
- rate limit reached

The system should fail predictably and preserve useful diagnostic information.

---

## 12. Performance and Cost

Production-oriented evaluation includes:

- end-to-end latency
- p50 latency
- p95 latency
- model latency
- retrieval latency
- tool latency
- token usage
- estimated model cost
- average cost per investigation
- error rate

Quality improvements must be evaluated alongside cost and latency.

---

## 13. Evaluation Run Metadata

Every meaningful evaluation run should eventually record:

- evaluation_run_id
- timestamp
- dataset_version
- application_version
- workflow_version
- prompt_version
- model_name
- model_version where available
- embedding_model
- retrieval_version
- knowledge_base_version
- tool_versions
- configuration
- metrics

This enables reproducible comparisons.

---

## 14. Regression Evaluation

Before:

- changing prompts
- changing models
- changing orchestration
- changing retrieval
- changing chunking
- changing embeddings
- changing tool-selection behavior

ARGUS should run the relevant baseline evaluation.

After the change, the same dataset is rerun.

Compare:

Baseline
vs
Candidate

A candidate should not be promoted based on one impressive example.

---

## 15. Evaluation Gates

Future CI may contain two evaluation levels.

### Pull Request Smoke Eval

Small and inexpensive.

Purpose:

- detect major regressions
- validate structured outputs
- verify basic tool behavior
- test critical adversarial cases

### Full Evaluation

Larger suite executed:

- before release
- on major AI architecture changes
- on model changes
- on retrieval changes

Full evaluations may be scheduled or manually approved due to cost.

---

## 16. Human Evaluation

Not all investigation quality can initially be captured automatically.

Human review may score:

- correctness
- evidence quality
- usefulness
- clarity
- uncertainty handling
- security analyst usefulness

Human evaluation criteria should use a defined rubric.

---

## 17. Evaluation Failure Analysis

A failed investigation should be classified.

Potential failure categories:

- INPUT_FAILURE
- RETRIEVAL_FAILURE
- TOOL_SELECTION_FAILURE
- TOOL_EXECUTION_FAILURE
- ORCHESTRATION_FAILURE
- REASONING_FAILURE
- GROUNDING_FAILURE
- CITATION_FAILURE
- SECURITY_FAILURE
- INFRASTRUCTURE_FAILURE

This prevents treating every bad result as "the LLM was wrong."

---

## 18. Evaluation-Driven Development

The desired improvement loop is:

Observe Failure
    |
    v
Classify Failure
    |
    v
Create Reproducible Eval Case
    |
    v
Change System
    |
    v
Run Evaluation
    |
    v
Compare Against Baseline
    |
    v
Accept or Reject Change

Evaluation therefore becomes part of development, not only final testing.

---

## 19. Initial Evaluation Scope

ARGUS will not begin with hundreds of AI evaluation cases.

Evaluation will grow with system capability.

Initial progression:

M1:
- deterministic IOC tests

M2:
- threat-intelligence integration tests
- evidence normalization tests

M3:
- tool-selection cases
- agent workflow cases

M4:
- retrieval benchmark
- citation tests

M5:
- AI security adversarial suite

M6:
- dedicated evaluation platform
- larger gold dataset
- regression dashboards

---

## 20. Evaluation Success Criteria

The evaluation system succeeds when ARGUS can answer:

- Did the new version improve investigation quality?
- Did retrieval improve?
- Did hallucinations decrease?
- Did tool selection improve?
- Did security regress?
- Did latency change?
- Did cost change?
- Which component caused a failure?

The goal is not to prove that ARGUS is perfect.

The goal is to make AI quality measurable, reproducible and improvable.
