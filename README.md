# Clinical Trial Intelligence MVP

A molecule-first intelligence platform for analyzing failed clinical trials, classifying why they stopped, estimating salvage potential, and surfacing repurposing opportunities for drug assets.

## What this system does

The current codebase combines:

- trial ingestion from an AACT-compatible PostgreSQL source
- enrichment with design, sponsor, site, safety, and outcome metadata
- AI-assisted failure classification with a layered inference pipeline
- three-tier salvageability scoring for rescue potential
- canonical molecule resolution and deduplication
- molecule-level intelligence such as trial history, patent/IP signals, literature, and repurposing hypotheses
- a Next.js frontend for exploration and workflow control

## Current architecture

- Backend: FastAPI + SQLAlchemy + Pydantic
- Frontend: Next.js + React + Tailwind
- Data store: PostgreSQL
- Inference stack: NVIDIA/NIM-style chat API as primary, Ollama as fallback, embedding-based fallback for resilience
- Enrichment: PubChem, ChEMBL, PubMed, patent/IP lookups, and real-world indication signals

## Major capabilities

### 1. Trial ingestion and enrichment

The backend can ingest terminated, withdrawn, or suspended trials from an AACT-style database and enrich each record with:

- trial design data
- sponsor and site metadata
- enrollment and duration context
- safety and outcome information
- reason for stopping and related trial context

### 2. AI-assisted failure classification

The main classifier in backend/app/services/ml_classifier.py evaluates trial context and classifies the primary failure reason into one of:

- Recruitment failure
- Business termination
- Lack of efficacy
- Toxicity
- Endpoint failure
- Operational issue
- Unknown

It also produces:

- a confidence score
- a salvageability modifier
- recommendation hints
- structured scoring metadata

### 3. Three-tier salvageability scoring

The scoring engine in backend/app/services/scorer.py computes a rescue score based on:

- protocol and design signals (Tier 1)
- contextual enrichment (Tier 2)
- results and safety evidence (Tier 3)

The score is adjusted with modality-aware heuristics and LLM-derived signals.

### 4. Molecule intelligence layer

After a trial is classified and stored, the system resolves the primary drug into a canonical molecule record and links it to the trial. The molecule layer now supports:

- PubChem and ChEMBL-based resolution
- modality inference
- mechanism and target extraction
- aggregate rescue metrics per molecule
- usage timeline tracking across linked trials
- real-world indication/approval signals
- patent/IP enrichment
- PubMed literature enrichment
- repurposing hypothesis generation

### 5. BD-ready exports and exploration UI

The product includes:

- a dashboard overview of trial volume and failure pattern distributions
- a searchable failed-trials browser with score-based ranking
- a molecule library with filters for modality, score, IP status, and publications
- molecule detail pages with chemical identity, linked trials, patent/IP summary, literature, and hypotheses
- Excel export for molecule intelligence reporting

## Backend API surface

### Health

- GET /
- GET /health

### Trials

- GET /trials/
- GET /trials/stats
- GET /trials/{trial_id}
- GET /trials/nct/{nct_id}
- PATCH /trials/{trial_id}
- DELETE /trials/{trial_id}

### Classification

- POST /classify/

### Ingestion

- POST /ingest/
- POST /ingest/background

### Molecules

- GET /molecules/
- GET /molecules/stats
- GET /molecules/export
- GET /molecules/{molecule_id}
- GET /molecules/{molecule_id}/timeline
- GET /molecules/{molecule_id}/real-world-usage
- POST /molecules/{molecule_id}/hypotheses

## Frontend experience

The UI includes pages for:

- dashboard overview
- failed trial review and filtering
- trial detail inspection
- molecule library browsing
- molecule detail exploration
- ingestion workflow initiation
- classification experiments

## Environment variables

The backend expects the following environment variables:

- DATABASE_URL — PostgreSQL URL for the application database
- AACT_DATABASE_URL — source database for AACT-style ingestion
- AACT_SCHEMA — schema name used for the AACT source (defaults to ctgov where applicable)
- NVIDIA_API_KEY — primary model provider API key
- NVIDIA_MODEL — primary model identifier
- OLLAMA_URL — local Ollama endpoint
- OLLAMA_MODEL — Ollama model name
- NCBI_API_KEY — optional PubMed API key
- NEXT_PUBLIC_API_URL — frontend base URL for the backend

## Local development

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

Create a .env file and then start the API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker

```bash
docker-compose up -d --build
```

Default service ports:

- PostgreSQL: 5433
- Ollama: 11434
- Backend: 8001
- Frontend: 3001

## Project structure

- backend/app/main.py — FastAPI application entrypoint
- backend/app/api/ — route modules for trials, classification, ingestion, and molecules
- backend/app/services/ — scoring, classifier, ingestion, molecule resolution, and enrichment services
- backend/app/models/ — SQLAlchemy and Pydantic models
- frontend/pages/ — dashboard, trials, molecules, ingestion, and classification UI
- frontend/services/api.ts — frontend API client
- docker-compose.yml — local orchestration for DB, Ollama, backend, and frontend

## Notes

- The ingestion flow is designed for AACT-compatible PostgreSQL sources rather than the ClinicalTrials.gov REST endpoint directly.
- The current API uses the ML-based classifier pipeline rather than the older simpler rule-based classifier.
- Molecule enrichment and hypothesis generation may run asynchronously after ingestion.
- The Excel export endpoint requires openpyxl.

## Contributing

Contributions are welcome. A typical workflow is:

1. fork the repository
2. create a feature branch
3. verify the relevant backend/frontend behavior locally
4. open a pull request with a summary of the changes

