"""Command-line entry point for Apollo Sync."""

from __future__ import annotations

import logging
from pathlib import Path

from src.config import Config, ConfigError, ConfigFileError
from src.logger import get_logger
from src.main import ApolloSyncApp
from src.setup_wizard import run_setup_wizard
from src.utils import config_path

logger = get_logger(__name__)


def _show_config_error_dialog(config_file: Path, error: BaseException) -> None:
    """Show a concise configuration error, falling back to logging if needed."""
    message = (
        "ApolloSync could not load its configuration file.\n\n"
        "Your existing config.json was not changed.\n\n"
        f"Please correct config.json at:\n{config_file}\n\n"
        "Then restart ApolloSync, or check the Logs for details."
    )
    try:
        from tkinter import messagebox

        messagebox.showerror("ApolloSync — Configuration Error", message)
    except Exception:
        logger.exception("Could not display configuration error dialog: %s", type(error).__name__)


def main() -> int:
    """Run Apollo Sync until the user interrupts it with Ctrl+C."""
    app = ApolloSyncApp()
    try:
        logger.info("Apollo Sync starting.")
        config_file = config_path()
        try:
            Config.load(config_file)
        except ConfigFileError as exc:
            if config_file.exists():
                raise
            logger.info("No local config.json found; opening first-run setup.")
            if not run_setup_wizard(config_file):
                logger.info("First-run setup cancelled; Apollo Sync will exit.")
                return 0
        app.start()
        app.wait_for_shutdown()
    except KeyboardInterrupt:
        return 0
    except ConfigError as exc:
        logger.error("Apollo Sync could not start because config.json is missing or invalid: %s", exc)
        logger.error("Create or fix the external configuration file at %s.", config_path())
        if config_file.exists():
            _show_config_error_dialog(config_file, exc)
        return 1
    except Exception as exc:
        logger.error("Apollo Sync could not start: %s", exc)
        return 1
    finally:
        logger.info("Apollo Sync shutting down.")
        app.stop()
        logging.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
