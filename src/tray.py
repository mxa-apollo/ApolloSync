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
from .status import StatusSnapshot

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
        status_provider: Callable[[], StatusSnapshot] | None = None,
    ) -> None:
        """Create the tray icon without starting its UI loop."""
        self._status_provider = status_provider or (lambda: StatusSnapshot())
        self._icon = pystray.Icon(
            name="apollo_sync",
            icon=_load_icon(),
            title="Apollo Sync",
            menu=pystray.Menu(
                pystray.MenuItem(lambda _item: self._state_text(), None, enabled=False),
                pystray.MenuItem(lambda _item: self._last_sync_text(), None, enabled=False),
                pystray.MenuItem(lambda _item: self._stats_text(), None, enabled=False),
                pystray.MenuItem(lambda _item: self._error_text(), None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open Music Folder", _menu_action(open_music_folder)),
                pystray.MenuItem("Open Playlists Folder", _menu_action(open_playlists_folder)),
                pystray.MenuItem("Open Logs", _menu_action(open_logs_folder)),
                pystray.MenuItem("Scan Playlists", _menu_action(run_scan_now)),
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

    def refresh_status(self, _snapshot: StatusSnapshot | None = None) -> None:
        """Refresh dynamic status labels after a status update."""
        if not self._is_running:
            return
        try:
            self._icon.update_menu()
        except Exception:
            logger.exception("Failed refreshing tray status.")

    def _snapshot(self) -> StatusSnapshot:
        try:
            return self._status_provider()
        except Exception:
            logger.exception("Failed reading application status for tray.")
            return StatusSnapshot(state="error", last_error="Status unavailable")

    def _state_text(self) -> str:
        snapshot = self._snapshot()
        if snapshot.state == "starting":
            return "🟡 Starting..."
        if snapshot.state == "stopped":
            return "⚪ Stopped"
        if snapshot.state == "error":
            return "🔴 Error / Not watching" if not snapshot.watching else "🔴 Error (watching)"
        return "🟢 Watching"

    def _last_sync_text(self) -> str:
        timestamp = self._snapshot().last_sync_time
        return f"Last sync: {timestamp.strftime('%H:%M:%S') if timestamp else 'never'}"

    def _stats_text(self) -> str:
        snapshot = self._snapshot()
        return f"Synced: {snapshot.total_synced}  |  Errors: {snapshot.total_failed}"

    def _error_text(self) -> str:
        error = self._snapshot().last_error
        return f"Last error: {error}" if error else "Last error: none"


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
