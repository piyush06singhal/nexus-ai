"""Files security — path containment, type/size validation, deny-lists (Phase 10).

The host filesystem is never exposed raw (§42/§43): file access flows through a
workspace provider, and every path is validated against the workspace root
before use. System/credential-sensitive locations are always refused, so a
misconfigured workspace root cannot reach ``/etc``, the shell config, dotfiles
or mounted secret mount points.
"""

from __future__ import annotations

import re
from pathlib import Path

MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1 MiB in Phase 10 (documented bound)

# Credential/system-sensitive path fragments that are always refused.
_DENIED_FRAGMENTS = (
    "/etc/",
    "/proc/",
    "/sys/",
    "/dev/",
    "/root/",
    "id_rsa",
    "id_ed25519",
    ".ssh",
    ".aws",
    "credentials",
    "secrets",
    "passwd",
    "shadow",
    "known_hosts",
    ".env",
    ".bashrc",
    ".zshrc",
    ".git/",
)

_ALLOWED_TEXT_MIME = (
    "text/plain",
    "application/json",
    "application/xml",
    "text/markdown",
    "text/csv",
    "application/yaml",
    "text/yaml",
)
_MIME_BY_SUFFIX = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".csv": "text/csv",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".xml": "application/xml",
}


class FileSecurityError(ValueError):
    """A file operation was refused by the workspace guard."""


PathTraversalError = FileSecurityError  # alias for path-containment callers/tests


def validate_path(path: str | Path, workspace: str | Path) -> bool:
    """Confirm ``path`` resolves strictly inside ``workspace``; raise otherwise.

    Absolute paths are interpreted against the workspace root: a path outside
    the root (or a symlink that resolves outside it) raises
    :class:`PathTraversalError`. Returns ``True`` for an in-root file.
    """
    root = Path(workspace).resolve()
    # ``root / absolute`` yields the absolute path (a root cannot prefix an
    # absolute), so traversal via an absolute or ``..``-laden path is caught by
    # the containment check below.
    candidate = (root / str(path)).resolve()
    if candidate != root and root not in candidate.parents:
        raise PathTraversalError(f"Path escapes the workspace root: {path!r}")
    _deny_checked(str(candidate))
    return True


def safe_resolve(root: Path, relative: str) -> Path:
    """Resolve *relative* inside *root*, refusing any escaping path.

    Raises :class:`FileSecurityError` on absolute paths, ``..`` traversal, or a
    resolved path outside the root.
    """
    if not relative or relative.startswith(("/", "~")):
        raise FileSecurityError(f"Path must be relative to the workspace: {relative!r}")
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise FileSecurityError(f"Path escapes the workspace root: {relative!r}")
    _deny_checked(str(candidate))
    return candidate


def _deny_checked(path: str) -> None:
    lowered = path.lower().replace("\\", "/")
    for fragment in _DENIED_FRAGMENTS:
        if fragment in lowered:
            raise FileSecurityError(f"Path touches a denied location: {path!r}")


def validate_fragment(fragment: str) -> None:
    """Reject obviously-hostile path fragments before they reach the root."""
    if _TRAVERSAL.search(fragment):
        raise FileSecurityError("Path contains traversal segments")


_TRAVERSAL = re.compile(r"(^|[\\/])\.\.[\\/]|(^|[\\/])\.\.$")


def validate_for_write(path: Path, size_bytes: int) -> str:
    """Validate a concrete file path + size for a write.

    Returns the MIME type derived from the suffix, or raises when empty,
    oversize, or in a denied location.
    """
    if path.is_dir():
        raise FileSecurityError(f"{path} is a directory, not a file")
    if size_bytes > MAX_FILE_SIZE_BYTES:
        raise FileSecurityError(f"File exceeds the {MAX_FILE_SIZE_BYTES}-byte cap")
    _deny_checked(str(path))
    suffix = path.suffix.lower()
    if not suffix:
        raise FileSecurityError(f"File must have a recognised extension: {path!r}")
    return _MIME_BY_SUFFIX.get(suffix, "application/octet-stream")


def mime_allowed(mime_type: str) -> bool:
    return mime_type in _ALLOWED_TEXT_MIME


def is_path_denied(path: str) -> bool:
    try:
        _deny_checked(path)
        return False
    except FileSecurityError:
        return True
