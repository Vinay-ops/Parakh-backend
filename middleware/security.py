"""Security headers middleware (CSP fix).

Adds HTTP response headers for Content Security Policy and other security
directives that cannot be set via <meta> tags in the frontend HTML.

Directives set here:
  - frame-ancestors 'none': blocks clickjacking in iframes (HTTP header only;
    browsers ignore this directive when set via <meta>).
  - Other security headers can be added as needed.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # frame-ancestors 'none': prevent clickjacking. Must be set as an HTTP
        # header; browsers ignore it in <meta> tags.
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"

        return response
