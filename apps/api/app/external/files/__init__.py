"""Files: virtual/sandboxed workspace + security guards (Phase 10 §42/§43)."""

from __future__ import annotations

from app.external.files.security import FileSecurityError, safe_resolve
from app.external.files.workspace import WorkspaceFileProvider

__all__ = ["FileSecurityError", "WorkspaceFileProvider", "safe_resolve"]
