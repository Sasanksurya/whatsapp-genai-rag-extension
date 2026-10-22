# WhatsApp GenAI Extension — Secure Multi-Agent RAG for Document & Data Retrieval

![CI](https://github.com/Sasanksurya/whatsapp-genai-rag-extension/actions/workflows/ci.yml/badge.svg)

A document-question-answering application that ingests PDF documents, retrieves relevant passages, and generates answers grounded in those passages. The project combines a FastAPI RAG service with a Node.js backend and uses hybrid retrieval (dense + BM25 with Reciprocal Rank Fusion, plus optional cross-encoder reranking) to improve recall and relevance.

> **Project status:** Core upload and query flows have been tested locally. `Gradient.pdf` was indexed into 149 chunks; the query endpoint returned HTTP 200, cited `Gradient.pdf`, and an unrelated question received an insufficient-information response. These are manual test results, not a claim of production readiness.

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Project structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Quick start (Docker)](#quick-start-docker)
- [Run locally without Docker](#run-locally-without-docker)
- [Environment configuration](#environment-configuration)
- [API endpoints](#api-endpoints)
- [Retrieval and answer generation](#retrieval-and-answer-generation)
- [Evaluation](#evaluation)
- [Continuous integration](#continuous-integration)
- [Limitations](#limitations)
- [Security checklist](#security-checklist)
- [Troubleshooting](#troubleshooting)

## Features

- PDF/text extraction and chunking for document ingestion.
- Vector storage and dense retrieval using ChromaDB.
- Hybrid retrieval combining sparse and dense signals, with Reciprocal Rank Fusion (RRF).
- Optional cross-encoder reranking.
- Relevance-ranked context assembly with neighboring-chunk expansion.
- Context size limit to keep prompts within a bounded budget.
- Answers generated from retrieved context, with source filenames returned by the API.
- Insufficient-information behavior for questions not supported by the retrieved context.
- Owner, conversation, and optional document scoping for retrieval.
- FastAPI Swagger documentation for interactive API testing.

## Architecture

```text
Client / Swagger UI
        |
        v
FastAPI RAG service (port 8000)
        |
        +--> Document extraction and chunking
        |          |
        |          v
        |       ChromaDB
        |
        +--> Query
                   |
                   v
          Dense + sparse retrieval
                   |
                   v
             RRF fusion
                   |
                   v
       Optional cross-encoder reranking
                   |
                   v
      Context ranking and neighbor expansion
                   |
                   v
          Groq-hosted LLM generation
                   |
                   v
        Answer + source filenames

Node.js backend (port 5000)
  |-- conversation membership/authorization integration
  |-- Redis-compatible service (Memurai locally, port 6379)
  |-- MongoDB Atlas connection
```

The exact request/authentication flow depends on the current application configuration. Keep the Node.js backend running when using endpoints that verify conversation membership through it.

## Technology stack

- **Python:** RAG pipeline and API
- **FastAPI + Uvicorn:** HTTP API and local development server
- **ChromaDB:** vector storage
- **Sparse retrieval:** BM25 (`rank_bm25`)
- **Dense retrieval:** embedding-based similarity search (`sentence-transformers`)
- **RRF:** combines retrieval rankings
- **Optional reranker:** cross-encoder reranking
- **Groq:** LLM API client
- **Node.js:** backend integration
- **Redis-compatible service:** Memurai on Windows for local development
- **MongoDB Atlas:** database service
- **Docker + Docker Compose:** containerized RAG service
- **GitHub Actions:** CI (lint, tests, Docker build)

Check `requirements.txt`, `package.json`, and the source files for the exact package versions used by your checkout.

## Project structure

Relevant files and folders include:

```text
whatsapp-genai-rag-extension/
├── .github/
│   └── workflows/
│       └── ci.yml          # CI: lint, tests, Docker build
├── app/
│   ├── main.py
│   ├── core/
│   │   └── config.py
│   ├── documents/
│   │   ├── chunker.py
│   │   └── extractors.py
│   ├── llm/
│   │   └── groq_client.py
│   └── rag/
│       ├── pipeline.py
│       ├── retrieval.py
│       └── vectorstore.py
├── data/                   # Local documents/data; don't commit private files
├── docs/
├── static/
├── tests/
├── whatsapp_backend/
│   ├── package.json
│   └── ...
├── .env                    # Local secrets; do not commit
├── .env.example            # Placeholder configuration
├── Dockerfile
├── docker-compose.yml
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # Runtime + pytest + ruff
└── README.md
```

This is a guide to the known project layout; actual optional files may differ.

## Prerequisites

- **Docker route:** Docker Desktop (with WSL 2 on Windows).
- **Local route:** Python (3.11 was used during development; the Docker image and CI use 3.12), Node.js and npm.
- A Groq API key (free tier at <https://console.groq.com/keys>).
- For endpoints that verify conversation membership: a running Node.js backend, a Redis-compatible service (Memurai on port `6379` in the local Windows setup), and a reachable MongoDB Atlas cluster with your current public IP in the Atlas access list.

## Quick start (Docker)

This starts the FastAPI RAG service in a container.

```powershell
copy .env.example .env      # macOS/Linux: cp .env.example .env
# open .env and set GROQ_API_KEY
docker compose up --build
```

When the logs show Uvicorn running, open the interactive API docs at <http://localhost:8000/docs>.

Notes:

- The first build is slow (it downloads PyTorch, using the CPU-only build to keep the image smaller). The first query is also slow because the embedding model is downloaded once, then cached in the data volume.
- Data (vector DB, model cache) is stored in the named Docker volume `app_data`, so it survives restarts. `docker compose down` stops the service and keeps the data; `docker compose down -v` also deletes it.
- The container runs as a non-root user and defines a health check against `/docs`.
- Docker Compose runs the **FastAPI service only**. The Node.js backend, Redis-compatible service and MongoDB are not part of the compose file. Endpoints that verify conversation membership through the Node.js backend need that backend running (see below). If the FastAPI configuration points at `localhost` for the backend, note that `localhost` inside a container is the container itself; on Docker Desktop use `host.docker.internal` instead.

## Run locally without Docker

Run the following in **two separate terminals** from the repository root. Keep both open while testing.

### 1. Start the Node.js backend

```powershell
cd whatsapp_backend
npm install
npm start
```

The backend has a `start` script that runs its TypeScript watcher and Node process. Look for a message indicating that the server is listening on port `5000`, and confirm that the MongoDB and Redis connections succeed.

### 2. Start the FastAPI service

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Set conservative numerical-library thread limits in this terminal if needed for your Windows environment:

```powershell
$env:OPENBLAS_NUM_THREADS="1"
$env:OMP_NUM_THREADS="1"
$env:MKL_NUM_THREADS="1"
```

Start the API:

```powershell
python -m uvicorn app.main:app --reload --log-level info
```

Open the interactive API documentation:

- Swagger UI: <http://127.0.0.1:8000/docs>
- Local API base URL: `http://127.0.0.1:8000`

### Run the tests

```powershell
python -m pip install -r requirements-dev.txt
pytest tests/ -v
```

## Environment configuration

Copy `.env.example` to `.env` and fill in your values. **Do not commit the real `.env` file or paste its secrets into issues, screenshots, or chat.**

| Purpose | Variable name | Notes |
|---|---|---|
| Groq API key | `GROQ_API_KEY` | Required. Free key from console.groq.com. |
| Groq model | `GROQ_MODEL` | Default in `.env.example`: `llama-3.3-70b-versatile`. |
| Whisper model size | `WHISPER_MODEL_SIZE` | Voice transcription model size. |
| Rate limiting | `RATE_LIMIT_MAX_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS` | Requests allowed per window. |
| Drive token encryption | `DRIVE_TOKEN_ENCRYPTION_KEY` | Generate with the command in `.env.example`. |
| Retrieval relevance | `RELEVANCE_DISTANCE_THRESHOLD` | Lower is stricter. |
| WhatsApp / Twilio | `WHATSAPP_*`, `TWILIO_*` | Needed only for the WhatsApp adapters. |
| MongoDB Atlas URI | `DATABASE` (reported in this setup) | Node.js backend. Contains credentials; keep secret. Verify the name in the `whatsapp_backend` source/config. |
| Redis connection | See the Node.js Redis client configuration | Tested locally at `127.0.0.1:6379`; verify the expected variable name. |

Never add real credentials to this README.

## API endpoints

The following endpoints were observed in the local Swagger UI:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/documents/upload` | Upload and index a document. The observed request uses multipart form data with a PDF file and a `conversation_id`. |
| `POST` | `/api/v1/documents/query` | Query authorized documents. The JSON body includes `query`, `conversation_id`, and optional `document_id`. |

The query endpoint description indicates that Node.js verifies conversation membership and ChromaDB retrieval is scoped by `owner_id`, `conversation_id`, and (when supplied) `document_id`. Authentication headers may be required; use the exact fields and security controls displayed in Swagger.

### Example query request

Use the current document ID returned by your own upload response. Do not rely on an ID from an old test run.

```json
{
  "query": "What is the main conclusion in this document?",
  "conversation_id": "<your-conversation-id>",
  "document_id": "<document-id-returned-by-upload>"
}
```

The query response observed during testing has this shape:

```json
{
  "answer": "Generated answer grounded in retrieved context.",
  "sources": [
    "Gradient.pdf"
  ]
}
```

Exact response content depends on the document, retrieval results, and LLM output.

## Retrieval and answer generation

1. Extract text from the uploaded document.
2. Split the extracted text into chunks.
3. Store chunks and metadata for retrieval.
4. Retrieve candidates with dense and sparse search when hybrid mode is enabled.
5. Fuse rankings using RRF.
6. Optionally rerank candidates with a cross-encoder.
7. Build a bounded context from relevant chunks, preserving document/owner/conversation scope and optionally including adjacent chunks.
8. Ask the LLM to answer from the context and return source filenames.

The pipeline's context limit is currently configured as `12,000` characters. The cross-encoder reranker is optional because it can increase latency.

## Evaluation

Evaluation scripts and a small query set were used during development. Previously reported runs showed that reranking improved ranking metrics compared with the hybrid baseline, but results varied across runs/configurations. The evaluation set was small (about 10 queries), so these results are preliminary and should not be presented as production-level proof.

Metrics used/reported in project experiments include:

- **MRR (Mean Reciprocal Rank):** rewards relevant evidence appearing near the top of the ranking.
- **NDCG@k:** evaluates ranked relevance, with higher ranks weighted more strongly.
- **Recall@k:** measures whether relevant evidence appears within the top `k` retrieved chunks.
- **Latency:** measures retrieval/reranking time; separate it from full LLM response latency.

For reproducibility, report the exact evaluation dataset, query count, retrieval configuration, `k`, reranker setting, and hardware/software setup beside any numeric results. Do not compare measurements taken with different settings as if they were the same experiment.

Manual checks completed during local development:

- `Gradient.pdf` upload returned HTTP 200 and reported 149 indexed chunks.
- A Stochastic Heavy Ball question returned HTTP 200 and cited `Gradient.pdf`.
- A question asking for Hyderabad's population from the unrelated document returned: `I don't have enough information.`

The mathematical answer was refined with stronger prompt instructions after an incorrect coefficient appeared in an earlier response. Recheck exact equations against the source PDF before claiming all mathematical outputs are fully validated.

## Continuous integration

Every push to `main` and every pull request runs a GitHub Actions workflow (`.github/workflows/ci.yml`) that:

1. Installs CPU-only PyTorch and the dev dependencies (`requirements-dev.txt`).
2. Runs `ruff` for serious errors only (syntax errors and undefined names). A full style-lint pass is planned once the existing style issues are cleaned up.
3. Runs `pytest tests/ -v`.
4. Builds the Docker image to confirm the Dockerfile works.

## Limitations

- The evaluation dataset is small; metrics may not generalize to other documents or query types.
- LLM responses can still misstate equations or coefficients. Critical mathematical, legal, or financial content requires source-level verification.
- Reranking can improve relevance but adds latency and computational cost.
- PDF extraction quality varies with scanned pages, tables, equations, columns, and unusual formatting.
- A source filename citation does not prove every statement is supported; chunk-level evidence and answer faithfulness should be evaluated separately.
- Redis, MongoDB Atlas, Groq, and any authentication service must be reachable and correctly configured.
- There is no hosted deployment yet; the project is run locally or with Docker.

## Security checklist

Before pushing or submitting:

- [ ] Ensure `.env` is ignored by Git.
- [ ] Ensure API keys, database credentials, and tokens are not in tracked files, notebooks, logs, or screenshots.
- [ ] Ensure `venv/`, `node_modules/`, caches, and generated local databases are excluded from version control.
- [ ] Use least-privilege MongoDB credentials and restrict Atlas Network Access to required IPs.
- [ ] Do not use a permissive Atlas IP access rule in production.
- [ ] Confirm retrieval always enforces owner/conversation/document authorization.
- [ ] Avoid logging secrets or sensitive document contents.
- [ ] Rotate any credential that has accidentally been committed or shared.

A typical `.gitignore` should include entries like these (merge with the existing file rather than overwriting project-specific rules):

```gitignore
.env
.env.*
!.env.example
venv/
.venv/
node_modules/
__pycache__/
*.py[cod]
.pytest_cache/
.chroma/
chroma_db/
```

Only include `!.env.example` if that example file contains placeholders and no real credentials.

## Troubleshooting

### `docker` is not recognized, or the Docker engine is not running

Install Docker Desktop, start it, and wait until it shows **Engine running**. Then open a new terminal and run `docker compose up --build` again.

### `No such file or directory: app/rag/pipeline.py`

Change into the repository root before running Python commands:

```powershell
python -m py_compile app\rag\pipeline.py
```

### FastAPI telemetry warnings

ChromaDB telemetry messages such as `capture() takes 1 positional argument but 3 were given` were observed during development. If the API completes startup and serves requests, these messages were non-fatal in that run. Investigate dependency compatibility if they become startup-blocking.

### Node.js cannot connect to port 5000

Start the backend from its own folder:

```powershell
cd whatsapp_backend
npm start
```

### MongoDB Atlas connection failure

Check that the Atlas cluster is active, the current public IP is permitted in Network Access, and the connection URI/credentials are correct. Never disclose the URI containing credentials.

### Redis connection timeout

Check that Memurai is running and port `6379` is reachable. A successful Python ping confirms that the local Redis-compatible service responds to that Python client, but does not by itself prove the Node.js client uses the same host and configuration.