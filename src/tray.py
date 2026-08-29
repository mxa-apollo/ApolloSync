"""System tray presentation for Apollo Sync.

The tray contains no application policy. Each menu action delegates to a
callback supplied by the application coordinator.
"""

from __future__ import annotations

from collections.abc import Callable

import pystray
from PIL import Image

from .logger import get_logger
from .utils import asset_path

__all__ = ["ApolloSyncTray"]

logger = get_logger(__name__)


class ApolloSyncTray:
    """Display Apollo Sync controls in the Windows notification area.

    Args:
        open_music_folder: Opens the configured music folder.
        open_playlists_folder: Opens the configured playlist folder.
        open_logs_folder: Opens the application log folder.
        run_scan_now: Starts an application-managed playlist scan.
        exit_callback: Requests clean application shutdown.
    """

    def __init__(
        self,
        *,
        open_music_folder: Callable[[], None],
        open_playlists_folder: Callable[[], None],
        open_logs_folder: Callable[[], None],
        run_scan_now: Callable[[], None],
        exit_callback: Callable[[], None],
    ) -> None:
        """Create the tray icon without starting its UI loop."""
        self._icon = pystray.Icon(
            name="apollo_sync",
            icon=_load_icon(),
            title="Apollo Sync — 🟢 Watching",
            menu=pystray.Menu(
                pystray.MenuItem("🟢 Watching", lambda _icon, _item: None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open Music Folder", _menu_action(open_music_folder)),
                pystray.MenuItem("Open Playlists Folder", _menu_action(open_playlists_folder)),
                pystray.MenuItem("Open Logs Folder", _menu_action(open_logs_folder)),
                pystray.MenuItem("Run Scan Now", _menu_action(run_scan_now)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", _menu_action(exit_callback)),
            ),
        )
        self._is_running = False

    @property
    def is_running(self) -> bool:
        """Return whether the tray UI has been started."""
        return self._is_running

    def start(self) -> None:
        """Start the tray UI on pystray's detached background thread."""
        if self._is_running:
            return
        self._icon.run_detached()
        self._is_running = True

    def stop(self) -> None:
        """Stop the tray UI. Safe to call before start or more than once."""
        if not self._is_running:
            return
        self._is_running = False
        self._icon.stop()


def _menu_action(callback: Callable[[], None]) -> Callable[[pystray.Icon, pystray.MenuItem], None]:
    """Adapt a zero-argument application callback to pystray's menu signature."""
    def invoke(_icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        try:
            callback()
        except Exception:
            logger.exception("Unexpected system tray callback exception.")

    return invoke


def _load_icon() -> Image.Image:
    """Load the supplied branding icon, with a safe blank fallback if absent."""
    icon_file = asset_path("icon.ico")
    try:
        with Image.open(icon_file) as source:
            icon = source.convert("RGBA")
            icon.load()
            return icon
    except (FileNotFoundError, OSError) as exc:
        logger.error("Apollo Sync tray icon unavailable at %s: %s", icon_file, exc)
        # pystray requires an image object; keep the tray usable without
        # inventing replacement artwork when a deployment omits the asset.
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
