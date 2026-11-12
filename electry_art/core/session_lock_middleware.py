"""Serialize requests sharing a Django DB-backed session.

Must run OUTSIDE SessionMiddleware so the lock covers both session loading
and SessionMiddleware's final save during response processing.
PostgreSQL session-level advisory locks are released in finally.
"""
import hashlib

from django.conf import settings
from django.db import connection


class SessionRequestLockMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        if not session_key:
            return self.get_response(request)

        # An exact 64-bit signed integer, stable across workers/processes.
        digest = hashlib.sha256(session_key.encode("utf-8")).digest()
        lock_id = int.from_bytes(digest[:8], byteorder="big", signed=True)

        # Do not silently fall back to unsafe concurrency behavior.
        if connection.vendor != "postgresql":
            raise RuntimeError("SessionRequestLockMiddleware requires PostgreSQL.")

        # pg_advisory_lock is SESSION-scoped, not transaction-scoped.
        # It must be acquired and released on the same DB connection.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [lock_id])
        try:
            return self.get_response(request)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])
