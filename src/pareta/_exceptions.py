"""Typed error hierarchy for the Pareta SDK.

The backend is FastAPI, so error bodies are `{"detail": "<message>"}` with a
standard HTTP status. We map status → a specific exception so callers can
`except pareta.InsufficientCreditsError` instead of sniffing status codes.

Status → exception mapping:
    400 → BadRequestError
    401 → AuthenticationError      ("invalid API key")
    402 → InsufficientCreditsError ("organization is out of credit…")
    404 → NotFoundError
    409 → ConflictError            (seed/legacy endpoint not deployed)
    422 → BadRequestError          (FastAPI validation)
    429 → RateLimitError
    5xx → APIStatusError (incl. 503 EndpointNotReadyError for stopped/booting)
"""

from __future__ import annotations


class ParetaError(Exception):
    """Base class for every error raised by the SDK."""


class APIConnectionError(ParetaError):
    """The request never reached the server (DNS, TCP, TLS, timeout)."""

    def __init__(self, message: str = "connection error", *, cause: BaseException | None = None):
        super().__init__(message)
        self.__cause__ = cause


class APITimeoutError(APIConnectionError):
    """The request timed out before a response was received."""

    def __init__(self, message: str = "request timed out", *, cause: BaseException | None = None):
        super().__init__(message, cause=cause)


class APIStatusError(ParetaError):
    """The server returned a non-2xx status.

    Attributes:
        status_code: the HTTP status.
        detail:      the server's `detail` message (or the raw body).
        request_id:  value of the `x-request-id` response header, if present.
        response:    the underlying httpx.Response (for advanced use).
    """

    status_code: int

    def __init__(self, message: str, *, status_code: int, detail=None, request_id=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
        self.request_id = request_id
        self.response = response


class BadRequestError(APIStatusError):       # 400, 422
    pass


class AuthenticationError(APIStatusError):   # 401
    pass


class PermissionDeniedError(APIStatusError):  # 403
    pass


class NotFoundError(APIStatusError):         # 404


    pass


class ConflictError(APIStatusError):         # 409
    pass


class InsufficientCreditsError(APIStatusError):  # 402
    """The org is out of credit. Top up in the dashboard (billing is browser-only)."""


class RateLimitError(APIStatusError):        # 429
    pass


class EndpointNotReadyError(APIStatusError):  # 503 — cold / provider down
    """The serving capacity behind the request isn't ready yet (cold-starting
    or provider down) — retryable."""


def error_from_response(status_code: int, *, detail, request_id, response) -> APIStatusError:
    """Construct the most specific APIStatusError subclass for a status code."""
    message = detail if isinstance(detail, str) and detail else f"HTTP {status_code}"
    cls = _STATUS_MAP.get(status_code)
    if cls is None:
        cls = RateLimitError if status_code == 429 else APIStatusError
    return cls(message, status_code=status_code, detail=detail, request_id=request_id, response=response)


_STATUS_MAP: dict[int, type[APIStatusError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    402: InsufficientCreditsError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: BadRequestError,
    429: RateLimitError,
    503: EndpointNotReadyError,
}
