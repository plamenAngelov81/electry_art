import logging

sec = logging.getLogger("django.security")

SUSPICIOUS_PATHS = (
    "/.env",
    "/wp-admin",
    "/admin.php",
    "/.git",
    "/phpmyadmin",
)


class SecurityEventsMiddleware:
    """
    Logs suspicious access + permission issues into security.log
    Includes request_id for cross-log tracing.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = getattr(request, "request_id", None)
        ip = request.META.get("REMOTE_ADDR")
        user_id = getattr(getattr(request, "user", None), "pk", None)

        # suspicious path detection
        path_lower = (request.path or "").lower()
        if any(p in path_lower for p in SUSPICIOUS_PATHS):
            sec.warning(
                "SUSPICIOUS_PATH path=%s ip=%s request_id=%s",
                request.path,
                ip,
                rid,
            )

        response = self.get_response(request)

        # permission denied
        if response.status_code == 403:
            sec.warning(
                "PERMISSION_DENIED path=%s method=%s user_id=%s ip=%s request_id=%s",
                request.path,
                request.method,
                user_id,
                ip,
                rid,
            )

        return response
