import json
import logging
from datetime import datetime, timezone
from hashlib import sha256


def _anonymize_identifier(value: object) -> str:
    text = str(value)
    return sha256(text.encode("utf-8")).hexdigest()[:12]


def _sanitize_text(value: object) -> str:
    text = str(value)
    if "eyJ" in text or text.startswith("sk-"):
        return "[redacted]"
    if len(text) > 280:
        return text[:277] + "..."
    return text


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": _sanitize_text(record.getMessage()),
            "logger": record.name,
            "module": record.module,
        }
        for key in ("event", "request_id", "route", "status", "latency_ms", "user_id", "session_id", "reason", "path", "database_host"):
            value = getattr(record, key, None)
            if value is not None:
                if key in {"user_id", "session_id"}:
                    payload[key] = _anonymize_identifier(value)
                    continue
                if key == "reason":
                    payload[key] = _sanitize_text(value)
                    continue
                payload[key] = value
        return json.dumps(payload, ensure_ascii=True)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
