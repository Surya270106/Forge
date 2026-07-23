import logging
import sys

import structlog
from pythonjsonlogger import jsonlogger  # type: ignore  # pyright: ignore[reportPrivateImportUsage]


def configure_logging(log_level: str = "INFO", environment: str = "development") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure stdlib logging
    handler = logging.StreamHandler(sys.stdout)
    if environment == "production":
        formatter = jsonlogger.JsonFormatter(  # type: ignore
            "%(timestamp)s %(level)s %(name)s %(message)s"
        )
        handler.setFormatter(formatter)
    else:
        # ConsoleRenderer for dev
        pass

    logging.basicConfig(level=level, handlers=[handler], force=True)

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer() if environment == "production" else structlog.dev.ConsoleRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
