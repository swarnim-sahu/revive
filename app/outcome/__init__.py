"""
Phase 7 Outcome Measurement & Revenue Attribution Package.
Export key schemas, configuration, observer, resolver, attribution, revenue, engine, and evaluation modules.
"""

from app.outcome.config import DEFAULT_OUTCOME_CONFIG, OutcomeConfig
from app.outcome.schemas import (
    AttributionMethod,
    AttributionStatus,
    OutcomeRecord,
    OutcomeType,
)
from app.outcome.observer import EventObserver
from app.outcome.resolver import OutcomeResolver
from app.outcome.attribution import AttributionEngine
from app.outcome.revenue import RevenueCalculator
from app.outcome.engine import OutcomeEngine
from app.outcome.evaluation import OutcomeEvaluator

__all__ = [
    "OutcomeConfig",
    "DEFAULT_OUTCOME_CONFIG",
    "OutcomeType",
    "AttributionStatus",
    "AttributionMethod",
    "OutcomeRecord",
    "EventObserver",
    "OutcomeResolver",
    "AttributionEngine",
    "RevenueCalculator",
    "OutcomeEngine",
    "OutcomeEvaluator",
]
