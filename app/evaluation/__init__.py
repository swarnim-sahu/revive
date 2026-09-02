"""
Evaluation package for REVIVE Phase B Controlled Experimentation and Incremental Revenue Proof.
"""

from app.evaluation.schemas import (
    ControlCaseRecord,
    TreatmentCaseRecord,
    PairedCaseResult,
    ComparativeEconomics,
    DiagnosisAccuracySummary,
    InterventionAppropriatenessSummary,
    DecisionFunnelSummary,
    SafetyGovernanceSummary,
    ThroughputSummary,
    ExceptionRecord,
    ExperimentMetadata,
    PhaseBEvaluationResult,
)
from app.evaluation.control import ControlEvaluator
from app.evaluation.exceptions import ExceptionLedger
from app.evaluation.batch import EvaluationResponseSimulator
from app.evaluation.phase_b import (
    PhaseBEvaluator,
    ConversionClassification,
    classify_treatment_conversion,
    determine_paired_increment,
)
from app.evaluation.reporting import PhaseBReportGenerator

__all__ = [
    "ControlCaseRecord",
    "TreatmentCaseRecord",
    "PairedCaseResult",
    "ComparativeEconomics",
    "DiagnosisAccuracySummary",
    "InterventionAppropriatenessSummary",
    "DecisionFunnelSummary",
    "SafetyGovernanceSummary",
    "ThroughputSummary",
    "ExceptionRecord",
    "ExperimentMetadata",
    "PhaseBEvaluationResult",
    "ControlEvaluator",
    "ExceptionLedger",
    "EvaluationResponseSimulator",
    "ConversionClassification",
    "classify_treatment_conversion",
    "determine_paired_increment",
    "PhaseBEvaluator",
    "PhaseBReportGenerator",
]
