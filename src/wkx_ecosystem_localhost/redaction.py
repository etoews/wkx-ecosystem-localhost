"""Make facts safe to display: mask emails, strip credentials, relativise paths.

Redaction happens once, here, before values reach a model, so no downstream code
has to remember to do it. These three functions are what keep a casual screenshot
of the board from leaking an identity, a token, or a username.
"""

from __future__ import annotations

from pathlib import Path

_BULLETS = "•••"


def mask_email(email: str) -> str:
    """Mask an email's local part while keeping its domain.

    The mask is a fixed three bullets regardless of the real length, so it leaks
    neither the name nor how long it was. The domain is kept because a provider
    (``example.com``) is not identifying and helps tell accounts apart. A string
    with no ``@`` is masked whole.

    Args:
        email: The raw address.

    Returns:
        ``a•••@example.com`` for ``ada@example.com``; ``•••`` when there is no
        local part or no ``@``.
    """
    local, sep, domain = email.partition("@")
    if not sep or not local:
        return _BULLETS
    return f"{local[0]}{_BULLETS}@{domain}"


def strip_credentials(url: str) -> str:
    """Remove any userinfo from a ``scheme://`` URL.

    A token embedded in a remote URL rides in the userinfo, whether as
    ``user:token@`` or as ``token@``, so the whole userinfo is dropped. SCP-style
    remotes (``git@host:path``, no scheme) are left untouched: their ``git@`` is
    the conventional SSH user, not a secret, and users recognise the form.

    Args:
        url: The raw remote URL.

    Returns:
        The URL with userinfo removed for scheme URLs; unchanged otherwise.
    """
    scheme, sep, rest = url.partition("://")
    if not sep:
        return url
    authority, slash, path = rest.partition("/")
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    return f"{scheme}://{authority}{slash}{path}"


def relativise_text(text: str, home: Path) -> str:
    """Rewrite a home-directory prefix embedded in free text to ``~``.

    For values that are not paths in their own right but may still carry one, such
    as a git config ``core.editor`` set to an absolute program path under home.
    Only a home prefix followed by a separator, or the home path exactly, is
    rewritten, so an unrelated path like ``/home-backup`` is left untouched.

    Args:
        text: The free-form value to scrub.
        home: The home directory to rewrite.

    Returns:
        ``text`` with any home prefix replaced by ``~``.
    """
    home_str = str(home)
    if text == home_str:
        return "~"
    return text.replace(f"{home_str}/", "~/")


def relativise(path: Path, home: Path) -> str:
    """Render ``path`` relative to ``home`` as ``~/...``.

    Keeps a username out of a displayed path. A path that is not under ``home`` is
    returned as-is; ``home`` itself becomes ``~``.

    Args:
        path: The absolute path to display.
        home: The home directory to relativise against.

    Returns:
        ``~/dev/acme`` for a path under home, ``~`` for home itself, or the
        original path string when it lies outside home.
    """
    try:
        relative = path.relative_to(home)
    except ValueError:
        return str(path)
    return "~" if str(relative) == "." else f"~/{relative.as_posix()}"
