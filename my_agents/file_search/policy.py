# pyre-strict
from __future__ import annotations

from pathlib import Path
from typing import Optional

from confucius.core.analect.analect import AnalectRunContext
from confucius.orchestrator.extensions.file.policy.base import (
    FileAccessPolicyBase,
    FileAccessResult,
)


class ReadOnlyExceptTmpPolicy(FileAccessPolicyBase):
    """File access policy that allows read-only access everywhere,
    but permits writes (create, update, delete) only under /tmp.

    This ensures the file search agent can search any folder on the system
    but can only make modifications within the /tmp directory.
    """

    writable_root: str = "/tmp"

    def _is_writable_path(self, path: Path) -> bool:
        """Check if the path falls under the writable root directory."""
        try:
            resolved = path.resolve()
            writable = Path(self.writable_root).resolve()
            return str(resolved).startswith(str(writable) + "/") or resolved == writable
        except (OSError, ValueError):
            return False

    async def check_read(
        self,
        path: Path,
        is_directory: bool = False,
        context: Optional[AnalectRunContext] = None,
    ) -> FileAccessResult:
        """Reading is always allowed from any path."""
        return FileAccessResult.allow()

    async def check_create(
        self, path: Path, context: Optional[AnalectRunContext] = None
    ) -> FileAccessResult:
        """Creating files is only allowed under /tmp."""
        if self._is_writable_path(path):
            return FileAccessResult.allow()
        return FileAccessResult.deny(
            f"Cannot create file at {path}: write operations are only allowed under {self.writable_root}"
        )

    async def check_update(
        self, path: Path, context: Optional[AnalectRunContext] = None
    ) -> FileAccessResult:
        """Updating files is only allowed under /tmp."""
        if self._is_writable_path(path):
            return FileAccessResult.allow()
        return FileAccessResult.deny(
            f"Cannot update file at {path}: write operations are only allowed under {self.writable_root}"
        )

    async def check_delete(
        self, path: Path, context: Optional[AnalectRunContext] = None
    ) -> FileAccessResult:
        """Deleting files is only allowed under /tmp."""
        if self._is_writable_path(path):
            return FileAccessResult.allow()
        return FileAccessResult.deny(
            f"Cannot delete file at {path}: write operations are only allowed under {self.writable_root}"
        )
