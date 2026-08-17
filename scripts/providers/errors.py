"""Provider errors. Failed fetches are not converted into price 0."""


class ProviderError(Exception):
    """Base error for market-data providers."""


class FetchError(ProviderError):
    """HTTP or payload failure. Callers must treat the series as missing."""


class BotWallError(FetchError):
    """HTML/JS challenge page instead of market data."""


class InvalidPriceDataError(ProviderError):
    """Payload exists but cannot be interpreted as prices."""
