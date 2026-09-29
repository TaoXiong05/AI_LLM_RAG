# VM deployment

The application runs on the existing ARM64 VM without publishing an app or database port to the internet. The shared Caddy edge proxy is the only public entry point. Chat, embedding and OCR models are hosted by Google Gemini and called through its OpenAI-compatible API; no model runs on the VM.

## Runtime topology

```text
Internet -> Caddy (edge) -> ai-llm-rag-app:8501 ─┐
                                                  ├─> ai-llm-rag-db (Postgres + pgvector)
            ai-llm-rag-mail-worker ───────────────┘
                 │
                 ├─> Google Gemini API (chat / embeddings / OCR)
                 └─> Resend API (poll received mail for support@taoxiong.site, send replies)
```

- `ai-llm-rag-app` joins the external `edge` network (for Caddy) and `ai-llm-rag-db-internal`.
- `ai-llm-rag-mail-worker` runs the same image with `python -m backend.mail_worker`. It joins only `ai-llm-rag-db-internal`, exposes no port, and reaches Gemini and Resend over outbound HTTPS. The image's Streamlit healthcheck is disabled for it.
- Postgres joins only `ai-llm-rag-db-internal`; its port is bound to `127.0.0.1` on the VM.

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
| Variable | `OPENAI_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| Secret | `OPENAI_API_KEY` | Google AI Studio (Gemini) API key |
| Variable | `CHAT_MODEL` | Gemini chat model, for example `gemini-3.1-flash-lite` |
| Variable | `OCR_MODEL` | Gemini vision model, for example `gemini-3.5-flash` |
| Variable | `EMBED_MODEL` | Gemini embedding model, for example `gemini-embedding-2` |
| Variable | `COLLECTION_NAME` | pgvector collection name, for example `rag_gemma_qwen_v1` |
| Variable | `TOP_K` | `3` |
| Secret | `CLEAR_KB_PASSWORD` | strong knowledge-base deletion password |
| Secret | `RESEND_API_KEY` | Resend API key with **Full access** (a "Sending access" key cannot read received mail). Leave unset to keep the mail worker idle. |
| Variable | `MAIL_FROM` | optional; defaults to `RAG Support <support@taoxiong.site>` |

The workflow writes these values to `/home/deploy/ai-llm-rag/.env`, which both the app and the mail worker read. The other `MAIL_*` settings (poll interval, daily limits, retries) use the defaults documented in `.env.example`.

Use a new `COLLECTION_NAME` when changing the embedding model. Existing vectors created with a different model must be re-ingested.

## Email auto-reply

- DNS for `taoxiong.site` (Namecheap): root MX points to Resend receiving; `send` and `rsend` CNAMEs (SPF), `resend._domainkey` TXT (DKIM) and `_dmarc` TXT (`v=DMARC1; p=none;`) authenticate outgoing mail. Every address `@taoxiong.site` is received by Resend; the worker only answers mail addressed to `support@taoxiong.site`.
- The worker creates its own table `email_log` on start (`CREATE TABLE IF NOT EXISTS`). No existing table is changed.
- On first start it only processes mail received in the last 24 hours.
- Design: `docs/superpowers/specs/2026-09-29-email-auto-reply-design.md`.

## First deployment

1. Create a DNS A record for `rag.taoxiong.site` pointing at the VM.
2. Configure the GitHub environment values above.
3. (No longer needed — this repo's own `deploy.yml` pushes `deploy/rag.caddy` to the shared `/opt/edge-proxy` stack on every deploy. See `edge-proxy-extraction-design.md` in `Roster_Creator` for how the shared proxy works.)
4. Push the RAG deployment workflow to `master`. It builds an ARM64 image, writes `/home/deploy/ai-llm-rag/.env`, starts the database, app and mail worker, then validates the Compose stack.
5. The fragment lands at `deploy/rag.caddy`, gets pushed to `/opt/edge-proxy/sites-enabled/rag.caddy`, and is validated with `caddy validate` before being committed. If validation fails, the fragment is reverted and the CI job fails; the previously-working config keeps serving traffic throughout. On success, the commit lands and Caddy hot-reloads.

## Checks

```bash
curl -fsS https://rag.taoxiong.site/_stcore/health
docker compose -f /home/deploy/ai-llm-rag/docker-compose.yml ps
docker logs --tail 50 ai-llm-rag-mail-worker
```

Without SSH access, run the **Diagnose mail worker** workflow (GitHub → Actions → Run workflow). It prints the worker's status, recent errors, the last `email_log` rows (no sender or subject — Actions logs are public) and live model/retrieval checks from inside the worker container.
