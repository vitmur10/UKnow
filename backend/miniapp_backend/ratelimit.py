import time
import ipaddress

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse


def _client_ip(request):
    # Forwarded headers are client-controlled unless Apache/Cloudflare is a
    # known trusted proxy. Never let a public client rotate the rate-limit key.
    remote_addr = request.META.get("REMOTE_ADDR", "")
    trusted = remote_addr in getattr(settings, "TRUSTED_PROXY_IPS", {"127.0.0.1"})
    if trusted:
        forwarded = request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("HTTP_X_FORWARDED_FOR")
        candidate = (forwarded or "").split(",")[0].strip()
        try:
            ipaddress.ip_address(candidate)
            return candidate
        except ValueError:
            pass
    return remote_addr or "unknown"


class ApiRateLimitMiddleware:
    """
    Simple in-process / cache-based rate limiter for Django /api/ paths.

    Works correctly with Daphne single-worker.  If Redis cache backend is
    used with multi-worker processes the counters are still shared but
    may slightly overshoot during cache TTL boundaries – acceptable for
    a light anti-abuse barrier.
    """

    _SLOT_SECONDS = 60
    _SENSITIVE_PATHS = [
        ("/api/miniapp/auth/", 30),
        ("/api/miniapp/bootstrap/", 30),
    ]
    _MEDIA_LIMIT = 90
    _GENERAL_LIMIT = 120

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not getattr(settings, "RATE_LIMIT_ENABLED", True):
            return self.get_response(request)
        if not request.path.startswith("/api/"):
            return self.get_response(request)

        ip = _client_ip(request)
        path = request.path

        try:
            for prefix, limit in self._SENSITIVE_PATHS:
                if path.startswith(prefix):
                    if self._exceeds(ip, f"s:{prefix}", limit):
                        return JsonResponse({"error": "Too many requests"}, status=429)
                    return self.get_response(request)

            if "/media/" in path:
                if self._exceeds(ip, "m:", self._MEDIA_LIMIT):
                    return JsonResponse({"error": "Too many requests"}, status=429)
            else:
                if self._exceeds(ip, "g:", self._GENERAL_LIMIT):
                    return JsonResponse({"error": "Too many requests"}, status=429)
        except Exception:
            # If the cache backend is temporarily unavailable, let the
            # request through rather than blocking legitimate traffic.
            pass

        return self.get_response(request)

    def _exceeds(self, ip, scope, limit):
        bucket = int(time.time()) // self._SLOT_SECONDS
        key = f"rl:api:{bucket}:{scope}:{ip}"
        count = cache.get(key, 0)
        if count >= limit:
            return True
        cache.set(key, count + 1, self._SLOT_SECONDS + 10)
        return False
