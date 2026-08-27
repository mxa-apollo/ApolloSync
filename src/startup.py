"""Windows Startup-folder integration for Apollo Sync.

The module intentionally uses the current user's Startup folder rather than
the registry, avoiding administrator privileges and machine-wide changes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .logger import get_logger
from .utils import is_frozen

__all__ = ["apply_startup_setting"]

logger = get_logger(__name__)
_SHORTCUT_NAME = "ApolloSync.lnk"
_STARTUP_RELATIVE_PATH = Path("Microsoft") / "Windows" / "Start Menu" / "Programs" / "Startup"


def apply_startup_setting(enabled: bool) -> None:
    """Create, update, or remove Apollo Sync's per-user startup shortcut.

    Source execution is intentionally a no-op because there is no stable
    executable target to launch. Packaged execution targets the current frozen
    executable path, so re-running this function after moving the application
    updates the shortcut automatically. Any integration failure is logged and
    suppressed; the application remains usable without startup integration.

    Args:
        enabled: Whether Apollo Sync should launch when the user signs in.
    """
    try:
        if os.name != "nt":
            logger.warning("Windows startup integration is unavailable on this platform.")
            return
        shortcut = _startup_directory() / _SHORTCUT_NAME
        if not enabled:
            shortcut.unlink(missing_ok=True)
            return
        if not is_frozen():
            logger.warning("Windows startup integration is unavailable during source execution.")
            return

        shortcut.parent.mkdir(parents=True, exist_ok=True)
        _create_or_update_shortcut(shortcut, Path(sys.executable).resolve())
    except Exception:
        logger.exception("Failed to apply Windows startup integration.")


def _startup_directory() -> Path:
    """Return the current user's Windows Startup folder."""
    app_data = os.environ.get("APPDATA")
    if not app_data:
        raise RuntimeError("APPDATA is not available; cannot locate the Startup folder.")
    return Path(app_data) / _STARTUP_RELATIVE_PATH


def _create_or_update_shortcut(shortcut: Path, target: Path) -> None:
    """Create a Windows ``.lnk`` through the built-in Windows Script Host COM API."""
    def quote(value: Path) -> str:
        return str(value).replace("'", "''")

    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$link = $shell.CreateShortcut('{quote(shortcut)}'); "
        f"$link.TargetPath = '{quote(target)}'; "
        f"$link.WorkingDirectory = '{quote(target.parent)}'; "
        "$link.Description = 'Apollo Sync'; "
        "$link.Save()"
    )
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
        check=True,
        startupinfo=startupinfo,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        capture_output=True,
        text=True,
    )
