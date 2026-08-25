"""
Main FastAPI Application Entry Point for REVIVE Presentation Layer.
Exposes /health and mounts dashboard presentation router.
"""

from fastapi import FastAPI
from app.api.dashboard import router as dashboard_router
from app.api.schemas import HealthCheckResponse

app = FastAPI(
    title="REVIVE AI Engine — Presentation API",
    description="Thin presentation layer for REVIVE autonomous revenue recovery engine.",
    version="1.0.0",
)

app.include_router(dashboard_router)


@app.get("/health", response_model=HealthCheckResponse)
def health_check() -> HealthCheckResponse:
    """Service health check endpoint."""
    return HealthCheckResponse(status="ok", service="revive-api")
