"""
Centralized Configuration for Revive Root-Cause Diagnosis Engine (Phase 4).
Contains all evidence weights, thresholds, ambiguity margins, confidence boundaries,
and configuration versioning.
"""

from dataclasses import dataclass

DIAGNOSIS_CONFIG_VERSION = "1.0.0"


@dataclass(frozen=True)
class DiagnosisConfig:
    """Centralized diagnostic scoring weights and operational thresholds."""

    # Evidence weights
    strong_weight: float = 1.00
    moderate_weight: float = 0.60
    weak_weight: float = 0.25
    contradictory_weight: float = -0.40

    # Operational & Decision thresholds
    min_evidence_threshold: float = 0.30
    ambiguity_margin: float = 0.15
    risk_eligibility_threshold: float = 0.30  # risk_score < 0.30 -> NO_MEANINGFUL_RISK

    # Diagnostic confidence boundaries
    confidence_medium_threshold: float = 0.50
    confidence_high_threshold: float = 0.75
    confidence_very_high_threshold: float = 0.90

    # Config version
    config_version: str = DIAGNOSIS_CONFIG_VERSION


# Global default configuration instance
DEFAULT_DIAGNOSIS_CONFIG = DiagnosisConfig()
