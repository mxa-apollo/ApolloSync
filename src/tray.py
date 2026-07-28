"""System tray presentation for Apollo Sync.

The tray contains no application policy. Each menu action delegates to a
callback supplied by the application coordinator.
"""

from __future__ import annotations

from collections.abc import Callable

import pystray
from PIL import Image, ImageDraw

from .logger import get_logger

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
            icon=_create_icon(),
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


def _create_icon() -> Image.Image:
    """Create a small green Apollo Sync status icon without external assets."""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    drawing = ImageDraw.Draw(image)
    drawing.ellipse((6, 6, 58, 58), fill=(35, 170, 80, 255))
    drawing.ellipse((15, 15, 49, 49), fill=(255, 255, 255, 255))
    drawing.ellipse((23, 23, 41, 41), fill=(35, 170, 80, 255))
    return image
