import logging
import sys
from contextvars import ContextVar
from dataclasses import dataclass

from pythonjsonlogger.json import JsonFormatter


@dataclass
class RequestContext:
    """Per-request state. Mutated in place so worker threads can add timings."""

    request_id: str
    pool_acquire_ms: float = 0.0
    db_ms: float = 0.0


_request_ctx: ContextVar[RequestContext | None] = ContextVar("request_ctx", default=None)


def set_request_context(ctx: RequestContext):
    return _request_ctx.set(ctx)


def reset_request_context(token) -> None:
    _request_ctx.reset(token)


def get_request_context() -> RequestContext | None:
    return _request_ctx.get()


def current_request_id() -> str | None:
    ctx = _request_ctx.get()
    return ctx.request_id if ctx else None


def add_pool_acquire_time(seconds: float) -> None:
    ctx = _request_ctx.get()
    if ctx is not None:
        ctx.pool_acquire_ms += seconds * 1000.0


def add_db_time(seconds: float) -> None:
    ctx = _request_ctx.get()
    if ctx is not None:
        ctx.db_ms += seconds * 1000.0


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = current_request_id()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
            rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers[:] = []
        lg.propagate = True
    # The middleware writes its own access log line.
    logging.getLogger("uvicorn.access").disabled = True
