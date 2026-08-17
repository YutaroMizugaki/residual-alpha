"""Explicit data-quality errors. Missing values must never be coerced to zero."""


class QuantError(Exception):
    """Base error for the quant engine."""


class MissingDataError(QuantError):
    def __init__(self, field: str) -> None:
        super().__init__(f"missing data: {field}")
        self.field = field


class InsufficientHistoryError(QuantError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class InvalidInputError(QuantError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


STATUS_VALID = "valid"
STATUS_MISSING = "missing"
STATUS_INVALID = "invalid"
STATUS_INSUFFICIENT_HISTORY = "insufficient_history"
