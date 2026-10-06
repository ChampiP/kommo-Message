"""
Configuración centralizada de logging seguro.
Redacta credenciales, tokens, cookies y datos sensibles de los logs.
"""
import json
import logging
import os
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# Correlation id of the request being served (set by RequestContextMiddleware)
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Claves cuyos valores deben ser redactados
SENSITIVE_KEYS = {
    "csrf_token",
    "access_token",
    "refresh_token",
    "x_auth_token",
    "x-auth-token",
    "password",
    "secret",
    "cookies",
    "session_id",
    "authorization",
}

# Patrones regex para redactar cadenas de texto
REDACT_PATTERNS = [
    # Tokens en formato key=value o "key": "value" (evitando placeholders %s, %d, etc.)
    (
        re.compile(
            r'(?i)(["\']?(?:csrf_token|access_token|refresh_token|x_auth_token|x-auth-token|password|session_id)["\']?\s*[:=]\s*["\']?)(?!(?:%[sdf]|{[0-9a-zA-Z_]*}))([^"\'\s,}{]+)(["\']?)'
        ),
        r"\g<1>[REDACTED]\g<3>",
    ),
    # Header authorization / bearer
    (
        re.compile(r'(?i)(bearer\s+)([A-Za-z0-9_\-\.]+)'),
        r"\g<1>[REDACTED]",
    ),
    # Cookies en formato cookie_name=cookie_value
    (
        re.compile(
            r'(?i)((?:session_id|refresh_token|access_token|csrf_token)=)(?!(?:%[sdf]|{[0-9a-zA-Z_]*}))([^;\s]+)'
        ),
        r"\g<1>[REDACTED]",
    ),
]


def redact_text(text: str) -> str:
    """Redacta patrones sensibles en texto libre."""
    if not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in REDACT_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def redact_data(data: Any) -> Any:
    """Recorre estructuras de datos y redacta valores asociados a claves sensibles."""
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEYS:
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_data(v)
        return redacted
    elif isinstance(data, (list, tuple, set)):
        items = [redact_data(item) for item in data]
        if isinstance(data, tuple):
            return tuple(items)
        elif isinstance(data, set):
            return set(items)
        return items
    elif isinstance(data, str):
        return redact_text(data)
    return data


class RedactingFormatter(logging.Formatter):
    """Formatter que aplica redacción sobre el mensaje completamente formateado."""

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return redact_text(formatted)


_RESERVED = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "color_message"}


class JsonFormatter(logging.Formatter):
    """Single-line JSON formatter using ECS-style flattened dot keys, fully redacted."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, timezone.utc)
        doc: dict[str, Any] = {
            "@timestamp": ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z",
            "log.level": record.levelname,
            "log.logger": record.name,
            "message": redact_text(record.getMessage()),
            "service.name": os.getenv("SERVICE_NAME", "kommo-message"),
        }
        if env := os.getenv("APP_ENV"):
            doc["service.environment"] = env
        doc["process.pid"] = record.process
        doc["process.thread.name"] = record.threadName
        doc["log.origin.file.name"] = record.filename
        doc["log.origin.file.line"] = record.lineno
        doc["log.origin.function"] = record.funcName
        if (rid := request_id_var.get()) is not None:
            doc["http.request.id"] = rid
        if record.exc_info and record.exc_info[0] is not None:
            exc_type, exc, _ = record.exc_info
            doc["error.type"] = exc_type.__name__
            doc["error.message"] = redact_text(str(exc))
            doc["error.stack_trace"] = redact_text(self.formatException(record.exc_info))
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in doc:
                doc[key] = redact_data({key: value})[key]
        return json.dumps(doc, ensure_ascii=False, default=str)


class SensitiveDataFilter(logging.Filter):
    """Filtro de logging que asegura que argumentos y mensajes no contengan credenciales."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            if isinstance(record.args, dict):
                record.args = redact_data(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_data(a)
                    if isinstance(a, (dict, list))
                    else (redact_text(a) if isinstance(a, str) else a)
                    for a in record.args
                )
        elif isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        elif isinstance(record.msg, (dict, list)):
            record.msg = redact_data(record.msg)

        return True


_logging_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configura el logging estándar seguro para la aplicación."""
    global _logging_configured
    if _logging_configured:
        return

    formatter = JsonFormatter()
    level = logging.getLevelName(os.getenv("LOG_LEVEL", "").upper()) if os.getenv("LOG_LEVEL") else level
    if not isinstance(level, int):
        level = logging.INFO
    filter_ = SensitiveDataFilter()

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.addFilter(filter_)
            handler.setFormatter(formatter)
    else:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(filter_)
        root_logger.addHandler(console_handler)

    # Route uvicorn through the root JSON handler
    for name in ("uvicorn", "uvicorn.error"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
    # RequestContextMiddleware owns access logs; silence uvicorn's duplicate
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False

    _logging_configured = True


def get_logger(name: str) -> logging.Logger:
    """Retorna un logger configurado con filtro y formateador de datos sensibles."""
    setup_logging()
    logger = logging.getLogger(name)
    logger.addFilter(SensitiveDataFilter())
    return logger
