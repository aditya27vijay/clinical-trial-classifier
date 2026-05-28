# ⚕ Clinical Trial Failure Intelligence System — MVP v1

> Ingest terminated clinical trials from ClinicalTrials.gov, classify failure reasons, score salvageability, and generate rescue strategies.

---

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────┐
│  Next.js Frontend   │────▶│  FastAPI Backend      │────▶│  PostgreSQL │
│  (TailwindCSS)      │     │  (Python 3.11)        │     │  Database   │
│  localhost:3000     │     │  localhost:8000       │     │  port:5432  │
└─────────────────────┘     └──────────────────────┘     └─────────────┘
                                      │
                                      ▼
                            ClinicalTrials.gov API v2
                            https://clinicaltrials.gov
```

---

## Quick Start (Docker — Recommended)

### Prerequisites
- Docker & Docker Compose installed

### 1. Clone and start
```bash
cd clinical-trial-intelligence
docker-compose up --build
```

### 2. Wait for all services to start (~60s first time)

### 3. Open the app
- **Frontend:** http://localhost:3001
- **Backend API docs:** http://localhost:8001/docs

### 4. Ingest your first batch of trials
Go to **http://localhost:3000/ingest** and click **Run Ingestion** with default settings.

---

## Manual Setup (No Docker)

### Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL 14+

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your DATABASE_URL

# Run database migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env.local
# Edit .env.local — set NEXT_PUBLIC_API_URL=http://localhost:8000

# Start dev server
npm run dev
```

---

## Usage Workflow

### Step 1: Ingest Data
Navigate to `/ingest` and trigger ingestion from ClinicalTrials.gov.
- Set `max_results` (start with 50-100)
- Optionally filter by condition (e.g. "cancer") or drug
- Click **Run Ingestion** — takes 30-60s

### Step 2: Explore Dashboard
The `/` dashboard shows:
- Total trials, average salvageability score
- Failure category distribution chart
- Top 5 most salvageable assets

### Step 3: Browse & Filter Trials
Navigate to `/trials` to:
- Search by drug name, disease, sponsor, or NCT ID
- Filter by failure category, phase, status
- Set minimum salvageability score

### Step 4: Review Trial Details
Click any trial to see:
- Full termination reason
- AI-classified failure category
- Salvageability score (0–100 gauge)
- Specific rescue recommendations
- Links to ClinicalTrials.gov and PubMed

### Step 5: Use the Classifier
Go to `/classify` to test classification on any custom text:
```
"Study terminated due to insufficient enrollment at trial sites"
→ Recruitment failure | Score: 80 | Recommendations: ...
```

---

## API Reference

### Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/trials/` | List all trials (paginated, filterable) |
| GET | `/trials/stats` | Dashboard statistics |
| GET | `/trials/{id}` | Fetch single trial by ID |
| GET | `/trials/nct/{nct_id}` | Fetch trial by NCT ID |
| POST | `/classify/` | Classify a termination reason |
| POST | `/ingest/` | Trigger ClinicalTrials.gov ingestion |

Full interactive docs at: **http://localhost:8000/docs**

### Example: Classify a Reason
```bash
curl -X POST http://localhost:8000/classify/ \
  -H "Content-Type: application/json" \
  -d '{"why_stopped": "Study stopped due to futility at interim analysis"}'
```

Response:
```json
{
  "why_stopped": "Study stopped due to futility at interim analysis",
  "failure_category": "Lack of efficacy",
  "salvageability_score": 25,
  "recommended_actions": [
    "Investigate biomarker-stratified patient subgroups",
    "Explore combination therapy approaches",
    ...
  ]
}
```

---

## Classification Logic

| Failure Category | Keywords (examples) | Base Score |
|------------------|---------------------|------------|
| Business termination | sponsor decision, portfolio, funding | 85 |
| Recruitment failure | enrollment, accrual, insufficient patients | 80 |
| Operational issue | protocol deviation, site closure, supply | 70 |
| Endpoint failure | primary endpoint not met, futility | 60 |
| Lack of efficacy | no benefit, no response, not effective | 25 |
| Toxicity | adverse event, hepatotoxic, safety concern | 20 |
| Unknown | (no match) | 40 |

**Score modifiers:**
- Phase 1 trials: +5 (earlier stage = more room for optimization)
- Severe adverse events (fatal/death): -15
- Partial efficacy signals detected in text: +10

---

## Deployment

### Backend → Docker / Render / Railway
```bash
docker build -t ctfis-backend ./backend
docker run -p 8000:8000 -e DATABASE_URL=... ctfis-backend
```

### Frontend → Vercel
```bash
cd frontend
npx vercel deploy
# Set NEXT_PUBLIC_API_URL to your backend URL
```

### Database → Supabase
1. Create a project at supabase.com
2. Copy the connection string from Settings → Database
3. Set it as `DATABASE_URL` in backend `.env`
4. Run `alembic upgrade head`

---

## Project Structure

```
clinical-trial-intelligence/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── api/
│   │   │   ├── trials.py        # Trial CRUD endpoints
│   │   │   ├── classify.py      # Classification endpoint
│   │   │   └── ingest.py        # Ingestion endpoint
│   │   ├── models/
│   │   │   ├── trial.py         # SQLAlchemy model
│   │   │   └── schemas.py       # Pydantic schemas
│   │   ├── services/
│   │   │   ├── classifier.py    # Rule-based NLP classifier
│   │   │   ├── fetcher.py       # ClinicalTrials.gov API client
│   │   │   └── trial_service.py # CRUD service layer
│   │   └── database/
│   │       └── db.py            # DB connection & session
│   ├── migrations/              # Alembic migrations
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic.ini
├── frontend/
│   ├── pages/
│   │   ├── index.tsx            # Dashboard
│   │   ├── trials/
│   │   │   ├── index.tsx        # Trial list
│   │   │   └── [id].tsx         # Trial detail
│   │   ├── classify.tsx         # Classifier tool
│   │   └── ingest.tsx           # Data ingestion
│   ├── components/
│   │   ├── Layout.tsx           # Sidebar + nav
│   │   └── ui/index.tsx         # Reusable UI components
│   ├── services/api.ts          # API client
│   └── styles/globals.css       # Design system
├── docker-compose.yml
└── README.md
```

---

## Extending the MVP

Once MVP is validated, the PRD specifies these next-phase features:
- **PubMed integration** — link trials to publications
- **ML classifier** — replace keyword rules with a trained model
- **Vector search** — semantic similarity across trial descriptions
- **Knowledge graphs** — drug-disease-mechanism relationships
- **Patent analysis** — IP landscape for salvageable assets

---

## License

MIT
