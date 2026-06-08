# Clinical Trial Intelligence Project Overview

This document summarizes the full technical architecture, flow, and implementation details of the `clinical-trial-intelligence` project.

## 1. Project Purpose

The repository is an MVP for analyzing terminated clinical trials and estimating whether failed assets remain salvageable.
The system ingests trial metadata, classifies the termination reason, computes a rescue score, and builds a molecule-first intelligence layer for repurposing, BD outreach, and patent/literature insight.

## 2. High-level Architecture

- `backend/` contains a FastAPI service, database models, ingestion logic, classification, scoring, molecule resolution, and persistence.
- `frontend/` contains a Next.js UI, API client, and pages for dashboard, ingestion, classification experiments, trial browsing, and molecule intelligence.
- `docker-compose.yml` orchestrates:
  - Postgres DB
  - Ollama inference service
  - Backend API
  - Frontend app

## 3. Backend Flow

### 3.1 Entry Point

- `backend/app/main.py`
  - Creates the FastAPI app.
  - Loads database metadata and creates tables with SQLAlchemy.
  - Mounts routers for `/trials`, `/classify`, `/ingest`, and `/molecules`.
  - Exposes root `/` and `/health` endpoints.

### 3.2 API Routes

#### `/classify`
- Defined in `backend/app/api/classify.py`
- Accepts rich `ClassifyRequest` payload with:
  - `why_stopped` (required)
  - Tier 1 fields: `drug_name`, `phase`, `condition`, `sponsor_class`, `enrollment`, `num_sites`, `allocation`, etc.
  - Tier 2 fields: `publication_count`, `has_results`, `collaborator_count`, `detailed_description`, etc.
  - Tier 3 results fields: `completion_rate`, `sae_count`, `sae_rate`, `death_count`, `has_results_section`.
- Builds internal context keys using `_build_context_from_request`.
- Calls `full_analysis(...)` from `backend/app/services/ml_classifier.py`.
- Returns `ClassifyResponse` with:
  - `failure_category`
  - `salvageability_score`
  - `recommended_actions`
  - `data_confidence`
  - `score_breakdown`
  - optional warning if context is sparse.

#### `/trials`
- Defined in `backend/app/api/trials.py`
- Provides CRUD and query endpoints:
  - `GET /trials` list with pagination and filters
  - `GET /trials/stats` dashboard totals
  - `GET /trials/{trial_id}`
  - `GET /trials/nct/{nct_id}`
  - `PATCH /trials/{trial_id}` to update a trial
  - `DELETE /trials/{trial_id}`
- Uses `backend/app/services/trial_service.py` for DB operations.

#### `/ingest`
- Defined in `backend/app/api/ingest.py`
- Uses `AACTFetcher` and `MLClassifier` to fetch and classify trials from an AACT database.
- Offers both synchronous ingestion (`POST /ingest/`) and background enqueue (`POST /ingest/background`).
- For each trial:
  - checks DB by `nct_id`
  - enriches trial details via `AACTFetcher.enrich_trial_with_design_and_outcomes`
  - classifies with `MLClassifier.classify`
  - persists a `FailedTrial` record in DB
  - resolves the primary drug name into a deduplicated `Molecule` record
  - links the trial to the molecule via `MoleculeTrial`
  - triggers background enrichment for patents and literature

#### `/molecules`
- Defined in `backend/app/api/molecules_api.py`
- Provides molecule-first intelligence:
  - `GET /molecules/` list + filter library
  - `GET /molecules/stats` summary dashboard metrics
  - `GET /molecules/export` BD-ready Excel export
  - `GET /molecules/{id}` full molecule detail
  - `POST /molecules/{id}/hypotheses` trigger LLM repurposing hypothesis generation
- Uses `backend/app/services/molecule_service.py` for molecule CRUD, linking, aggregation, and enrichment.

### 3.3 Ingestion + Molecule Enrichment

- The ingest pipeline now includes molecule resolution and enrichment.
- After each trial is scored and stored, the backend resolves the trial drug via `backend/app/services/molecule_resolver.py`.
- Molecule resolution uses:
  - `PubChem` exact name and synonym lookup
  - `ChEMBL` molecule search for mechanism, targets, and modality
  - INN stem heuristics to infer modality for biologics, gene therapy, RNA, cell therapy, and small molecules
- Resolved molecules are upserted into the `molecules` table and linked to trials via `molecule_trials`.
- Aggregate molecule signals are recomputed after linking each trial:
  - `total_trials`, `total_indications`, `failure_categories`, `best_salvageability`, `avg_salvageability`, `latest_phase_reached`
- Background enrichment loads value-add BD signals:
  - USPTO patent records via `backend/app/services/patent_fetcher.py`
  - PubMed literature via `backend/app/services/pubmed_fetcher.py`
  - updates molecule IP status, expiry, publication counts, and PMIDs

### 3.4 Database

- `backend/app/database/db.py`
  - Loads `.env` values with `python-dotenv`.
  - Defines `DATABASE_URL` and normalizes `postgres://` to `postgresql://`.
  - Creates SQLAlchemy engine and session maker.
  - Exposes `get_db()` dependency.

- `backend/app/models/trial.py`
  - SQLAlchemy model `FailedTrial` maps to `failed_trials`.
  - Columns include `nct_id`, `title`, `condition`, `drug_name`, `phase`, `why_stopped`, `failure_category`, `salvageability_score`, `recommended_actions`, `data_confidence`, `score_breakdown`, `created_at`, `updated_at`.

- `backend/app/models/molecule_model.py`
  - SQLAlchemy model `Molecule` maps to `molecules`.
  - Tracks canonical identity, chemistry IDs, modality, mechanism, targets, aggregate rescue signals, patent/IP metadata, literature counts, and BD signals.
  - Associated tables include `molecule_trials`, `molecule_patents`, `molecule_literature`.

- `backend/app/models/schemas.py`
  - Pydantic schemas for request/response validation.
  - Defines `TrialBase`, `TrialCreate`, `TrialUpdate`, `TrialResponse`, `ClassifyRequest`, `ClassifyResponse`, `TrialListResponse`, `DashboardStats`.

## 4. Classification & Scoring Implementation

### 4.1 Primary classification pipeline

- `backend/app/services/ml_classifier.py` is the main classifier.
- Core pipeline in `full_analysis(...)` does:
  1. `category, confidence, llm_result, source = _classify(text, ctx)`
  2. `score, data_confidence, score_breakdown = compute_three_tier_score(...)`
  3. `recs = get_recommendations(category, modality)`
- `full_analysis` returns category, final score, recommendations, confidence label, and full breakdown.

### 4.2 LLM fallbacks

- The classifier is layered:
  1. `Groq` primary via `_classify_with_groq`
  2. `Ollama` fallback via `_classify_with_ollama`
  3. `BiomedBERT` emergency fallback via `_classify_with_embeddings`

- `Groq` behavior:
  - Uses env vars `GROQ_API_KEY` and `GROQ_MODEL`.
  - Calls `https://api.groq.com/openai/v1/chat/completions`.
  - Sends a JSON prompt with `SYSTEM_PROMPT` and trial context.
  - Expects response JSON with `category`, `confidence`, and extra fields.
  - Retries once on 429 rate-limit.

- `Ollama` behavior:
  - Calls local Ollama container at `OLLAMA_URL`.
  - Uses `qwen3:1.7b` by default.
  - Parses a JSON-formatted response from `resp.json().get('response')`.

- `BiomedBERT` fallback:
  - Uses sentence-transformers `pritamdeka/S-PubMedBert-MS-MARCO`.
  - Computes cosine similarity to fixed category reference sentences.
  - Provides a best-match category when both remote LLMs fail.

### 4.3 System prompt and context

- `SYSTEM_PROMPT` is a long medical expert instruction that defines seven categories:
  - `Recruitment failure`
  - `Business termination`
  - `Lack of efficacy`
  - `Toxicity`
  - `Endpoint failure`
  - `Operational issue`
  - `Unknown`
- It also includes classification rules and salvageability signal definitions.
- `_build_trial_context(...)` converts trial data into a compact prompt with fields such as:
  - `title`, `termination reason`, `drug`, `condition`, `phase`
  - `sponsor type`, `enrollment`, `design`, `duration`, safety summary, results presence, and disease area flags.

### 4.4 Category validation

- Valid categories are enforced with `VALID_CATEGORIES` list.
- If a returned category is not valid, it falls back to `Unknown`.

### 4.5 Recommendation generation

- Base recommendations are defined in `RECOMMENDATIONS` for each category.
- Additional `MODALITY_RECOMMENDATIONS` add drug modality-specific suggestions when modality is detected.
- Modality detection is performed by `detect_modality(...)`.

## 5. Salvageability Scoring

Implemented in `backend/app/services/scorer.py`.

### 5.1 Three-tier design

- Tier 1: Protocol fields (60% of score)
- Tier 2: Contextual enrichment (25%)
- Tier 3: Results data (15%, override when present)
- LLM signal adjustments are applied after combining tiers.

### 5.2 Tier 1 components

The score uses multiple protocol signals:
- phase scoring
- enrollment size
- trial duration
- sponsor class
- number of sites
- intervention model type
- FDA regulation flag
- disease area flags
- randomization allocation
- number of secondary outcomes

Results are scaled to 60 points, then multiplied by a confidence-blended category multiplier.

### 5.3 Category multiplier blending

- `CATEGORY_MULTIPLIERS` assigns a multiplier per failure category.
- Examples:
  - `Business termination`: 1.0
  - `Recruitment failure`: 0.90
  - `Endpoint failure`: 0.65
  - `Lack of efficacy`: 0.35
  - `Toxicity`: 0.25
- If confidence is below 0.75, the multiplier blends toward `Unknown` (0.60).

### 5.4 Tier 2 contextual signals

Tier 2 awards points for:
- expanded access status
- collaborator count
- publication count
- related studies
- results posted

Each signal is worth up to 5 points.

### 5.5 Tier 3 results override

If `_t3_has_results_section` is present, Tier 3 can add or subtract score based on:
- completion rate
- SAE rate
- death count penalty
- primary outcomes reported

This tier is treated as an authoritative adjustment when results are available.

### 5.6 LLM signal adjustments

Post-combination adjustments use LLM-extracted fields:
- `partial_efficacy_signal`
- `severity`
- `early_phase`
- `has_results_data`
- `large_unmet_need`
- `salvageability_modifier`

These can add or subtract up to ±20 points.

### 5.7 Output breakdown

`compute_three_tier_score(...)` returns a structured breakdown with:
- tier1/tier2/tier3 scores and components
- llm_adjustments
- combined_pre_llm
- final score
- data confidence label
- category multiplier and confidence

## 6. Ingestion / AACT Fetcher

### 6.1 AACTFetcher

- `backend/app/services/aact_fetcher.py`
- Connects to an AACT Postgres database via SQLAlchemy.
- Requires `AACT_DATABASE_URL` environment variable.
- `fetch_terminated_trials(...)` retrieves terminated trials with optional `condition` and `intervention` filters.
- `enrich_trial_with_design_and_outcomes(nct_id)` fetches detailed metadata for a single trial, such as:
  - drug names and conditions
  - design fields (`allocation`, `intervention_model`, `primary_purpose`, `masking`)
  - eligibility criteria count
  - collaborators and sponsor class
  - facility count / number of sites
  - computed trial duration
  - derived disease flags (`is_oncology`, `is_cns`)
  - safety outcomes from reported events if results exist

### 6.2 Ingest pipeline in `/ingest`

- Fetches trial list from AACT.
- For each trial:
  - checks for existing DB row by `nct_id`
  - enriches trial data further
  - calls the classification pipeline
  - inserts a `Trial` record with classification results and metadata.
  - resolves the primary drug and upserts a deduplicated molecule record
  - links the trial to the molecule and recalculates molecule-level aggregates
  - enqueues background patent and literature enrichment
- Logs success or failure for each trial.

## 7. Frontend Architecture

### 7.1 API client

- `frontend/services/api.ts`
- Uses `axios` to call backend endpoints.
- Exposes helper methods for:
  - listing trials
  - fetching stats
  - fetching trial detail by ID or NCT
  - classification
  - ingestion trigger
  - molecule library queries
  - molecule stats and detail fetches
  - molecule export and hypothesis generation

### 7.2 Pages

#### `frontend/pages/index.tsx`
- Dashboard page.
- Loads `/trials/stats`.
- Renders summary cards and charts using `recharts`.

#### `frontend/pages/classify.tsx`
- Single text input page for classification experiments.
- Calls `/classify/` with a termination reason string.
- Displays category, score, and recommendations.

#### `frontend/pages/ingest.tsx`
- Ingestion form for running data fetch.
- Sends parameters to `/ingest/`.
- Shows fetched/inserted/skipped counts.

#### `frontend/pages/trials/index.tsx`
- Trial listing page.
- Supports search, category filter, phase filter, status filter, and minimum score.
- Displays trial rows sorted by salvageability.

#### `frontend/pages/trials/[id].tsx`
- Trial detail view.
- Shows metadata, score gauge, recommendations, termination reason, and external links.

#### `frontend/pages/molecules/molecules_index.tsx`
- Molecule library page.
- Lists deduplicated molecules derived from failed trials.
- Supports filters for search, modality, minimum score, IP status, and publications.
- Displays aggregate BD signals like best salvageability, trial count, publication count, and IP state.

#### `frontend/pages/molecules/molecules_detail.tsx`
- Molecule detail page.
- Shows chemical identity, mechanism, targets, patent/IP summary, linked failed trials, literature, and repurposing hypotheses.
- Supports on-demand hypothesis generation via the `/molecules/{id}/hypotheses` endpoint.

### 7.3 UI components

- `frontend/components/Layout.tsx` wraps page content with header/navigation.
- `frontend/components/ui/index.tsx` contains reusable UI elements like `ScoreBadge`, `CategoryChip`, `StatusChip`, `PhaseBadge`, `Spinner`, `Skeleton`, `EmptyState`.
- Styling uses Tailwind CSS and custom CSS variables in `frontend/styles/globals.css`.

## 8. Deployment & Environment

### 8.1 Docker Compose

- `docker-compose.yml` defines services:
  - `db` → Postgres 15
  - `ollama` → local Ollama container
  - `backend` → FastAPI app served by uvicorn
  - `frontend` → Next.js dev server
- Backend environment supports `GROQ_API_KEY` and `GROQ_MODEL`.
- Frontend reads `NEXT_PUBLIC_API_URL`.

### 8.2 Environment variables

Key env vars used in the project:
- `DATABASE_URL` for backend Postgres
- `AACT_DATABASE_URL` for AACT ingestion source
- `OLLAMA_URL` for Ollama inference
- `GROQ_API_KEY` and `GROQ_MODEL` for Groq inference
- `NEXT_PUBLIC_API_URL` for frontend API base URL

### 8.3 Dependencies

- Backend dependencies: FastAPI, Uvicorn, SQLAlchemy, psycopg2, Pydantic, requests, python-dotenv, pandas, Alembic, sentence-transformers, transformers, torch, scikit-learn, groq.
- Frontend dependencies: Next.js, React, Recharts, axios, lucide-react, clsx, Tailwind CSS.

## 9. Important Files and Their Roles

- `backend/app/main.py` — FastAPI entrypoint
- `backend/app/api/classify.py` — classification endpoint
- `backend/app/api/ingest.py` — ingestion endpoint and molecule-resolving ingest workflow
- `backend/app/api/trials.py` — trial CRUD / queries
- `backend/app/api/molecules_api.py` — molecule library API, exports, detail views, hypothesis generation
- `backend/app/services/ml_classifier.py` — LLM / scoring pipeline
- `backend/app/services/scorer.py` — three-tier salvageability scoring
- `backend/app/services/aact_fetcher.py` — AACT metadata ingestion
- `backend/app/services/molecule_resolver.py` — PubChem / ChEMBL drug resolution and modality inference
- `backend/app/services/molecule_service.py` — molecule DB CRUD, linking, aggregation, patent and literature upserts
- `backend/app/services/patent_fetcher.py` — USPTO patent record retrieval and IP status determination
- `backend/app/services/pubmed_fetcher.py` — PubMed literature retrieval for molecules
- `backend/app/services/trial_service.py` — DB CRUD
- `backend/app/database/db.py` — SQLAlchemy database config
- `backend/app/models/trial.py` — SQLAlchemy trial model
- `backend/app/models/molecule_model.py` — SQLAlchemy molecule models
- `backend/app/models/schemas.py` — Pydantic request/response model
- `frontend/services/api.ts` — JS API client
- `frontend/pages/*.tsx` — UI pages for dashboard, classify, ingest, trials, molecules
- `docker-compose.yml` — service orchestration

## 10. Current Technical Notes

- The project currently blends remote LLM inference with rule-based scoring.
- The primary scoring path is in `ml_classifier.py`; the older `backend/app/services/classifier.py` contains a simpler rule-based fallback that does not appear to be used by the current API router.
- The ingestion flow is built around an AACT database schema, not the ClinicalTrials.gov REST API.
- A new molecule intelligence layer now deduplicates drug assets, enriches chemical identity, tracks patent/IP and literature, and generates repurposing hypotheses.
- The frontend is a thin React/Next.js client that depends on the backend for all business logic.
- The system is not production-hardened: classification relies on external LLM responses and the scoring model is heuristic.

---

This file is intended as a technical summary for reviewers, maintainers, or Claude-style analysis of the project.
