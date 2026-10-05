# ADR-001 — PostgreSQL + pgvector as Initial Data and Vector Architecture

- Status: Accepted
- Date: 2026-10-05

## Context

ARGUS requires storage for both operational application data and vector-based
security knowledge retrieval.

Operational data includes:

- investigations
- IOCs
- evidence
- findings
- tool runs
- agent runs
- approvals
- reports
- audit events
- evaluation runs

The RAG subsystem additionally requires:

- knowledge documents
- chunks
- embeddings
- metadata
- provenance
- vector similarity search

The initial architecture should support these requirements without introducing
unnecessary infrastructure complexity.

## Decision

ARGUS will use PostgreSQL as its primary operational database.

ARGUS will initially use the pgvector PostgreSQL extension for vector storage
and similarity search.

The initial architecture will therefore keep relational data, knowledge
metadata and vector embeddings within the PostgreSQL ecosystem.

This decision does not permanently prevent adoption of a specialized vector
database.

## Why PostgreSQL

PostgreSQL provides:

- mature relational storage
- transactions
- indexing
- constraints
- JSON support
- strong Python ecosystem support
- reliable operational tooling
- compatibility with SQLAlchemy and Alembic

ARGUS contains strongly relational security data.

For example:

Investigation
→ Evidence
→ Tool Run
→ Finding
→ Report
→ Audit Event

A relational database is therefore a natural foundation.

## Why pgvector Initially

pgvector allows ARGUS to implement semantic retrieval without immediately
operating a separate vector database.

Benefits include:

- reduced infrastructure complexity
- vector and relational data in one system
- metadata filtering using SQL
- transactional relationships with knowledge metadata
- support for exact vector search
- support for approximate indexes such as HNSW
- straightforward local development

This is especially useful during early development when retrieval behavior is
still being measured.

## Alternatives Considered

### Qdrant

Advantages:

- specialized vector-search engine
- strong filtering capabilities
- designed specifically for vector workloads
- scalable vector-search architecture

Reason not selected initially:

ARGUS does not yet have evidence that its retrieval scale or latency requires a
dedicated vector database.

Qdrant may be benchmarked later.

### Pinecone

Advantages:

- managed vector infrastructure
- low operational overhead
- production-oriented scaling

Reason not selected initially:

It introduces an additional external managed dependency before ARGUS has
measured requirements that justify it.

### Weaviate

Advantages:

- mature vector-search capabilities
- hybrid-search functionality
- rich retrieval features

Reason not selected initially:

It increases infrastructure and architectural complexity before those features
are proven necessary.

## Retrieval Strategy

ARGUS will begin with measurable retrieval rather than assuming a specific
indexing strategy is optimal.

Initial progression:

1. Establish a retrieval baseline.
2. Measure Recall@K, Precision@K, MRR and latency.
3. Compare exact vector search where practical.
4. Evaluate HNSW when dataset size justifies approximate search.
5. Evaluate hybrid retrieval and reranking based on measured failures.
6. Benchmark a specialized vector database only if requirements justify it.

## Consequences

Positive:

- simpler initial architecture
- fewer services to operate
- easier local development
- strong relational/vector integration
- easier evidence and provenance relationships

Negative:

- PostgreSQL may not be optimal for very large vector workloads
- specialized vector databases may provide better vector-specific performance
  or operational capabilities
- migration may eventually be required if scale increases significantly

## Migration Strategy

Vector access must remain behind an application-level retrieval interface.

Business logic should not depend directly on pgvector-specific implementation
details where avoidable.

This allows a future architecture such as:

ARGUS Retrieval Interface
        |
        +-- pgvector
        |
        +-- Qdrant
        |
        +-- other vector backend

without rewriting investigation-domain logic.

## Validation

This decision will be revisited if measurements show:

- unacceptable retrieval latency
- unacceptable indexing performance
- operational scaling problems
- vector dataset growth beyond practical PostgreSQL limits
- materially better retrieval capabilities from another system

Any replacement must be supported by benchmarks rather than technology
preference.

## Consequences for the Portfolio

This decision demonstrates that ARGUS does not adopt infrastructure merely for
technology coverage.

The architecture begins with the simpler system and preserves an explicit
migration path if measured requirements justify additional complexity.
