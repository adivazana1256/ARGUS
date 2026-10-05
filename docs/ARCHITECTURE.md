# ARGUS — System Architecture

## 1. Architecture Goals

ARGUS is designed as a production-oriented, evidence-driven cyber investigation platform.

The architecture must support:

- Deterministic security logic
- Agentic AI orchestration
- Multi-step investigations
- Secure tool execution
- Retrieval-Augmented Generation
- Evidence provenance
- Human-in-the-loop controls
- AI evaluation
- Observability
- Horizontal evolution toward production deployment

The architecture follows one central rule:

> AI may reason about evidence, but evidence and deterministic controls govern system behavior.

---

## 2. High-Level Architecture

User / Analyst
    |
    v
Web Application
    |
    v
FastAPI API Layer
    |
    v
Investigation Service
    |
    +-----------------------------+
    |                             |
    v                             v
Deterministic Core          AI Orchestration Layer
    |                             |
    |                       Investigation State
    |                             |
    |                  +----------+----------+
    |                  |          |          |
    |                  v          v          v
    |              Threat      Knowledge   Correlation
    |              Intel        Agent       Agent
    |              Agent
    |                  \          |          /
    |                   \         |         /
    |                    +--------+--------+
    |                             |
    |                             v
    |                      Verification Agent
    |                             |
    +-----------------------------+
                  |
                  v
            Evidence Layer
                  |
       +----------+-----------+
       |                      |
       v                      v
Security Tools             RAG System
       |                      |
       v                      v
MCP / APIs             PostgreSQL + pgvector
       |                      |
       +----------+-----------+
                  |
                  v
          Investigation Result
                  |
                  v
         Human Approval Gate
                  |
                  v
       Evidence-backed Report


Cross-cutting concerns:

- Authentication / Authorization
- Audit Logging
- Guardrails
- Rate Limiting
- Secrets Management
- Observability
- Evaluation
- Cost / Token Tracking

---

## 3. Deterministic Core

Not every decision belongs to an LLM.

The deterministic core is responsible for behavior that should be predictable and testable.

Initial responsibilities:

- IOC type detection
- IOC normalization
- Input validation
- Schema validation
- Investigation state transitions
- Tool permission enforcement
- Rate limiting
- Retry limits
- Maximum investigation iterations
- Cost / token budgets
- Confidence thresholds
- Human-approval rules
- Audit event creation

Example:

An LLM may propose calling a threat-intelligence tool.

The deterministic core decides whether that tool call is:

1. structurally valid
2. authorized
3. within investigation limits
4. safe to execute
5. subject to human approval

---

## 4. Investigation Service

The Investigation Service owns the lifecycle of an investigation.

Initial states may include:

CREATED
VALIDATING
TRIAGING
PLANNING
COLLECTING_EVIDENCE
RETRIEVING_KNOWLEDGE
CORRELATING
VERIFYING
WAITING_FOR_HUMAN
COMPLETED
FAILED
CANCELLED

State transitions must be explicit and auditable.

The service should not depend directly on a specific LLM provider.

---

## 5. AI Orchestration Layer

The AI orchestration layer manages reasoning-oriented investigation workflows.

Expected capabilities:

- Investigation planning
- Agent state
- Tool selection
- Multi-step workflows
- Parallelizable investigation tasks
- Retry / fallback behavior
- Missing-evidence analysis
- Human-in-the-loop interruption
- Bounded investigation loops
- Final synthesis

Candidate orchestration technologies:

- LangGraph
- OpenAI Agents SDK

A dedicated architecture spike will compare them before the final orchestration framework is selected.

Selection criteria:

- Explicit workflow control
- State management
- Failure handling
- Human-in-the-loop support
- MCP integration
- Observability
- Testing
- Model/provider portability
- Maintainability
- Framework lock-in

The decision will be documented as an Architecture Decision Record.

---

## 6. Initial Agent Responsibilities

### Investigator / Orchestrator

Responsibilities:

- understand the investigation objective
- maintain investigation context
- identify required evidence
- select the next investigation step
- stop when explicit completion conditions are satisfied

### Threat Intelligence Agent

Responsibilities:

- select appropriate threat-intelligence tools
- request IOC enrichment
- interpret normalized tool results
- identify additional intelligence requirements

### Knowledge Agent

Responsibilities:

- formulate retrieval queries
- apply relevant metadata constraints
- retrieve security knowledge
- provide source-backed context

### Correlation Agent

Responsibilities:

- correlate structured evidence
- identify relationships
- map relevant ATT&CK techniques where justified
- generate evidence-supported hypotheses

### Verification Agent

Responsibilities:

- challenge current hypotheses
- search for contradictory evidence
- identify unsupported claims
- detect missing evidence
- reduce premature high-confidence verdicts

Agent boundaries may be changed if evaluation demonstrates that a simpler architecture performs better.

---

## 7. Evidence Model

Evidence is a first-class domain object.

Every important finding should be connected to evidence.

Conceptual Evidence object:

- evidence_id
- investigation_id
- evidence_type
- source
- source_reference
- collected_at
- raw_reference
- normalized_value
- confidence
- trust_level
- metadata
- tool_run_id

The system should distinguish between:

- raw external data
- normalized evidence
- retrieved knowledge
- AI-generated hypotheses
- verified findings

AI-generated text must never silently become factual evidence.

---

## 8. Security Tool Layer

Security tools are exposed through controlled interfaces.

Examples:

- domain lookup
- IP lookup
- DNS enrichment
- file-hash lookup
- CVE lookup
- MITRE ATT&CK lookup
- security knowledge search

Agents must not receive unrestricted operating-system or network access.

Tool execution path:

Agent Proposal
    |
    v
Schema Validation
    |
    v
Authorization / Policy
    |
    v
Rate / Budget Check
    |
    v
Optional Human Approval
    |
    v
Tool Execution
    |
    v
Output Validation
    |
    v
Evidence Normalization
    |
    v
Audit Log

---

## 9. MCP Architecture

ARGUS intends to expose selected security capabilities through an MCP server.

Conceptual flow:

AI Orchestrator
    |
    v
MCP Client
    |
    v
ARGUS Security MCP Server
    |
    +-- lookup_domain
    +-- lookup_ip
    +-- lookup_hash
    +-- lookup_cve
    +-- lookup_mitre
    +-- search_security_knowledge

MCP is not used only for portfolio visibility.

It must provide real architectural value:

- standardized tool interfaces
- tool discovery
- schema-defined inputs
- permission boundaries
- interoperability
- auditable execution

Security controls will be applied around MCP tool execution.

---

## 10. RAG Architecture

The RAG subsystem has two primary flows.

### Ingestion

Trusted / Approved Sources
    |
    v
Fetch / Import
    |
    v
Parse
    |
    v
Normalize
    |
    v
Chunk
    |
    v
Metadata Enrichment
    |
    v
Embedding
    |
    v
PostgreSQL / pgvector

### Retrieval

Investigation Context
    |
    v
Query Construction
    |
    v
Metadata Filtering
    |
    v
Vector Retrieval
    |
    v
Optional Hybrid Retrieval
    |
    v
Optional Reranking
    |
    v
Context Selection
    |
    v
Source-backed Context

Retrieval quality must be evaluated independently from final answer quality.

---

## 11. Knowledge Provenance

Every ingested document should retain provenance where available:

- source
- source URL / identifier
- document type
- license / usage information
- published date
- ingestion date
- document version / hash
- chunk identifier
- trust classification

Retrieved text is treated as untrusted content even when the source itself is trusted.

---

## 12. Data Layer

### PostgreSQL

Primary operational database.

Expected entities include:

- users
- investigations
- investigation_events
- entities / IOCs
- evidence
- findings
- tool_runs
- agent_runs
- reports
- approvals
- audit_events
- knowledge_documents
- knowledge_chunks
- evaluation_runs

### pgvector

Initial vector-search implementation.

Reasons:

- integrates with PostgreSQL
- supports metadata-driven relational queries
- reduces early infrastructure complexity
- supports exact and approximate vector search
- allows retrieval benchmarking

A specialized vector database may be evaluated later if measurements justify it.

### Redis

Not required for the first implementation.

Potential later responsibilities:

- caching
- distributed rate limiting
- asynchronous job state
- short-lived workflow state

Redis will be introduced only when a concrete requirement exists.

---

## 13. Model Gateway

Application code should not directly depend on one model provider.

Conceptual interface:

ARGUS
    |
    v
Model Gateway
    |
    +-- reasoning model
    +-- low-cost model
    +-- embedding model
    +-- fallback model

The gateway should eventually support:

- model selection
- timeout policy
- retry policy
- token accounting
- cost accounting
- tracing
- structured outputs
- fallback behavior

Model routing decisions should eventually be driven by evaluation results rather than assumptions.

---

## 14. Structured AI Outputs

AI output used by application logic must be validated.

Example conceptual objects:

InvestigationPlan

- objective
- required_evidence
- proposed_actions
- rationale
- stop_conditions

Finding

- finding_type
- severity
- confidence
- summary
- evidence_ids
- uncertainties

Verdict

- classification
- confidence
- evidence_ids
- contradictory_evidence
- recommended_actions
- limitations

Pydantic models will enforce schemas at system boundaries.

---

## 15. Investigation Loop

ARGUS investigations use a bounded loop.

Plan
    |
    v
Gather Evidence
    |
    v
Analyze
    |
    v
Identify Missing Evidence
    |
    v
Select Next Action
    |
    v
Verify Hypothesis
    |
    v
Completion Gate
   / \
 NO   YES
 |     |
 +-----+--> Verdict

Stopping conditions may include:

- sufficient evidence
- confidence threshold
- no useful next action
- maximum iterations
- cost budget reached
- timeout reached
- human escalation required

No investigation may loop indefinitely.

---

## 16. Human-in-the-Loop

Human approval can be required when:

- confidence is below an accepted threshold
- contradictory evidence is significant
- a sensitive tool is requested
- a configured cost / execution threshold is reached
- an agent requests an action outside normal policy
- a security policy explicitly requires approval

The workflow must support pause and resume.

---

## 17. Backend Architecture

Initial backend stack:

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL
- pgvector

The backend should be structured by domain responsibility rather than as one large collection of API routes.

Initial logical layers:

API
|
Application
|
Domain
|
Infrastructure

AI frameworks and external APIs belong behind interfaces so that domain logic does not directly depend on them.

---

## 18. Frontend

Planned frontend:

- Next.js
- TypeScript

Primary experiences:

- submit investigation
- investigation timeline
- evidence explorer
- tool-call history
- retrieved sources
- agent reasoning summary
- confidence / verdict
- ATT&CK mappings
- human approval actions
- observability / evaluation summaries

Sensitive hidden chain-of-thought must not be exposed.

The UI should display concise decision rationale and evidence, not private model reasoning.

---

## 19. Observability

The architecture will support:

- structured application logs
- correlation / trace IDs
- API latency
- tool latency
- tool failures
- agent execution traces
- retrieval latency
- model latency
- token usage
- estimated cost
- investigation duration
- workflow failures
- guardrail events

Planned standards/tools:

- OpenTelemetry
- Prometheus
- Grafana

One dedicated LLM tracing solution will be selected later based on the orchestration framework.

---

## 20. Evaluation Architecture

Evaluation is a platform capability, not an afterthought.

Evaluation categories:

### Retrieval

- Recall@K
- Precision@K
- ranking quality
- citation/source relevance

### Agent

- correct tool selection
- tool-call success
- unnecessary tool calls
- workflow completion
- loop efficiency

### Investigation

- verdict quality
- groundedness
- citation correctness
- unsupported claims
- contradictory-evidence handling

### Production

- latency
- reliability
- token usage
- estimated cost

Evaluation datasets and versions must be reproducible.

---

## 21. Deployment Evolution

ARGUS will evolve incrementally.

### Phase 1

Local development:

- application services
- PostgreSQL
- Docker Compose when services exist

### Phase 2

Staging:

- container images
- managed infrastructure where justified
- automated deployment
- E2E testing

### Phase 3

Production-oriented deployment:

- Kubernetes
- secrets management
- health checks
- resource limits
- monitoring
- rollback
- versioned releases

Kubernetes will not be introduced before the application has a real orchestration requirement.

---

## 22. Security Boundaries

Major trust boundaries include:

1. User → API
2. API → Investigation Service
3. Agent → Tool Layer
4. MCP Client → MCP Server
5. ARGUS → External Threat Intelligence
6. RAG Pipeline → External Documents
7. Application → Model Provider
8. Frontend → Backend
9. CI/CD → Deployment Environment

Each boundary will receive explicit security analysis in SECURITY.md.

---

## 23. Engineering Loop

ARGUS itself is developed using a bounded engineering loop:

Requirement
    |
    v
Architecture
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
Evaluation Gate
    |
    v
Human Approval
    |
    v
Pull Request / CI

Failed checks return structured feedback to the implementation stage.

Autonomous retries must be bounded.

AI tools must not approve their own changes.

No automatic production deployment occurs without the required human gate.

---

## 24. Initial Architecture Decisions Still Open

The following decisions are intentionally not finalized:

- LangGraph vs OpenAI Agents SDK
- primary LLM provider/model
- embedding model
- LLM tracing platform
- cloud provider
- asynchronous job framework
- specialized vector database requirement
- reranking strategy
- hybrid-search strategy

These decisions will be resolved using architecture spikes, measurements and ADRs.

---

## 25. Architecture Success Criteria

The architecture succeeds if ARGUS can evolve from a deterministic cyber investigation service into a measurable, secure agentic AI platform without requiring a full rewrite.

The system should remain:

- explainable
- testable
- observable
- secure by design
- evidence-driven
- provider-aware but not unnecessarily provider-locked
- measurable
- maintainable
