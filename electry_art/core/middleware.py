from __future__ import annotations

import uuid
import logging
from typing import Callable

log = logging.getLogger("electryart.errors")


class RequestIdMiddleware:
    """
    Добавя request_id към request + връща X-Request-ID header в response.
    """
    def __init__(self, get_response: Callable):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        response = self.get_response(request)
        response["X-Request-ID"] = request.request_id
        return response


class ErrorBoundaryMiddleware:
    """
    Глобален boundary: хваща unhandled exceptions, логва ги с request_id и контекст,
    после re-raise (за да си остане стандартният Django 500 flow).
    """
    def __init__(self, get_response: Callable):
        self.get_response = get_response

    def __call__(self, request):
        
        try:
            return self.get_response(request)
        except Exception:  # noqa: BLE001
            rid = getattr(request, "request_id", None)
            user_id = getattr(getattr(request, "user", None), "pk", None)
            log.exception(
                "UNHANDLED_EXCEPTION path=%s method=%s request_id=%s user_id=%s",
                getattr(request, "path", ""),
                getattr(request, "method", ""),
                rid,
                user_id,
            )
            raise
