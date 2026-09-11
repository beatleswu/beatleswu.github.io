"""Small Flask-free result/error contract for Activation domain handoffs.

The owning domain supplies business decisions and an already-open transaction.
This module only gives the HTTP coordinator typed values to adapt; it has no
database, Flask, or transaction dependency.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


def _snapshot_body(body: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(body, Mapping):
        raise TypeError('Activation HTTP body must be a mapping')
    return MappingProxyType(dict(body))


def _validate_status_code(status_code: int) -> int:
    if isinstance(status_code, bool) or not isinstance(status_code, int):
        raise TypeError('Activation HTTP status_code must be an integer')
    if not 100 <= status_code <= 599:
        raise ValueError('Activation HTTP status_code must be between 100 and 599')
    return status_code


def _validate_code(code: str) -> str:
    if not isinstance(code, str) or not code or code != code.strip():
        raise ValueError('Activation domain error code must be a non-empty string')
    if any(character.isspace() for character in code):
        raise ValueError('Activation domain error code must not contain whitespace')
    return code


@dataclass(frozen=True, slots=True)
class ActivationDomainResult:
    """A domain-owned JSON object and its already-decided HTTP status."""

    body: Mapping[str, Any]
    status_code: int = 200

    def __post_init__(self) -> None:
        object.__setattr__(self, 'body', _snapshot_body(self.body))
        object.__setattr__(self, 'status_code', _validate_status_code(self.status_code))


class ActivationDomainError(Exception):
    """A typed, safe-to-adapt domain rejection or unavailable result."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int = 400,
        retryable: bool = False,
        message: str | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> None:
        self.code = _validate_code(code)
        self.status_code = _validate_status_code(status_code)
        if not isinstance(retryable, bool):
            raise TypeError('Activation domain retryable must be a boolean')
        self.retryable = retryable
        if message is not None and not isinstance(message, str):
            raise TypeError('Activation domain public message must be a string')
        self.message = message
        self.body = _snapshot_body({} if body is None else body)
        super().__init__(message or code)

    def to_http_body(self) -> dict[str, Any]:
        """Return a fresh body with coordinator-owned stable fields."""
        payload = dict(self.body)
        payload['error'] = self.code
        payload['code'] = self.code
        payload['retryable'] = self.retryable
        if self.message is not None:
            payload.setdefault('message', self.message)
        return payload


__all__ = ['ActivationDomainError', 'ActivationDomainResult']
