"""Exception hierarchy for wkx-ecosystem-localhost."""


class WkxEcosystemError(Exception):
    """Base class for all wkx-ecosystem-localhost exceptions."""


class ConfigError(WkxEcosystemError):
    """Raised when required configuration is missing or invalid."""
