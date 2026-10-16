# WhatsApp GenAI RAG

A document-question-answering application that ingests PDF documents, retrieves relevant passages, and generates answers grounded in those passages. The project combines a FastAPI RAG service with a Node.js backend and uses hybrid retrieval to improve recall and relevance.

> **Project status:** Core upload and query flows have been tested locally. `Gradient.pdf` was indexed into 149 chunks; the query endpoint returned HTTP 200, cited `Gradient.pdf`, and an unrelated question received an insufficient-information response. These are manual test results, not a claim of production readiness.

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Project structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup and run locally](#setup-and-run-locally)
- [Environment configuration](#environment-configuration)
- [API endpoints](#api-endpoints)
- [Retrieval and answer generation](#retrieval-and-answer-generation)
- [Evaluation](#evaluation)
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
- **Dense retrieval:** embedding-based similarity search
- **RRF:** combines retrieval rankings
- **Optional reranker:** cross-encoder reranking
- **Groq:** LLM API client
- **Node.js:** backend integration
- **Redis-compatible service:** Memurai on Windows for local development
- **MongoDB Atlas:** database service

Check `requirements.txt`, `package.json`, and the source files for the exact package versions used by your checkout.

## Project structure

Relevant files and folders include:

```text
whatsapp-genai-rag/
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
├── data/                 # Local documents/data; don't commit private files
├── tests/                # Tests, if present in this checkout
├── venv/                 # Local virtual environment; do not commit
├── whatsapp_backend/
│   ├── package.json
│   └── ...
├── .env                  # Local secrets; do not commit
└── README.md
```

This is a guide to the known project layout; actual optional files may differ.

## Prerequisites

- Windows with PowerShell (commands below use Windows paths).
- Python 3.11, matching the version used during development.
- Node.js and npm.
- A running Redis-compatible service. In the local Windows setup, Memurai listens on port `6379`.
- A reachable MongoDB Atlas cluster and an Atlas IP access-list entry for your current public IP.
- A Groq API key and any application-specific API key/configuration required by the project.

## Setup and run locally

Run the following commands in **two separate VS Code terminals**. Keep both terminals open while testing.

### 1. Start the Node.js backend

```powershell
cd D:\whatsapp-genai-project\whatsapp-genai-rag\whatsapp_backend
npm install
npm start
```

The backend has a `start` script that runs its TypeScript watcher and Node process. Look for a message indicating that the server is listening on port `5000`. Also confirm MongoDB and Redis connections succeed.

### 2. Start the FastAPI service

```powershell
cd D:\whatsapp-genai-project\whatsapp-genai-rag
.\venv\Scripts\Activate.ps1
```

If the virtual environment does not exist yet, create it and install the project's dependencies from the requirements file if present:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
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

If the `requirements.txt` file is absent, inspect the repository's dependency files and install the dependencies specified by the project rather than guessing versions.

## Environment configuration

Create a local `.env` file using the variable names expected by the current source code. **Do not commit the real `.env` file or paste its secrets into issues, screenshots, or chat.**

Configuration used by the project may include:

| Purpose | Variable name / location | Notes |
|---|---|---|
| MongoDB Atlas URI | `DATABASE` (reported in this project setup) | Contains credentials; keep secret. Verify this name in `whatsapp_backend` source/config. |
| Groq API key | Check `app/llm/groq_client.py` and `app/core/config.py` | Use the exact variable name read by the code. |
| Redis/Memurai connection | Check Node.js Redis client configuration | Local service was tested at `127.0.0.1:6379`; verify the expected env variable name. |
| Application/API key | Check FastAPI authentication/configuration and Swagger's `X-API-Key` header | Store the real key securely; never publish it. |
| Other application settings | `app/core/config.py` and backend config files | Use the exact names and defaults defined by the application. |

Example placeholders only (not a complete working `.env`):

```dotenv
# Replace names with those actually read by your application.
DATABASE=<your-mongodb-atlas-connection-string>
GROQ_API_KEY=<your-groq-api-key>
REDIS_URL=redis://127.0.0.1:6379
```

Do not copy this sample blindly: variable names differ between projects. Confirm the actual names in the source before using it. Never add real credentials to the README.

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

## Limitations

- The evaluation dataset is small; metrics may not generalize to other documents or query types.
- LLM responses can still misstate equations or coefficients. Critical mathematical, legal, or financial content requires source-level verification.
- Reranking can improve relevance but adds latency and computational cost.
- PDF extraction quality varies with scanned pages, tables, equations, columns, and unusual formatting.
- A source filename citation does not prove every statement is supported; chunk-level evidence and answer faithfulness should be evaluated separately.
- Redis, MongoDB Atlas, Groq, and any authentication service must be reachable and correctly configured.
- Local development commands and Windows paths may need adaptation for Linux, containers, or production hosting.

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

### `No such file or directory: app/rag/pipeline.py`

Change into the project root before running Python commands:

```powershell
cd D:\whatsapp-genai-project\whatsapp-genai-rag
python -m py_compile app\rag\pipeline.py
```

### FastAPI telemetry warnings

ChromaDB telemetry messages such as `capture() takes 1 positional argument but 3 were given` were observed during development. If the API completes startup and serves requests, these messages were non-fatal in that run. Investigate dependency compatibility if they become startup-blocking.

### Node.js cannot connect to port 5000

Start the backend from its own folder:

```powershell
cd D:\whatsapp-genai-project\whatsapp-genai-rag\whatsapp_backend
npm start
```

### MongoDB Atlas connection failure

Check that the Atlas cluster is active, the current public IP is permitted in Network Access, and the connection URI/credentials are correct. Never disclose the URI containing credentials.

### Redis connection timeout

Check that Memurai is running and port `6379` is reachable. A successful Python ping confirms that local Redis-compatible service responds to that Python client, but does not by itself prove the Node.js client uses the same host and configuration.

---

## Submission notes

Before submission, replace any placeholder instructions with the exact configuration names from the current source code, verify the dependency files are present, review `.gitignore`, and run the smoke tests from fresh terminals. Do not include private documents or secrets unless the submission explicitly requires them and you are authorized to share them.
