"""
Main FastAPI Application Entry Point for REVIVE Presentation Layer.
Exposes /health and mounts dashboard presentation router.
Includes CORS middleware configured for local development frontend origins.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dashboard import router as dashboard_router
from app.api.webhooks import router as webhooks_router
from app.api.schemas import HealthCheckResponse

app = FastAPI(
    title="REVIVE AI Engine — Presentation API",
    description="Thin presentation layer for REVIVE autonomous revenue recovery engine.",
    version="1.0.0",
)

# CORS configuration for local development frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router)
app.include_router(webhooks_router)


@app.get("/health", response_model=HealthCheckResponse)
def health_check() -> HealthCheckResponse:
    """Service health check endpoint."""
    return HealthCheckResponse(status="ok", service="revive-api")
