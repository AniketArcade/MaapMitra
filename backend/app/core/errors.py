class DomainError(Exception):
    """Raised by services; mapped to an HTTP response by the handler in app.main."""

    status_code = 400

    def __init__(self, detail: str, *, clear_cookies: bool = False) -> None:
        super().__init__(detail)
        self.detail = detail
        self.clear_cookies = clear_cookies


class AuthError(DomainError):
    status_code = 401


class Forbidden(DomainError):
    status_code = 403


class NotFound(DomainError):
    status_code = 404


class Conflict(DomainError):
    status_code = 409


class Unprocessable(DomainError):
    """422 for rules that need the stored row (e.g. PATCH merged-state checks)."""

    status_code = 422

    def __init__(self, detail: str, *, field: str | None = None) -> None:
        super().__init__(detail)
        self.field = field


class RateLimited(DomainError):
    status_code = 429
