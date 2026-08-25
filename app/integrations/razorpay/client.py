"""
Razorpay Client Abstraction Module for Revive Phase 9.
Provides BaseRazorpayClient interface, deterministic MockRazorpayClient for offline testing,
and RazorpaySandboxClient for sandbox integration.
"""

from abc import ABC, abstractmethod
import base64
import json
import time
import urllib.error
import urllib.request
from typing import Dict, Optional, Set, Tuple

from app.integrations.razorpay.config import DEFAULT_RAZORPAY_CONFIG, RazorpayConfig
from app.integrations.razorpay.schemas import (
    RazorpayPaymentLinkRequest,
    RazorpayPaymentLinkResponse,
)


class BaseRazorpayClient(ABC):
    """Abstract interface for Razorpay API interactions."""

    @abstractmethod
    def create_payment_link(
        self,
        request: RazorpayPaymentLinkRequest,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[Optional[RazorpayPaymentLinkResponse], Optional[str]]:
        """
        Create a payment link.
        Returns (response_model, error_message).
        """
        pass


class MockRazorpayClient(BaseRazorpayClient):
    """
    Deterministic Mock Razorpay Client for offline sandbox testing.
    Zero network access. Guarantees reproducible responses and idempotency tracking.
    """

    def __init__(self, config: RazorpayConfig = DEFAULT_RAZORPAY_CONFIG) -> None:
        self.config = config
        self.processed_idempotency_keys: Set[str] = set()
        self.created_links: Dict[str, RazorpayPaymentLinkResponse] = {}
        self.simulated_failure_reason: Optional[str] = None
        self.last_request: Optional[RazorpayPaymentLinkRequest] = None

    def create_payment_link(
        self,
        request: RazorpayPaymentLinkRequest,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[Optional[RazorpayPaymentLinkResponse], Optional[str]]:
        self.last_request = request

        if self.simulated_failure_reason:
            return None, self.simulated_failure_reason

        key = idempotency_key or request.reference_id

        # Idempotency check: if key was already processed, return existing link response
        if key in self.processed_idempotency_keys:
            if key in self.created_links:
                return self.created_links[key], None
            return None, f"Idempotent duplicate request '{key}' rejected"

        self.processed_idempotency_keys.add(key)

        link_id = f"plink_mock_{request.reference_id}"
        short_url = f"https://rzp.io/i/mock_{request.reference_id}"

        response = RazorpayPaymentLinkResponse(
            payment_link_id=link_id,
            short_url=short_url,
            status="created",
            reference_id=request.reference_id,
            amount=request.amount,
            currency=request.currency,
            created_at=int(time.time()),
        )
        self.created_links[key] = response
        return response, None


class RazorpaySandboxClient(BaseRazorpayClient):
    """
    Real Razorpay Sandbox API Client.
    Connects to api.razorpay.com/v1 endpoints when credentials exist.
    """

    def __init__(self, config: RazorpayConfig = DEFAULT_RAZORPAY_CONFIG) -> None:
        self.config = config

    def create_payment_link(
        self,
        request: RazorpayPaymentLinkRequest,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[Optional[RazorpayPaymentLinkResponse], Optional[str]]:
        if not self.config.key_id or not self.config.key_secret:
            return None, "Razorpay authentication failed: missing KEY_ID or KEY_SECRET credentials"

        url = f"{self.config.base_url.rstrip('/')}/payment_links"

        # Build request body payload
        payload_dict = {
            "amount": request.amount,
            "currency": request.currency,
            "accept_partial": request.accept_partial,
            "description": request.description,
            "customer": {
                "name": request.customer.name,
                "email": request.customer.email,
                "contact": request.customer.contact,
            },
            "notify": request.notify,
            "reminder_enable": request.reminder_enable,
            "reference_id": request.reference_id,
            "callback_url": request.callback_url,
            "callback_method": request.callback_method,
        }

        payload_dict["customer"] = {k: v for k, v in payload_dict["customer"].items() if v is not None}
        if request.callback_url is None:
            payload_dict.pop("callback_url", None)

        json_bytes = json.dumps(payload_dict).encode("utf-8")

        # Encode Basic Auth credentials
        creds = f"{self.config.key_id}:{self.config.key_secret}".encode("utf-8")
        auth_header = f"Basic {base64.b64encode(creds).decode('ascii')}"

        headers = {
            "Content-Type": "application/json",
            "Authorization": auth_header,
        }
        if idempotency_key or request.reference_id:
            headers["X-Razorpay-Idempotency"] = idempotency_key or request.reference_id

        http_req = urllib.request.Request(
            url=url,
            data=json_bytes,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(http_req, timeout=self.config.request_timeout_seconds) as resp:
                resp_bytes = resp.read()
                resp_str = resp_bytes.decode("utf-8")
                data = json.loads(resp_str)

                response_model = RazorpayPaymentLinkResponse(
                    payment_link_id=str(data.get("id", data.get("payment_link_id", ""))),
                    short_url=str(data.get("short_url", "")),
                    status=str(data.get("status", "created")),
                    reference_id=str(data.get("reference_id", request.reference_id)),
                    amount=int(data.get("amount", request.amount)),
                    currency=str(data.get("currency", request.currency)),
                    created_at=int(data.get("created_at", int(time.time()))),
                )
                return response_model, None

        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass

            safe_err = f"Razorpay API Error HTTP {e.code}: {e.reason}"
            if "error" in err_body.lower():
                try:
                    err_json = json.loads(err_body)
                    desc = err_json.get("error", {}).get("description")
                    if desc:
                        safe_err = f"Razorpay API Error HTTP {e.code}: {desc}"
                except Exception:
                    pass

            return None, safe_err

        except urllib.error.URLError as e:
            return None, f"Razorpay connection error: {e.reason}"

        except TimeoutError:
            return None, "Razorpay request timed out"

        except json.JSONDecodeError:
            return None, "Razorpay returned malformed JSON response"

        except Exception as e:
            err_msg = str(e)
            if self.config.key_secret and self.config.key_secret in err_msg:
                err_msg = err_msg.replace(self.config.key_secret, "[REDACTED]")
            return None, f"Razorpay request failed: {err_msg}"
