from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Optional

audit_logger = logging.getLogger("electryart.audit")


def mask_email(email: Optional[str]) -> str:
    if not email or "@" not in email:
        return "unknown"
    name, domain = email.split("@", 1)
    if len(name) <= 1:
        return f"*@{domain}"
    return f"{name[0]}***@{domain}"


@dataclass(frozen=True)
class Actor:
    type: str  # "user" | "guest" | "staff"
    id: Optional[int] = None


def audit_event(
    event: str,
    *,
    actor: Actor,
    request_id: Optional[str] = None,
    order_id: Optional[int] = None,
    serial: Optional[str] = None,
    status_from: Optional[str] = None,
    status_to: Optional[str] = None,
    email_mask: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    payload: dict[str, Any] = {
        "event": event,
        "actor_type": actor.type,
        "actor_id": actor.id,
    }
    if request_id:
        payload["request_id"] = request_id
    if order_id is not None:
        payload["order_id"] = order_id
    if serial:
        payload["serial"] = serial
    if status_from:
        payload["status_from"] = status_from
    if status_to:
        payload["status_to"] = status_to
    if email_mask:
        payload["email"] = email_mask
    if extra:
        payload.update(extra)

    # Записваме като key=value една линия (лесно за grep)
    msg = " ".join(f"{k}={v}" for k, v in payload.items())
    audit_logger.info(msg)
