"""Exception hierarchy for wkx-ecosystem-localhost."""


class WkxEcosystemError(Exception):
    """Base class for all wkx-ecosystem-localhost exceptions."""


class ConfigError(WkxEcosystemError):
    """Raised when required configuration is missing or invalid."""


class ViewError(WkxEcosystemError):
    """Base class for the board's View-file failures (read, merge, write)."""


class ViewParseError(ViewError):
    """Raised when the View file on disk does not parse, so a write is refused.

    The board never regenerates the file from memory: a corrupt file is a hand
    edit the operator must see, not a state to silently overwrite (ADR 0004).
    """


class ViewWriteError(ViewError):
    """Raised when the View file cannot be written (a read-only file, a full disk).

    Surfaced to the operator as the ``view-not-saved`` Flag in the config Section,
    so a preference that did not persist is visible rather than lost silently.
    """


class InvalidPreference(ViewError):
    """Raised when a PATCH names a preference the board's catalogue does not know.

    A write must name a real theme or a real panel id; an unknown one is a client
    bug, so the route rejects it rather than writing an unknown key to the file.
    """
