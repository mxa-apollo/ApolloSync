"""Command-line entry point for Apollo Sync."""

from __future__ import annotations

import sys
from threading import Event

from src.main import ApolloSyncApp


def main() -> int:
    """Run Apollo Sync until the user interrupts it with Ctrl+C."""
    app = ApolloSyncApp()
    try:
        app.start()
        print("Apollo Sync is watching playlists. Press Ctrl+C to stop.")
        Event().wait()
    except KeyboardInterrupt:
        print("\nApollo Sync stopped.")
        return 0
    except Exception as exc:
        print(f"Apollo Sync: could not start: {exc}", file=sys.stderr)
        return 1
    finally:
        app.stop()


if __name__ == "__main__":
    raise SystemExit(main())
