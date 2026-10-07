# YitetsuAI Setup Guide

## Requirements

- Docker Desktop or Docker Engine
- Python 3.12+
- Git

## Quick start with Docker

```bash
docker compose up -d --build
docker exec yitetsuai_ollama ollama pull llama2
curl http://localhost:8000/docs
```

PostgreSQL stores users, sessions, conversations, messages, and audit events in
the `yitetsuai` database. Its data survives container restarts in the
`postgres_data` volume. The `init.sql` schema is applied on first initialization.
On later starts, the API creates newly-added tables and applies the
`conversations.updated_at` column migration if it is missing.

To remove the stack without deleting saved database data, run:

```bash
docker compose down
```

`docker compose down -v` deletes the PostgreSQL and Ollama data volumes.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Useful commands

```bash
make up
make down
make logs
make pull-model
```

## Database notes

The PostgreSQL schema is defined in `init.sql` and includes:

- `users`
- `sessions`
- `conversations`
- `conversation_messages`
- `documents`
- `audit_log`

The `documents` table includes a vector column for semantic search using `pgvector`.
Passwords are stored as PBKDF2 hashes, session tokens are stored as SHA-256
hashes, and conversation message order is persisted explicitly.

The authenticated API exposes:

- `GET /conversations` to list the current user's conversations
- `POST /conversations` to create a conversation
- `GET /conversations/{id}/messages` to load its messages
- `POST /chat` to append a user prompt and assistant reply to the selected conversation

## Typo interpretation

Chat prompts receive conservative offline spelling correction in Spanish and
English. The API returns `interpreted_prompt` and the exact `corrections`, and
the frontend displays them so users can spot an unintended correction. The
original prompt is what is stored in the user message; unfamiliar or ambiguous
words remain untouched. This prototype correction layer is not a substitute for
an LLM-based intent reasoner and asks no external service to process prompts.

## Ethics validation

Every AI response is validated against the project ethics policy:

- No replacement of human labor
- Critical reasoning with `however`, `but`, or `alternatively`
- Transparency about limitations and uncertainty
- Audit logging for actions

## Tests

The API tests use an in-memory SQLite database and do not require Docker:

```bash
python -m unittest discover -s tests
```
