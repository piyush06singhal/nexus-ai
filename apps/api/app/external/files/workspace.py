"""Workspace file provider — virtual (default) or sandboxed local (Phase 10).

Phase 10 defaults to a *deterministic virtual workspace*: files live in a
per-company in-memory mapping, so tests/CI/demos need no host access. When an
operator configures ``external_workspace_root``, a strict local workspace is
available instead — every path goes through :mod:`.security` (containment,
allowed types, deny-lists, size caps). The host filesystem is never exposed
raw and the virtual workspace is the safe default (Rule 12).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.external.files.security import (
    FileSecurityError,
    mime_allowed,
    safe_resolve,
    validate_for_write,
)
from app.external.types import ExternalFile

_VIRTUAL_FS: dict[str, dict[str, bytes]] = {}


class WorkspaceFileProvider:
    """File operations over either the virtual or sandboxed local workspace."""

    def __init__(self, *, company_id: UUID, root: str | None = None) -> None:
        self.company_id = company_id
        self._root = root if root is not None else (settings.external_workspace_root or "")
        self._virtual = not self._root

    # ── Path helpers ──────────────────────────────────────────────────

    def _ensure_virtual(self) -> dict[str, bytes]:
        key = f"{self.company_id}"
        return _VIRTUAL_FS.setdefault(key, {})

    def _local_root(self) -> Path:
        root = Path(self._root).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return root

    # ── Reads ─────────────────────────────────────────────────────────

    def list_files(self, prefix: str = "") -> list[ExternalFile]:
        if self._virtual:
            store = self._ensure_virtual()
            files = []
            for path, blob in store.items():
                if prefix and not path.startswith(prefix):
                    continue
                files.append(
                    ExternalFile(
                        path=path,
                        name=Path(path).name,
                        mime_type=_mime(path),
                        size_bytes=len(blob),
                        workspace="virtual",
                    )
                )
            return files
        root = self._local_root()
        out = []
        for path in sorted(root.rglob("**/*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root))
            if prefix and not rel.startswith(prefix):
                continue
            try:
                safe_resolve(root, rel)
            except FileSecurityError:
                continue
            out.append(
                ExternalFile(
                    path=rel,
                    name=path.name,
                    mime_type=_mime(rel),
                    size_bytes=path.stat().st_size,
                    workspace="local",
                )
            )
        return out

    def read(self, relative: str) -> ExternalFile:
        if self._virtual:
            store = self._ensure_virtual()
            if relative not in store:
                raise FileSecurityError(f"Virtual file {relative!r} not found")
            blob = store[relative]
            return ExternalFile(
                path=relative,
                name=Path(relative).name,
                mime_type=_mime(relative),
                size_bytes=len(blob),
                workspace="virtual",
            )
        root = self._local_root()
        path = safe_resolve(root, relative)
        if not path.exists():
            raise FileSecurityError(f"File {relative!r} not found")
        return ExternalFile(
            path=relative,
            name=path.name,
            mime_type=_mime(relative),
            size_bytes=path.stat().st_size,
            workspace="local",
        )

    # ── Writes ────────────────────────────────────────────────────────

    def write(self, relative: str, content: bytes, *, max_bytes: int | None = None) -> ExternalFile:
        cap = max_bytes or 1024 * 1024
        if len(content) > cap:
            raise FileSecurityError(f"Content exceeds the {cap}-byte cap")
        mime = _mime(relative)
        if not mime_allowed(mime):
            raise FileSecurityError(f"MIME type {mime!r} is not permitted")
        if self._virtual:
            store = self._ensure_virtual()
            store[relative] = content
            return ExternalFile(
                path=relative,
                name=Path(relative).name,
                mime_type=mime,
                size_bytes=len(content),
                workspace="virtual",
            )
        root = self._local_root()
        path = safe_resolve(root, relative)
        _validate_write(path, len(content))
        path.write_bytes(content)
        return ExternalFile(
            path=relative,
            name=path.name,
            mime_type=mime,
            size_bytes=len(content),
            workspace="local",
        )

    def delete(self, relative: str) -> bool:
        if self._virtual:
            store = self._ensure_virtual()
            return store.pop(relative, None) is not None
        root = self._local_root()
        path = safe_resolve(root, relative)
        if not path.exists():
            return False
        path.unlink()
        return True

    def clear_virtual(self) -> None:
        """Drop the in-memory workspace (test/demo hygiene)."""
        _VIRTUAL_FS.pop(f"{self.company_id}", None)


def _mime(relative: str) -> str:
    suffix = Path(relative).suffix.lower()
    return {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".json": "application/json",
        ".csv": "text/csv",
        ".yaml": "application/yaml",
        ".yml": "application/yaml",
        ".xml": "application/xml",
    }.get(suffix, "application/octet-stream")


def _validate_write(path: Path, size_bytes: int) -> None:
    validate_for_write(path, size_bytes)
