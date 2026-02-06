import logging
from django.dispatch import Signal
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver


# Fired when a user successfully registers
# We will pass: user (required)
user_registered = Signal()


# Loggers
logger = logging.getLogger("electryart.user_profiles")
audit_logger = logging.getLogger("electryart.audit")


def _client_ip(request):
    if not request:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "unknown"
    name, domain = email.split("@", 1)
    if len(name) <= 1:
        return f"*@{domain}"
    return f"{name[0]}***@{domain}"


@receiver(user_logged_in)
def log_user_logged_in(sender, request, user, **kwargs):
    ip = _client_ip(request)
    logger.info("User logged in. user_id=%s ip=%s", user.pk, ip)
    audit_logger.info("LOGIN_SUCCESS user_id=%s ip=%s", user.pk, ip)


@receiver(user_logged_out)
def log_user_logged_out(sender, request, user, **kwargs):
    ip = _client_ip(request)
    user_id = getattr(user, "pk", None)
    logger.info("User logged out. user_id=%s ip=%s", user_id, ip)
    audit_logger.info("LOGOUT user_id=%s ip=%s", user_id, ip)


@receiver(user_login_failed)
def log_user_login_failed(sender, credentials, request, **kwargs):
    ip = _client_ip(request)
    identifier = credentials.get("username") or credentials.get("email") or "unknown"
    logger.warning("Login failed. identifier=%s ip=%s", identifier, ip)
    audit_logger.info("LOGIN_FAILED identifier=%s ip=%s", identifier, ip)

