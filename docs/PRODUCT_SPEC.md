# ARGUS — Product Specification

## 1. Product Vision

ARGUS is a production-oriented Agentic Cyber Threat Investigation Platform.

The system receives a security event or Indicator of Compromise (IOC), gathers evidence from trusted security tools and knowledge sources, reasons over the collected evidence, identifies missing information, performs additional investigation when required, and produces an evidence-backed security verdict.

ARGUS is designed around a core principle:

> The LLM is not the source of truth. Evidence is.

LLMs are used for planning, orchestration, correlation, reasoning and report generation. Security tools, structured data and retrieved knowledge provide the factual foundation.

---

## 2. Primary Goals

ARGUS will demonstrate:

- Production-oriented AI engineering
- Agentic AI workflows
- Multi-step autonomous investigation
- Tool / Function Calling
- Retrieval-Augmented Generation (RAG)
- Secure MCP-based tool integration
- Threat intelligence integration
- Evidence-based reasoning
- AI evaluation
- AI security and guardrails
- Human-in-the-loop workflows
- Backend engineering
- Observability
- Secure software development
- CI/CD and production deployment

---

## 3. Initial Investigation Inputs

ARGUS v1 will support:

- Domain
- IPv4 / IPv6 address
- URL
- SHA256 file hash
- Structured security alert

Future versions may support:

- Endpoint telemetry
- Process events
- Authentication events
- Network events
- Email / phishing artifacts
- Multi-event investigations

---

## 4. Investigation Lifecycle

A high-level investigation follows:

Security Event
→ Normalize
→ Validate
→ Initial Risk Triage
→ Investigation Planning
→ Evidence Collection
→ Threat Intelligence Enrichment
→ Knowledge Retrieval
→ Evidence Correlation
→ Hypothesis Verification
→ Missing Evidence Analysis
→ Additional Investigation if required
→ Confidence Assessment
→ Human Approval when required
→ Final Verdict
→ Evidence-backed Investigation Report

---

## 5. Investigation Loop

ARGUS does not perform a single LLM request.

Investigations operate as a bounded evidence-driven loop:

Plan
→ Gather Evidence
→ Analyze
→ Identify Missing Evidence
→ Select Next Action
→ Gather Additional Evidence
→ Correlate
→ Challenge Hypothesis
→ Evaluate Confidence

If sufficient evidence exists:
→ Produce Verdict

If evidence is insufficient:
→ Continue Investigation

If the system reaches safety, cost, iteration or confidence limits:
→ Escalate to Human Review

The loop must always have explicit stopping conditions.

---

## 6. Core Principles

### Evidence First

No security verdict should rely exclusively on an LLM statement.

### Source Attribution

Important claims must be traceable to their supporting evidence.

### Least Privilege

Agents receive only the tools and permissions required for their task.

### Untrusted Data

User input, retrieved documents and external tool responses are treated as untrusted data.

### Structured Outputs

Agent outputs used by application logic must follow validated schemas.

### Human Control

Sensitive actions and low-confidence investigations can require human approval.

### Measurable AI

AI behavior must be evaluated using repeatable datasets and metrics.

### Reproducibility

Important investigation runs should record relevant model, prompt, workflow, knowledge-base and tool versions.

---

## 7. Initial Agent Roles

### Investigator / Orchestrator

Controls investigation state and determines the next required action.

### Threat Intelligence Agent

Selects and queries appropriate threat-intelligence tools.

### Knowledge Agent

Retrieves relevant security knowledge through the RAG system.

### Correlation Agent

Connects evidence, threat intelligence, vulnerabilities, attack techniques and security context.

### Verification Agent

Challenges conclusions, searches for contradictory evidence and reduces unsupported conclusions.

Agent roles may change as evaluation results provide evidence for or against the multi-agent architecture.

---

## 8. Knowledge System

The RAG subsystem will eventually support:

- Document ingestion
- Parsing and normalization
- Chunking
- Metadata enrichment
- Embeddings
- Vector indexing
- Metadata filtering
- Retrieval
- Optional hybrid retrieval
- Reranking
- Context construction
- Source attribution
- Retrieval evaluation

Potential knowledge sources include legally usable and appropriately licensed/public security information such as:

- MITRE ATT&CK
- CVE / NVD data
- CISA advisories
- Security documentation
- Detection knowledge
- Curated investigation playbooks

Source provenance must be retained.

---

## 9. Security Requirements

ARGUS will explicitly consider:

- Prompt injection
- Indirect prompt injection
- Malicious retrieved documents
- RAG poisoning
- Tool abuse
- Excessive tool execution
- Input validation
- Output validation
- Authentication
- Authorization
- Least privilege
- Secrets management
- Rate limiting
- Audit logging
- Dependency security
- Container security

---

## 10. AI Quality Requirements

The platform will eventually measure:

- Retrieval quality
- Retrieval Recall@K
- Tool selection quality
- Tool-call success rate
- Investigation completion rate
- Verdict quality
- Groundedness
- Citation correctness
- Hallucination / unsupported claim rate
- Latency
- Token usage
- Estimated model cost
- Regression performance

---

## 11. Engineering Philosophy

ARGUS will be developed using a controlled engineering loop:

Specification
→ Architecture
→ Implementation Plan
→ Implementation
→ Automated Tests
→ Independent Review
→ Security Review
→ Evaluation
→ Human Approval
→ Pull Request
→ CI
→ Staging
→ Monitoring
→ Feedback

AI coding tools may assist implementation but do not define architecture or approve their own changes.

Large AI-generated changes must be reviewed and tested before merge.

---

## 12. Non-Goals for Early Versions

ARGUS v1 is not intended to:

- Replace a SOC analyst
- Automatically perform destructive remediation
- Execute offensive security actions
- Provide unrestricted shell access to agents
- Support every security event type
- Integrate dozens of threat-intelligence providers
- Use multiple AI frameworks merely for technology coverage
- Claim production readiness before production requirements are actually implemented

---

## 13. Definition of Success

ARGUS succeeds when it can take supported security inputs and produce reproducible, evidence-backed investigations whose quality can be measured.

The final portfolio should demonstrate not only that the system works, but also:

- why the architecture was selected
- how AI decisions are controlled
- how retrieval quality is measured
- how failures are handled
- how agents and tools are secured
- how the system is tested
- how it is observed in production
- what limitations remain
