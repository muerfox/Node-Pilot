from __future__ import annotations

import contextvars
import json
import logging
import time

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)
organization_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("organization_id", default=None)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        record.organization_id = organization_id_var.get()
        return True


class StructuredFormatter(logging.Formatter):
    """Emits one JSON object per log line: request_id, user_id, org_id,
    operation, duration, result, plus the raw message."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "user_id": getattr(record, "user_id", None),
            "organization_id": getattr(record, "organization_id", None),
        }
        extra = getattr(record, "context", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def log_operation(logger: logging.Logger, operation: str, *, duration: float | None = None, result: str = "success", **context):
    logger.info(
        "%s %s",
        operation,
        result,
        extra={"context": {"operation": operation, "duration": duration, "result": result, **context}},
    )


class Timer:
    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc):
        self.elapsed = time.monotonic() - self._start
