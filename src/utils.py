"""Shared application resource and path discovery helpers.

Paths are resolved relative to the project directory during normal execution
and beside the executable when running from a frozen PyInstaller bundle.
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = [
    "application_directory",
    "asset_path",
    "assets_directory",
    "config_path",
    "is_frozen",
    "logs_directory",
    "resource_path",
]


def is_frozen() -> bool:
    """Return whether the process is running from a frozen executable."""
    return bool(getattr(sys, "frozen", False))


def application_directory() -> Path:
    """Return the external application directory for source or frozen runs.

    For source execution this is the repository root (the parent of ``src``).
    For both PyInstaller one-folder and one-file execution this is the folder
    containing ``sys.executable``. It intentionally never returns
    ``sys._MEIPASS``, which is temporary in one-file mode.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(relative_path: str | Path) -> Path:
    """Return an application resource path beneath :func:`application_directory`.

    Args:
        relative_path: Relative resource name such as ``"config.json"`` or
            ``"assets/icon.ico"``.

    Raises:
        ValueError: If the supplied path is absolute or escapes the application
            directory.
    """
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Resource paths must remain inside the application directory.")
    return application_directory() / path


def config_path() -> Path:
    """Return the external ``config.json`` path beside the application."""
    return resource_path("config.json")


def logs_directory() -> Path:
    """Return the writable application log directory."""
    return resource_path("logs")


def assets_directory() -> Path:
    """Return the directory containing bundled or source assets."""
    return resource_path("assets")


def asset_path(name: str | Path) -> Path:
    """Return the path to one asset, such as the future ``icon.ico`` file."""
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Asset names must remain inside the assets directory.")
    return assets_directory() / path
