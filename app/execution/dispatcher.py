"""
Execution Dispatcher Boundary for Revive Phase 6.
Provides an explicit abstraction separating test-mode execution simulation from live payment infrastructure,
guaranteeing structurally that no live Razorpay mutations occur in TEST_MODE.
"""

from typing import Optional
from app.execution.schemas import InterventionPayload


class ExecutionDispatcher:
    """Abstract interface for intervention recovery workflow dispatchers."""

    def dispatch(
        self,
        payload: InterventionPayload,
        environment: str,
        simulated_failure: Optional[str] = None,
    ) -> Optional[str]:
        """
        Dispatch an intervention payload in the given execution environment.
        Returns None if dispatch succeeded, or a failure reason string if dispatch failed.
        """
        raise NotImplementedError("Subclasses must implement dispatch()")


class TestModeDispatcher(ExecutionDispatcher):
    """
    Deterministic Test-Mode Dispatcher.
    Enforces absolute sandbox isolation: raises RuntimeError if invoked outside TEST_MODE.
    """

    def dispatch(
        self,
        payload: InterventionPayload,
        environment: str,
        simulated_failure: Optional[str] = None,
    ) -> Optional[str]:
        if environment != "TEST_MODE":
            raise RuntimeError(
                f"Live execution dispatcher is blocked. REVIVE Phase 6 operates strictly in TEST_MODE sandbox. Provided environment: '{environment}'."
            )

        # In TEST_MODE, payload target_url MUST be a simulated URI (sim://revive/...)
        if payload.target_url and not payload.target_url.startswith("sim://revive/"):
            raise ValueError(
                f"Unsafe target URL '{payload.target_url}' in TEST_MODE. Expected sim://revive/... scheme."
            )

        # Return simulated failure if passed, otherwise return None (success)
        return simulated_failure
