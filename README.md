# Nebula — Django AI Chat Workspace

Nebula is a complete, self-hostable AI chat application built with Django. It pairs a dark,
animated UI with token-by-token WebSocket streaming, document-aware answers (RAG), per-account
token quotas, and a JWT-authenticated REST API.

It is designed to work **out of the box**: no frontend build step, no API key required, and no
external services needed for local development. A deterministic `MockLLM` provider streams
believable replies until you point the app at a real model.

---

## Highlights

| Area | What you get |
| --- | --- |
| **Streaming chat** | WebSocket streaming (`ws/chat/<uuid>/`), live Markdown rendering, stop button, heartbeat, exponential reconnect, and an automatic HTTP fallback when JavaScript or the socket is unavailable. |
| **Conversations** | Create, rename/configure, search (HTMX), archive, restore, clear, delete, and export as JSON. Titles are generated from the first message. |
| **Per-chat settings** | Model, system prompt, temperature slider, and document-use toggle, editable from a modal. |
| **Documents (RAG)** | Upload PDF, DOCX, Markdown, or text; extract → chunk → embed → retrieve; inline `[n]` citations shown on answers. Drag-and-drop upload with live status. |
| **Accounts** | Email-based custom user model, signup, login, logout, password reset, profile with avatar and bio. |
| **Usage limits** | Every chat and embedding call is metered; a monthly token quota is enforced before each turn and visualised on a 30-day dashboard. |
| **REST API** | JWT auth, conversations, messages, documents, usage and quota endpoints. Browsable API in development. |
| **Operations** | Django admin, health endpoint, Docker image, Postgres + Redis + Celery compose stack, WhiteNoise static files, structured logging. |
| **UI** | “Nebula” dark theme, hand-written SVG icon sprite, animated background orbs, toasts, confirm dialogs, pointer spotlight cards, responsive sidebar, keyboard shortcuts (`N` new chat, `/` search, `Esc` close). |
| **Quality** | 60+ pytest tests covering services, views, API, RAG, and the real WebSocket consumer; Ruff linting; `manage.py check` clean. |

---

## Stack

- **Python 3.13** (3.12+ works; avoid 3.15 until Autobahn ships wheels)
- **Django 6.1** with a custom email-based user model
- **Django Channels 4 + Daphne** for ASGI/WebSockets
- **Django REST Framework + SimpleJWT**
- **HTMX 2** and **Tailwind CSS (CDN)** with a custom CSS design system
- **Celery + Redis** for background document ingestion (eager/inline by default)
- **SQLite** by default; **PostgreSQL** in Docker
- **httpx** for any OpenAI-compatible provider
- **pypdf / python-docx** for extraction, **Markdown + bleach** for safe rendering

No Node.js, bundler, or frontend build is required.

---

## Project layout

```text
.
├── config/
│   ├── settings/          base.py, development.py, production.py
│   ├── asgi.py            HTTP + WebSocket protocol router
│   ├── celery.py          Celery app
│   └── urls.py            Root URL map
├── apps/
│   ├── accounts/          Custom User + Profile, auth views and forms
│   ├── api/               DRF serializers, viewsets, JWT endpoints
│   ├── chat/              Conversations, messages, services, WS consumer, views
│   ├── core/              Landing page, health check, template tags, context processors
│   ├── llm/               Provider contract, mock provider, OpenAI-compatible adapter
│   ├── rag/               Documents, chunking, embeddings, retrieval, ingestion task
│   └── usage/             UsageEvent, quotas, dashboard
├── templates/             Server-rendered UI (base, chat, accounts, rag, usage, errors)
├── static/
│   ├── css/app.css        Design system, animations, responsive layout
│   └── js/                app.js (global UI) and chat.js (streaming client)
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── requirements.txt
├── requirements-dev.txt
├── pytest.ini
└── pyproject.toml         Ruff configuration
```

---

## Quick start

### Prerequisites

- Python 3.12 or 3.13 (this project was built and tested on 3.13)
- pip
- Optional: Docker Desktop for the container workflow

### Windows (PowerShell)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

Copy-Item .env.example .env   # optional; defaults work without it
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### macOS / Linux

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env          # optional; defaults work without it
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open <http://127.0.0.1:8000>. Sign up, or use the superuser you created at
<http://127.0.0.1:8000/admin/>.

> **No `.env` is required.** The defaults are: SQLite, `LLM_PROVIDER=mock`, in-memory channel
> layer, and eager Celery tasks. `createsuperuser` prompts for an email address because the
> custom user model has no username.

### Everyday commands

```bash
python manage.py runserver        # Daphne ASGI server, HTTP + WebSockets
python manage.py migrate
python manage.py makemigrations
python manage.py collectstatic
python manage.py check
```

---

## Configuring a model provider

Copy `.env.example` to `.env` and set `LLM_PROVIDER=openai`. The adapter speaks the de-facto
OpenAI `/chat/completions` (SSE) and `/embeddings` wire format, so the same configuration works
across many providers.

| Variable | Purpose |
| --- | --- |
| `LLM_PROVIDER` | `mock` (default) or any OpenAI-compatible alias (`openai`, `groq`, `openrouter`, `together`, `ollama`, `lmstudio`, `azure`, …) |
| `LLM_BASE_URL` | API root **without** `/chat/completions`, e.g. `https://api.openai.com/v1` |
| `LLM_API_KEY` | Bearer token. Leave empty for local servers that do not require one. |
| `LLM_CHAT_MODEL` | Default chat model |
| `LLM_EMBEDDING_MODEL` | Embedding model used for RAG |
| `LLM_EMBEDDING_BASE_URL` | Optional separate host/deployment for embeddings |
| `LLM_MODEL_CHOICES` | Comma-separated list offered in the per-chat settings modal |
| `LLM_TEMPERATURE`, `LLM_MAX_TOKENS`, `LLM_TIMEOUT` | Generation defaults |
| `LLM_EXTRA_HEADERS` | JSON object of extra request headers |
| `LLM_EXTRA_QUERY` | JSON object of extra query string parameters |
| `MOCK_LLM_DELAY` | Seconds between mock tokens (default `0.02`) |

### Provider examples

**OpenAI**

```dotenv
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_CHAT_MODEL=gpt-4o-mini
LLM_EMBEDDING_MODEL=text-embedding-3-small
LLM_MODEL_CHOICES=gpt-4o-mini,gpt-4o
```

**Groq**

```dotenv
LLM_PROVIDER=groq
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_...
LLM_CHAT_MODEL=llama-3.3-70b-versatile
LLM_EMBEDDING_BASE_URL=https://api.openai.com/v1   # Groq has no embeddings API
LLM_EMBEDDING_MODEL=text-embedding-3-small
```

**OpenRouter**

```dotenv
LLM_PROVIDER=openrouter
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-...
LLM_CHAT_MODEL=openai/gpt-4o-mini
LLM_EXTRA_HEADERS={"HTTP-Referer": "http://localhost:8000", "X-Title": "Nebula"}
```

**Ollama (local)**

```dotenv
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_CHAT_MODEL=llama3.1
LLM_EMBEDDING_MODEL=nomic-embed-text
```

**Azure OpenAI**

Azure uses an `api-key` header and an `api-version` query parameter instead of a Bearer token:

```dotenv
LLM_PROVIDER=azure
LLM_BASE_URL=https://my-resource.openai.azure.com/openai/deployments/my-gpt4o
LLM_API_KEY=
LLM_EXTRA_HEADERS={"api-key": "YOUR_AZURE_KEY"}
LLM_EXTRA_QUERY={"api-version": "2024-02-01"}
LLM_CHAT_MODEL=my-gpt4o
LLM_EMBEDDING_BASE_URL=https://my-resource.openai.azure.com/openai/deployments/my-embedding
LLM_EMBEDDING_MODEL=my-embedding
```

> If your provider has no embeddings endpoint, RAG retrieval is skipped gracefully and chat keeps
> working. Point `LLM_EMBEDDING_BASE_URL` at a provider that does embeddings to enable it.

---

## How RAG works

1. **Upload** — PDF, DOCX, `.md`, `.markdown`, or `.txt`, up to `RAG_MAX_UPLOAD_MB` (20 MB default).
2. **Extract** — `pypdf` or `python-docx`, with a plain-text reader for Markdown/text.
3. **Chunk** — overlapping word windows (`RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`).
4. **Embed** — batched embedding calls (`RAG_EMBED_BATCH_SIZE`), with usage recorded for quotas.
5. **Store** — vectors in a `JSONField`; no pgvector extension needed to get started.
6. **Retrieve** — Python cosine similarity over the user's documents, filtered by conversation
   scope, then the top `RAG_TOP_K` above `RAG_MIN_SCORE`.
7. **Answer** — excerpts are injected into the system prompt; the UI shows citation chips and the
   stored message carries structured `citations` metadata.

Ingestion runs through Celery. In development (`CELERY_TASK_ALWAYS_EAGER=True`) it runs inline; if
a broker is unreachable, the service falls back to synchronous ingestion so uploads never hang.

**Scaling note:** JSON vectors are perfect for a self-hosted single instance. For large corpora,
swap `apps/rag/services.py` retrieval for `pgvector` (or another vector store) — the rest of the
contract stays the same.

---

## REST API

All endpoints live under `/api/v1/`. Authenticate with a JWT:

```bash
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your-password"}'
```

Response:

```json
{"refresh": "...", "access": "..."}
```

Send the access token as `Authorization: Bearer <token>`.

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/auth/token/` | Obtain access + refresh tokens |
| `POST` | `/auth/token/refresh/` | Refresh an access token |
| `GET` | `/auth/me/` | Current user, display name, quota |
| `GET` | `/usage/` | Quota and lifetime token totals |
| `GET/POST` | `/conversations/` | List or create conversations |
| `GET/PATCH/DELETE` | `/conversations/<uuid>/` | Retrieve, update, delete |
| `GET/POST` | `/conversations/<uuid>/messages/` | List history or send a message |
| `POST` | `/conversations/<uuid>/clear/` | Delete all messages |
| `POST` | `/conversations/<uuid>/archive/` | Toggle archived state |
| `GET/POST` | `/documents/` | List or upload documents (multipart) |
| `GET/DELETE` | `/documents/<uuid>/` | Retrieve or delete a document |

Example — create a conversation and send a message:

```bash
TOKEN="paste-access-token"

CONVERSATION=$(curl -s -X POST http://localhost:8000/api/v1/conversations/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "API chat", "temperature": 0.5}' | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -X POST "http://localhost:8000/api/v1/conversations/$CONVERSATION/messages/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Explain vector databases in two sentences."}'
```

The API returns complete replies. Use the WebSocket endpoint for streaming. When a quota is
exhausted the send endpoint returns HTTP `429` with `{"code": "quota_exceeded"}`.

---

## WebSocket protocol

Connect to `ws/chat/<conversation-uuid>/` from the same origin (session-authenticated). The client
sends JSON actions and receives JSON events:

**Client → server**

```json
{"action": "send", "message": "Hello"}
{"action": "stop"}
{"action": "ping"}
```

**Server → client**

| Event | Payload |
| --- | --- |
| `ready` | `conversation_id`, JSON-safe `quota` |
| `turn_start` | `user_html`, `user_message`, `title` |
| `token` | `content` (incremental delta) |
| `done` | `html`, `message`, `error`, `stopped`, `quota` |
| `error` | `message` |
| `pong` | heartbeat acknowledgement |

`chat.js` renders streamed Markdown when the turn completes, keeps partial text on disconnect,
and reconnects with backoff (capped at 15 s).

---

## Tests, linting, and checks

```bash
python -m pytest                 # full suite
python -m pytest apps/chat -q    # one app
python -m ruff check .           # lint
python manage.py check           # Django system checks
```

Tests use the deterministic `mock` provider, a temporary media root, and a high RAG threshold so
they run offline and finish quickly. The WebSocket tests exercise the real consumer through
`WebsocketCommunicator`, including quota payload serialisation and unknown-action handling.

---

## Docker

The compose stack runs Daphne, a Celery worker, PostgreSQL 17, and Redis 7.

```bash
cp .env.example .env
# Edit .env: set a strong SECRET_KEY, your LLM settings, and ALLOWED_HOSTS
docker compose up --build
```

Then open <http://localhost:8000>.

Production settings are selected by `DJANGO_SETTINGS_MODULE=config.settings.production`. On
startup the entrypoint collects static files, applies migrations, and optionally creates a
superuser when `DJANGO_SUPERUSER_EMAIL` and `DJANGO_SUPERUSER_PASSWORD` are present:

```bash
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=change-me-now
```

Common compose commands:

```bash
docker compose logs -f web
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py shell
docker compose down          # keep volumes
docker compose down -v       # remove Postgres/Redis/media data
```

---

## Production checklist

- [ ] Set `DJANGO_SETTINGS_MODULE=config.settings.production`
- [ ] Set a long random `SECRET_KEY` (production refuses the development placeholder)
- [ ] Set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` to your real domains
- [ ] Set `REDIS_URL` — required for WebSockets to work across multiple Daphne processes
- [ ] Use PostgreSQL (`DATABASE_URL`); SQLite is fine for a single small instance
- [ ] Serve media from shared storage (S3, GCS, NFS) if you run more than one web container
- [ ] Terminate TLS at a proxy; the app trusts `X-Forwarded-Proto`
- [ ] Set real email credentials (password reset uses the console backend by default)
- [ ] Raise or lower the default quota from the admin (`Profile.monthly_token_quota`)
- [ ] Put `db.sqlite3`, `.env`, `media/`, and `staticfiles/` outside version control

Static files are served by WhiteNoise with hashed, compressed filenames. Media uploads are served
by Django only when `DEBUG=True`; in production your proxy or object store should serve
`/media/`.

---

## Design system

The UI is intentionally dependency-light and hand-crafted:

- `static/css/app.css` defines tokens, layout, components, and animations (orbs, shimmer, message
  enter transitions, streaming caret, toasts, dialogs, responsive sidebar).
- `templates/partials/icons.html` is a single SVG sprite with a unique icon set; templates reference
  icons via `<use href="#i-name">`.
- `static/js/app.js` handles toasts, dialogs, confirmations, clipboard copy, auto-growing textareas,
  drag-and-drop uploads, HTMX CSRF headers, pointer spotlight effects, and shortcuts.
- `static/js/chat.js` owns the WebSocket state machine and Markdown rendering.
- Tailwind, HTMX, and Google Fonts load from CDNs. Vendor them locally for air-gapped deployments.

---

## License

This project is provided as a complete starting point for your own product. Add the license that
fits your organisation before distributing it.
