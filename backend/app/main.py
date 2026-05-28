from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import trials, classify, ingest
from app.database.db import engine, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Clinical Trial Failure Intelligence System",
    description="MVP v1 - Ingests terminated clinical trials, classifies failure reasons, and recommends rescue strategies.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(trials.router, prefix="/trials", tags=["Trials"])
app.include_router(classify.router, prefix="/classify", tags=["Classification"])
app.include_router(ingest.router, prefix="/ingest", tags=["Ingestion"])


@app.get("/")
def root():
    return {
        "message": "Clinical Trial Failure Intelligence System API",
        "version": "MVP v1",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
