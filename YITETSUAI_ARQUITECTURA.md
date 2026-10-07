# YitetsuAI architecture

## Layer 1 — Client

- Web: React 18 + TypeScript + Tailwind
- Future expansion: React Native and CLI tooling

## Layer 2 — API Gateway

- FastAPI with async endpoints
- JWT-style authentication for protected routes
- Pydantic validation and rate-limit support

## Layer 3 — Orchestration

- LangChain for prompt orchestration
- Retrieval-augmented generation with document embeddings
- Ethical validation layer with critical reasoning and transparency requirements

## Layer 4 — Models

- MVP: Ollama with Llama 2
- Expansion: external providers and self-hosted model serving

## Layer 5 — Persistence

- PostgreSQL 15 with pgvector support
- Redis for session and cache use cases
- Audit log for traceability

## Ethical rules

1. Do not replace human labor.
2. Require critical reasoning with `however`, `but`, or `alternatively`.
3. Expose uncertainty and limitations.
4. Keep audit logs for every generated response.
