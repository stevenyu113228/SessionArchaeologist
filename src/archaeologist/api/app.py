"""FastAPI application — REST API for SessionArchaeologist."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from archaeologist.api.routes import sessions, turns, chunks, narratives, pipeline, search, export

app = FastAPI(
    title="SessionArchaeologist",
    description="Transform Claude Code session histories into research narratives",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(turns.router, prefix="/api/sessions", tags=["turns"])
app.include_router(chunks.router, prefix="/api/sessions", tags=["chunks"])
app.include_router(narratives.router, prefix="/api/sessions", tags=["narratives"])
app.include_router(pipeline.router, prefix="/api", tags=["pipeline"])
app.include_router(search.router, prefix="/api/sessions", tags=["search"])
app.include_router(export.router, prefix="/api/sessions", tags=["export"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
