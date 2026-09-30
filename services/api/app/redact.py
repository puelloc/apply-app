"""Log redaction + structured JSON logging.

`redact` is pure (testable). `JsonFormatter` emits one JSON object per line so logs are filterable
and searchable; callers can attach context via `logging`'s `extra=` (see `_CONTEXT_FIELDS`).
"""

from __future__ import annotations

import json
import logging
import re

_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[EMAIL]"),
    (re.compile(r"(?i)\bBearer\s+\S+"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization)\b\s*[=:]\s*\S+"),
     r"\1=[REDACTED]"),
]

# Optional fields carried on the LogRecord (via extra={...}) that we surface for filtering/search.
_CONTEXT_FIELDS = ("correlation_id", "job_id", "run_id", "step", "adapter", "action", "error_code")


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for field in _CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
