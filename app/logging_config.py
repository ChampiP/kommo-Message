"""
Configuración centralizada de logging seguro.
Redacta credenciales, tokens, cookies y datos sensibles de los logs.
"""
import logging
import re
from typing import Any

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

    formatter = RedactingFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
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

    _logging_configured = True


def get_logger(name: str) -> logging.Logger:
    """Retorna un logger configurado con filtro y formateador de datos sensibles."""
    setup_logging()
    logger = logging.getLogger(name)
    logger.addFilter(SensitiveDataFilter())
    return logger
