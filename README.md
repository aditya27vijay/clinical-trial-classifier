# Clinical Trial Failure Intelligence System

Molecule-first AI system for ingesting failed clinical trials, classifying why they stopped, estimating rescue potential, and generating molecule intelligence insights.

---

## Table of Contents
- Overview
- Architecture
- Key features
- Quickstart (Docker)
- Local development
- Environment variables
- API reference
- Data model
- Project structure
- Notes
- Contributing

---

## Overview

This repository contains an MVP for analyzing terminated, withdrawn, and suspended clinical trials and surfacing potentially salvageable drug assets.
The backend reads trial data from an AACT-style Postgres source, enriches each trial with design and results metadata, classifies trial failure reason through a layered LLM pipeline, computes a salvageability score, resolves drugs into canonical molecules, and enriches molecules with patent and PubMed evidence.

The frontend is a Next.js app that provides dashboards, trial browsing, molecule discovery, classification experiments, and ingestion controls.

---

## Architecture

The stack consists of:

- `backend/` — FastAPI backend with SQLAlchemy persistence, ingestion logic, classification/scoring services, and molecule intelligence.
- `frontend/` — Next.js UI that consumes backend endpoints.
- `docker-compose.yml` — orchestrates Postgres, Ollama, backend, and frontend.

### Core pipeline

1. Fetch terminated trial metadata from an AACT-compatible Postgres database.
2. Enrich trials with design, sponsor, site, safety, outcome, and publication metadata.
3. Classify termination reasons using:
   - Groq remote model (primary)
   - Ollama local model (fallback)
   - BiomedBERT embeddings (emergency fallback)
4. Compute a three-tier salvageability score.
5. Persist trials into `failed_trials`.
6. Resolve trial drug names into canonical `molecules` records.
7. Enrich molecules with patents, literature, and optional repurposing hypotheses.

---

## Key features

- Ingestion of terminated/withdrawn/suspended trials from AACT Postgres
- LLM-backed failure category classification
- Three-tier salvageability scoring model
- Canonical molecule resolution using PubChem and ChEMBL
- Molecule library with IP status, publication counts, and rescue signals
- Excel export for BD-ready molecule reporting
- Frontend dashboard, trial list, molecule library, classification page, and ingestion page
- Background enrichment for patents and PubMed literature

---

## Quickstart (Docker)

From the repository root:

```bash
docker-compose up -d --build
```

Default ports:

- Postgres: `5433`
- Ollama: `11434`
- Backend: `8001`
- Frontend: `3001`

Open the backend docs at `http://localhost:8001/docs` and the frontend at `http://localhost:3001`.

> Note: `docker-compose.yml` includes `AACT_DATABASE_URL` and expects a valid AACT/ctgov Postgres data source.

---

## Local development

### Backend

1. Create and activate a virtual environment:

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate   # Windows
pip install -r requirements.txt
```

2. Create a `.env` file with:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/clinical_trials
AACT_DATABASE_URL=postgresql://user:pass@host:5432/aact
AACT_SCHEMA=ctgov
OLLAMA_URL=http://localhost:11434/api/generate
GROQ_API_KEY=<your-groq-api-key>
GROQ_MODEL=llama-3.1-8b-instant
NCBI_API_KEY=<optional>
```

3. Start the backend:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

From the root:

```bash
cd frontend
npm install
npm run dev
```

If the backend runs on a non-default port, set `NEXT_PUBLIC_API_URL` accordingly.

---

## Environment variables

- `DATABASE_URL` — backend persistence database URL.
- `AACT_DATABASE_URL` — AACT Postgres source for trial ingestion.
- `AACT_SCHEMA` — AACT schema name, default `ctgov`.
- `OLLAMA_URL` — Ollama generation endpoint.
- `OLLAMA_MODEL` — Ollama model name, default `qwen3:1.7b`.
- `GROQ_API_KEY` — Groq API key for remote inference.
- `GROQ_MODEL` — Groq model name, default `llama-3.3-70b-versatile`.
- `NCBI_API_KEY` — Optional NCBI key for PubMed requests.
- `NEXT_PUBLIC_API_URL` — frontend backend base URL.

---

## API reference

### Health

- `GET /` — API metadata
- `GET /health` — health check

### Trials

- `GET /trials` — list trials with pagination and filters
- `GET /trials/stats` — dashboard statistics
- `GET /trials/{trial_id}` — retrieve trial by ID
- `GET /trials/nct/{nct_id}` — retrieve trial by NCT ID
- `PATCH /trials/{trial_id}` — update a trial
- `DELETE /trials/{trial_id}` — delete a trial

### Classification

- `POST /classify` — classify a termination reason
  - Example payload: `{ "why_stopped": "Stopped for futility at interim analysis" }`

### Ingestion

- `POST /ingest` — run ingestion synchronously
- `POST /ingest/background` — enqueue ingestion in background

### Molecules

- `GET /molecules` — list molecules
- `GET /molecules/stats` — molecule library stats
- `GET /molecules/export` — export molecules as Excel
- `GET /molecules/{id}` — view molecule detail
- `POST /molecules/{id}/hypotheses` — generate repurposing hypotheses

---

## Data model

### Trial model

- `failed_trials` — stores ingested trial metadata, classification results, salvageability scores, and scoring breakdowns.

### Molecule intelligence

- `molecules` — canonical molecule registry with PubChem/ChEMBL resolution, modality, mechanism, target biology, aggregated trial signals, IP, and literature.
- `molecule_trials` — links trials to molecules.
- `molecule_patents` — patent records per molecule.
- `molecule_literature` — PubMed publications per molecule.

---

## Project structure

- `backend/app/main.py` — FastAPI app entrypoint
- `backend/app/database/db.py` — SQLAlchemy engine and session
- `backend/app/api/` — REST route definitions
- `backend/app/models/` — SQLAlchemy and Pydantic models
- `backend/app/services/` — ingestion, classification, scoring, resolution, enrichment, and CRUD logic
- `frontend/pages/` — Next.js dashboard, classify, ingest, trials, and molecules pages
- `frontend/services/api.ts` — frontend API client
- `docker-compose.yml` — dev orchestration

---

## Notes

- The ingestion pipeline is built for an AACT-compatible Postgres source, not the ClinicalTrials.gov REST API.
- If `GROQ_API_KEY` is absent, the backend falls back to Ollama and then to an embeddings-based fallback.
- Molecule resolution depends on PubChem and ChEMBL public APIs.
- `openpyxl` is required for the `/molecules/export` endpoint.

---

## Contributing

Contributions welcome. Suggested flow:
1. Fork the repository
2. Create a feature branch
3. Verify locally
4. Open a PR with a description

---

## License

This repository currently does not include a license file. Add a `LICENSE` to clarify terms.

If you'd like, I can also:
- add API examples as a separate `docs/` folder
- generate OpenAPI examples or a Postman collection
- add CI steps for linting, tests, and Docker image builds
