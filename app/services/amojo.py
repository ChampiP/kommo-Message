"""
Sesión Amojo: obtiene x_auth_token y session_account_uuid.
Reglas:
- Refresca el token cada 10 minutos en segundo plano.
- Cada llamada a get_x_auth_token() fuerza un token nuevo (para peticiones GET).
- Logging seguro y estructurado en cada refresco (sin exponer tokens ni cookies).
"""
import threading
import time
import requests
from typing import Optional, Callable
from datetime import datetime

from app.core.config import KOMMO_BASE_URL
from app.logging_config import get_logger

logger = get_logger(__name__)

REFRESH_INTERVAL = 600  # 10 minutos


class AmojoError(Exception):
    pass


class AmojoSession:

    def __init__(self, session_provider: Callable[[], requests.Session]):
        self._session_provider = session_provider
        self._x_auth_token: Optional[str] = None
        self._session_account_uuid: Optional[str] = None
        self._expired_at: Optional[int] = None
        self._lock = threading.Lock()
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop = False

    def refresh_session(self, session: requests.Session, motivo: str = "forzado") -> None:
        """POST /ajax/v1/chats/session → nuevo x_auth_token con logging seguro."""
        url = f"{KOMMO_BASE_URL.rstrip('/')}/ajax/v1/chats/session"

        logger.info("Refreshing Amojo session (reason: %s)", motivo)

        try:
            res = session.post(
                url,
                data={"request[chats][session][action]": "create"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        except requests.RequestException as e:
            logger.error("Network error during Amojo session refresh: %s", e)
            raise AmojoError(f"Error de red en chats/session: {e}")

        if res.status_code != 200:
            logger.error("Amojo chats/session failed with status_code=%d", res.status_code)
            raise AmojoError(f"chats/session falló: status {res.status_code}")

        try:
            chat_data = res.json()["response"]["chats"]["session"]
            nuevo_token = chat_data["access_token"]
            account_id = str(chat_data["account"]["id"])
            expired_at = chat_data.get("expired_at")
        except (KeyError, TypeError, ValueError) as e:
            logger.error("Unexpected response structure from Amojo chats/session: %s", e)
            raise AmojoError("Estructura de respuesta inesperada en chats/session")

        with self._lock:
            self._x_auth_token = nuevo_token
            self._session_account_uuid = account_id
            self._expired_at = expired_at

        expira = (
            datetime.fromtimestamp(expired_at).strftime("%Y-%m-%d %H:%M:%S")
            if expired_at
            else "unknown"
        )
        logger.info(
            "Amojo session refreshed: account_uuid=%s, expires_at=%s, reason=%s",
            account_id,
            expira,
            motivo,
        )

    def get_x_auth_token(self) -> str:
        """Siempre genera un token nuevo (para cada petición GET)."""
        session = self._session_provider()
        self.refresh_session(session, motivo="peticion GET")
        with self._lock:
            return self._x_auth_token

    def get_session_account_uuid(self) -> str:
        with self._lock:
            if self._session_account_uuid:
                return self._session_account_uuid
        self.get_x_auth_token()
        with self._lock:
            return self._session_account_uuid

    def _refresh_loop(self) -> None:
        """Refresca el token cada 10 minutos en segundo plano."""
        while not self._stop:
            for _ in range(REFRESH_INTERVAL):
                if self._stop:
                    return
                time.sleep(1)
            try:
                session = self._session_provider()
                self.refresh_session(session, motivo="background cada 10 min")
            except Exception as e:
                logger.error("Error in Amojo background refresh: %s", e)

    def start_background_refresh(self) -> None:
        if self._refresh_thread and self._refresh_thread.is_alive():
            return
        self._stop = False
        session = self._session_provider()
        self.refresh_session(session, motivo="inicio del servidor")
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()
        logger.info(
            "Amojo automatic refresh started (interval=%d min)",
            REFRESH_INTERVAL // 60,
        )

    def stop_background_refresh(self) -> None:
        self._stop = True
