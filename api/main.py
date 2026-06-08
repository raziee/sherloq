from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import analyze, catalog, jobs

WEB_ROOT = Path(__file__).resolve().parents[1] / "web" / "static"

app = FastAPI(
    title="Sherloq Forensics API",
    description="Web API for digital image forensic analysis tools from Sherloq.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router, prefix="/api/v1", tags=["catalog"])
app.include_router(analyze.router, prefix="/api/v1", tags=["analyze"])
app.include_router(jobs.router, prefix="/api/v1", tags=["jobs"])

if WEB_ROOT.exists():
    app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


@app.get("/")
def index():
    index_file = WEB_ROOT / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Sherloq API is running", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok"}
