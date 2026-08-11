# Production pilot notes

PaperScape now exposes provider-neutral inference contracts in
`backend/app/models/provider.py` and `backend/app/services/provider_ports.py`.
The existing watsonx provider remains backward compatible while implementing
structured and text capability ports. OpenAI and OpenAI-compatible chat
completion routes use the same request/result contract and return safe
generation provenance.

Provider selection is backend-only. Configure `DEFAULT_PROVIDER` as
`managed` (watsonx first, then OpenAI), `openai`, or `byok`/`compatible`.
`OPENAI_API_KEY`, `COMPATIBLE_API_KEY`, and compatible endpoint settings are
never returned by an API route.

The creator-pack API is derived only from a completed, validated research map:

```text
POST /api/v1/papers/{paper_id}/creator-packs
GET  /api/v1/papers/{paper_id}/creator-packs
PATCH /api/v1/papers/{paper_id}/creator-packs/{pack_id}
POST /api/v1/papers/{paper_id}/creator-packs/{pack_id}/approve
GET  /api/v1/papers/{paper_id}/creator-packs/{pack_id}/export
```

Packs are editable drafts. Export is rejected until the user approves the
pack. Evidence IDs are minted by the backend; model output does not author
pages, excerpts, or citation links.

The local Docker Compose path remains SQLite-backed for compatibility with the
hackathon prototype. PostgreSQL, durable workers, object storage, account
isolation, and secret-manager integrations are the next deployment increment
for the hosted pilot.
