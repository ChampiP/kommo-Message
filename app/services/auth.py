"""
Autenticación Kommo via login usuario/contraseña.
Flujo: GET / → csrf_token; POST /oauth2/authorize → cookies de sesión.
"""
import threading
import time
import requests
from typing import Optional

from config import (
    KOMMO_BASE_URL,
    KOMMO_USERNAME,
    KOMMO_PASSWORD,
    KOMMO_SESSION_REFRESH_INTERVAL,
)
from app.logging_config import get_logger

logger = get_logger(__name__)


class AuthError(Exception):
    pass


class KommoAuth:

    def __init__(self):
        self._session: Optional[requests.Session] = None
        self._lock = threading.Lock()
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop = False

    def login(self) -> requests.Session:
        base = KOMMO_BASE_URL.rstrip("/")
        session = requests.Session()

        logger.info("Starting Kommo authentication login")

        # 1. GET / → obtiene cookies (csrf_token). No raise_for_status porque Kommo
        # puede devolver 401 para visitas no autenticadas mientras establece cookies.
        try:
            session.get(f"{base}/")
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
            )
        except requests.RequestException as e:
            logger.error("Network error during Kommo login authorization: %s", e)
            raise AuthError(f"Error en autorización Kommo: {e}")

        cookie_names = list(session.cookies.keys())
        if res.status_code not in (200, 302) and not session.cookies.get("session_id"):
            logger.error(
                "Kommo login returned status_code=%d without session cookie",
                res.status_code,
            )
            raise AuthError(f"Kommo login falló: status {res.status_code}")

        logger.info(
            "Kommo authentication successful: active_cookie_names=%s", cookie_names
        )

        with self._lock:
            self._session = session

        return session

    def get_session(self) -> requests.Session:
        with self._lock:
            if self._session:
                return self._session
        return self.login()

    def _refresh_loop(self) -> None:
        while not self._stop:
            time.sleep(KOMMO_SESSION_REFRESH_INTERVAL)
            if self._stop:
                break
            try:
                self.login()
                logger.info("Kommo session renewed successfully")
            except Exception as e:
                logger.error("Error renewing Kommo session: %s", e)

    def start_background_refresh(self) -> None:
        if self._refresh_thread and self._refresh_thread.is_alive():
            return
        self._stop = False
        self.login()
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()
        logger.info(
            "Background session refresh started (interval=%ds)",
            KOMMO_SESSION_REFRESH_INTERVAL,
        )

    def stop_background_refresh(self) -> None:
        self._stop = True
