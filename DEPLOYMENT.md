# VM deployment

The application runs on the existing ARM64 VM without publishing an app, database, or Ollama port to the host. The existing Roster Caddy instance is the only public entry point.

## Runtime topology

```text
Internet -> Caddy (edge) -> ai-llm-rag-app:8501
                              |             |
                              v             v
                    ai-llm-rag-db     ai-llm-rag-ollama:11434
```

`ai-llm-rag-app` joins the existing external networks `edge` and `ai-llm-rag-internal`. Postgres only joins the private `ai-llm-rag-db-internal` network. Ollama has no host port binding.

## GitHub environment

Create a GitHub environment named `production` and configure these values before pushing the deployment workflow:

| Kind | Name | Value |
| --- | --- | --- |
| Secret | `SSH_HOST` | VM host/IP |
| Secret | `SSH_USER` | `deploy` |
| Secret | `SSH_PRIVATE_KEY` | deployment SSH private key |
| Variable | `PG_DATABASE` | `ragdb` |
| Variable | `PG_USER` | dedicated Postgres user, for example `ragapp` |
| Secret | `PG_PASSWORD` | strong dedicated database password |
| Variable | `COLLECTION_NAME` | new collection name, for example `rag_gemma_qwen_v1` |
| Variable | `TOP_K` | `3` |
| Secret | `CLEAR_KB_PASSWORD` | strong knowledge-base deletion password |

The workflow writes the remaining model values explicitly:

```env
OPENAI_BASE_URL=http://ollama:11434/v1/
OPENAI_API_KEY=ollama
CHAT_MODEL=gemma3:4b
OCR_MODEL=gemma3:4b
EMBED_MODEL=qwen3-embedding:0.6b
```

Use a new `COLLECTION_NAME` when changing the embedding model. Existing vectors created with a different model must be re-ingested.

## First deployment

1. Create a DNS A record for `rag.taoxiong.site` pointing at the VM.
2. Configure the GitHub environment values above.
3. (No longer needed — this repo's own `deploy.yml` pushes `deploy/edge.Caddyfile` to the shared `/opt/edge-proxy` stack on every deploy. See `edge-proxy-extraction-design.md` in `Roster_Creator` for how the shared proxy works.)
4. Push the RAG deployment workflow to `master`. It builds an ARM64 image, writes `/home/deploy/ai-llm-rag/.env`, starts the isolated database and app, then validates the Compose stack.
5. The Caddy step validates its configuration before hot-reloading, after the app health check passes.

## Checks

```bash
curl -fsS https://rag.taoxiong.site/_stcore/health
docker compose -f /home/deploy/ai-llm-rag/docker-compose.yml ps
docker exec ai-llm-rag-ollama ollama list
```
