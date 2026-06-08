# Clinical Trial Intelligence Skill Context

This document is intended to give Claude a concise, project-specific view of how `clinical-trial-intelligence` is built, how the architecture has evolved, and where the key responsibilities live.

## Core project purpose

- The app is an MVP for analyzing terminated clinical trials and estimating whether failed assets are salvageable.
- It started as a trial-focused intelligence system and has been extended into a molecule-first rescue intelligence layer.
- The goal is to surface failed drug assets, classify why they stopped, score rescue potential, and add molecule-centric BD and repurposing signals.

## Architecture overview

- `backend/` is a FastAPI service with SQLAlchemy models, ingest logic, classification, scoring, and molecule intelligence.
- `frontend/` is a Next.js UI with pages for dashboards, ingestion control, trial browsing, and molecule library/detail views.
- `docker-compose.yml` brings up Postgres, Ollama, backend, and frontend.

## Backend responsibilities

- `backend/app/main.py` wires the app and exposes routers under `/trials`, `/classify`, `/ingest`, and `/molecules`.
- `backend/app/api/ingest.py` is the ingest pipeline entrypoint.
  - Uses `AACTFetcher` to source terminated trials from AACT.
  - Classifies and scores trials with `backend/app/services/ml_classifier.py` and `backend/app/services/scorer.py`.
  - Persists scored trials to `failed_trials`.
  - Resolves the trial drug to a molecule record and links the trial to that molecule.
  - Kicks off background enrichment for patents and PubMed literature.
- `backend/app/api/molecules_api.py` exposes molecule-first endpoints, including list, stats, export, detail, and hypothesis generation.
- `backend/app/services/molecule_resolver.py` resolves drug names through PubChem, ChEMBL, and INN stem heuristics to derive modality, targets, and identifiers.
- `backend/app/services/molecule_service.py` manages deduplication, molecule trial linking, aggregate signal computation, patent/literature upserts, and query helpers.
- `backend/app/models/molecule_model.py` defines the molecule intelligence schema, including molecules, molecule_trials, molecule_patents, and molecule_literature.

## Classification and scoring

- `backend/app/services/ml_classifier.py` is the primary classification pipeline.
  - It first tries Groq, falls back to Ollama, and finally uses an embedding-based BiomedBERT fallback.
  - It builds a trial context prompt and extracts category, confidence, and heuristics used in scoring.
- `backend/app/services/scorer.py` computes a three-tier salvageability score:
  - Tier 1: protocol/design fields
  - Tier 2: contextual enrichment
  - Tier 3: results data override when results are available
  - It also applies category-based multipliers and LLM-derived salvageability adjustments.

## Molecule intelligence

- The new molecule layer transforms per-trial evidence into deduplicated drug assets.
- Molecules are resolved via PubChem/ChEMBL and enriched with modality, mechanism, targets, and identifiers.
- Linked failed trials feed molecule aggregates such as total trials, indications, best and average salvageability, latest phase reached, and categorized failure counts.
- Background enrichment adds patent/IP metadata and PubMed literature counts, increasing molecule BD signal value.
- On-demand repurposing hypotheses are generated through an LLM endpoint at `/molecules/{id}/hypotheses`.

## Frontend responsibilities

- `frontend/pages/index.tsx` is the main dashboard.
- `frontend/pages/classify.tsx` is a classification experiment page.
- `frontend/pages/ingest.tsx` is the ingestion controller.
- `frontend/pages/trials/index.tsx` and `frontend/pages/trials/[id].tsx` are trial browsing and detail views.
- `frontend/pages/molecules/molecules_index.tsx` is the molecule library page.
- `frontend/pages/molecules/molecules_detail.tsx` is the molecule detail page with chemical identity, IP/literature, linked trials, and hypothesis generation.

## Development context

- The architecture has been evolving from a pure trial analysis tool into a molecule-first intelligence platform.
- New development has focused on:
  - adding molecule deduplication and drug identity resolution
  - linking failed trials to molecules
  - computing molecule-level rescue aggregates
  - enriching molecules with patents and PubMed literature
  - adding molecule library/detail UI pages
  - exposing BD export and hypothesis generation
- The project is not production hardened; it is built as an experimental MVP with heuristic scoring and LLM dependencies.

## Best way to use this context

- Use this skill as a reference for how ingestion, classification, scoring, and molecule enrichment are connected.
- When making changes, keep the separation between trial scoring and molecule intelligence clear.
- Prefer updating the molecule layer through `molecule_service.py`, `molecule_resolver.py`, and `molecules_api.py` when adding new molecule signals.
