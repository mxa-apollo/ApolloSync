"""Command-line entry point for Apollo Sync."""

from __future__ import annotations

import logging
from time import sleep

from src.config import ConfigError
from src.logger import get_logger
from src.main import ApolloSyncApp
from src.utils import config_path

logger = get_logger(__name__)


def main() -> int:
    """Run Apollo Sync until the user interrupts it with Ctrl+C."""
    app = ApolloSyncApp()
    try:
        logger.info("Apollo Sync starting.")
        app.start()
        while not app.shutdown_requested:
            sleep(0.1)
    except KeyboardInterrupt:
        return 0
    except ConfigError as exc:
        logger.error("Apollo Sync could not start because config.json is missing or invalid: %s", exc)
        logger.error("Create or fix the external configuration file at %s.", config_path())
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
