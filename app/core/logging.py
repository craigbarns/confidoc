"""ConfiDoc Backend — Logging structuré avec structlog."""

import logging
import sys

import structlog


def setup_logging(log_level: str = "DEBUG", json_output: bool = False) -> None:
    """Configure structlog pour un logging structuré et cohérent.

    Args:
        log_level: Niveau de log (DEBUG, INFO, WARNING, ERROR).
        json_output: Si True, output JSON (pour production). Sinon, console colorée.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.DEBUG))

    # Réduire le bruit des librairies tierces
    for noisy_logger in ("uvicorn.access", "sqlalchemy.engine", "asyncpg"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Obtenir un logger structuré."""
    return structlog.get_logger(name)
