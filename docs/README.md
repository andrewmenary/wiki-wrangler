# Wiki Wrangler — Design Documentation

This folder contains the production-quality design and roadmap for Wiki Wrangler,
produced in response to the project brief in
[wiki-wrangler-prompt.md](../wiki-wrangler-prompt.md). Implementation code
intentionally follows these documents rather than preceding them.

## Reading Order

1. [Product Requirements Document (PRD)](./01-prd.md) — vision, problem statement,
   goals, functional/non-functional requirements, success metrics.
2. [User Stories](./02-user-stories.md) — per-epic stories tagged MVP/P2/P3.
3. [Domain Model](./03-domain-model.md) — entities, relationships, and the Item
   lifecycle state machine.
4. [System Architecture](./04-architecture.md) — evaluation and revision of the
   proposed architecture, with component responsibilities.
5. [Database Schema](./05-database-schema.md) — SQLite DDL and design notes.
6. [Docker Architecture](./06-docker-architecture.md) — container topology, example
   Compose file, volumes, scaling path.
7. [Microsoft Graph Integration Strategy](./07-ms-graph-integration.md) — app
   registration, per-source connector design, webhooks vs. polling.
8. [Edge Extension Architecture](./08-edge-extension-architecture.md) — capture flow,
   device-token auth, required permissions.
9. [Security Model](./09-security-model.md) — authN/authZ, secrets, data protection,
   publish-path integrity, audit.
10. [MVP Roadmap](./10-mvp-roadmap.md) — phased plan to the core capture→publish loop.
11. [Implementation Status](./implementation-status.md) — checked-off implementation
   work and remaining tasks.
12. [Post-MVP Roadmap](./11-post-mvp-roadmap.md) — connectors, AI features, scale-out.
13. [Suggested Repository Structure](./12-repo-structure.md) — application monorepo
    layout and target wiki repo layout.
14. [Recommended Technology Stack](./13-tech-stack.md) — backend, frontend, extension,
    infra, and tooling choices with rationale.
15. [Sequence Diagrams](./14-sequence-diagrams.md) — major workflows end to end.
16. [Risk Analysis & Mitigation Plan](./15-risk-analysis.md) — scored risks across
    product, technical, Graph integration, security, and operational dimensions.

## Status

Design phase complete. Backend implementation has begun; use the
[Implementation Status](./implementation-status.md) checklist for current progress
and the [MVP Roadmap](./10-mvp-roadmap.md) for the intended sequence.
