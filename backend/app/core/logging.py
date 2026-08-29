import logging
import sys

from app.core.config import settings


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
    get_logger("startup").info("logging configured for app_env=%s", settings.app_env)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"usv.{name}")
