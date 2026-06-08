from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import trials, classify, ingest, molecules_api as molecules
from app.database.db import engine, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Clinical Trial Failure Intelligence System",
    description="Molecule-first drug rescue intelligence for biologists and BD teams.",
    version="MVP v4 — Molecule Intelligence",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trials.router,    prefix="/trials",    tags=["Trials"])
app.include_router(classify.router,  prefix="/classify",  tags=["Classification"])
app.include_router(ingest.router,    prefix="/ingest",    tags=["Ingestion"])
app.include_router(molecules.router, prefix="/molecules", tags=["Molecules"])


@app.get("/")
def root():
    return {
        "message": "Clinical Trial Failure Intelligence System API",
        "version": "MVP v4",
        "docs":    "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}