# Build Log

This is the phase-by-phase development history — what was built, why,
what was tested and how, and two real bugs found via user testing with
full root-cause writeups. Kept for transparency and as a detailed
technical record; see the top-level [README.md](../README.md) for the
project overview.

---

## Phase 1 scope

- Project structure and settings management
- FastAPI backend skeleton
- LLM Gateway abstraction wrapping Groq (swappable provider layer)
- `/health` and `/chat` endpoints

## Setup

```bash
cd whatsapp-genai-rag
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Get a **free** Groq API key at https://console.groq.com/keys and put it
in `.env`:

```
GROQ_API_KEY=gsk_your_real_key_here
```

## Run

```bash
uvicorn app.main:app --reload
```

Visit http://127.0.0.1:8000/docs for interactive Swagger UI.

## Test

```bash
curl http://127.0.0.1:8000/api/v1/health

curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Say hello in one sentence."}'
```

`/health` reports whether `GROQ_API_KEY` is set — but note it only
checks the key is *present*, not that it's valid (that's a
placeholder-detection improvement to add before Phase 5 security
hardening).

## Notes

- This was scaffolded and smoke-tested in a sandboxed environment
  that blocks outbound calls to `api.groq.com` — `/` and `/health`
  were verified working there; `/chat` needs to be run with real
  network access and a real key (i.e., on your own machine).
- The `LLMGateway` class in `app/llm/groq_client.py` is the single
  chokepoint for all LLM calls — later agents (RAG, Verification,
  etc.) will call `llm_gateway.generate()` rather than importing the
  Groq SDK directly.

## Next: Phase 2

Document ingestion + single/multi-document RAG (PDF/DOCX/TXT/XLSX
extraction, chunking, embeddings, vector DB).

---

## Phase 2 — Document Ingestion + RAG

New endpoints:

```
POST /api/v1/documents/upload   (multipart: owner_id, file)
POST /api/v1/documents/query    (json: owner_id, query)
GET  /api/v1/documents?owner_id=...
```

### How it works

1. Upload a PDF/DOCX/TXT/XLSX with an `owner_id` — text is extracted,
   chunked, embedded locally (`sentence-transformers`), and stored in
   a local ChromaDB collection tagged with that `owner_id`.
2. Query with the same `owner_id` — only chunks belonging to that
   owner are searched (this is the authorization boundary: User B
   passing User B's `owner_id` can never retrieve User A's chunks,
   even with an identical query).
3. Only the top-k retrieved chunks (not whole documents) are sent to
   Groq, along with a system prompt that forbids answering outside
   the given context. The response includes which source file(s)
   were used.

### First run will download a small (~90MB) embedding model

The first time you call `/documents/upload` or `/documents/query`,
`sentence-transformers` downloads `all-MiniLM-L6-v2` from Hugging
Face. This requires normal internet access (it was verified to fail
in the sandboxed dev environment this was built in, which blocks
`huggingface.co` — it will work fine on your machine). After the
first download it's cached locally and works offline.

### Test it

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload \
  -F "owner_id=user_ravi" \
  -F "file=@/path/to/registration.pdf"

curl -X POST http://127.0.0.1:8000/api/v1/documents/query \
  -H "Content-Type: application/json" \
  -d '{"owner_id": "user_ravi", "query": "Who is the current owner?"}'

curl "http://127.0.0.1:8000/api/v1/documents?owner_id=user_ravi"
```

Try uploading a second document and asking a question that needs
both — that's the multi-document RAG case, since retrieval isn't
scoped to a single document.

### Verified in the sandboxed build environment

- Extraction + chunking logic (tested directly, no network needed)
- All routes register correctly (`/documents/upload`, `/documents/query`, `/documents`)
- Confirmed *why* live embedding/Groq calls can't run here (network
  allowlist blocks `huggingface.co` and `api.groq.com`) — this is an
  environment restriction, not a code issue

### Next: Phase 3

Conversation-aware RAG (resolving "it"/"his"/"that document" from
chat history) + multi-agent orchestration (Supervisor, Conversation,
RAG, Verification agents).

---

## Phase 3 — Conversation-Aware RAG + Multi-Agent Orchestration

New endpoint:

```
POST /api/v1/converse   (json: conversation_id, owner_id, message)
```

### How it works — one turn through the pipeline

1. **Conversation Agent** looks at the last few turns for this
   `conversation_id` and rewrites the message into a self-contained
   query (e.g. "what's his ownership %?" → "What is Ravi Kumar's
   ownership percentage in the registration document?"). Skipped
   entirely on the first message of a conversation — no history, no
   extra LLM call.
2. **Supervisor Agent** classifies the resolved query as
   `document_query` (needs RAG) or `general_chat`.
3. Routed to either:
   - the **RAG pipeline** from Phase 2 (retrieval scoped to
     `owner_id`, only relevant chunks reach the LLM), or
   - a normal conversational reply using recent history.
4. For RAG answers only, the **Verification Agent** makes an
   independent check that every claim in the answer is actually
   backed by the retrieved context, and appends a warning note if
   not — this is a second line of defense against hallucination, on
   top of the RAG system prompt's instructions.
5. Both the user message and the assistant's reply are stored in the
   (in-memory, per-process) conversation history for that
   `conversation_id`.

### Test it — the "his" reference-resolution scenario from your spec

```bash
# Turn 1 — establish context
curl -X POST http://127.0.0.1:8000/api/v1/converse \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"conv1","owner_id":"user_ravi","message":"Check the registration document and tell me who the current owner is."}'

# Turn 2 — ambiguous "his" — should resolve using turn 1's context
curl -X POST http://127.0.0.1:8000/api/v1/converse \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"conv1","owner_id":"user_ravi","message":"What is his ownership percentage?"}'
```

Check the response's `resolved_query` field to see exactly what the
Conversation Agent rewrote the ambiguous message into, and
`agent_used`/`verified` to see which path was taken.

### Verified in the sandboxed build environment

- All routes register correctly (`/converse` included)
- Reference resolution and routing logic tested directly (mocked LLM
  responses, since live Groq/embedding calls need network this
  sandbox restricts) — confirmed "his" correctly resolves to the
  person named two turns earlier, and the first-turn case correctly
  skips the extra resolution call

### Known limitation to flag

Conversation history is **in-memory** — it resets if the server
restarts. That's fine for this demo phase; Phase 6 (or earlier, if
you want it sooner) should move this to Redis/Postgres for anything
beyond local testing.

### Next: Phase 4

MCP integration (authorized website + Google Drive retrieval) +
voice input/NLP.

---

## Phase 4 — MCP Integration + Voice Input

New endpoints:

```
POST /api/v1/mcp/ingest-url        (json: owner_id, url)
GET  /api/v1/mcp/drive/auth-url    (query: owner_id)
GET  /api/v1/mcp/drive/callback    (query: code, state) — Google redirects here
POST /api/v1/mcp/drive/ingest      (json: owner_id, file_id)
POST /api/v1/voice/transcribe      (multipart: file)
POST /api/v1/voice/converse        (multipart: conversation_id, owner_id, file)
```

### Website MCP — how it works

`/mcp/ingest-url` fetches a public URL, extracts clean article text
(`trafilatura` — strips nav bars/ads, not just raw HTML), chunks it,
and stores it in the **same vector store** as uploaded documents,
tagged `source_type: "web"`. That means `/converse` and
`/documents/query` automatically search it too — no separate
retrieval path needed.

**SSRF protection is built in** (`app/mcp/security.py`): before
fetching, the URL's scheme and resolved IP are checked and blocked if
they point at localhost, private IP ranges, or the cloud metadata
endpoint (`169.254.169.254`) — this stops the fetcher being used as
an open proxy into internal infrastructure. Verified in the sandboxed
build environment: 6 test URLs (localhost, loopback, metadata
endpoint, private range, non-http scheme, and one real public URL)
all behaved correctly.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/mcp/ingest-url \
  -H "Content-Type: application/json" \
  -d '{"owner_id":"user_ravi","url":"https://en.wikipedia.org/wiki/Land_registration"}'
```

### Google Drive MCP — setup required (free, one-time)

This needs your own free Google Cloud OAuth credentials — there's no
way around a real consent screen for "authorized" access, per the
spec's requirement that MCP never bypass authorization.

1. Go to https://console.cloud.google.com/ → create a project (free).
2. APIs & Services → Library → enable **Google Drive API**.
3. APIs & Services → OAuth consent screen → set it up as **External**,
   add your own Google account as a test user.
4. APIs & Services → Credentials → Create Credentials → **OAuth client
   ID** → Application type: **Web application**.
5. Under "Authorized redirect URIs" add exactly:
   `http://127.0.0.1:8000/api/v1/mcp/drive/callback`
6. Download the JSON, rename it `credentials.json`, and place it in
   the project root (same folder as `requirements.txt`). It's already
   covered by `.gitignore` — never commit this file.

Then the flow is:

```bash
# 1. Get the consent URL (open it in a browser, log in, approve)
curl "http://127.0.0.1:8000/api/v1/mcp/drive/auth-url?owner_id=user_ravi"

# 2. Google redirects to /drive/callback automatically — token is saved

# 3. Ingest a specific file by its Drive file ID (from the file's URL)
curl -X POST http://127.0.0.1:8000/api/v1/mcp/drive/ingest \
  -H "Content-Type: application/json" \
  -d '{"owner_id":"user_ravi","file_id":"<drive-file-id>"}'
```

Verified in the sandboxed build environment: the endpoint correctly
returns a clean setup-instructions error (not a crash) when
`credentials.json` is missing — the OAuth exchange itself needs a
real browser + real Google account and couldn't be tested end-to-end
here.

### Voice — how it works

`/voice/transcribe` runs local, free speech-to-text
(`faster-whisper`, open-source Whisper — no API key, no per-request
cost) and returns just the transcript. `/voice/converse` does the
full spec flow in one call: audio in → transcript → Conversation
Agent → Supervisor → RAG/chat → reply out, so the user never has to
manually type what they said.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/voice/converse \
  -F "conversation_id=conv1" \
  -F "owner_id=user_ravi" \
  -F "file=@/path/to/voice_message.wav"
```

First call downloads the Whisper "base" model (~140MB) from Hugging
Face — same one-time-download pattern as the embedding model in
Phase 2. This needs real internet access (verified to be blocked in
this sandbox's network allowlist, same as the embedding model).

### Known limitations to flag

- Drive tokens are stored as **plaintext JSON** per owner
  (`data/drive_tokens/`) — fine for local testing, but flagged for
  encryption in Phase 5 before this touches real user data.
- SSRF protection checks the resolved IP at request time but doesn't
  defend against DNS rebinding (re-resolving to a different IP
  between check and connect) — a hardening item for Phase 5, not a
  concern for a portfolio demo.

### Next: Phase 5

Security hardening (encrypt Drive tokens, rate limiting, audit
logging, input validation, prompt-injection testing) + the prototype
chat interface.

---

## Phase 5 — Security Hardening + Prototype Chat Interface

### The main fix: real authentication

**Every Phase 1–4 endpoint trusted a client-supplied `owner_id`.**
Anyone could type `"owner_id": "someone_else"` in a request body and
read that person's documents — the RAG filtering itself was correct,
but there was no proof of who was actually asking. That's fixed now.

```
POST /api/v1/auth/register   (json: owner_id)  -> { api_key }
```

Every other endpoint now requires an `X-API-Key` header and derives
`owner_id` from that key server-side — it's no longer accepted as a
request field anywhere. The key is shown once, at creation, and
stored as a SHA-256 hash (never plaintext) in `data/api_keys.json`.

**Demo simplification, flagged honestly:** `/auth/register` lets
anyone mint a key for any `owner_id` name with no real identity
check — fine for local testing, but not how this should work once
WhatsApp is wired up in Phase 6, where `owner_id` should come from
the verified WhatsApp sender's phone number via the official
integration, not be self-declared.

```bash
# 1. Register and save the key
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" -d '{"owner_id":"user_ravi"}'

# 2. Use it on every subsequent call
curl http://127.0.0.1:8000/api/v1/documents -H "X-API-Key: wgk_..."
```

Verified in the sandboxed build environment: no key → `401`, wrong
key → `401`, valid key → `200`, and the old "spoof owner_id in the
JSON body" trick no longer has any effect since identity comes from
the key, not the body.

### Rate limiting

Per-`owner_id` sliding window (`RATE_LIMIT_MAX_REQUESTS` /
`RATE_LIMIT_WINDOW_SECONDS` in `.env`, default 30 requests/60s) on
`/chat`, `/converse`, `/mcp/*`, and `/voice/converse`. Deliberately
keyed by owner, not IP — in the real WhatsApp deployment, all
traffic arrives from Meta's own infrastructure IPs, so per-IP limits
would throttle everyone equally instead of stopping one abusive user.
Verified directly: 4th request within the window correctly returns
`429`, and a different owner is unaffected by another owner's usage.

### Audit logging

Every document upload, RAG query, MCP ingest, and Drive authorization
appends a structured JSON line to `data/audit.log` — who
(`owner_id`), what action, when, and non-sensitive metadata (filename,
chunk counts, blocked URLs). Deliberately never logs full document
content or full LLM answers.

### Encrypted Google Drive tokens

Phase 4 stored Drive OAuth tokens as plaintext JSON — flagged then as
a gap, fixed now. Tokens are encrypted at rest with Fernet, keyed by
`DRIVE_TOKEN_ENCRYPTION_KEY`. Generate one:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the output into `.env`. **Without this key set, saving a Drive
token now fails loudly** rather than silently falling back to
plaintext. Verified: round-trip encrypt/decrypt matches the original
token, the file on disk contains no readable trace of the token, and
saving without a configured key raises a clear error instead of
writing anything.

### Prompt-injection hardening

The RAG and Conversation Agent system prompts now explicitly instruct
the LLM to treat retrieved document/web content and conversation
history as **data only, never as instructions** — with an explicit
example of what to do if content tries to override its behavior
(ignore it, flag it, keep answering the real question). Retrieved
chunks are also wrapped in `<<<BEGIN/END DOCUMENT CONTENT>>>`
delimiters to make injected text harder to mistake for a new
instruction block.

### Other hardening

- Upload size caps: 10MB documents, 15MB audio, 5MB fetched web pages
- Security response headers (`X-Content-Type-Options`,
  `X-Frame-Options`, `Cache-Control: no-store`) — verified present on
  responses
- `.gitignore` covers `data/api_keys.json`, `data/audit.log`,
  `data/drive_tokens/`, and `credentials.json`

### Prototype chat interface

A single-file, no-build-step WhatsApp-style demo UI, served at
**`/demo`** once the server is running (e.g.
http://127.0.0.1:8000/demo). It's clearly banner-labeled as a
prototype, not the real WhatsApp app, per the spec's requirement.

What it demonstrates end-to-end:
- Register for an API key right in the UI
- Send text messages through `/converse`
- Upload a document or ingest a URL, then ask about it in chat
- Record a voice message (browser mic) through `/voice/converse`
- Shows which agent handled each reply and its sources

Verified in the sandboxed build environment: served correctly at
`/demo` with expected content; the auth/upload/converse network
calls it makes are the same ones already tested above via curl, so
end-to-end interaction depends on you running it locally with a real
Groq key.

### Next: Phase 6

WhatsApp official integration research + testing + deployment/docs.

---

## Phase 6 — WhatsApp Integration Research + Testing + Deployment

### Research findings (verified against Meta's own developer docs, not third-party summaries)

Before writing any integration code, per the original spec's explicit
instruction to never invent WhatsApp capabilities, I checked Meta's
current developer documentation and several independent sources. Key
findings, as of this build:

1. **No native UI extension exists.** There is no official way to add
   a `+ → AI` button or otherwise hook into the consumer WhatsApp
   app's UI. All integration happens through the **WhatsApp Business
   Platform** — a separate Cloud API (Graph API) + webhooks system for
   a *business's own number*, not a personal-account extension. The
   old On-Premises API is fully sunset.

2. **Policy conflict with the original spec's scenario.** Meta's terms
   prohibit "AI Providers" — including general-purpose AI assistants —
   from using the WhatsApp Business Platform when that AI functionality
   is the primary purpose being offered. This is why Meta shut down
   OpenAI's 1-800-ChatGPT number on January 15, 2026. The original
   spec's scenario (a general assistant riding along in a *personal*
   1:1/group chat) doesn't map onto anything officially available today
   — there's no mechanism to attach a general AI to a personal user's
   arbitrary chats via official APIs.

3. **The sanctioned path: a business's own document assistant.** Meta
   has confirmed this restriction doesn't affect a business using AI
   to serve its own customers, and has launched an official "Meta
   Business Agent" platform for exactly this — AI agents scoped to one
   business's own knowledge base (files, FAQs, websites) plus custom
   API connectors. **This project is reframed accordingly**: instead of
   a general personal assistant, it's now a document-retrieval
   assistant for a specific business's own clients — e.g. a small
   records/registration office where `owner_id` maps to an
   authorized client's phone number, and only documents that
   office has uploaded for that client are retrievable. This fits
   squarely within what's actually allowed.

4. **This is genuinely still moving.** The general-purpose-bot
   restriction is under active regulatory challenge (EU Commission
   review opened Dec 2025; Italy and Brazil ordered it suspended), so
   enforcement varies by region and could change again. Treat this as
   an evolving compliance area, not a settled fact — check
   Meta's current developer docs before relying on any specific rule
   here.

### What was built: the WhatsApp Adapter

```
app/whatsapp_adapter/
  security.py         # HMAC-SHA256 webhook signature verification
  payload_parser.py    # Cloud API webhook JSON -> IncomingMessage
  client.py             # send messages + download media via Graph API
  handler.py             # routes messages into the existing Phases 1-5 pipeline
app/api/routes_whatsapp.py  # GET verify handshake + POST webhook receiver
```

New endpoints:

```
GET  /api/v1/whatsapp/webhook   # Meta's one-time verification handshake
POST /api/v1/whatsapp/webhook   # incoming messages (text/voice/document)
```

**Identity fix, closing a gap flagged back in Phase 5:** WhatsApp
messages carry `owner_id` as the sender's verified phone number,
straight from the signed webhook payload — not a client-supplied
header. This is a *stronger* identity guarantee than the `/auth/register`
demo flow, and is exactly what Phase 5's README said should happen
once WhatsApp was wired up.

**How a message flows:**
- Text → Conversation Agent → Supervisor → RAG/chat (same pipeline as `/converse`)
- Voice note → downloaded via Graph API → transcribed locally
  (faster-whisper) → same pipeline as text
- Document attachment → downloaded → ingested into that sender's
  RAG index → confirmation reply sent

**Security:** every POST is HMAC-SHA256 verified against your app
secret before anything is processed — an unsigned or forged request
is silently dropped (still returns `200`, since returning an error
can cause Meta to disable your webhook after repeated failures; see
`routes_whatsapp.py` for why).

### Verified in the sandboxed build environment

- **31 automated tests** (`pytest tests/`) covering: document
  extraction/chunking, SSRF protection, auth (register/reject/revoke),
  rate limiting (per-owner isolation), Drive token encryption
  round-trip, the Phase 5 RAG-routing-override fix, and — new this
  phase — webhook signature verification (valid/tampered/wrong-secret/
  missing all behave correctly) and payload parsing (text/audio/
  document/status-update/empty payloads all parse correctly). All 31
  pass.
- Webhook verification handshake tested live: correct token echoes
  the challenge (completes Meta's setup flow), wrong token returns
  `403`, forged POST signatures are correctly rejected.
- **What couldn't be tested here:** actually sending/receiving real
  WhatsApp messages requires a verified Meta Business App, a real
  phone number registered on the Business Platform, and a public
  HTTPS URL for the webhook (Meta won't call `localhost`) — none of
  which can exist inside this sandboxed build environment. The setup
  steps below are accurate to Meta's current docs, but you'll need to
  complete them yourself with real credentials to test end-to-end.

### WhatsApp setup (you'll need this to actually connect it)

1. Create a Meta App at https://developers.facebook.com/apps →
   add the "WhatsApp" product.
2. Under WhatsApp → API Setup, note your **temporary access token**
   and **Phone Number ID** (a free test number is provided for
   development).
3. Under App Settings → Basic, note your **App Secret**.
4. Put these in `.env`: `WHATSAPP_ACCESS_TOKEN`,
   `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`. Set
   `WHATSAPP_VERIFY_TOKEN` to any random string you choose yourself.
5. Your webhook needs a public HTTPS URL. For local testing, use
   `ngrok http 8000` and take the `https://...ngrok.../api/v1/whatsapp/webhook`
   URL it gives you.
6. In the Meta App dashboard → WhatsApp → Configuration → Webhook,
   enter that URL and your `WHATSAPP_VERIFY_TOKEN`, then subscribe to
   the `messages` field.
7. Message the test number from your own WhatsApp — it should reach
   your running server.

**Note:** a free Meta developer test number can only message phone
numbers you've explicitly added as testers in the App dashboard.
Reaching arbitrary real users requires Meta's Business verification
process — out of scope to complete here, but the code path is ready
for it once you have a verified number.

### Deployment

```bash
docker build -t whatsapp-genai-backend .
docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/app/data whatsapp-genai-backend
```

For a free hosted deployment (so the webhook has a stable public URL
instead of an ngrok tunnel that changes every restart), Render.com's
free tier works with this Dockerfile as-is — connect your GitHub repo,
choose "Docker" as the environment, and add your `.env` values as
environment variables in Render's dashboard. Free tier does spin down
on inactivity, so isn't suited for production, but is fine for a
portfolio demo link.

### Running the test suite

```bash
pip install pytest  # already in requirements.txt
pytest tests/ -v
```

### Project summary — all 6 phases

| Phase | What it built |
|---|---|
| 1 | FastAPI backend + Groq LLM gateway (free, no `ANTHROPIC_API_KEY`) |
| 2 | Document ingestion (PDF/DOCX/TXT/XLSX) + local embeddings + ChromaDB RAG |
| 3 | Conversation-aware RAG (pronoun/reference resolution) + multi-agent orchestration |
| 4 | MCP (website + Google Drive retrieval, SSRF-protected) + local voice transcription |
| 5 | API-key auth, rate limiting, audit logging, encrypted tokens, prompt-injection hardening, demo UI |
| 6 | WhatsApp Business Platform integration, retrieval-routing fix, 31-test suite, Docker deployment |

Two real bugs were found through actual testing (not just
sandbox verification) and fixed with root-cause analysis documented
above: a hallucination-correction gap in the Verification Agent, and
a Supervisor misrouting bug that bypassed RAG entirely — both are
covered by regression tests now (`test_orchestrator_routing.py`).


---

### Fix: RAG answers weren't strictly grounded (found via real-world testing)

**Reported:** asking "What skills does he have?" against an uploaded
resume returned skills that weren't actually in the document.

**Root cause:** the Verification Agent detected unsupported claims
correctly, but only *appended a warning note* to the answer — the
hallucinated content itself stayed in the reply. Grounded-with-a-
disclaimer isn't the same as grounded.

**Fix:**
- The Verification Agent now has a `correct_answer()` step. When
  verification fails, the answer is rewritten using only what's in
  the retrieved context, unsupported items are removed entirely (not
  hedged), and the corrected answer is re-verified before being
  returned. The warning note is now a last-resort fallback, not the
  primary defense.
- The RAG system prompt has an explicit LIST rule: for
  skills/tools/project-type questions, include only items literally
  named in the context — no "typical for the role" padding, even
  when it seems like a safe inference.
- `retrieval_top_k` raised from 5 to 8, since smaller documents (like
  a one-page resume) are more likely to have a relevant section
  narrowly miss the cut at lower k.

Verified directly (mocked LLM responses simulating this exact case):
initial answer flagged as unsupported → corrected answer strips the
invented items → re-verification confirms the corrected answer is
fully grounded.

---

### Fix #2: the correction fix above didn't help — because RAG never ran

**Reported (via real-world testing with an actual resume):** the same
question still returned invented skills (R, Spark/Hadoop, Tableau,
SageMaker, CI/CD) after Fix #1 — but the response's `agent_used` field
showed **`conversation_agent`, not `rag_agent`.**

**Root cause:** the Supervisor Agent's LLM classification misrouted
"What skills does he have?" (after reference resolution) to
`general_chat`. That skipped retrieval, the RAG prompt, and the
Verification/correction agent entirely — the plain chat path has none
of those safeguards, so the model free-associated "typical
data-science skills" from conversation history alone. Fix #1 was
correct but never executed, because the routing decision happens
before it.

**Fix:** stop trusting the intent classifier as the sole gate for RAG
access. `retrieve()` now runs first (cheap local vector search, no
LLM call) whenever the owner has any indexed documents. If any
retrieved chunk is strongly relevant (cosine distance ≤
`RELEVANCE_DISTANCE_THRESHOLD`, default 0.9), the turn is routed to
RAG **regardless of what the classifier said.** The classifier is
still consulted, but only decides the outcome when there's no strong
retrieval match — it can no longer single-handedly cause silent
hallucination on a clearly document-related question.

Verified directly: simulated the exact failure (strong resume hits
present, classifier saying `general_chat`) and confirmed the override
correctly forces `use_rag = True`; confirmed empty/weak (irrelevant)
hits correctly do NOT force RAG, so plain chit-chat still routes
normally.

**Note on `RELEVANCE_DISTANCE_THRESHOLD`:** the default of `0.9` is a
reasonable starting point but couldn't be tuned against your actual
embedding model's real distance distribution in this sandboxed
environment (embeddings require `huggingface.co`, which is blocked
here). After testing, if you find real questions about your documents
aren't triggering the override, check the actual `distance` values
your hits return (log them, or inspect via `/documents/query` which
still exposes retrieval) and adjust the threshold — lower means
stricter (fewer false RAG triggers), higher means looser (catches
more borderline matches, at some risk of triggering RAG on
tangentially related chit-chat).






