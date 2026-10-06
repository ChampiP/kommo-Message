"""
Autenticación Kommo via login usuario/contraseña.
Flujo: GET / → csrf_token; POST /oauth2/authorize → cookies de sesión.
"""
import threading
import requests
from typing import Optional

from app.core.config import (
    KOMMO_BASE_URL,
    KOMMO_USERNAME,
    KOMMO_PASSWORD,
    DEFAULT_HTTP_TIMEOUT,
)
from app.logging_config import get_logger

logger = get_logger(__name__)


class AuthError(Exception):
    pass


class KommoAuth:

    def __init__(self):
        self._session: Optional[requests.Session] = None
        self._lock = threading.Lock()

    def _perform_login(self) -> requests.Session:
        base = KOMMO_BASE_URL.rstrip("/")
        session = requests.Session()

        logger.info("Starting Kommo authentication login")

        # 1. GET / → obtiene cookies (csrf_token). No raise_for_status porque Kommo
        # puede devolver 401 para visitas no autenticadas mientras establece cookies.
        try:
            session.get(f"{base}/", timeout=DEFAULT_HTTP_TIMEOUT)
        except requests.RequestException as e:
            logger.error("Failed to reach Kommo base URL during login: %s", e)
            raise AuthError(f"Error al conectar con Kommo: {e}")

        csrf_token = session.cookies.get("csrf_token")
        if not csrf_token:
            logger.warning("CSRF token not found in initial Kommo cookies")

        # 2. POST /oauth2/authorize con usuario, contraseña y csrf_token
        try:
            res = session.post(
                f"{base}/oauth2/authorize",
                json={
                    "username": KOMMO_USERNAME,
                    "password": KOMMO_PASSWORD,
                    "csrf_token": csrf_token,
                    "temporary_auth": "N",
                },
                timeout=DEFAULT_HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            logger.error("Network error during Kommo login authorization: %s", e)
            raise AuthError(f"Error en autorización Kommo: {e}")

        cookie_names = list(session.cookies.keys())
        has_session_cookie = bool(session.cookies.get("session_id"))
        if res.status_code not in (200, 302) or not has_session_cookie:
            logger.error(
                "Kommo login failed: status_code=%d, session_id_cookie=%s",
                res.status_code,
                has_session_cookie,
            )
            if res.status_code not in (200, 302):
                raise AuthError(f"Kommo login falló: status {res.status_code}")
            raise AuthError("Kommo login falló: cookie session_id no encontrada")

        logger.info(
            "Kommo authentication successful: active_cookie_names=%s", cookie_names
        )

        return session

    def login(self) -> requests.Session:
        with self._lock:
            session = self._perform_login()
            self._session = session
            return session

    def get_session(self) -> requests.Session:
        with self._lock:
            if self._session is not None:
                return self._session
            session = self._perform_login()
            self._session = session
            return session

    def recover_session(
        self, failed_session: Optional[requests.Session] = None
    ) -> requests.Session:
        """
        Recovers the Kommo session. Single-flight: if another thread already
        renewed the session while this thread was waiting for the lock, reuses that new session
        without performing duplicate logins.
        """
        with self._lock:
            if (
                failed_session is not None
                and self._session is not None
                and self._session is not failed_session
            ):
                logger.info(
                    "Kommo session was already recovered by another thread; reusing updated session"
                )
                return self._session

            logger.info("Recovering Kommo session via re-login")
            session = self._perform_login()
            self._session = session
            return session

    def invalidate(self) -> None:
        with self._lock:
            self._session = None
            logger.info("Kommo in-memory session invalidated")
