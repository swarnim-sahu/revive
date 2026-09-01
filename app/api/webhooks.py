"""
Razorpay Webhook Route Handler for REVIVE Presentation & Integration API.
Receives raw HTTP request body, extracts Razorpay headers, and delegates to RazorpayWebhookHandler.
"""

from typing import Optional
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.integrations.razorpay.webhook import RazorpayWebhookHandler, ReviveRuntimeContext
from app.integrations.razorpay.config import DEFAULT_RAZORPAY_CONFIG

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Authoritative shared application runtime context
_runtime_context: Optional[ReviveRuntimeContext] = None


def get_runtime_context() -> ReviveRuntimeContext:
    """Retrieve or initialize the authoritative shared application ReviveRuntimeContext."""
    global _runtime_context
    if _runtime_context is None:
        _runtime_context = ReviveRuntimeContext(config=DEFAULT_RAZORPAY_CONFIG)
    return _runtime_context


def set_runtime_context(context: ReviveRuntimeContext) -> None:
    """Set or override the authoritative shared application ReviveRuntimeContext (used in DI/testing)."""
    global _runtime_context
    _runtime_context = context


def get_webhook_handler() -> RazorpayWebhookHandler:
    """Retrieve the RazorpayWebhookHandler bound to the shared runtime context."""
    return get_runtime_context().webhook_handler


def set_webhook_handler(handler: RazorpayWebhookHandler) -> None:
    """Override or set the active RazorpayWebhookHandler on the shared runtime context."""
    context = get_runtime_context()
    context.webhook_handler = handler


@router.post("/razorpay")
async def handle_razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    x_razorpay_event_id: Optional[str] = Header(None, alias="X-Razorpay-Event-Id"),
) -> JSONResponse:
    """
    Ingest, verify, deduplicate, and process incoming Razorpay webhooks.
    Operates strictly on the raw body bytes for HMAC-SHA256 signature verification.
    """
    raw_body = await request.body()
    handler = get_webhook_handler()

    status_code, response_data = handler.process_webhook(
        raw_body=raw_body,
        signature=x_razorpay_signature,
        event_id_header=x_razorpay_event_id,
    )

    return JSONResponse(status_code=status_code, content=response_data)
