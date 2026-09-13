"""Files security — path containment, type/size validation, deny-lists (Phase 10).

The host filesystem is never exposed raw (§42/§43): file access flows through a
workspace provider, and every path is validated against the workspace root
before use. System/credential-sensitive locations are always refused, so a
misconfigured workspace root cannot reach ``/etc``, the shell config, dotfiles
or mounted secret mount points.
"""

from __future__ import annotations

import re
import stat
from pathlib import Path

MAX_FILE_SIZE_BYTES = 1024 * 1024  # 1 MiB in Phase 10 (documented bound)

# Credential/system-sensitive path fragments that are always refused.  The
# list is deliberately broad (Phase 11 hardening): cloud-CLI credentials, shell
# rc files, package-manager auth, WiFi/keychain stores, and per-user configs in
# addition to the Phase 10 SSH/aws/env set.
_DENIED_FRAGMENTS = (
    "/etc/",
    "/proc/",
    "/sys/",
    "/dev/",
    "/boot/",
    "/run/",
    "/mnt/",
    "/media/",
    "/root/",
    "/home/",  # any user home: ~/.aws, ~/.ssh, ~/.gnupg, …
    "/users/",  # macOS /Users/
    "id_rsa",
    "id_ed25519",
    "id_dsa",
    "id_ecdsa",
    ".ssh",
    ".aws",
    ".azure",
    ".gcp",
    ".google-cloud",
    ".config/gcloud",
    ".kube",
    "kubeconfig",
    "credentials",
    "secrets",
    "secret_key",
    "private_key",
    "passwd",
    "shadow",
    "master.passwd",
    "known_hosts",
    "authorized_keys",
    ".env",
    ".pypirc",
    ".npmrc",
    ".gnupg",
    ".netrc",
    ".git-credentials",
    ".config/gh",
    ".config/hub",
    "keyring",
    ".bashrc",
    ".bash_profile",
    ".profile",
    ".zshrc",
    ".zprofile",
    ".gitconfig",
    ".git/",
    "KeePass",
    ".1password",
)

# Fragments whose exact-directory form is sensitive (e.g. ``config`` alone
# would be too broad, but a mount/secret-dir path is not).
_DENIED_DIR_FRAGMENTS = (
    "/secrets/",
    "/secret/",
    "/vault/",
    "/certs/",
    "/tls/",
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
    raw = root / str(path)
    _check_symlinks(raw, root)
    candidate = raw.resolve()
    if candidate != root and root not in candidate.parents:
        raise PathTraversalError(f"Path escapes the workspace root: {path!r}")
    _deny_checked(str(candidate))
    _refuse_special_file(candidate)
    return True


def safe_resolve(root: Path, relative: str) -> Path:
    """Resolve *relative* inside *root*, refusing any escaping path.

    Raises :class:`FileSecurityError` on absolute paths, ``..`` traversal, or a
    resolved path outside the root.
    """
    if not relative or relative.startswith(("/", "~")):
        raise FileSecurityError(f"Path must be relative to the workspace: {relative!r}")
    root_resolved = root.resolve()
    raw = root_resolved / relative
    _check_symlinks(raw, root_resolved)
    candidate = raw.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise FileSecurityError(f"Path escapes the workspace root: {relative!r}")
    _deny_checked(str(candidate))
    _refuse_special_file(candidate)
    return candidate


def _deny_checked(path: str) -> None:
    lowered = path.lower().replace("\\", "/").rstrip("/")
    for fragment in _DENIED_FRAGMENTS:
        if fragment in lowered:
            raise FileSecurityError(f"Path touches a denied location: {path!r}")
    for fragment in _DENIED_DIR_FRAGMENTS:
        # Match an exact directory segment, not a loose substring (``/vaults``
        # or ``secrets.md`` are fine; ``/secrets/…`` is not).
        if fragment[:-1] + "/" in lowered or lowered.endswith(fragment[:-1]):
            raise FileSecurityError(f"Path touches a denied location: {path!r}")


def _check_symlinks(raw: Path, root: Path) -> None:
    """Refuse any symlink in *raw* whose realpath escapes *root*.

    ``Path.resolve()`` already hardens containment by resolving the final path,
    but it does so *silently* and can mask the intent (a link inside the root
    that points outside). This pre-flight names the offender and refuses it
    before any open()/read follows it.
    """
    try:
        rel = raw.relative_to(root)
    except ValueError:
        return  # not lexically under root — the containment check handles it
    parts = [root, *rel.parts]
    for idx in range(1, len(parts)):
        current = Path(*parts[: idx + 1])
        if not current.exists():
            continue
        if current.is_symlink():
            real = current.resolve()
            if root not in real.parents and real != root:
                raise FileSecurityError(f"Symlink escapes the workspace root: {str(current)!r}")
        mode = _stat_mode(current)
        if mode is not None and not stat.S_ISREG(mode) and not stat.S_ISLNK(mode):
            raise FileSecurityError(f"Path traverses a non-regular path: {str(current)!r}")


def _stat_mode(path: Path) -> int | None:
    try:
        return path.lstat().st_mode
    except OSError:  # pragma: no cover
        return None


def _refuse_special_file(path: Path) -> None:
    """Refuse device nodes, sockets, and FIFOs after resolution (best effort)."""
    mode = _stat_mode(path)
    if mode is not None and not stat.S_ISREG(mode):
        raise FileSecurityError(f"Refusing non-regular file: {str(path)!r}")


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
