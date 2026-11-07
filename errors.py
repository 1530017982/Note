"""Shared application errors; the Flask entry point serializes these errors."""

from __future__ import annotations


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str,
                 field: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field

    def to_dict(self) -> dict:
        body = {"error": self.message, "code": self.code}
        if self.field is not None:
            body["field"] = self.field
        return body
