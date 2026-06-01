# Clinical Trial Failure Intelligence System

AI-assisted system to ingest terminated clinical trials, classify why they stopped, estimate salvageability, and recommend possible rescue strategies.

---

## Table of Contents
- Overview
- Features
- Architecture
- Quickstart (Docker)
- Local development (backend & frontend)
- Environment variables
- Database & migrations
- API reference
- Project structure (key files)
- Contributing & license

---

**Overview**

This repository contains an MVP for analyzing terminated clinical trials to find potentially salvageable drug assets. The backend ingests trials (ClinicalTrials.gov), classifies failure reasons using an LLM pipeline with a new primary Groq model, computes a salvageability score, and exposes a REST API consumed by a Next.js frontend.

**Core goals**: collect failed trial data, classify failure modes (e.g. toxicity, lack of efficacy, recruitment failure), estimate salvageability, and surface actionable recommendations.

---

**Features**
- **Ingestion**: fetch failed trials and upsert into a Postgres DB.
- **Classification**: LLM-driven classification with a BiomedBERT fallback and confidence blending.
- **Dashboard/API**: browse trials, filter, update and view detailed classification results.
- **Extensible**: modular services for fetcher, classifier, and trial persistence.

---

**Architecture (high level)**

ClinicalTrials.gov → fetcher → classifier (Groq Llama primary, Ollama fallback, embeddings emergency fallback) → Postgres DB → API → Next.js frontend

---

**Quickstart (Docker)**

1. Build and start all services (Postgres, Ollama, backend, frontend):

```bash
docker-compose up -d --build
```

2. Services and default ports:
- Postgres: `5433` (container exposes 5432)
- Ollama API: `11434`
- Backend (FastAPI/uvicorn): `8001` (proxied to container 8000)
- Frontend (Next.js): `3001` (proxied to container 3000)

3. Verify API docs: open `http://localhost:8001/docs`

Refer to [docker-compose.yml](docker-compose.yml) for service configs.

---

**Local development — Backend**

Prerequisites: Python 3.11+, pip, Postgres (or use Docker compose above).

1. Create a virtualenv and install dependencies:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # on Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

2. Environment variables (example `.env`):

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/clinical_trials
GROQ_API_KEY=<your-groq-api-key>
GROQ_MODEL=llama-3.1-8b-instant
OLLAMA_URL=http://localhost:11434/api/generate
```

3. Initialize DB tables (SQLAlchemy creates tables on startup) and run the app:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

4. Useful backend files:
- API & router entry: [backend/app/main.py](backend/app/main.py#L1)
- Trials routes: [backend/app/api/trials.py](backend/app/api/trials.py#L1)
- Classification route: [backend/app/api/classify.py](backend/app/api/classify.py#L1)
- Ingest route: [backend/app/api/ingest.py](backend/app/api/ingest.py#L1)
- DB config: [backend/app/database/db.py](backend/app/database/db.py#L1)
- Models: [backend/app/models/trial.py](backend/app/models/trial.py#L1)
- Classifier implementation: [backend/app/services/ml_classifier.py](backend/app/services/ml_classifier.py#L1)
- Requirements: [backend/requirements.txt](backend/requirements.txt)

---

**Local development — Frontend**

1. From the repo root:

```bash
cd frontend
npm install
npm run dev
```

2. Ensure the frontend can reach the backend by setting `NEXT_PUBLIC_API_URL` (defaults in `docker-compose.yml` to `http://localhost:8001`). See [frontend/package.json](frontend/package.json) for scripts.

---

**Environment variables**
- `DATABASE_URL`: SQLAlchemy DB URL (defaults to `postgresql://postgres:postgres@localhost:5432/clinical_trials` in development). See [backend/app/database/db.py](backend/app/database/db.py#L1).
- `GROQ_API_KEY`: API key for Groq remote inference. When set, the backend uses Groq as the primary classifier.
- `GROQ_MODEL`: Groq model name to use for classification. Default is `llama-3.3-70b-versatile`; this repo also supports overrides such as `llama-3.1-8b-instant` for lower-cost tests.
- `OLLAMA_URL`: Ollama generate endpoint (e.g. `http://ollama:11434/api/generate`). Default set in [docker-compose.yml](docker-compose.yml).
- `NEXT_PUBLIC_API_URL`: Frontend API base URL (e.g. `http://localhost:8001`). See [frontend/package.json](frontend/package.json).

---

**Database & migrations**

This project uses SQLAlchemy models and Alembic for migrations. Alembic config is present at `backend/alembic.ini`.

Common commands (run from `backend`):

```bash
# generate migration after model changes
alembic revision --autogenerate -m "describe change"
# apply migrations
alembic upgrade head
```

If you prefer Docker-managed DB for local dev, `docker-compose up` will create the `db` service automatically.

---

**API reference (selected endpoints)**

Base: `GET /` → simple API metadata

- `GET /health` — health check
- `GET /trials` — list trials with pagination and filters
  - Query params: `page`, `page_size`, `search`, `phase`, `failure_category`, `overall_status`, `min_score`, `max_score`
  - See implementation: [backend/app/api/trials.py](backend/app/api/trials.py#L1)
- `GET /trials/stats` — dashboard statistics
- `GET /trials/{trial_id}` — fetch by internal id
- `GET /trials/nct/{nct_id}` — fetch by NCT identifier
- `PATCH /trials/{trial_id}` — partial update (salvageability, category, recommended actions)
- `DELETE /trials/{trial_id}` — delete trial

- `POST /classify` — classify termination reason
  - Body: `{ "why_stopped": "...", "drug_name": "...", "phase": "..." }`
  - Response: classification category, score, recommended actions. See: [backend/app/api/classify.py](backend/app/api/classify.py#L1)

- `POST /ingest` — run an ingestion synchronously
  - Query params: `max_results`, `condition`, `intervention`
- `POST /ingest/background` — enqueue ingestion as a background task
  - Triggers fetcher → classifier → upsert pipeline. See: [backend/app/api/ingest.py](backend/app/api/ingest.py#L1)

Example curl (classify):

```bash
curl -X POST "http://localhost:8001/classify" -H "Content-Type: application/json" \
  -d '{"why_stopped":"Stopped for futility at interim analysis","drug_name":"ExampleDrug","phase":"Phase 2"}'
```

---

**Project structure (key files)**
- [backend/](backend) — FastAPI backend and services
  - [backend/app/main.py](backend/app/main.py#L1) — FastAPI app entry
  - [backend/app/api/](backend/app/api) — API routes
  - [backend/app/services/](backend/app/services) — fetcher, classifier, trial service
  - [backend/app/models/](backend/app/models) — SQLAlchemy models and Pydantic schemas
- [frontend/](frontend) — Next.js frontend
- [docker-compose.yml](docker-compose.yml) — orchestrates DB, Ollama, backend, frontend

---

**Development notes & tips**
- Groq / Groq API: the project now prefers Groq with a Llama-based model as the primary classification engine. Set `GROQ_API_KEY` and optionally `GROQ_MODEL` in `.env`.
- Ollama: this project retains Ollama as a fallback. If Groq is unavailable or the Groq API key is missing, the classifier falls back to Ollama Qwen3:1.7b.
- If both Groq and Ollama fail, the system uses a BiomedBERT embeddings emergency fallback to keep classification working.
- Example low-cost override: `GROQ_MODEL=llama-3.1-8b-instant`.

**Known limitations and drawbacks**
- The new Groq primary flow introduces an external API dependency and requires a valid `GROQ_API_KEY`.
- Groq model usage may increase latency and cost compared to the previous on-prem Ollama-only setup.
- Smaller Llama variants like `llama-3.1-8b-instant` can reduce cost, but may also lower classification accuracy and confidence.
- The fallback chain helps resilience, but each step may produce different category outputs and confidence scores.
- Classification remains heuristic-driven for trial-specific failure modes; the model is not a medical-grade decision system and should be validated before production use.
- The classifier blends an LLM confidence score with rule-based baseline scores; see [backend/app/services/ml_classifier.py](backend/app/services/ml_classifier.py#L1).
- If using a remote Postgres (Heroku/Supabase), ensure `DATABASE_URL` begins with `postgresql://` (the backend auto-fixes `postgres://`).

---

**Contributing**

Contributions welcome — open an issue or PR. Suggested flow:
1. Fork repository
2. Create a feature branch
3. Run tests / verify locally
4. Open PR with description and screenshot (if UI changes)

---

**License & attribution**

This project currently does not include a license file. Add a `LICENSE` to clarify terms.

---

If you'd like, I can also:
- add API examples as a separate `docs/` folder
- generate OpenAPI examples or a Postman collection
- add CI steps for linting, tests, and Docker image builds
