"""
Durable Phase 9 Correlation Projection Persistence Module for REVIVE.
Bridges the CLI execution process (Process A) and the Uvicorn/FastAPI webhook process (Process B).

Strict Invariants:
1. Truthful persistence: Phase9RuntimeContext is a durable correlation projection of recorded
   execution data, not a literal live in-memory object from a terminated process.
2. Atomic persistence: Temporary-file writes with atomic os.replace() and process-safe locking.
3. Strict recovery guard: Artifact updates to PAID/RECOVERED occur ONLY after verified signature,
   exact correlation, successful OutcomeEngine resolution with outcome == RECOVERED and
   attribution_status == DIRECTLY_OBSERVED.
4. Delivery idempotency: Authoritative event-id tracking preserved across process boundaries.
5. Zero secrets logged or persisted.
"""

import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.entities import Plan
from app.models.events import BaseEvent
from app.intervention.schemas import InterventionDecision
from app.execution.schemas import ExecutionAuditRecord
from app.outcome.schemas import OutcomeRecord, OutcomeType, AttributionStatus

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PHASE9_CONTEXT_PATH = (
    _PROJECT_ROOT / "docs" / "evidence" / "phase9_razorpay_runtime_context.json"
)
DEFAULT_PHASE9_ARTIFACT_PATH = (
    _PROJECT_ROOT / "docs" / "evidence" / "phase9_razorpay_sandbox_demo.json"
)


@contextlib.contextmanager
def file_lock(lock_path: Path, timeout: float = 5.0, poll_interval: float = 0.05):
    """
    Cross-platform process-safe atomic file lock.
    Uses atomic os.open(..., O_CREAT | O_EXCL) to guarantee single-writer safety
    under concurrent or near-simultaneous webhook deliveries.
    """
    lock_file = str(lock_path)
    start = time.time()
    fd = None
    while True:
        try:
            fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            # Check for stale lock (older than 30s)
            try:
                if time.time() - os.path.getmtime(lock_file) > 30.0:
                    os.remove(lock_file)
                    continue
            except OSError:
                pass

            if time.time() - start >= timeout:
                raise TimeoutError(f"Could not acquire lock on {lock_path} within {timeout}s")
            time.sleep(poll_interval)
        except OSError:
            if time.time() - start >= timeout:
                raise TimeoutError(f"OS error acquiring lock on {lock_path} within {timeout}s")
            time.sleep(poll_interval)

    try:
        yield
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.remove(lock_file)
            except OSError:
                pass


def atomic_write_json(target_path: Path, data: Dict[str, Any]) -> None:
    """
    Atomically write JSON data to target_path using a temporary sibling file and os.replace().
    Prevents torn reads or corrupted state across concurrent processes.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f"{target_path.name}.tmp.{os.getpid()}_{int(time.time() * 1000)}")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, target_path)
    except Exception:
        if temp_path.exists():
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise


class Phase9RuntimeContext(BaseModel):
    """
    Durable Phase 9 Correlation Projection.
    Provides verifiable, authoritative execution and policy context bridging the
    CLI demonstration runner (Process A) and the webhook ingestion server (Process B).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    payload_id: str
    execution_id: str
    decision_id: str
    customer_id: str
    provider_reference: Optional[str] = None
    short_url: Optional[str] = None
    decision: Dict[str, Any]
    plan: Dict[str, Any]
    execution_record: Dict[str, Any]
    customer_events: List[Dict[str, Any]] = Field(default_factory=list)
    processed_event_ids: List[str] = Field(default_factory=list)
    created_at: str
    updated_at: str

    def get_decision(self) -> InterventionDecision:
        """Hydrate authoritative InterventionDecision from persisted projection."""
        return InterventionDecision.model_validate(self.decision)

    def get_plan(self) -> Plan:
        """Hydrate authoritative Plan from persisted projection."""
        return Plan.model_validate(self.plan)

    def get_execution_record(self) -> ExecutionAuditRecord:
        """Hydrate authoritative ExecutionAuditRecord from persisted projection."""
        return ExecutionAuditRecord.model_validate(self.execution_record)

    def get_customer_events(self) -> List[BaseEvent]:
        """Hydrate observable customer BaseEvents from persisted projection."""
        return [BaseEvent.model_validate(e) for e in self.customer_events]


def save_phase9_runtime_context(
    context: Phase9RuntimeContext,
    path: Optional[Path] = None,
) -> None:
    """Save Phase9RuntimeContext atomically with process locking."""
    target_path = path or DEFAULT_PHASE9_CONTEXT_PATH
    lock_path = target_path.with_suffix(".lock")

    with file_lock(lock_path):
        data = context.model_dump(mode="json")
        atomic_write_json(target_path, data)


def load_phase9_runtime_context(
    path: Optional[Path] = None,
) -> Optional[Phase9RuntimeContext]:
    """
    Load Phase9RuntimeContext from disk.
    Returns None if file does not exist or fails validation.
    """
    target_path = path or DEFAULT_PHASE9_CONTEXT_PATH
    if not target_path.exists():
        return None

    lock_path = target_path.with_suffix(".lock")
    try:
        with file_lock(lock_path, timeout=3.0):
            with open(target_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            return Phase9RuntimeContext.model_validate(raw_data)
    except Exception:
        return None


def is_phase9_event_processed(
    event_id: str,
    path: Optional[Path] = None,
) -> bool:
    """Check whether a webhook event ID has already been processed in persistent context."""
    if not event_id or not event_id.strip():
        return False
    ctx = load_phase9_runtime_context(path=path)
    if not ctx:
        return False
    return event_id.strip() in ctx.processed_event_ids


def update_phase9_event_processed(
    event_id: str,
    path: Optional[Path] = None,
) -> None:
    """
    Record a successfully processed webhook event ID in persistent Phase9RuntimeContext.
    Thread-safe and process-safe via atomic replace and file lock.
    """
    clean_id = event_id.strip() if event_id else ""
    if not clean_id:
        return

    target_path = path or DEFAULT_PHASE9_CONTEXT_PATH
    lock_path = target_path.with_suffix(".lock")

    with file_lock(lock_path):
        if not target_path.exists():
            return
        with open(target_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        ctx = Phase9RuntimeContext.model_validate(raw_data)
        if clean_id not in ctx.processed_event_ids:
            ctx.processed_event_ids.append(clean_id)
            ctx.updated_at = datetime.now(timezone.utc).isoformat()
            atomic_write_json(target_path, ctx.model_dump(mode="json"))


def update_phase9_demo_artifact_on_recovery(
    outcome_record: OutcomeRecord,
    event_id: str,
    artifact_path: Optional[Path] = None,
    context_path: Optional[Path] = None,
) -> bool:
    """
    Update docs/evidence/phase9_razorpay_sandbox_demo.json ONLY after verified recovery.

    Guard Requirements:
    - outcome == RECOVERED
    - attribution_status == DIRECTLY_OBSERVED

    Transitions:
    - payment_status = PAID
    - webhook_status = PROCESSED
    - outcome_status = RECOVERED
    - attribution_status = DIRECTLY_OBSERVED

    Returns True if updated, False if skipped due to non-recovery.
    """
    outcome_val = (
        outcome_record.outcome.value
        if hasattr(outcome_record.outcome, "value")
        else str(outcome_record.outcome)
    )
    attr_val = (
        outcome_record.attribution_status.value
        if hasattr(outcome_record.attribution_status, "value")
        else str(outcome_record.attribution_status)
    )

    # Strict invariant check: do not claim recovery unless OutcomeEngine confirmed RECOVERED + DIRECTLY_OBSERVED
    if outcome_val != "RECOVERED" or attr_val != "DIRECTLY_OBSERVED":
        return False

    target_artifact = artifact_path or DEFAULT_PHASE9_ARTIFACT_PATH
    lock_path = target_artifact.with_suffix(".lock")

    with file_lock(lock_path):
        if not target_artifact.exists():
            return False

        with open(target_artifact, "r", encoding="utf-8") as f:
            demo_data = json.load(f)

        now_iso = datetime.now(timezone.utc).isoformat()
        demo_data["execution_status"] = "EXECUTED"
        demo_data["payment_status"] = "PAID"
        demo_data["webhook_status"] = "PROCESSED"
        demo_data["outcome_status"] = outcome_val
        demo_data["attribution_status"] = attr_val

        if "timestamps" not in demo_data:
            demo_data["timestamps"] = {}
        demo_data["timestamps"]["webhook_timestamp"] = now_iso
        demo_data["timestamps"]["outcome_timestamp"] = now_iso

        atomic_write_json(target_artifact, demo_data)

    # Also record event ID in runtime context
    update_phase9_event_processed(event_id, path=context_path)
    return True
