"""Domain errors. HTTP maps code → status; message is a short Chinese sentence."""

from __future__ import annotations


class DomainError(Exception):
    code: str = "DomainError"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(DomainError):
    code = "ValidationError"


class NotFound(DomainError):
    code = "NotFound"


class DaySealed(DomainError):
    code = "DaySealed"

    def __init__(self, message: str, *, date: str | None = None) -> None:
        super().__init__(message)
        self.date = date


class Conflict(DomainError):
    code = "Conflict"
